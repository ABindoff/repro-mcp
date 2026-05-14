"""repro-mcp: Reproducibility logging and rule enforcement MCP server."""

import os
from pathlib import Path
from typing import Any

import mcp.server.stdio
import mcp.types as types
from mcp.server import Server

from . import environment as env_mod
from .rules import run_checks
from .session import SessionRegistry

app = Server("repro-mcp")
registry = SessionRegistry()


def _project_root() -> Path:
    """Use CWD as the project root — this is set by the MCP client at launch."""
    return Path(os.getcwd())


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="session_start",
            description=(
                "Start a new reproducibility logging session. "
                "Snapshots the current environment and opens a markdown log file. "
                "Call this at the beginning of any significant work session."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_name": {"type": "string", "description": "Short name for this project"},
                    "goal": {"type": "string", "description": "Plain-language description of what this session is trying to accomplish"},
                    "branch": {"type": "string", "description": "Git branch name (auto-detected if omitted)"},
                },
                "required": ["project_name", "goal"],
            },
        ),
        types.Tool(
            name="session_end",
            description="Close the current session, write a git diff summary, and update the index.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "outcome": {
                        "type": "string",
                        "enum": ["success", "abandoned", "inconclusive"],
                        "description": "How the session concluded",
                    },
                    "notes": {"type": "string", "description": "Optional closing notes"},
                },
                "required": ["session_id", "outcome"],
            },
        ),
        types.Tool(
            name="log_exchange",
            description=(
                "Log a prompt/response exchange to the session log. "
                "Call after each significant AI interaction."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "prompt": {"type": "string"},
                    "response": {"type": "string"},
                    "tool_calls": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "Any tool calls made during this turn",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Topic tags e.g. ['data-loading', 'model-fit']",
                    },
                },
                "required": ["session_id", "prompt", "response"],
            },
        ),
        types.Tool(
            name="log_decision",
            description=(
                "Log a significant design or methodological decision. "
                "These become the most citable parts of the session log."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "decision": {"type": "string", "description": "What was decided"},
                    "rationale": {"type": "string", "description": "Why this decision was made"},
                    "alternatives": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Options that were considered and rejected",
                    },
                },
                "required": ["session_id", "decision", "rationale"],
            },
        ),
        types.Tool(
            name="snapshot_environment",
            description="Capture the current environment state (packages, git hash, platform) and append it to the session log.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "label": {"type": "string", "description": "Optional label e.g. 'before model training'"},
                },
                "required": ["session_id"],
            },
        ),
        types.Tool(
            name="check_rules",
            description=(
                "Check a code snippet or plan against the project's reproducibility rules. "
                "Returns a list of violations with severity levels."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "context": {"type": "string", "description": "Code or plan text to check"},
                },
                "required": ["session_id", "context"],
            },
        ),
    ]


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:

    if name == "session_start":
        session = registry.start(
            project_name=arguments["project_name"],
            goal=arguments["goal"],
            project_root=_project_root(),
            branch=arguments.get("branch"),
        )
        return [types.TextContent(
            type="text",
            text=(
                f"Session started: `{session.session_id}`\n"
                f"Log: `{session.logger.log_path}`\n"
                f"Branch: {session.branch or '(none)'}\n"
                f"Git hash: {session.git_hash[:12] if session.git_hash else '(none)'}"
            ),
        )]

    if name == "session_end":
        session = registry.end(
            session_id=arguments["session_id"],
            outcome=arguments["outcome"],
            notes=arguments.get("notes"),
        )
        return [types.TextContent(
            type="text",
            text=f"Session `{arguments['session_id']}` closed ({arguments['outcome']}). Index updated.",
        )]

    if name == "log_exchange":
        session = registry.require(arguments["session_id"])
        session.logger.log_exchange(
            prompt=arguments["prompt"],
            response=arguments["response"],
            tool_calls=arguments.get("tool_calls"),
            tags=arguments.get("tags"),
        )
        return [types.TextContent(type="text", text="Exchange logged.")]

    if name == "log_decision":
        session = registry.require(arguments["session_id"])
        session.logger.log_decision(
            decision=arguments["decision"],
            rationale=arguments["rationale"],
            alternatives=arguments.get("alternatives"),
        )
        return [types.TextContent(type="text", text="Decision logged.")]

    if name == "snapshot_environment":
        session = registry.require(arguments["session_id"])
        snapshot = env_mod.capture()
        snapshot.label = arguments.get("label", "")
        session.logger.log_snapshot(snapshot)
        return [types.TextContent(
            type="text",
            text=f"Environment snapshot captured ({len(snapshot.packages)} packages).",
        )]

    if name == "check_rules":
        session = registry.require(arguments["session_id"])
        violations = run_checks(arguments["context"], session.project_root)
        if not violations:
            return [types.TextContent(type="text", text="All rules passed.")]
        lines = ["Rule violations found:\n"]
        for v in violations:
            lines.append(f"- **[{v.severity.upper()}]** `{v.rule}`: {v.message}")
        passed = not any(v.severity == "error" for v in violations)
        lines.append(f"\n**Passed (no errors):** {passed}")
        return [types.TextContent(type="text", text="\n".join(lines))]

    raise ValueError(f"Unknown tool: {name}")


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------

@app.list_resources()
async def list_resources() -> list[types.Resource]:
    resources = []
    root = _project_root()
    index = root / ".repro" / "index.md"
    if index.exists():
        resources.append(types.Resource(
            uri="repro://index",
            name="Reproducibility Index",
            description="Table of all logged sessions",
            mimeType="text/markdown",
        ))
    logs_dir = root / ".repro" / "logs"
    if logs_dir.exists():
        for log_file in sorted(logs_dir.glob("*.md"), reverse=True)[:20]:
            sid = log_file.stem
            resources.append(types.Resource(
                uri=f"repro://session/{sid}",
                name=f"Session {sid}",
                mimeType="text/markdown",
            ))
    return resources


@app.read_resource()
async def read_resource(uri: str) -> str:
    root = _project_root()
    if uri == "repro://index":
        p = root / ".repro" / "index.md"
        return p.read_text(encoding="utf-8") if p.exists() else "No index yet."
    if uri.startswith("repro://session/"):
        sid = uri.removeprefix("repro://session/")
        p = root / ".repro" / "logs" / f"{sid}.md"
        return p.read_text(encoding="utf-8") if p.exists() else f"Session {sid} not found."
    raise ValueError(f"Unknown resource URI: {uri}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    import asyncio

    async def _run() -> None:
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await app.run(read_stream, write_stream, app.create_initialization_options())

    asyncio.run(_run())


if __name__ == "__main__":
    main()
