"""
FILE: test_scaffold_generator.py
ROLE: Generate test file skeletons from Python source files.
WHAT IT DOES:
  - AST-scans a .py file and extracts public functions and classes
  - Generates a test file with test_ stubs for each public function/method
  - Includes proper imports, class-based test organization, and fixture hints
  - Optionally writes the test file or returns it inline
  - Respects existing test files (will not overwrite without force flag)
HOW TO USE:
  - python src/tools/test_scaffold_generator.py metadata
  - python src/tools/test_scaffold_generator.py run --input-json '{"source_file": "src/core/engine.py"}'
  - python src/tools/test_scaffold_generator.py run --input-json '{"source_file": "...", "output_file": "tests/test_engine.py"}'
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).resolve().parents[1]))
from common import standard_main, tool_result, tool_error

FILE_METADATA = {
    "tool_name": "test_scaffold_generator",
    "version": "1.0.0",
    "entrypoint": "src/tools/test_scaffold_generator.py",
    "category": "scaffold",
    "summary": "Generate test file skeletons with test_ stubs for each public function and method in a Python source file.",
    "mcp_name": "test_scaffold_generator",
    "input_schema": {
        "type": "object",
        "required": ["source_file"],
        "properties": {
            "source_file": {
                "type": "string",
                "description": "Path to the Python source file to generate tests for."
            },
            "output_file": {
                "type": "string",
                "description": "Path to write the generated test file. If omitted, returns content inline."
            },
            "force": {
                "type": "boolean",
                "default": False,
                "description": "If true, overwrite existing test file."
            },
            "framework": {
                "type": "string",
                "enum": ["pytest", "unittest"],
                "default": "pytest",
                "description": "Test framework style to generate."
            },
            "include_private": {
                "type": "boolean",
                "default": False,
                "description": "If true, also generate stubs for private (_prefixed) functions."
            }
        }
    }
}


def _extract_public_api(filepath: Path, include_private: bool) -> dict[str, Any]:
    """Extract public functions and classes with their methods."""
    source = filepath.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(source, filename=str(filepath))

    functions: list[dict] = []
    classes: list[dict] = []

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not include_private and node.name.startswith("_"):
                continue
            params = []
            for arg in node.args.args:
                if arg.arg not in ("self", "cls"):
                    params.append(arg.arg)
            functions.append({
                "name": node.name,
                "params": params,
                "is_async": isinstance(node, ast.AsyncFunctionDef),
                "line": node.lineno,
                "docstring": ast.get_docstring(node) or "",
            })

        elif isinstance(node, ast.ClassDef):
            if not include_private and node.name.startswith("_"):
                continue
            methods = []
            for item in ast.iter_child_nodes(node):
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if item.name.startswith("__") and item.name.endswith("__"):
                        continue  # Skip dunders
                    if not include_private and item.name.startswith("_"):
                        continue
                    params = []
                    for arg in item.args.args:
                        if arg.arg not in ("self", "cls"):
                            params.append(arg.arg)
                    methods.append({
                        "name": item.name,
                        "params": params,
                        "is_async": isinstance(item, ast.AsyncFunctionDef),
                        "line": item.lineno,
                    })
            classes.append({
                "name": node.name,
                "methods": methods,
                "line": node.lineno,
            })

    return {"functions": functions, "classes": classes}


def _generate_pytest(source_file: Path, api: dict) -> str:
    """Generate pytest-style test scaffold."""
    module_name = source_file.stem
    lines = [
        f'"""Tests for {module_name}."""',
        "",
        "import pytest",
        f"# from <package> import {module_name}  # TODO: adjust import path",
        "",
        "",
    ]

    # Standalone functions
    for func in api["functions"]:
        if func["is_async"]:
            lines.append("@pytest.mark.asyncio")
            lines.append(f"async def test_{func['name']}():")
        else:
            lines.append(f"def test_{func['name']}():")

        if func["docstring"]:
            hint = func["docstring"].split("\n")[0][:80]
            lines.append(f'    """Test {func["name"]}: {hint}"""')

        if func["params"]:
            lines.append(f"    # Params: {', '.join(func['params'])}")

        lines.append(f"    # TODO: test {func['name']}")
        lines.append("    assert False, 'Not implemented'")
        lines.append("")
        lines.append("")

    # Classes
    for cls in api["classes"]:
        lines.append(f"class Test{cls['name']}:")
        lines.append(f'    """Tests for {cls["name"]}."""')
        lines.append("")

        if not cls["methods"]:
            lines.append("    def test_instantiation(self):")
            lines.append(f"        # TODO: test {cls['name']} can be created")
            lines.append("        assert False, 'Not implemented'")
            lines.append("")
        else:
            for method in cls["methods"]:
                if method["is_async"]:
                    lines.append("    @pytest.mark.asyncio")
                    lines.append(f"    async def test_{method['name']}(self):")
                else:
                    lines.append(f"    def test_{method['name']}(self):")

                if method["params"]:
                    lines.append(f"        # Params: {', '.join(method['params'])}")

                lines.append(f"        # TODO: test {cls['name']}.{method['name']}")
                lines.append("        assert False, 'Not implemented'")
                lines.append("")

        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _generate_unittest(source_file: Path, api: dict) -> str:
    """Generate unittest-style test scaffold."""
    module_name = source_file.stem
    lines = [
        f'"""Tests for {module_name}."""',
        "",
        "import unittest",
        f"# from <package> import {module_name}  # TODO: adjust import path",
        "",
        "",
    ]

    # Group everything into a test class
    class_name = f"Test{module_name.title().replace('_', '')}"
    lines.append(f"class {class_name}(unittest.TestCase):")
    lines.append(f'    """Tests for {module_name}."""')
    lines.append("")

    # Standalone functions
    for func in api["functions"]:
        lines.append(f"    def test_{func['name']}(self):")
        if func["params"]:
            lines.append(f"        # Params: {', '.join(func['params'])}")
        lines.append(f"        # TODO: test {func['name']}")
        lines.append("        self.fail('Not implemented')")
        lines.append("")

    # Class methods
    for cls in api["classes"]:
        lines.append(f"    # --- {cls['name']} ---")
        lines.append("")
        for method in cls["methods"]:
            lines.append(f"    def test_{cls['name'].lower()}_{method['name']}(self):")
            if method["params"]:
                lines.append(f"        # Params: {', '.join(method['params'])}")
            lines.append(f"        # TODO: test {cls['name']}.{method['name']}")
            lines.append("        self.fail('Not implemented')")
            lines.append("")

    lines.append("")
    lines.append("if __name__ == '__main__':")
    lines.append("    unittest.main()")
    lines.append("")

    return "\n".join(lines)


def run(arguments: dict) -> dict:
    source_file = Path(arguments["source_file"])
    if not source_file.exists():
        return tool_error(FILE_METADATA["tool_name"], arguments, f"File not found: {source_file}")
    if source_file.suffix != ".py":
        return tool_error(FILE_METADATA["tool_name"], arguments, f"Not a Python file: {source_file}")

    output_file = arguments.get("output_file")
    force = arguments.get("force", False)
    framework = arguments.get("framework", "pytest")
    include_private = arguments.get("include_private", False)

    try:
        api = _extract_public_api(source_file, include_private)

        total_stubs = len(api["functions"])
        for cls in api["classes"]:
            total_stubs += max(1, len(cls["methods"]))

        if total_stubs == 0:
            return tool_result(FILE_METADATA["tool_name"], arguments, {
                "message": "No public functions or classes found to test.",
                "source_file": str(source_file),
            })

        # Generate
        if framework == "unittest":
            content = _generate_unittest(source_file, api)
        else:
            content = _generate_pytest(source_file, api)

        result: dict[str, Any] = {
            "source_file": str(source_file),
            "framework": framework,
            "functions": len(api["functions"]),
            "classes": len(api["classes"]),
            "test_stubs": total_stubs,
        }

        # Write or return inline
        if output_file:
            out_path = Path(output_file)
            if out_path.exists() and not force:
                return tool_error(
                    FILE_METADATA["tool_name"], arguments,
                    f"Test file already exists: {out_path}. Use force=true to overwrite."
                )
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(content, encoding="utf-8")
            result["output_file"] = str(out_path)
            result["written"] = True
        else:
            result["content"] = content
            result["written"] = False

        return tool_result(FILE_METADATA["tool_name"], arguments, result)

    except Exception as exc:
        return tool_error(FILE_METADATA["tool_name"], arguments, str(exc))


if __name__ == "__main__":
    standard_main(FILE_METADATA, run)
