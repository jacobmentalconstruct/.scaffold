from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common import standard_main, tool_result
from lib.sidecar_release import check_onboarding_site


FILE_METADATA = {
    "tool_name": "onboarding_site_check",
    "version": "1.0.0",
    "entrypoint": "src/tools/onboarding_site_check.py",
    "category": "testing",
    "summary": "Verify that the offline onboarding microsite and its supporting launchers, assets, and doctrine links remain intact.",
    "mcp_name": "onboarding_site_check",
    "input_schema": {
        "type": "object",
        "properties": {
            "toolbox_root": {"type": "string"}
        },
        "additionalProperties": False
    }
}


def run(arguments: dict) -> dict:
    result = check_onboarding_site(arguments.get("toolbox_root"))
    return tool_result(FILE_METADATA["tool_name"], arguments, result)


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
