"""`make reproduce` (C12): every report rebuilt from the cached runs, with no model call.

Entry: `python -m report.reproduce [--root DIR] [--runs-dir DIR]`. While it runs, the
provider every gate would take (`llm.provider.get_provider`, `real_provider`, `placeholder`)
is replaced by `refuse`, which raises: a step that would call a model fails the command.
It rebuilds, from the runs found under the runs directory:

- the confirmatory report (report.confirm), when runs/confirm/complete.json exists;
- the development reports (runs/<protocol>/report.json and report.html, protocols dev-subset
  and dev-full) by calling eval.metrics.evaluate and report.dev_eval.render directly;
- the operating-point grid (eval.operating_point, never with --write), when
  runs/dev-full-system holds traces.

A report whose runs are absent is skipped with one line. Exits with the confirmatory report's
code (1: an agent incomplete or invalid), else 0.
"""

import argparse
import contextlib
import json
from pathlib import Path

import runner
from eval import operating_point
from eval.metrics import evaluate
from llm import provider as providers
from report import confirm, dev_eval

DEV_PROTOCOLS = ("dev-subset", "dev-full")


class ProviderCalled(RuntimeError):
    """A model call was attempted inside `make reproduce`."""


def refuse(model, *args, **kwargs):
    raise ProviderCalled(f"make reproduce calls no model (asked for {model})")


@contextlib.contextmanager
def no_provider():
    """Every provider the gate could take raises while the block runs."""
    saved = {
        name: getattr(providers, name)
        for name in ("get_provider", "real_provider", "placeholder")
    }
    providers.get_provider = lambda model: refuse
    providers.real_provider = refuse
    providers.placeholder = refuse
    try:
        yield refuse
    finally:
        for name, fn in saved.items():
            setattr(providers, name, fn)


def dev_reports(root, runs_dir):
    """The development reports rebuilt from runs/<protocol>-<agent>; the protocols written."""
    done = []
    for p in DEV_PROTOCOLS:
        agents = [a for a in runner.STUDY_AGENTS if (runs_dir / f"{p}-{a}").is_dir()]
        if not agents:
            print(f"skipped {p}: no run under {runs_dir}")
            continue
        report = evaluate(root, p, agents, runs_dir)
        out = runs_dir / p
        out.mkdir(parents=True, exist_ok=True)
        (out / "report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n"
        )
        (out / "report.html").write_text(dev_eval.render(report))
        print(f"report: {out / 'report.html'}")
        done.append(p)
    return done


def grid(root, runs_dir):
    run_dir = runs_dir / operating_point.RUN
    if not (run_dir / "traces").is_dir():
        print(f"skipped the operating-point grid: no traces in {run_dir}")
        return None
    rows = operating_point.rescore(root, run_dir)
    for r in rows:
        print(
            f"window {r['window']:>2}: {r['critical_errors']} critical, "
            f"{r['unnecessary_escalations']} unnecessary"
        )
    print(f"operating point: window={operating_point.choose(rows)['window']} min")
    return rows


def reproduce(root, runs_dir):
    """Every report from the cached runs, under no_provider; returns the exit code."""
    root, runs_dir = Path(root), Path(runs_dir)
    code = 0
    with no_provider() as installed:
        assert providers.get_provider("any") is installed
        print(f"provider: {installed.__module__}.{installed.__name__} (raises)")
        if (runs_dir / confirm.RUN / "complete.json").exists():
            report = confirm.build(root, runs_dir)
            print(f"report: {runs_dir / confirm.RUN / 'report.html'}")
            code = confirm.exit_code(report)
        else:
            print(f"skipped report-confirm: no {runs_dir / confirm.RUN}/complete.json")
        dev_reports(root, runs_dir)
        grid(root, runs_dir)
    return code


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(runner.ROOT))
    ap.add_argument("--runs-dir")
    a = ap.parse_args(argv)
    runs_dir = Path(a.runs_dir) if a.runs_dir else Path(a.root) / "runs"
    raise SystemExit(reproduce(a.root, runs_dir))


if __name__ == "__main__":
    # Run as the importable module, so the installed provider is report.reproduce.refuse
    # (the one a test of the module sees), not a copy under __main__.
    import importlib

    importlib.import_module("report.reproduce").main()
