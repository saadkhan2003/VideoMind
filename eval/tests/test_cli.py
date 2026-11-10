import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = ""
    return subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_run_eval_imports_as_a_script_and_as_a_module():
    script = _run(["eval/run_eval.py", "--help"])
    module = _run(["-m", "eval.run_eval", "--help"])
    assert script.returncode == 0, script.stderr
    assert module.returncode == 0, module.stderr
    assert "Evaluate VideoMind retrieval" in script.stdout
    assert "Evaluate VideoMind retrieval" in module.stdout


def test_align_labels_imports_as_a_script_and_as_a_module():
    script = _run(["eval/align_labels.py", "--help"])
    module = _run(["-m", "eval.align_labels", "--help"])
    assert script.returncode == 0, script.stderr
    assert module.returncode == 0, module.stderr
