import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from workflow_generator_mcp import analyze as az  # noqa: E402


@pytest.fixture
def az_module():
    return az


def write_project(tmp_path: Path, files: dict) -> Path:
    """Write {relative_path: content} under tmp_path and return the root."""
    for rel, content in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    return tmp_path
