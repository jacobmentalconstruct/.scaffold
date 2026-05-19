"""
FILE: tkinter_widget_tree.py
ROLE: Map the Tkinter widget hierarchy from a Python source file.
WHAT IT DOES:
  - AST-scans a .py file for Tkinter widget instantiations
  - Maps parent-child widget nesting from constructor arguments
  - Identifies geometry manager calls (pack/grid/place) and their parameters
  - Detects variable bindings (StringVar, IntVar, etc.)
  - Detects event bindings (.bind, .configure, command= callbacks)
  - Outputs a structured widget tree for agent orientation before UI edits
  - Zero write risk — purely read-only introspection
HOW TO USE:
  - python src/tools/tkinter_widget_tree.py metadata
  - python src/tools/tkinter_widget_tree.py run --input-json '{"file_path": "path/to/ui_file.py"}'
  - python src/tools/tkinter_widget_tree.py run --input-json '{"file_path": "...", "include_geometry": true}'
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
from common import standard_main, tool_result, tool_error

FILE_METADATA = {
    "tool_name": "tkinter_widget_tree",
    "version": "1.0.0",
    "entrypoint": "src/tools/tkinter_widget_tree.py",
    "category": "analysis",
    "summary": "Map the Tkinter widget hierarchy from a Python source file: widgets, parent-child nesting, geometry managers, variable bindings, and event bindings.",
    "mcp_name": "tkinter_widget_tree",
    "input_schema": {
        "type": "object",
        "required": ["file_path"],
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the Python file containing Tkinter UI code."
            },
            "include_geometry": {
                "type": "boolean",
                "default": True,
                "description": "If true, include geometry manager calls (pack/grid/place) and their parameters."
            },
            "include_bindings": {
                "type": "boolean",
                "default": True,
                "description": "If true, include event bindings and command callbacks."
            }
        }
    }
}

# Known Tkinter widget classes
WIDGET_CLASSES = {
    # tkinter core
    "Tk", "Toplevel", "Frame", "LabelFrame", "PanedWindow",
    "Label", "Button", "Entry", "Text", "Canvas",
    "Listbox", "Scrollbar", "Scale", "Spinbox",
    "Checkbutton", "Radiobutton", "Menubutton", "OptionMenu",
    "Menu", "Message",
    # ttk widgets
    "Combobox", "Notebook", "Treeview", "Progressbar", "Separator",
    "Sizegrip", "LabeledScale", "Panedwindow",
}

# Also match with tk./ttk. prefix patterns
WIDGET_PREFIXES = {"tk", "ttk", "tkinter", "tkinter.ttk"}

# Tkinter variable types
VAR_CLASSES = {"StringVar", "IntVar", "DoubleVar", "BooleanVar", "Variable"}

# Geometry manager methods
GEOMETRY_METHODS = {"pack", "grid", "place", "pack_forget", "grid_forget", "place_forget"}

# Event binding methods
BIND_METHODS = {"bind", "bind_all", "bind_class"}


def _is_widget_call(node: ast.Call) -> str | None:
    """Check if a Call node is a Tkinter widget instantiation. Return class name or None."""
    func = node.func

    # Simple name: Button(parent, ...)
    if isinstance(func, ast.Name) and func.id in WIDGET_CLASSES:
        return func.id

    # Attribute access: tk.Button(parent, ...) or ttk.Treeview(parent, ...)
    if isinstance(func, ast.Attribute) and func.attr in WIDGET_CLASSES:
        if isinstance(func.value, ast.Name) and func.value.id in WIDGET_PREFIXES:
            return f"{func.value.id}.{func.attr}"
        return func.attr

    return None


def _is_var_call(node: ast.Call) -> str | None:
    """Check if a Call node is a Tkinter variable instantiation."""
    func = node.func
    if isinstance(func, ast.Name) and func.id in VAR_CLASSES:
        return func.id
    if isinstance(func, ast.Attribute) and func.attr in VAR_CLASSES:
        return func.attr
    return None


def _get_assign_name(node: ast.AST) -> str | None:
    """Get the variable name from an assignment target."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parts = []
        cur = node
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            parts.append(cur.id)
        return ".".join(reversed(parts))
    return None


def _get_parent_arg(node: ast.Call) -> str | None:
    """Extract the parent widget name from a constructor's first positional arg."""
    if node.args:
        first = node.args[0]
        return _get_assign_name(first)
    # Check for 'master' or 'parent' keyword
    for kw in node.keywords:
        if kw.arg in ("master", "parent"):
            return _get_assign_name(kw.value)
    return None


def _get_keyword_value(node: ast.keyword) -> str:
    """Best-effort string representation of a keyword argument value."""
    val = node.value
    if isinstance(val, ast.Constant):
        return repr(val.value)
    if isinstance(val, ast.Name):
        return val.id
    if isinstance(val, ast.Attribute):
        name = _get_assign_name(val)
        return name if name else "<attr>"
    if isinstance(val, ast.Call):
        func_name = _get_assign_name(val.func) if hasattr(val, 'func') else None
        return f"{func_name}(...)" if func_name else "<call>"
    return "<expr>"


def _extract_keywords(node: ast.Call) -> dict[str, str]:
    """Extract keyword arguments as a dict of name -> string repr."""
    result = {}
    for kw in node.keywords:
        if kw.arg:
            result[kw.arg] = _get_keyword_value(kw)
    return result


def _scan_file(filepath: Path, include_geometry: bool, include_bindings: bool) -> dict:
    """Scan a Python file and extract the widget tree."""
    source = filepath.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(source, filename=str(filepath))

    widgets: list[dict] = []
    variables: list[dict] = []
    geometry_calls: list[dict] = []
    event_bindings: list[dict] = []

    # Walk the AST looking for assignments and method calls
    for node in ast.walk(tree):

        # Widget instantiation: self.btn = tk.Button(parent, text="Click")
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            if isinstance(node, ast.Assign):
                targets = node.targets
                value = node.value
            else:
                targets = [node.target] if node.target else []
                value = node.value

            if not isinstance(value, ast.Call):
                continue

            for target in targets:
                var_name = _get_assign_name(target)
                if not var_name:
                    continue

                # Check for widget
                widget_class = _is_widget_call(value)
                if widget_class:
                    parent = _get_parent_arg(value)
                    config = _extract_keywords(value)
                    # Remove parent from config if it's a positional
                    widget_info: dict = {
                        "name": var_name,
                        "class": widget_class,
                        "parent": parent,
                        "line": node.lineno,
                    }
                    # Extract meaningful config keys
                    for key in ("text", "textvariable", "variable", "command",
                                "width", "height", "columns", "show",
                                "orient", "selectmode", "wrap", "state"):
                        if key in config:
                            widget_info.setdefault("config", {})[key] = config[key]
                    widgets.append(widget_info)
                    continue

                # Check for variable
                var_class = _is_var_call(value)
                if var_class:
                    variables.append({
                        "name": var_name,
                        "class": var_class,
                        "line": node.lineno,
                    })

        # Geometry and binding calls: self.btn.pack(side="left")
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
            if isinstance(call.func, ast.Attribute):
                method = call.func.attr
                obj_name = _get_assign_name(call.func.value)

                if include_geometry and method in GEOMETRY_METHODS:
                    geo_info: dict = {
                        "widget": obj_name,
                        "method": method,
                        "line": node.lineno,
                    }
                    params = _extract_keywords(call)
                    if params:
                        geo_info["params"] = params
                    geometry_calls.append(geo_info)

                if include_bindings and method in BIND_METHODS:
                    bind_info: dict = {
                        "widget": obj_name,
                        "method": method,
                        "line": node.lineno,
                    }
                    if call.args:
                        if isinstance(call.args[0], ast.Constant):
                            bind_info["event"] = call.args[0].value
                        if len(call.args) > 1:
                            handler = _get_assign_name(call.args[1])
                            if handler:
                                bind_info["handler"] = handler
                    event_bindings.append(bind_info)

                # command= in .configure() calls
                if include_bindings and method == "configure":
                    config_kw = _extract_keywords(call)
                    if "command" in config_kw:
                        event_bindings.append({
                            "widget": obj_name,
                            "method": "configure",
                            "config_key": "command",
                            "handler": config_kw["command"],
                            "line": node.lineno,
                        })

    # Build parent-child tree structure
    widget_by_name: dict[str, dict] = {w["name"]: w for w in widgets}
    children_map: dict[str, list[str]] = {}
    roots: list[str] = []

    for w in widgets:
        parent = w.get("parent")
        if parent and parent in widget_by_name:
            children_map.setdefault(parent, []).append(w["name"])
        else:
            roots.append(w["name"])

    # Attach children info
    for w in widgets:
        kids = children_map.get(w["name"], [])
        if kids:
            w["children"] = kids

    result: dict = {
        "file": str(filepath),
        "widget_count": len(widgets),
        "widgets": widgets,
        "root_widgets": roots,
        "variables": variables,
    }
    if include_geometry:
        result["geometry_calls"] = geometry_calls
    if include_bindings:
        result["event_bindings"] = event_bindings

    return result


def run(arguments: dict) -> dict:
    filepath = Path(arguments["file_path"])
    if not filepath.exists():
        return tool_error(FILE_METADATA["tool_name"], arguments, f"File not found: {filepath}")
    if not filepath.suffix == ".py":
        return tool_error(FILE_METADATA["tool_name"], arguments, f"Not a Python file: {filepath}")

    include_geometry = arguments.get("include_geometry", True)
    include_bindings = arguments.get("include_bindings", True)

    try:
        result = _scan_file(filepath, include_geometry, include_bindings)
        return tool_result(FILE_METADATA["tool_name"], arguments, result)
    except Exception as exc:
        return tool_error(FILE_METADATA["tool_name"], arguments, str(exc))


if __name__ == "__main__":
    standard_main(FILE_METADATA, run)
