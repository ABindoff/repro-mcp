"""In-memory session registry with disk persistence."""

import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import environment as env_mod
from .logger import SessionLogger

_GIT_ENV = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}


def _session_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S")


def _git_branch() -> str | None:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=5, env=_GIT_ENV,
            stdin=subprocess.DEVNULL,
        )
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


@dataclass
class Session:
    session_id: str
    project_name: str
    goal: str
    branch: str | None
    git_hash: str | None
    project_root: Path
    logger: SessionLogger = field(repr=False)


class SessionRegistry:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def start(self, project_name: str, goal: str, project_root: Path, branch: str | None = None) -> Session:
        sid = _session_id()
        snapshot = env_mod.capture()
        resolved_branch = branch or snapshot.git_branch
        git_hash = snapshot.git_hash

        logger = SessionLogger(sid, project_root)
        logger.write_header(project_name, goal, resolved_branch, git_hash, snapshot)

        session = Session(
            session_id=sid,
            project_name=project_name,
            goal=goal,
            branch=resolved_branch,
            git_hash=git_hash,
            project_root=project_root,
            logger=logger,
        )
        self._sessions[sid] = session
        return session

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def require(self, session_id: str) -> Session:
        s = self.get(session_id)
        if s is None:
            raise KeyError(f"No active session '{session_id}'. Call session_start first.")
        return s

    def end(self, session_id: str, outcome: str, notes: str | None) -> Session:
        session = self.require(session_id)
        session.logger.write_footer(outcome, notes)
        session.logger.update_index(
            session.project_name,
            session.goal,
            outcome,
            session.branch,
            session.git_hash,
        )
        del self._sessions[session_id]
        return session
