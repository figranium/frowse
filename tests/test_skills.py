"""Tests for bundled Frowse agent skills."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from frowse.skills import install_skills, list_skills, read_skill


def test_list_and_read_skills():
    items = list_skills()
    names = {s["name"] for s in items}
    assert {"frowse", "frowse-extract", "frowse-auth", "frowse-debug"}.issubset(names)
    for item in items:
        content = read_skill(item["name"])
        assert len(content) < 2500  # Keep skills lean and bloat-free
        assert "frowse" in content


def test_install_skills_and_cli(tmp_path: Path):
    installed = install_skills(dest_dir=str(tmp_path))
    assert len(installed) == 4
    assert (tmp_path / "frowse" / "SKILL.md").is_file()

    frowse_bin = str(Path(sys.executable).parent / "frowse")
    proc = subprocess.run(
        [frowse_bin, "--json", "skills", "list"],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(proc.stdout)["data"]
    assert len(data["skills"]) == 4
