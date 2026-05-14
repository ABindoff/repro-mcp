"""Rule engine for reproducibility checks."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml

Severity = Literal["error", "warn", "info"]


@dataclass
class Violation:
    rule: str
    severity: Severity
    message: str

    def to_dict(self) -> dict:
        return {"rule": self.rule, "severity": self.severity, "message": self.message}


# ---------------------------------------------------------------------------
# Built-in rule implementations
# ---------------------------------------------------------------------------

_RNG_CALLS = re.compile(
    r"\b(random\.|np\.random\.|torch\.manual_seed|tf\.random\.set_seed"
    r"|sklearn.*random_state|numpy\.random\.|scipy\.stats\.|rng\.|rng =)",
    re.IGNORECASE,
)
_SEED_SET = re.compile(
    r"(random\.seed|np\.random\.seed|torch\.manual_seed|tf\.random\.set_seed"
    r"|random_state\s*=\s*\d|seed\s*=\s*\d)",
    re.IGNORECASE,
)
_ABS_PATH = re.compile(r'(["\'])(/[^"\']+|[A-Z]:\\[^"\']+)\1')
_HARDCODED_PATH_EXCEPTIONS = re.compile(r"(/usr/|/etc/|/tmp/|/dev/null)")


def check_random_seed(context: str) -> Violation | None:
    if _RNG_CALLS.search(context) and not _SEED_SET.search(context):
        return Violation(
            rule="random-seed",
            severity="error",
            message="RNG call detected but no seed set. Add a seed for reproducibility.",
        )
    return None


def check_no_hardcoded_paths(context: str) -> Violation | None:
    matches = _ABS_PATH.findall(context)
    real = [m[1] for m in matches if not _HARDCODED_PATH_EXCEPTIONS.search(m[1])]
    if real:
        return Violation(
            rule="no-hardcoded-paths",
            severity="error",
            message=f"Hardcoded absolute path(s) found: {real[:3]}. Use config or relative paths.",
        )
    return None


def check_env_pinned(project_root: Path) -> Violation | None:
    req = project_root / "requirements.txt"
    env_yml = project_root / "environment.yml"

    for f in [req, env_yml]:
        if f.exists():
            content = f.read_text(encoding="utf-8")
            unpinned = [
                line.strip()
                for line in content.splitlines()
                if line.strip()
                and not line.startswith("#")
                and not line.startswith("-")
                and "==" not in line
                and ">=" not in line
                and "<=" not in line
                and "~=" not in line
                and "name:" not in line
                and "channels:" not in line
                and "dependencies:" not in line
            ]
            if unpinned:
                return Violation(
                    rule="env-pinned",
                    severity="warn",
                    message=f"{f.name} has unpinned packages: {unpinned[:5]}",
                )
            return None  # found and pinned

    return Violation(
        rule="env-pinned",
        severity="warn",
        message="No requirements.txt or environment.yml found. Consider pinning your environment.",
    )


def check_no_inplace_data_mutation(context: str) -> Violation | None:
    # Warn on writes that target common raw data dirs
    pattern = re.compile(
        r'(\.to_csv|\.to_parquet|\.to_excel|open\(.*["\']w["\'])'
        r'.*?(raw|data/raw|inputs/)',
        re.IGNORECASE,
    )
    if pattern.search(context):
        return Violation(
            rule="no-inplace-data-mutation",
            severity="warn",
            message="Possible write to raw data directory detected. Raw data should be read-only.",
        )
    return None


def check_gpu_nondeterminism(context: str) -> Violation | None:
    if re.search(r"\b(cuda|torch\.cuda|\.to\([\"']cuda)", context, re.IGNORECASE):
        if not re.search(r"deterministic|benchmark\s*=\s*False|use_deterministic", context, re.IGNORECASE):
            return Violation(
                rule="gpu-nondeterminism",
                severity="info",
                message="CUDA ops detected. Consider torch.use_deterministic_algorithms(True) and cudnn.benchmark=False.",
            )
    return None


# ---------------------------------------------------------------------------
# Rule registry and runner
# ---------------------------------------------------------------------------

_CONTEXT_RULES = {
    "random-seed": check_random_seed,
    "no-hardcoded-paths": check_no_hardcoded_paths,
    "no-inplace-data-mutation": check_no_inplace_data_mutation,
    "gpu-nondeterminism": check_gpu_nondeterminism,
}

_PROJECT_RULES = {
    "env-pinned": check_env_pinned,
}


def load_enabled_rules(project_root: Path) -> set[str]:
    rules_file = project_root / ".repro" / "rules.yaml"
    if not rules_file.exists():
        # all rules on by default
        return set(_CONTEXT_RULES) | set(_PROJECT_RULES)
    config = yaml.safe_load(rules_file.read_text(encoding="utf-8")) or {}
    rules = config.get("rules", {})
    return {name for name, cfg in rules.items() if cfg.get("enabled", True)}


def run_checks(context: str, project_root: Path) -> list[Violation]:
    enabled = load_enabled_rules(project_root)
    violations: list[Violation] = []

    for name, fn in _CONTEXT_RULES.items():
        if name in enabled:
            v = fn(context)
            if v:
                violations.append(v)

    for name, fn in _PROJECT_RULES.items():
        if name in enabled:
            v = fn(project_root)
            if v:
                violations.append(v)

    return violations
