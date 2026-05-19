"""
FILE: tokenizing_patcher.py
ROLE: Whitespace-immune hunk-based patcher for source files.
WHAT IT DOES:
  - Applies search/replace patch hunks using tokenization to ignore indentation differences
  - Supports single-file, multi-target, and multi-file manifest modes
  - Validates patches without writing (dry_run mode)
  - Rebases patch indentation onto target file indentation by default
HOW TO USE:
  - Metadata: python src/tools/tokenizing_patcher.py metadata
  - Run:      python src/tools/tokenizing_patcher.py run --input-json '{"target": "src/app.py", "patch": {"hunks": [...]}}'
INPUT:
  - target: path to the file to patch (single-file mode)
  - targets: list of paths to patch with the same hunks (multi-target mode)
  - patch: inline patch object with "hunks" list (single/multi-target) or "files" list (manifest)
  - patch_file: path to a JSON file containing the patch (alternative to inline patch)
  - root_dir: base directory for resolving manifest files[].path entries
  - output_dir: redirect writes to a separate directory
  - force_indent: use patch indentation exactly instead of rebasing (default: false)
  - dry_run: validate and compute without writing (default: false)
  - backup: create .bak backup when patching in place (default: false)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common import standard_main, tool_result

FILE_METADATA = {
    "tool_name": "tokenizing_patcher",
    "version": "4.3.0",
    "entrypoint": "src/tools/tokenizing_patcher.py",
    "category": "editing",
    "summary": "Apply whitespace-immune hunk-based patches to source files.",
    "mcp_name": "tokenizing_patcher",
    "notes": (
        "Complements structured_patch. Uses tokenization to match search blocks even when "
        "indentation differs. Supports single-file, multi-target, and multi-file manifest modes."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "description": "Path to a single file to patch.",
            },
            "targets": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of file paths to patch with the same hunks.",
            },
            "patch": {
                "type": "object",
                "description": "Inline patch object: {hunks: [...]} for single/multi-target, or {files: [...]} for manifest mode.",
            },
            "patch_file": {
                "type": "string",
                "description": "Path to a JSON file containing the patch (alternative to inline patch).",
            },
            "root_dir": {
                "type": "string",
                "description": "Base directory for resolving manifest files[].path entries.",
            },
            "output_dir": {
                "type": "string",
                "description": "Redirect patched output files to this directory.",
            },
            "force_indent": {
                "type": "boolean",
                "description": "Use patch indentation exactly instead of rebasing to target indentation.",
                "default": False,
            },
            "dry_run": {
                "type": "boolean",
                "description": "Validate and compute the patch without writing files.",
                "default": False,
            },
            "backup": {
                "type": "boolean",
                "description": "Create a .bak backup when patching files in place.",
                "default": False,
            },
            "validate_only": {
                "type": "boolean",
                "description": "Only validate that patches apply cleanly, do not write.",
                "default": False,
            },
        },
        "additionalProperties": False,
    },
}


# ── Patching engine ──────────────────────────────────────────

class PatchError(Exception):
    pass


class StructuredLine:
    __slots__ = ["indent", "content", "trailing", "original"]

    def __init__(self, line: str):
        self.original = line
        m = re.match(r"(^[ \t]*)(.*?)([ \t]*$)", line, re.DOTALL)
        if m:
            self.indent, self.content, self.trailing = m.group(1), m.group(2), m.group(3)
        else:
            self.indent, self.content, self.trailing = "", line, ""

    def reconstruct(self) -> str:
        return f"{self.indent}{self.content}{self.trailing}"


def tokenize_text(text: str):
    if "\r\n" in text:
        newline = "\r\n"
    elif "\n" in text:
        newline = "\n"
    else:
        newline = "\n"
    raw_lines = text.splitlines()
    lines = [StructuredLine(l) for l in raw_lines]
    return lines, newline


def locate_hunk(file_lines, search_lines, floating: bool = False):
    if not search_lines:
        return []
    matches = []
    max_start = len(file_lines) - len(search_lines)
    for start in range(max_start + 1):
        ok = True
        for i, s in enumerate(search_lines):
            f = file_lines[start + i]
            if floating:
                if f.content != s.content:
                    ok = False
                    break
            else:
                if f.reconstruct() != s.reconstruct():
                    ok = False
                    break
        if ok:
            matches.append(start)
    return matches


def _common_indent_prefix(lines):
    prefix = None
    for line in lines:
        if not line.content:
            continue
        indent = line.indent
        if prefix is None:
            prefix = indent
            continue
        i = 0
        max_i = min(len(prefix), len(indent))
        while i < max_i and prefix[i] == indent[i]:
            i += 1
        prefix = prefix[:i]
    return prefix or ""


def _strip_indent_prefix(indent: str, prefix: str) -> str:
    if prefix and indent.startswith(prefix):
        return indent[len(prefix):]
    return indent


def apply_patch_text(original_text: str, patch_obj: dict, global_force_indent: bool = False) -> str:
    if not isinstance(patch_obj, dict) or "hunks" not in patch_obj:
        raise PatchError("Patch must be a dict with a 'hunks' list.")

    hunks = patch_obj.get("hunks", [])
    if not isinstance(hunks, list):
        raise PatchError("'hunks' must be a list.")

    file_lines, newline = tokenize_text(original_text)
    applications = []

    for idx, hunk in enumerate(hunks, start=1):
        search_block = hunk.get("search_block")
        replace_block = hunk.get("replace_block")
        use_patch_indent = hunk.get("use_patch_indent", global_force_indent)

        if search_block is None or replace_block is None:
            raise PatchError(f"Hunk {idx}: Missing 'search_block' or 'replace_block'.")

        s_lines = [StructuredLine(l) for l in search_block.splitlines()]
        r_lines = [StructuredLine(l) for l in replace_block.splitlines()]

        matches = locate_hunk(file_lines, s_lines, floating=False)
        if not matches:
            matches = locate_hunk(file_lines, s_lines, floating=True)

        if not matches:
            raise PatchError(f"Hunk {idx}: Search block not found.")
        if len(matches) > 1:
            raise PatchError(f"Hunk {idx}: Ambiguous match ({len(matches)} found).")

        start = matches[0]
        applications.append({
            "start": start,
            "end": start + len(s_lines),
            "replace_lines": r_lines,
            "use_patch_indent": bool(use_patch_indent),
            "id": idx,
        })

    applications.sort(key=lambda a: a["start"])
    for i in range(len(applications) - 1):
        if applications[i]["end"] > applications[i + 1]["start"]:
            raise PatchError(
                f"Hunks {applications[i]['id']} and {applications[i + 1]['id']} overlap in the target file."
            )

    for app in reversed(applications):
        start = app["start"]
        end = app["end"]
        r_lines = app["replace_lines"]
        use_patch_indent = app["use_patch_indent"]

        matched_indent = file_lines[start].indent if start < len(file_lines) else ""
        patch_base_indent = _common_indent_prefix(r_lines)
        adjusted_lines = []
        for r in r_lines:
            line = StructuredLine(r.reconstruct())
            if not use_patch_indent:
                relative_indent = _strip_indent_prefix(line.indent, patch_base_indent)
                if line.content:
                    line.indent = matched_indent + relative_indent
                else:
                    line.indent = ""
            adjusted_lines.append(line)

        file_lines[start:end] = adjusted_lines

    result = newline.join(line.reconstruct() for line in file_lines)
    if original_text.endswith(("\n", "\r\n")):
        result += newline
    return result


# ── File I/O helpers ─────────────────────────────────────────

def _read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PatchError(f"Unable to read target file '{path}': {exc}") from exc


def _write_text_file(path: Path, text: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="")
    except OSError as exc:
        raise PatchError(f"Unable to write output file '{path}': {exc}") from exc


def _build_summary(original_text: str, patched_text: str, patch_obj: dict) -> dict:
    return {
        "changed": original_text != patched_text,
        "original_line_count": len(original_text.splitlines()),
        "patched_line_count": len(patched_text.splitlines()),
        "hunk_count": len(patch_obj.get("hunks", [])),
    }


def _is_manifest_patch(obj: dict) -> bool:
    return isinstance(obj, dict) and isinstance(obj.get("files"), list)


def _is_single_patch(obj: dict) -> bool:
    return isinstance(obj, dict) and isinstance(obj.get("hunks"), list)


def _resolve_output_path(target_path: Path, output_dir: Path | None) -> Path:
    if output_dir:
        return output_dir / target_path
    return target_path


# ── Patch operations ─────────────────────────────────────────

def patch_file(target_path: Path, patch_obj: dict, output_dir: Path | None = None,
               force_indent: bool = False, dry_run: bool = False, create_backup: bool = False) -> dict:
    if not _is_single_patch(patch_obj):
        raise PatchError("Single-file patching requires a patch object with a 'hunks' list.")

    original_text = _read_text_file(target_path)
    patched_text = apply_patch_text(original_text, patch_obj, global_force_indent=force_indent)
    summary = _build_summary(original_text, patched_text, patch_obj)
    final_output = _resolve_output_path(target_path, output_dir)

    if dry_run:
        return {"status": "dry-run", "target": str(target_path), "output": str(final_output), **summary}

    if create_backup and final_output == target_path:
        backup_path = target_path.with_suffix(target_path.suffix + ".bak")
        _write_text_file(backup_path, original_text)

    _write_text_file(final_output, patched_text)
    return {"status": "applied", "target": str(target_path), "output": str(final_output), **summary}


def validate_patch(target_path: Path, patch_obj: dict, force_indent: bool = False) -> dict:
    if not _is_single_patch(patch_obj):
        raise PatchError("Single-file validation requires a patch object with a 'hunks' list.")
    original_text = _read_text_file(target_path)
    patched_text = apply_patch_text(original_text, patch_obj, global_force_indent=force_indent)
    return {"status": "valid", "target": str(target_path), **_build_summary(original_text, patched_text, patch_obj)}


def patch_many_files(targets, patch_obj: dict, output_dir: Path | None = None, force_indent: bool = False,
                     dry_run: bool = False, create_backup: bool = False) -> dict:
    if not _is_single_patch(patch_obj):
        raise PatchError("Multi-target mode requires a single-file patch object with a 'hunks' list.")
    results = []
    changed_count = 0
    for target in targets:
        res = patch_file(target, patch_obj, output_dir=output_dir, force_indent=force_indent,
                         dry_run=dry_run, create_backup=create_backup)
        changed_count += int(bool(res.get("changed")))
        results.append(res)
    return {
        "status": "dry-run" if dry_run else "applied",
        "mode": "multi-target",
        "target_count": len(targets),
        "changed_count": changed_count,
        "results": results,
    }


def patch_manifest(manifest: dict, root_dir: Path | None = None, output_dir: Path | None = None,
                   force_indent: bool = False, dry_run: bool = False, create_backup: bool = False) -> dict:
    if not _is_manifest_patch(manifest):
        raise PatchError("Manifest mode requires a patch object with a 'files' list.")
    root = root_dir or Path(".")
    manifest_default = bool(manifest.get("default_use_patch_indent", False))
    results = []
    changed_count = 0
    for idx, entry in enumerate(manifest.get("files", []), start=1):
        rel_path = entry.get("path")
        if not rel_path:
            raise PatchError(f"Manifest entry {idx} is missing 'path'.")
        target = root / Path(rel_path)
        file_default = entry.get("default_use_patch_indent", manifest_default)
        patch_obj = {
            "hunks": [
                {
                    **hunk,
                    **({} if "use_patch_indent" in hunk else {"use_patch_indent": file_default}),
                }
                for hunk in entry.get("hunks", [])
            ]
        }
        res = patch_file(target, patch_obj, output_dir=output_dir, force_indent=force_indent,
                         dry_run=dry_run, create_backup=create_backup)
        changed_count += int(bool(res.get("changed")))
        results.append(res)
    return {
        "status": "dry-run" if dry_run else "applied",
        "mode": "manifest",
        "target_count": len(results),
        "changed_count": changed_count,
        "results": results,
    }


# ── Tool contract entry point ────────────────────────────────

def run(arguments: dict) -> dict:
    target = arguments.get("target")
    targets = arguments.get("targets")
    patch = arguments.get("patch")
    patch_file_path = arguments.get("patch_file")
    root_dir = arguments.get("root_dir")
    output_dir = arguments.get("output_dir")
    force_indent = bool(arguments.get("force_indent", False))
    dry_run = bool(arguments.get("dry_run", False))
    backup = bool(arguments.get("backup", False))
    validate_only = bool(arguments.get("validate_only", False))

    # Resolve patch object
    if patch and patch_file_path:
        return tool_result(FILE_METADATA["tool_name"], arguments,
                           {"message": "Use either 'patch' or 'patch_file', not both."}, status="error")
    if patch_file_path:
        pf = Path(patch_file_path)
        if not pf.exists():
            return tool_result(FILE_METADATA["tool_name"], arguments,
                               {"message": f"Patch file not found: {pf}"}, status="error")
        try:
            patch = json.loads(pf.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            return tool_result(FILE_METADATA["tool_name"], arguments,
                               {"message": f"Failed to load patch file: {exc}"}, status="error")
    if not patch:
        return tool_result(FILE_METADATA["tool_name"], arguments,
                           {"message": "Either 'patch' or 'patch_file' is required."}, status="error")

    out_dir = Path(output_dir) if output_dir else None

    try:
        if _is_manifest_patch(patch):
            # Manifest mode
            rd = Path(root_dir) if root_dir else None
            if validate_only or dry_run:
                result = patch_manifest(patch, root_dir=rd, output_dir=out_dir,
                                        force_indent=force_indent, dry_run=True, create_backup=False)
            else:
                result = patch_manifest(patch, root_dir=rd, output_dir=out_dir,
                                        force_indent=force_indent, dry_run=False, create_backup=backup)
        elif targets:
            # Multi-target mode
            target_paths = [Path(t) for t in targets]
            if validate_only:
                results = []
                for tp in target_paths:
                    results.append(validate_patch(tp, patch, force_indent=force_indent))
                result = {"status": "valid", "mode": "multi-target",
                          "target_count": len(results), "results": results}
            else:
                result = patch_many_files(target_paths, patch, output_dir=out_dir,
                                          force_indent=force_indent, dry_run=dry_run, create_backup=backup)
        elif target:
            # Single-file mode
            tp = Path(target)
            if not tp.exists():
                return tool_result(FILE_METADATA["tool_name"], arguments,
                                   {"message": f"Target file not found: {tp}"}, status="error")
            if validate_only:
                result = validate_patch(tp, patch, force_indent=force_indent)
            else:
                result = patch_file(tp, patch, output_dir=out_dir,
                                    force_indent=force_indent, dry_run=dry_run, create_backup=backup)
        else:
            return tool_result(FILE_METADATA["tool_name"], arguments,
                               {"message": "Provide 'target', 'targets', or a manifest patch with 'files'."}, status="error")
    except PatchError as exc:
        return tool_result(FILE_METADATA["tool_name"], arguments,
                           {"message": str(exc)}, status="error")

    return tool_result(FILE_METADATA["tool_name"], arguments, result)


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
