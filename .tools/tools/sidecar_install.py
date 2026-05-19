from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common import standard_main, tool_result
from lib.sidecar_release import install_sidecar, release_payload_inventory


FILE_METADATA = {
    "tool_name": "sidecar_install",
    "version": "1.0.0",
    "entrypoint": "src/tools/sidecar_install.py",
    "category": "install",
    "summary": "Install the full sidecar .dev-tools payload into a target project root using the release payload manifest.",
    "mcp_name": "sidecar_install",
    "input_schema": {
        "type": "object",
        "properties": {
            "target_project_root": {"type": "string"},
            "source_toolbox_root": {"type": "string"},
            "overwrite": {"type": "boolean", "default": False},
            "preview": {"type": "boolean", "default": False}
        },
        "required": ["target_project_root"],
        "additionalProperties": False
    }
}


def run(arguments: dict) -> dict:
    result = install_sidecar(
        arguments["target_project_root"],
        source_toolbox_root=arguments.get("source_toolbox_root"),
        overwrite=arguments.get("overwrite", False),
        preview=arguments.get("preview", False),
    )
    result["payload_inventory"] = release_payload_inventory(arguments.get("source_toolbox_root"))
    return tool_result(FILE_METADATA["tool_name"], arguments, result)


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
