"""
FILE: python_complexity_scorer.py
ROLE: Score Python files/functions by complexity to identify decomposition targets.
WHAT IT DOES:
  - AST-scans Python files and computes per-function metrics:
    cyclomatic complexity, nesting depth, line count, parameter count
  - Scores each function/method and ranks them by complexity
  - Identifies files that are candidates for module_decomp_planner
  - Zero write risk — purely read-only introspection
HOW TO USE:
  - python src/tools/python_complexity_scorer.py metadata
  - python src/tools/python_complexity_scorer.py run --input-json '{"target": "path/to/file_or_dir"}'
  - python src/tools/python_complexity_scorer.py run --input-json '{"target": "src/", "threshold": 10}'
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).resolve().parents[1]))
from common import standard_main, tool_result, tool_error, should_skip_dir

FILE_METADATA = {
    "tool_name": "python_complexity_scorer",
    "version": "1.0.0",
    "entrypoint": "src/tools/python_complexity_scorer.py",
    "category": "analysis",
    "summary": "Score Python functions by cyclomatic complexity, nesting depth, line count, and parameter count to identify decomposition targets.",
    "mcp_name": "python_complexity_scorer",
    "input_schema": {
        "type": "object",
        "required": ["target"],
        "properties": {
            "target": {
                "type": "string",
                "description": "Path to a .py file or directory to scan."
            },
            "threshold": {
                "type": "integer",
                "default": 8,
                "description": "Complexity score threshold. Functions at or above this are flagged."
            },
            "top_n": {
                "type": "integer",
                "default": 20,
                "description": "Return only the top N most complex functions."
            },
            "include_all": {
                "type": "boolean",
                "default": False,
                "description": "If true, include all functions regardless of threshold."
            }
        }
    }
}


class _ComplexityVisitor(ast.NodeVisitor):
    """Count branching nodes for cyclomatic complexity."""

    def __init__(self) -> None:
        self.branches = 0

    def visit_If(self, node: ast.If) -> None:
        self.branches += 1
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        self.branches += 1
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None:
        self.branches += 1
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        self.branches += 1
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> None:
        self.branches += 1
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        # Each and/or adds a branch
        self.branches += len(node.values) - 1
        self.generic_visit(node)

    def visit_IfExp(self, node: ast.IfExp) -> None:
        self.branches += 1
        self.generic_visit(node)

    def visit_comprehension(self, node: ast.comprehension) -> None:
        self.branches += 1
        self.branches += len(node.ifs)
        self.generic_visit(node)


def _cyclomatic_complexity(node: ast.AST) -> int:
    """Compute cyclomatic complexity for a function/method node."""
    visitor = _ComplexityVisitor()
    visitor.visit(node)
    return visitor.branches + 1  # Base complexity of 1


def _max_nesting_depth(node: ast.AST, current: int = 0) -> int:
    """Compute maximum nesting depth of control structures."""
    max_depth = current
    nesting_types = (ast.If, ast.For, ast.While, ast.With, ast.Try, ast.ExceptHandler)

    for child in ast.iter_child_nodes(node):
        if isinstance(child, nesting_types):
            child_depth = _max_nesting_depth(child, current + 1)
            max_depth = max(max_depth, child_depth)
        else:
            child_depth = _max_nesting_depth(child, current)
            max_depth = max(max_depth, child_depth)

    return max_depth


def _param_count(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Count parameters (excluding self/cls)."""
    args = node.args
    total = len(args.args) + len(args.posonlyargs) + len(args.kwonlyargs)
    if args.vararg:
        total += 1
    if args.kwarg:
        total += 1
    # Subtract self/cls
    if args.args and args.args[0].arg in ("self", "cls"):
        total -= 1
    return total


def _line_count(node: ast.AST) -> int:
    """Approximate line count for a function node."""
    if hasattr(node, "end_lineno") and hasattr(node, "lineno"):
        return (node.end_lineno or node.lineno) - node.lineno + 1
    return 0


def _composite_score(cyclo: int, nesting: int, lines: int, params: int) -> float:
    """Weighted composite complexity score."""
    return round(
        cyclo * 1.0
        + nesting * 1.5
        + (lines / 20.0)  # 20 lines = 1 point
        + (max(0, params - 3) * 0.5),  # Penalty starts at 4+ params
        2
    )


def _analyze_file(filepath: Path) -> list[dict[str, Any]]:
    """Analyze all functions/methods in a file."""
    try:
        source = filepath.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(filepath))
    except (SyntaxError, UnicodeDecodeError):
        return []

    results: list[dict[str, Any]] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        # Determine if it's a method (inside a class)
        class_name = None
        for parent in ast.walk(tree):
            if isinstance(parent, ast.ClassDef):
                for child in ast.iter_child_nodes(parent):
                    if child is node:
                        class_name = parent.name
                        break

        name = f"{class_name}.{node.name}" if class_name else node.name
        cyclo = _cyclomatic_complexity(node)
        nesting = _max_nesting_depth(node)
        lines = _line_count(node)
        params = _param_count(node)
        score = _composite_score(cyclo, nesting, lines, params)

        results.append({
            "function": name,
            "file": str(filepath),
            "line": node.lineno,
            "cyclomatic_complexity": cyclo,
            "max_nesting_depth": nesting,
            "line_count": lines,
            "param_count": params,
            "composite_score": score,
        })

    return results


def _collect_py_files(target: Path) -> list[Path]:
    """Collect .py files from a file or directory."""
    if target.is_file():
        return [target] if target.suffix == ".py" else []
    files = []
    for f in sorted(target.rglob("*.py")):
        skip = False
        for parent in f.relative_to(target).parents:
            if parent.name and should_skip_dir(parent.name):
                skip = True
                break
        if not skip:
            files.append(f)
    return files


def run(arguments: dict) -> dict:
    target = Path(arguments["target"])
    if not target.exists():
        return tool_error(FILE_METADATA["tool_name"], arguments, f"Not found: {target}")

    threshold = arguments.get("threshold", 8)
    top_n = arguments.get("top_n", 20)
    include_all = arguments.get("include_all", False)

    try:
        py_files = _collect_py_files(target)
        all_functions: list[dict] = []

        for filepath in py_files:
            all_functions.extend(_analyze_file(filepath))

        # Sort by composite score descending
        all_functions.sort(key=lambda f: f["composite_score"], reverse=True)

        # Filter
        if include_all:
            flagged = all_functions
        else:
            flagged = [f for f in all_functions if f["composite_score"] >= threshold]

        # Trim relative paths if scanning a directory
        if target.is_dir():
            for f in all_functions:
                try:
                    f["file"] = str(Path(f["file"]).relative_to(target))
                except ValueError:
                    pass

        top = flagged[:top_n]

        # Per-file summary
        file_scores: dict[str, list[float]] = {}
        for f in all_functions:
            file_scores.setdefault(f["file"], []).append(f["composite_score"])

        file_summary = []
        for fpath, scores in sorted(file_scores.items(), key=lambda x: max(x[1]), reverse=True):
            file_summary.append({
                "file": fpath,
                "function_count": len(scores),
                "max_score": max(scores),
                "avg_score": round(sum(scores) / len(scores), 2),
                "functions_above_threshold": sum(1 for s in scores if s >= threshold),
            })

        result: dict[str, Any] = {
            "target": str(target),
            "files_scanned": len(py_files),
            "functions_found": len(all_functions),
            "functions_above_threshold": len(flagged),
            "threshold": threshold,
            "top_complex": top,
            "file_summary": file_summary[:top_n],
        }

        return tool_result(FILE_METADATA["tool_name"], arguments, result)

    except Exception as exc:
        return tool_error(FILE_METADATA["tool_name"], arguments, str(exc))


if __name__ == "__main__":
    standard_main(FILE_METADATA, run)
