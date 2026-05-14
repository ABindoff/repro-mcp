"""Captures a snapshot of the current compute environment."""

import platform
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class EnvironmentSnapshot:
    timestamp: str
    python_version: str
    platform_info: str
    packages: list[str]
    git_hash: str | None
    git_branch: str | None
    conda_env: str | None
    label: str = ""

    def to_markdown(self) -> str:
        lines = [f"### Environment snapshot{f' — {self.label}' if self.label else ''} `{self.timestamp}`"]
        lines.append(f"- **Python:** {self.python_version}")
        lines.append(f"- **Platform:** {self.platform_info}")
        if self.conda_env:
            lines.append(f"- **Conda env:** {self.conda_env}")
        if self.git_hash:
            branch_str = f" ({self.git_branch})" if self.git_branch else ""
            lines.append(f"- **Git:** `{self.git_hash[:12]}`{branch_str}")
        if self.packages:
            lines.append("\n**Packages:**")
            lines.append("```")
            lines.extend(self.packages[:80])  # cap at 80 to keep logs readable
            if len(self.packages) > 80:
                lines.append(f"... and {len(self.packages) - 80} more")
            lines.append("```")
        return "\n".join(lines)


def _run(cmd: list[str]) -> str | None:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


def capture() -> EnvironmentSnapshot:
    python_version = sys.version.replace("\n", " ")
    platform_info = f"{platform.system()} {platform.release()} ({platform.machine()})"

    # pip freeze is the most universal; fall back gracefully
    pip_output = _run([sys.executable, "-m", "pip", "freeze"])
    packages = pip_output.splitlines() if pip_output else []

    git_hash = _run(["git", "rev-parse", "HEAD"])
    git_branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"])

    import os
    conda_env = os.environ.get("CONDA_DEFAULT_ENV") or os.environ.get("VIRTUAL_ENV")

    return EnvironmentSnapshot(
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        python_version=python_version,
        platform_info=platform_info,
        packages=packages,
        git_hash=git_hash,
        git_branch=git_branch,
        conda_env=conda_env,
    )
