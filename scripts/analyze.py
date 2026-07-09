#!/usr/bin/env python3
"""Compatibility shim — the analyzer lives in workflow_generator_mcp/analyze.py.

Kept so existing integrations keep working unchanged:
    python3 ~/.claude/skills/workflow-generator/scripts/analyze.py <project> <out.html>
"""

import runpy
from pathlib import Path

runpy.run_path(
    str(Path(__file__).resolve().parent.parent / "workflow_generator_mcp" / "analyze.py"),
    run_name="__main__",
)
