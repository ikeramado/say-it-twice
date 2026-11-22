import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEYS = ("ANTHROPIC_API_KEY", "LLM_API_KEY")


def run_make(env_file, **extra):
    env = {k: v for k, v in os.environ.items() if k not in KEYS}
    env.update(extra)
    return subprocess.run(
        ["make", "env-check", f"ENV_FILE={env_file}"],
        check=False, cwd=ROOT, env=env, capture_output=True, text=True,
    )


def test_loads_key_from_file(tmp_path):
    f = tmp_path / "keys.env"
    f.write_text("ANTHROPIC_API_KEY=dummy-value\n")
    r = run_make(f)
    assert r.returncode == 0
    assert "ANTHROPIC_API_KEY: set" in r.stdout
    assert "LLM_API_KEY: not set" in r.stdout
    assert "dummy-value" not in r.stdout + r.stderr


def test_missing_file(tmp_path):
    r = run_make(tmp_path / "absent.env")
    assert r.returncode == 0
    assert "ANTHROPIC_API_KEY: not set" in r.stdout


def test_precedence_environment_wins(tmp_path):
    f = tmp_path / "keys.env"
    f.write_text("LLM_API_KEY=\n")
    r = run_make(f, LLM_API_KEY="from-env")
    assert "LLM_API_KEY: set" in r.stdout
    assert "from-env" not in r.stdout + r.stderr
