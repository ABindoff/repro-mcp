"""Standalone CLI for repro-mcp hooks — no MCP server or in-memory state needed.

Called by Claude Code SessionStart/SessionEnd hooks. Persists session state to
.repro/.active_session.json so any process can pick it up without the MCP server.
"""

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from . import environment as env_mod
from .logger import SessionLogger

ACTIVE_SESSION_FILE = ".repro/.active_session.json"


def _session_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S")


def _project_root() -> Path:
    return Path(os.getcwd())


def cmd_start(args) -> None:
    root = _project_root()
    active_path = root / ACTIVE_SESSION_FILE

    if active_path.exists():
        existing = json.loads(active_path.read_text(encoding="utf-8"))
        print(f"repro-mcp: session already active — {existing['session_id']}")
        return

    sid = _session_id()
    project_name = args.project_name or root.name
    snapshot = env_mod.capture()

    logger = SessionLogger(sid, root)
    logger.write_header(
        project_name,
        args.goal,
        snapshot.git_branch,
        snapshot.git_hash,
        snapshot,
    )

    active_path.parent.mkdir(parents=True, exist_ok=True)
    active_path.write_text(
        json.dumps({
            "session_id": sid,
            "project_name": project_name,
            "goal": args.goal,
            "branch": snapshot.git_branch,
            "git_hash": snapshot.git_hash,
        }),
        encoding="utf-8",
    )
    print(f"repro-mcp: session started — {sid}")


def cmd_end(args) -> None:
    root = _project_root()
    active_path = root / ACTIVE_SESSION_FILE

    if not active_path.exists():
        return  # no active session — silent no-op

    active = json.loads(active_path.read_text(encoding="utf-8"))
    sid = active["session_id"]

    logger = SessionLogger(sid, root)
    logger.write_footer(args.outcome, getattr(args, "notes", None))
    logger.update_index(
        active["project_name"],
        active["goal"],
        args.outcome,
        active.get("branch"),
        active.get("git_hash"),
    )
    active_path.unlink()
    print(f"repro-mcp: session closed — {sid} ({args.outcome})")


def main() -> None:
    parser = argparse.ArgumentParser(prog="repro", description="repro-mcp CLI for hooks and manual use")
    sub = parser.add_subparsers(dest="command", required=True)

    p_start = sub.add_parser("start", help="Start a reproducibility session")
    p_start.add_argument("project_name", nargs="?", default=None, help="Short project name (defaults to current directory name)")
    p_start.add_argument("goal", nargs="?", default="Claude Code session", help="What this session is trying to accomplish")
    p_start.set_defaults(func=cmd_start)

    p_end = sub.add_parser("end", help="End the active reproducibility session")
    p_end.add_argument("outcome", choices=["success", "abandoned", "inconclusive"])
    p_end.add_argument("--notes", default=None)
    p_end.set_defaults(func=cmd_end)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
