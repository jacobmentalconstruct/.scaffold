"""
FILE: import_graph_mapper.py
ROLE: Map the import dependency graph for a Python project.
WHAT IT DOES:
  - AST-scans all .py files under a project root
  - Extracts every import and from-import statement
  - Classifies imports as internal (within the project) or external (stdlib/third-party)
  - Builds a structured dependency graph: which modules depend on which
  - Detects circular import chains
  - Reports per-module import depth, fan-in (who depends on me), fan-out (what I depend on)
  - Zero write risk — purely read-only introspection
HOW TO USE:
  - python src/tools/import_graph_mapper.py metadata
  - python src/tools/import_graph_mapper.py run --input-json '{"project_root": "path/to/project"}'
  - python src/tools/import_graph_mapper.py run --input-json '{"project_root": "...", "src_dir": "src"}'
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
from common import standard_main, tool_result, tool_error, should_skip_dir

FILE_METADATA = {
    "tool_name": "import_graph_mapper",
    "version": "1.0.0",
    "entrypoint": "src/tools/import_graph_mapper.py",
    "category": "analysis",
    "summary": "Map the import dependency graph for a Python project: internal/external classification, circular import detection, fan-in/fan-out metrics.",
    "mcp_name": "import_graph_mapper",
    "input_schema": {
        "type": "object",
        "required": ["project_root"],
        "properties": {
            "project_root": {
                "type": "string",
                "description": "Path to the project root directory."
            },
            "src_dir": {
                "type": "string",
                "default": "",
                "description": "Subdirectory to scan (e.g. 'src'). If empty, scans from project_root."
            },
            "include_external": {
                "type": "boolean",
                "default": False,
                "description": "If true, include external/stdlib imports in the graph."
            },
            "detect_cycles": {
                "type": "boolean",
                "default": True,
                "description": "If true, detect and report circular import chains."
            }
        }
    }
}


def _collect_py_files(root: Path) -> list[Path]:
    """Collect all .py files, skipping ignored directories."""
    files = []
    for item in sorted(root.rglob("*.py")):
        # Check each parent directory
        skip = False
        for parent in item.relative_to(root).parents:
            if parent.name and should_skip_dir(parent.name):
                skip = True
                break
        if not skip:
            files.append(item)
    return files


def _module_name_from_path(path: Path, root: Path) -> str:
    """Convert a file path to a dotted module name."""
    rel = path.relative_to(root)
    parts = list(rel.parts)
    # Remove .py extension from last part
    if parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    # Remove __init__ from the end
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) if parts else ""


def _extract_imports(filepath: Path) -> list[dict]:
    """Extract all imports from a Python file using AST."""
    try:
        source = filepath.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(filepath))
    except (SyntaxError, UnicodeDecodeError):
        return []

    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append({
                    "type": "import",
                    "module": alias.name,
                    "alias": alias.asname,
                    "line": node.lineno,
                })
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            level = node.level  # 0 = absolute, 1+ = relative
            for alias in node.names:
                imports.append({
                    "type": "from",
                    "module": module,
                    "name": alias.name,
                    "alias": alias.asname,
                    "level": level,
                    "line": node.lineno,
                })
    return imports


def _resolve_relative_import(importer_module: str, module: str, level: int) -> str:
    """Resolve a relative import to an absolute module path."""
    if level == 0:
        return module
    parts = importer_module.split(".")
    # Go up 'level' packages
    if level <= len(parts):
        base = ".".join(parts[:-level])
    else:
        base = ""
    if module:
        return f"{base}.{module}" if base else module
    return base


def _classify_import(resolved_module: str, internal_modules: set[str]) -> str:
    """Classify an import as 'internal' or 'external'."""
    # Check if any internal module is a prefix match
    for internal in internal_modules:
        if resolved_module == internal or resolved_module.startswith(internal + "."):
            return "internal"
        if internal.startswith(resolved_module + "."):
            return "internal"
    # Check top-level package
    top = resolved_module.split(".")[0]
    for internal in internal_modules:
        if internal.split(".")[0] == top:
            return "internal"
    return "external"


def _find_cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    """Find all circular import chains using DFS."""
    cycles: list[list[str]] = []
    visited: set[str] = set()
    rec_stack: set[str] = set()
    path: list[str] = []

    def dfs(node: str) -> None:
        visited.add(node)
        rec_stack.add(node)
        path.append(node)

        for neighbor in sorted(graph.get(node, set())):
            if neighbor not in visited:
                dfs(neighbor)
            elif neighbor in rec_stack:
                # Found a cycle — extract it
                idx = path.index(neighbor)
                cycle = path[idx:] + [neighbor]
                # Normalize: start with the lexicographically smallest
                min_idx = cycle[:-1].index(min(cycle[:-1]))
                normalized = cycle[min_idx:-1] + cycle[:min_idx] + [cycle[min_idx]]
                if normalized not in cycles:
                    cycles.append(normalized)

        path.pop()
        rec_stack.discard(node)

    for node in sorted(graph):
        if node not in visited:
            dfs(node)

    return cycles


def run(arguments: dict) -> dict:
    project_root = Path(arguments["project_root"])
    if not project_root.is_dir():
        return tool_error(FILE_METADATA["tool_name"], arguments, f"Not a directory: {project_root}")

    src_dir = arguments.get("src_dir", "")
    scan_root = project_root / src_dir if src_dir else project_root
    if not scan_root.is_dir():
        return tool_error(FILE_METADATA["tool_name"], arguments, f"Not a directory: {scan_root}")

    include_external = arguments.get("include_external", False)
    detect_cycles = arguments.get("detect_cycles", True)

    try:
        py_files = _collect_py_files(scan_root)

        # Build module name set
        internal_modules: set[str] = set()
        file_to_module: dict[str, str] = {}
        for f in py_files:
            mod = _module_name_from_path(f, scan_root)
            if mod:
                internal_modules.add(mod)
                file_to_module[str(f)] = mod

        # Extract and classify imports per module
        modules: dict[str, dict] = {}
        internal_graph: dict[str, set[str]] = {}  # for cycle detection

        for filepath in py_files:
            mod_name = file_to_module.get(str(filepath), "")
            if not mod_name:
                continue

            raw_imports = _extract_imports(filepath)
            internal_deps: list[dict] = []
            external_deps: list[dict] = []

            dep_set: set[str] = set()

            for imp in raw_imports:
                level = imp.get("level", 0)
                raw_module = imp["module"]

                resolved = _resolve_relative_import(mod_name, raw_module, level)
                classification = _classify_import(resolved, internal_modules)

                entry = {
                    "module": resolved,
                    "line": imp["line"],
                }
                if imp["type"] == "from":
                    entry["name"] = imp["name"]
                if level > 0:
                    entry["relative"] = True

                if classification == "internal":
                    internal_deps.append(entry)
                    # For graph, use the top-level resolved module
                    target = resolved.split(".")[0]
                    for im in internal_modules:
                        if resolved == im or resolved.startswith(im + ".") or im.startswith(resolved + "."):
                            target = im
                            break
                    dep_set.add(target)
                else:
                    external_deps.append(entry)

            internal_graph[mod_name] = dep_set - {mod_name}  # no self-loops

            mod_info: dict = {
                "file": str(filepath.relative_to(project_root)),
                "internal_imports": internal_deps,
                "fan_out": len(dep_set - {mod_name}),
            }
            if include_external:
                mod_info["external_imports"] = external_deps

            modules[mod_name] = mod_info

        # Compute fan-in (who depends on me)
        fan_in: dict[str, list[str]] = {m: [] for m in modules}
        for mod, deps in internal_graph.items():
            for dep in deps:
                if dep in fan_in:
                    fan_in[dep].append(mod)

        for mod_name in modules:
            modules[mod_name]["fan_in"] = len(fan_in.get(mod_name, []))
            modules[mod_name]["depended_on_by"] = sorted(fan_in.get(mod_name, []))

        # Detect cycles
        cycles: list[list[str]] = []
        if detect_cycles:
            cycles = _find_cycles(internal_graph)

        # Collect unique external packages
        ext_packages: set[str] = set()
        if include_external:
            for mod_info in modules.values():
                for imp in mod_info.get("external_imports", []):
                    ext_packages.add(imp["module"].split(".")[0])

        # Summary
        result: dict = {
            "project_root": str(project_root),
            "scan_root": str(scan_root),
            "files_scanned": len(py_files),
            "modules_found": len(modules),
            "modules": modules,
        }
        if detect_cycles:
            result["circular_imports"] = cycles
            result["has_circular_imports"] = len(cycles) > 0
        if include_external:
            result["external_packages"] = sorted(ext_packages)

        return tool_result(FILE_METADATA["tool_name"], arguments, result)

    except Exception as exc:
        return tool_error(FILE_METADATA["tool_name"], arguments, str(exc))


if __name__ == "__main__":
    standard_main(FILE_METADATA, run)
