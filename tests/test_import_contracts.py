"""The layer rules of docs/plan.md as import contracts (T15, ADR-0003, ADR-0004)."""

import ast
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LINT_IMPORTS = Path(sys.executable).parent / "lint-imports"
PACKAGES = [
    "agents",
    "cases",
    "eval",
    "ingest",
    "labeler_rules",
    "labeling",
    "llm",
    "report",
    "rules",
]

C1 = "Agents, gate and runner never see evaluation"
C2 = "Only the access point reads rules and flights"
C3 = "The gate stands alone"
C4 = "Ingest and rules are the base"
C5 = "Nothing imports the report"

VIOLATIONS = [
    (C1, "agents/placeholder.py", "import labeling"),
    (C1, "agents/placeholder.py", "import labeler_rules"),
    (C2, "agents/placeholder.py", "import rules"),
    (C3, "llm/gate.py", "import runner"),
    (C4, "ingest/pipeline.py", "import cases"),
    (C5, "eval/consistency.py", "import report"),
]


def lint(cwd: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": str(cwd)}
    return subprocess.run(
        [str(LINT_IMPORTS), "--no-cache"],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


# @criterion C4
def test_five_kept():
    result = lint(ROOT)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Contracts: 5 kept, 0 broken." in result.stdout
    for name in (C1, C2, C3, C4, C5):
        assert f"{name} KEPT" in result.stdout


def copy_project(dest: Path) -> None:
    ignore = shutil.ignore_patterns("__pycache__", "work", "sources", "dev", "test")
    for package in PACKAGES:
        shutil.copytree(ROOT / package, dest / package, ignore=ignore)
    shutil.copy(ROOT / "runner.py", dest / "runner.py")
    shutil.copy(ROOT / ".importlinter", dest / ".importlinter")


@pytest.fixture(scope="module")
def project_copy(tmp_path_factory):
    dest = tmp_path_factory.mktemp("contracts")
    copy_project(dest)
    return dest


# @criterion C4
def test_violations_unmodified_copy_passes(project_copy):
    result = lint(project_copy)
    assert result.returncode == 0, result.stdout + result.stderr


# @criterion C4
@pytest.mark.parametrize(("contract", "path", "line"), VIOLATIONS)
def test_violations(tmp_path, contract, path, line):
    copy_project(tmp_path)
    target = tmp_path / path
    target.write_text(target.read_text() + f"\n{line}\n")
    result = lint(tmp_path)
    assert result.returncode != 0, result.stdout
    assert f"{contract} BROKEN" in result.stdout, result.stdout


def top_level_imports(path: Path) -> set[str]:
    names = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names.add(node.module.split(".")[0])
    return names


# @criterion C4
def test_runner_never_sees_evaluation_or_report():
    # runner.py is a module, which import-linter refuses as a root package: its own imports
    # are checked here, and contract 1 checks what agents and llm import in turn.
    forbidden = {"eval", "labeler_rules", "labeling", "report"}
    assert not top_level_imports(ROOT / "runner.py") & forbidden
