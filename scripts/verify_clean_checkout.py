"""Rehearse the candidate checkout in a new venv and fresh npm installation."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/evidence/day4/clean-checkout"


def run(name, command, *, cwd, env, timeout=360):
    print(f"Running {name}", flush=True)
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="backslashreplace",
        timeout=timeout,
    )
    (EVIDENCE / name).write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"{name}: exit {result.returncode}")
    return result.stdout


def main():
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().endswith("API_KEY")
    }
    env.pop("OPENAI_MODEL", None)
    env.pop("PYTHONPATH", None)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    with TemporaryDirectory(prefix="af4-") as temporary:
        checkout = Path(temporary) / "checkout"
        run(
            "git-clone.txt",
            ["git", "clone", "--local", "--no-hardlinks", str(ROOT), str(checkout)],
            cwd=ROOT,
            env=env,
        )
        # Day 4 is deliberately uncommitted. Overlay the exact non-ignored
        # candidate files, never pretend the public GitHub HEAD already has them.
        names = (
            subprocess.check_output(
                ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                cwd=ROOT,
            )
            .decode("utf-8")
            .split("\0")
        )
        hashes = {}
        for name in names:
            if not name or name.startswith("docs/evidence/day4/"):
                continue
            source = ROOT / name
            target = checkout / name
            if not source.is_file():
                if target.is_file():
                    target.unlink()
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            hashes[name] = hashlib.sha256(source.read_bytes()).hexdigest()
        assert not (checkout / ".venv").exists()
        assert not (checkout / "apps/web/node_modules").exists()
        run("venv.txt", [sys.executable, "-m", "venv", ".venv"], cwd=checkout, env=env)
        python = (
            checkout
            / ".venv"
            / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        )
        run(
            "pip-install.txt",
            [str(python), "-m", "pip", "install", "-e", ".[test]"],
            cwd=checkout,
            env=env,
        )
        npm = shutil.which("npm.cmd") or shutil.which("npm")
        run("npm-ci.txt", [npm, "--prefix", "apps/web", "ci"], cwd=checkout, env=env)
        run("pip-check.txt", [str(python), "-m", "pip", "check"], cwd=checkout, env=env)
        run("pytest.txt", [str(python), "-m", "pytest", "-q"], cwd=checkout, env=env)
        run(
            "build.txt",
            [npm, "--prefix", "apps/web", "run", "build"],
            cwd=checkout,
            env=env,
        )
        demo = json.loads(
            run(
                "demo.json",
                [str(python), "-m", "agentforge.demo"],
                cwd=checkout,
                env=env,
            )
        )
        assert demo["status"] == "COMPLETED"
        output = run(
            "eval.txt",
            [
                str(python),
                "-m",
                "agentforge.evals",
                "run",
                "--output",
                "data/fresh-eval",
            ],
            cwd=checkout,
            env=env,
        )
        assert json.loads(output)["failed"] == 0
        run(
            "browser.txt",
            [str(python), "scripts/verify_day4.py", "--browser-only"],
            cwd=checkout,
            env=env,
        )
        browser = json.loads(
            (checkout / "docs/evidence/day4/browser-summary.json").read_text(
                encoding="utf-8"
            )
        )
        assert browser["status"] == "PASS"
        report = {
            "status": "PASS",
            "method": "Fresh local git clone plus exact uncommitted candidate overlay; not a claim that public GitHub HEAD includes Day 4.",
            "python_environment": "new venv; pip install -e .[test]",
            "frontend_environment": "fresh node_modules from npm ci",
            "api_keys": "removed from child environments",
            "browser": "installed host Edge or Playwright Chromium, not a fresh OS",
            "checks": [
                "pip check",
                "pytest -q",
                "frontend build",
                "Mock CLI",
                "42-case independent eval",
                "four-page Playwright and actual HTTP",
            ],
            "candidate_files_sha256": hashes,
        }
        (EVIDENCE / "summary.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        shutil.copy2(
            checkout / "docs/evidence/day4/browser-summary.json",
            EVIDENCE / "browser-summary.json",
        )
        print(
            "PASS: clean candidate checkout, new venv, npm ci, tests, build, eval and browser.",
            flush=True,
        )


if __name__ == "__main__":
    main()
