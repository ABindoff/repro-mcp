"""Writes and maintains .repro/ markdown log files."""

import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .environment import EnvironmentSnapshot

REPRO_DIR = ".repro"
LOGS_DIR = f"{REPRO_DIR}/logs"
INDEX_FILE = f"{REPRO_DIR}/index.md"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S UTC")


def _git_diff_summary() -> str | None:
    try:
        result = subprocess.run(
            ["git", "diff", "--stat", "HEAD"],
            capture_output=True, text=True, timeout=10
        )
        return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else None
    except Exception:
        return None


class SessionLogger:
    def __init__(self, session_id: str, project_root: Path):
        self.session_id = session_id
        self.project_root = project_root
        self.log_path = project_root / LOGS_DIR / f"{session_id}.md"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def write_header(
        self,
        project_name: str,
        goal: str,
        branch: str | None,
        git_hash: str | None,
        env_snapshot: EnvironmentSnapshot,
    ) -> None:
        lines = [
            f"# Session: {self.session_id}",
            f"**Project:** {project_name}  ",
            f"**Goal:** {goal}  ",
        ]
        if branch:
            lines.append(f"**Branch:** {branch}  ")
        if git_hash:
            lines.append(f"**Git hash:** {git_hash[:12]}  ")
        lines.append("")
        lines.append(env_snapshot.to_markdown())
        lines.append("\n---\n")
        self.log_path.write_text("\n".join(lines), encoding="utf-8")

    def append(self, block: str) -> None:
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(block + "\n\n")

    def log_exchange(
        self,
        prompt: str,
        response: str,
        tool_calls: list | None = None,
        tags: list[str] | None = None,
    ) -> None:
        tag_str = f"  \n**Tags:** {', '.join(f'`{t}`' for t in tags)}" if tags else ""
        tool_str = ""
        if tool_calls:
            tool_str = "\n\n**Tool calls:** " + ", ".join(
                f"`{t.get('name', t)}`" for t in tool_calls
            )
        block = (
            f"## Exchange — {_now()}{tag_str}\n"
            f"**Prompt:** {prompt}\n\n"
            f"**Response:** {response}{tool_str}\n\n"
            f"---"
        )
        self.append(block)

    def log_decision(
        self,
        decision: str,
        rationale: str,
        alternatives: list[str] | None = None,
    ) -> None:
        alt_str = ""
        if alternatives:
            alt_str = "\n**Alternatives considered:** " + "; ".join(alternatives)
        block = (
            f"## Decision — {_now()}\n"
            f"**Decision:** {decision}  \n"
            f"**Rationale:** {rationale}{alt_str}\n\n"
            f"---"
        )
        self.append(block)

    def log_snapshot(self, snapshot: EnvironmentSnapshot) -> None:
        self.append(snapshot.to_markdown() + "\n\n---")

    def write_footer(self, outcome: str, notes: str | None) -> None:
        diff = _git_diff_summary()
        lines = [f"## Session close — {_now()}"]
        lines.append(f"**Outcome:** {outcome}  ")
        if notes:
            lines.append(f"**Notes:** {notes}  ")
        if diff:
            lines.append(f"\n**Git diff summary:**\n```\n{diff}\n```")
        self.append("\n".join(lines))

    def update_index(
        self,
        project_name: str,
        goal: str,
        outcome: str,
        branch: str | None,
        git_hash: str | None,
    ) -> None:
        index_path = self.project_root / INDEX_FILE
        header = "| Session | Date | Goal | Outcome | Branch | Git hash |\n|---|---|---|---|---|---|\n"
        date = self.session_id[:10]
        rel_log = f"logs/{self.session_id}.md"
        row = (
            f"| [{self.session_id}]({rel_log}) "
            f"| {date} "
            f"| {goal[:60]} "
            f"| {outcome} "
            f"| {branch or '—'} "
            f"| `{git_hash[:12] if git_hash else '—'}` |\n"
        )
        if not index_path.exists():
            index_path.parent.mkdir(parents=True, exist_ok=True)
            index_path.write_text(f"# Reproducibility Log Index\n\n{header}{row}", encoding="utf-8")
        else:
            content = index_path.read_text(encoding="utf-8")
            if header.splitlines()[0] not in content:
                content += f"\n{header}"
            content += row
            index_path.write_text(content, encoding="utf-8")
