"""The public copy export (T66): the file set, the bans, the redaction and the scan."""

import fnmatch
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from publish import export as pub

FIXTURE = Path(__file__).parent / "fixtures" / "public_copy" / "tree"
ROOT = Path(__file__).resolve().parent.parent


def _key() -> str:
    # Built here so no file of the repository holds a key-shaped string.
    return "AI" + "za" + "A1b2C3d4E5" * 3 + "xyzab"


def _git(repo: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env=pub.git_env(),
    )
    return out.stdout


def _source(tmp_path: Path, extra: dict[str, str] | None = None) -> Path:
    src = tmp_path / "src"
    shutil.copytree(FIXTURE, src)
    page = src / "rules/sources/page.html"
    page.write_text(page.read_text().replace("__KEY__", _key()))
    (src / "notes.txt").write_text("a comment: harness" + " check runs this\n")
    for rel, text in (extra or {}).items():
        (src / rel).write_text(text)
    _git(src, "init", "-q", "-b", "main")
    _git(src, "config", "user.name", "Fixture Author")
    _git(src, "config", "user.email", "fixture@example.org")
    _git(src, "add", "-A")
    _git(src, "commit", "-q", "-m", "fixture")
    return src


def _violations(files, ban):
    """Files a ban entry (fnmatch, alone or as a directory) names; independent of the export."""
    return [
        f
        for f in files
        for b in ban
        if fnmatch.fnmatchcase(f, b.rstrip("/"))
        or fnmatch.fnmatchcase(f, b.rstrip("/") + "/*")
    ]


def _paths(dest: Path) -> set[str]:
    return {
        p.relative_to(dest).as_posix()
        for p in dest.rglob("*")
        if p.is_file() and ".git" not in p.relative_to(dest).parts[:1]
    }


def test_the_copy_keeps_the_listed_files_and_leaves_out_the_banned(tmp_path):
    src = _source(tmp_path)
    dest = tmp_path / "out"
    assert pub.export(dest, src) == 5
    assert _paths(dest) == {
        "keep.txt",
        "notes.txt",
        "docs/pitch.md",
        "rules/sources/page.html",
        "config/public.yaml",
        "conftest.py",
    }


def test_the_copy_is_one_commit_on_main_with_no_remote_and_the_source_identity(
    tmp_path,
):
    src = _source(tmp_path)
    dest = tmp_path / "out"
    pub.export(dest, src)
    assert _git(dest, "rev-list", "--count", "HEAD").strip() == "1"
    assert _git(dest, "branch", "--show-current").strip() == "main"
    assert _git(dest, "log", "-1", "--format=%an <%ae>|%B").strip() == (
        "Config Author <fixture@example.org>|say-it-twice: public copy"
    )
    assert _git(dest, "log", "-1", "--format=%cn <%ce>").strip() == (
        "Config Author <fixture@example.org>"
    )
    assert _git(dest, "remote").strip() == ""
    assert _git(dest, "status", "--short").strip() == ""


def test_untracked_files_are_never_copied(tmp_path):
    src = _source(tmp_path)
    (src / "untracked.txt").write_text("not committed")
    dest = tmp_path / "out"
    pub.export(dest, src)
    assert "untracked.txt" not in _paths(dest)


def test_a_key_shaped_string_in_a_source_page_is_redacted(tmp_path):
    src = _source(tmp_path)
    dest = tmp_path / "out"
    pub.export(dest, src)
    page = (dest / "rules/sources/page.html").read_text()
    assert "REDACTED" in page and "AIza" not in page
    # the source repository keeps the page as saved
    assert _key() in (src / "rules/sources/page.html").read_text()


def test_the_methods_names_are_rewritten_in_published_files(tmp_path):
    src = _source(tmp_path)
    dest = tmp_path / "out"
    pub.export(dest, src)
    assert (dest / "notes.txt").read_text() == "a comment: the linter runs this\n"


def test_a_target_that_is_not_empty_is_refused(tmp_path, capsys):
    src = _source(tmp_path)
    dest = tmp_path / "out"
    dest.mkdir()
    (dest / "x").write_text("x")
    assert pub.main(["--dest", str(dest), "--root", str(src)]) == 1
    assert "not an empty directory" in capsys.readouterr().err
    assert _paths(dest) == {"x"}


def test_a_target_inside_the_source_repository_is_refused(tmp_path):
    src = _source(tmp_path)
    with pytest.raises(pub.ExportError):
        pub.export(src / "inside", src)


@pytest.mark.parametrize(
    ("secret", "pattern_part"),
    [
        ("AI" + "za" + "Q" * 35, "AIza"),
        ("gh" + "p_" + "a1" * 18, "ghp_"),
        ("api_key = " + "z9" * 14, "api[_-]?key"),
    ],
)
def test_a_planted_secret_fails_and_prints_the_path_and_pattern_not_the_secret(
    tmp_path, capsys, secret, pattern_part
):
    src = _source(tmp_path, {"keep.txt": f"value {secret}\n"})
    dest = tmp_path / "out"
    assert pub.main(["--dest", str(dest), "--root", str(src)]) == 1
    err = capsys.readouterr().err
    assert "keep.txt" in err and pattern_part in err
    assert secret not in err
    assert secret.split()[-1] not in err
    assert not (dest / ".git").exists()
    assert list(dest.iterdir()) == []  # the copy that held the secret is removed


def test_a_key_assignment_in_a_saved_source_page_is_not_a_hit(tmp_path):
    src = _source(tmp_path, {"rules/sources/page.html": "token: " + "k" * 30 + "\n"})
    dest = tmp_path / "out"
    pub.export(dest, src)
    # the page is copied as it is: the assignment is not rewritten and not a scan hit
    assert (dest / "rules/sources/page.html").read_text() == "token: " + "k" * 30 + "\n"


def test_a_binary_file_is_not_scanned(tmp_path):
    src = tmp_path / "bin"
    shutil.copytree(FIXTURE, src)
    (src / "rules/sources/page.html").write_text("plain\n")
    (src / "blob.bin").write_bytes(b"\0" + _key().encode())
    _git(src, "init", "-q", "-b", "main")
    _git(src, "config", "user.name", "A")
    _git(src, "config", "user.email", "a@example.org")
    _git(src, "add", "-A")
    _git(src, "commit", "-q", "-m", "x")
    pub.export(tmp_path / "out", src)
    assert (tmp_path / "out" / "blob.bin").is_file()


def test_the_projects_own_file_set_has_no_banned_path_and_keeps_the_listed_docs():
    cfg = pub.load_config(ROOT)
    files = pub.file_set(ROOT, cfg)
    assert not _violations(files, cfg["ban"])
    assert "README.md" in files and "uv.lock" in files and ".python-version" in files
    assert "docs/pitch.md" in files and "docs/modules/prereg.md" in files
    assert "docs/plan.md" not in files and "docs/spec.md" not in files
    assert set(cfg) >= {"ban", "docs", "rewrite", "skip_tests", "scan"}


def test_the_ban_check_catches_banned_paths_spelled_as_globs():
    ban = pub.load_config(ROOT)["ban"]
    banned = [
        "." + "harness/ask-paths",
        "STATE" + ".md",
        "FRICTIONS" + ".md",
        "tasks/" + "T1.md",
    ]
    assert _violations([*banned, "README.md", "docs/pitch.md"], ban) == banned
    # the export drops the same paths
    assert all(pub._banned(f, ban) for f in banned)
    assert not pub._banned("README.md", ban)


def test_the_generated_conftest_skips_the_listed_tests_in_the_copy(tmp_path):
    tests = "def test_a():\n    assert False\n\n\ndef test_b():\n    assert True\n"
    src = _source(tmp_path, {"test_skipme.py": tests})
    dest = tmp_path / "out"
    pub.export(dest, src)
    conftest = (dest / "conftest.py").read_text()
    assert "test_skipme.py::test_a" in conftest
    out = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-rs",
            "-p",
            "no:cacheprovider",
            "test_skipme.py",
        ],
        cwd=dest,
        capture_output=True,
        text=True,
        env={**pub.git_env(), "PYTHONPATH": ""},
        check=False,
    )
    assert "1 passed, 1 skipped" in out.stdout, out.stdout
    assert "needs what the copy leaves out" in out.stdout


def test_no_conftest_when_nothing_is_skipped(tmp_path):
    src = _source(tmp_path)
    (src / "config/public.yaml").write_text(
        (src / "config/public.yaml").read_text().split("skip_tests:")[0]
        + "skip_tests: []\nscan: []\n"
    )
    _git(src, "commit", "-q", "-am", "no skips")
    pub.export(tmp_path / "out", src)
    assert not (tmp_path / "out" / "conftest.py").exists()


def test_the_real_rewrite_rules_clean_the_importlinter_comment_and_the_decision_cards():
    rules = pub.load_config(ROOT)["rewrite"]
    method = "`harness" + " check`"
    imp = f"# (ADR-0003). {method} runs `lint-imports`. scrape/ is tooling\n".encode()
    out = pub._rewrite(".importlinter", imp, rules).decode()
    assert "harness" not in out and "`lint-imports` checks them" in out
    task = "tasks/" + "T58-delays.md"
    adr = f"Format based on MADR. Card: `{task}`. Nothing\n".encode()
    out = pub._rewrite("docs/decisions/0008-x.md", adr, rules).decode()
    assert out == "Format based on MADR. Card: T58. Nothing\n"
    # a file no rule names is returned as it is
    assert pub._rewrite("README.md", adr, rules) == adr
