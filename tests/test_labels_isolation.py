import ast
from pathlib import Path

import pytest

from agents.system.tools import read_data

REPO = Path(__file__).resolve().parent.parent


def test_runtime(tmp_path):
    # @criterion C4
    (tmp_path / "data" / "labels").mkdir(parents=True)
    (tmp_path / "data" / "labels" / "l.csv").write_text("x")
    (tmp_path / "data" / "clean").mkdir()
    (tmp_path / "data" / "clean" / "ok.csv").write_text("ok")
    (tmp_path / "data" / "clean" / "link").symlink_to(tmp_path / "data" / "labels")
    assert read_data("data/clean/ok.csv", tmp_path) == "ok"
    for p in (
        "data/labels/l.csv",
        "data/clean/../labels/l.csv",
        "data/clean/link/l.csv",
        "data/labels",
    ):
        with pytest.raises(PermissionError):
            read_data(p, tmp_path)
    with pytest.raises(PermissionError):
        read_data("pyproject.toml", tmp_path)


def _is_labels(name: str) -> bool:
    parts = name.split(".")
    return parts[0] in ("eval", "labeling", "labeler_rules") or "labels" in name


GUARD = REPO / "agents" / "system" / "tools.py"


def labels_violations(src: str) -> list[str]:
    """Names of labels references: the path, a "labels" string literal, or a labels import."""
    out = []
    tree = ast.parse(src)
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            if "labels" in n.value.lower() or "labeler_rules" in n.value.lower():
                out.append(n.value)
        elif isinstance(n, ast.Import):
            out += [a.name for a in n.names if _is_labels(a.name)]
        elif isinstance(n, ast.ImportFrom):
            mods = [n.module or ""] + [a.name for a in n.names]
            out += [m for m in mods if m and _is_labels(m)]
    return out


def test_static():
    # @criterion C4
    files = [REPO / "runner.py"]
    for d in ("agents", "llm"):
        files += (REPO / d).rglob("*.py")
    assert files
    for f in files:
        assert not labels_violations(
            f.read_text(encoding="utf-8"),
        ), f


def test_static_catches_parts_joined_path():
    # @criterion C4
    assert labels_violations('p = Path("data") / "labels" / "x.csv"')
    assert labels_violations('p = os.path.join("data", "labels")')
    assert labels_violations("import eval.consistency")
    assert labels_violations("from labeling import x")
    assert not labels_violations('p = Path("data") / "clean"')


def test_static_catches_labeler_rules():
    # @criterion C4
    assert labels_violations("import labeler_rules.x")
    assert labels_violations("from labeler_rules import decide")
    assert labels_violations("from labeler_rules.decide import decide")
    assert labels_violations('p = Path("labeler_rules") / "decide.py"')
    assert not labels_violations("import rules.lookup")


def test_guard_names_no_labels():
    # @criterion C4
    assert GUARD.is_file()
    assert "labels" not in GUARD.read_text(encoding="utf-8").lower()
