"""
FILE: smoke_test_runner.py
ROLE: Meta-runner that finds and executes all smoke tests across the toolbox.
WHAT IT DOES:
  - Discovers every smoke_test.py in the toolbox and vendable packages
  - Runs each in its own subprocess with a timeout
  - Aggregates pass/fail results into one structured report
  - Reports total pass rate, failures with stderr, and timing
HOW TO USE:
  - python src/tools/smoke_test_runner.py metadata
  - python src/tools/smoke_test_runner.py run --input-json "{}"
  - python src/tools/smoke_test_runner.py run --input-json '{"timeout_seconds": 60, "include_packages": true}'
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).resolve().parents[1]))
from common import standard_main, tool_result, tool_error

FILE_METADATA = {
    "tool_name": "smoke_test_runner",
    "version": "1.0.0",
    "entrypoint": "src/tools/smoke_test_runner.py",
    "category": "testing",
    "summary": "Find and run all smoke_test.py files across the toolbox and vendable packages, aggregating pass/fail into one report.",
    "mcp_name": "smoke_test_runner",
    "input_schema": {
        "type": "object",
        "properties": {
            "toolbox_root": {
                "type": "string",
                "description": "Path to the .dev-tools root. Defaults to auto-detected from this tool's location."
            },
            "include_packages": {
                "type": "boolean",
                "default": True,
                "description": "If true, also run smoke tests in vendable packages under packages/."
            },
            "timeout_seconds": {
                "type": "integer",
                "default": 30,
                "description": "Timeout per smoke test in seconds."
            },
            "stop_on_failure": {
                "type": "boolean",
                "default": False,
                "description": "If true, stop after the first failure."
            },
            "targets": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Specific smoke test paths to run. If set, skips auto-discovery."
            }
        }
    }
}

TOOLBOX_ROOT = Path(__file__).resolve().parents[2]  # src/tools/ -> src/ -> .dev-tools


def _discover_smoke_tests(root: Path, include_packages: bool) -> list[dict[str, Any]]:
    """Find all smoke_test.py files in the toolbox."""
    tests: list[dict[str, Any]] = []

    # Main toolbox smoke test
    main_test = root / "src" / "smoke_test.py"
    if main_test.exists():
        tests.append({
            "path": str(main_test),
            "cwd": str(root / "src"),
            "label": "toolbox (src/smoke_test.py)",
        })

    # Package smoke tests
    if include_packages:
        packages_dir = root / "packages"
        if packages_dir.is_dir():
            for pkg_dir in sorted(packages_dir.iterdir()):
                if not pkg_dir.is_dir():
                    continue
                pkg_test = pkg_dir / "smoke_test.py"
                if pkg_test.exists():
                    tests.append({
                        "path": str(pkg_test),
                        "cwd": str(pkg_dir),
                        "label": f"packages/{pkg_dir.name}",
                    })

    # Authorities smoke tests
    authorities_dir = root / "authorities"
    if authorities_dir.is_dir():
        for auth_dir in sorted(authorities_dir.iterdir()):
            if not auth_dir.is_dir():
                continue
            auth_test = auth_dir / "smoke_test.py"
            if auth_test.exists():
                tests.append({
                    "path": str(auth_test),
                    "cwd": str(auth_dir),
                    "label": f"authorities/{auth_dir.name}",
                })

    return tests


def _run_smoke_test(test: dict, timeout: int) -> dict[str, Any]:
    """Run a single smoke test and return the result."""
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            [sys.executable, test["path"]],
            cwd=test["cwd"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        duration = round(time.perf_counter() - started, 3)

        result: dict[str, Any] = {
            "label": test["label"],
            "path": test["path"],
            "passed": completed.returncode == 0,
            "returncode": completed.returncode,
            "duration_seconds": duration,
        }

        if completed.returncode != 0:
            # Include output for failures
            stderr = completed.stderr.strip()
            stdout = completed.stdout.strip()
            if stderr:
                result["stderr"] = stderr[-1000:]  # Last 1000 chars
            if stdout:
                result["stdout"] = stdout[-1000:]

        return result

    except subprocess.TimeoutExpired:
        duration = round(time.perf_counter() - started, 3)
        return {
            "label": test["label"],
            "path": test["path"],
            "passed": False,
            "returncode": -1,
            "duration_seconds": duration,
            "error": f"Timed out after {timeout}s",
        }
    except Exception as exc:
        return {
            "label": test["label"],
            "path": test["path"],
            "passed": False,
            "returncode": -1,
            "duration_seconds": 0,
            "error": str(exc),
        }


def run(arguments: dict) -> dict:
    root = Path(arguments.get("toolbox_root") or TOOLBOX_ROOT).resolve()
    include_packages = arguments.get("include_packages", True)
    timeout = arguments.get("timeout_seconds", 30)
    stop_on_failure = arguments.get("stop_on_failure", False)
    explicit_targets = arguments.get("targets")

    if not root.is_dir():
        return tool_error(FILE_METADATA["tool_name"], arguments, f"Not a directory: {root}")

    try:
        # Discover or use explicit targets
        if explicit_targets:
            tests = []
            for t in explicit_targets:
                p = Path(t).resolve()
                if p.exists():
                    tests.append({
                        "path": str(p),
                        "cwd": str(p.parent),
                        "label": str(p.relative_to(root)) if p.is_relative_to(root) else str(p),
                    })
        else:
            tests = _discover_smoke_tests(root, include_packages)

        if not tests:
            return tool_result(FILE_METADATA["tool_name"], arguments, {
                "message": "No smoke tests found.",
                "toolbox_root": str(root),
            })

        # Run all tests
        results: list[dict] = []
        total_duration = 0.0

        for test in tests:
            result = _run_smoke_test(test, timeout)
            results.append(result)
            total_duration += result.get("duration_seconds", 0)

            if stop_on_failure and not result["passed"]:
                break

        passed = sum(1 for r in results if r["passed"])
        failed = sum(1 for r in results if not r["passed"])

        report: dict[str, Any] = {
            "toolbox_root": str(root),
            "tests_found": len(tests),
            "tests_run": len(results),
            "passed": passed,
            "failed": failed,
            "pass_rate": round(passed / len(results), 3) if results else 0,
            "total_duration_seconds": round(total_duration, 3),
            "all_passed": failed == 0,
            "results": results,
        }

        if failed > 0:
            report["failures"] = [r for r in results if not r["passed"]]

        return tool_result(FILE_METADATA["tool_name"], arguments, report)

    except Exception as exc:
        return tool_error(FILE_METADATA["tool_name"], arguments, str(exc))


if __name__ == "__main__":
    standard_main(FILE_METADATA, run)
