"""Bundled agent skills manager for Frowse."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

_TARGET_DIRS = {
    "agents": ".agents/skills",
    "claude": ".claude/skills",
    "codex": ".codex/skills",
    "cursor": ".cursor/skills",
}


def get_skills_dir() -> Path:
    """Locate the bundled skills directory."""
    repo_skills = Path(__file__).resolve().parent.parent / "skills"
    if repo_skills.is_dir():
        return repo_skills
    pkg_skills = Path(__file__).resolve().parent / "skills"
    if pkg_skills.is_dir():
        return pkg_skills
    raise FileNotFoundError("Bundled skills directory not found")


def _parse_frontmatter(text: str) -> dict[str, str]:
    meta: dict[str, str] = {}
    if not text.startswith("---"):
        return meta
    parts = text.split("---", 2)
    if len(parts) < 3:
        return meta
    for line in parts[1].splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta


def list_skills() -> list[dict[str, str]]:
    skills_dir = get_skills_dir()
    items: list[dict[str, str]] = []
    for entry in sorted(skills_dir.iterdir()):
        skill_md = entry / "SKILL.md"
        if entry.is_dir() and skill_md.is_file():
            meta = _parse_frontmatter(skill_md.read_text(encoding="utf-8"))
            items.append(
                {
                    "name": meta.get("name", entry.name),
                    "description": meta.get("description", ""),
                    "path": str(skill_md),
                }
            )
    return items


def read_skill(name: str) -> str:
    skills_dir = get_skills_dir()
    skill_md = skills_dir / name / "SKILL.md"
    if not skill_md.is_file():
        available = ", ".join(s["name"] for s in list_skills())
        raise ValueError(f"Unknown skill {name!r}. Available: {available}")
    return skill_md.read_text(encoding="utf-8")


def install_skills(
    target: str = "agents",
    global_install: bool = False,
    names: list[str] | None = None,
    dest_dir: str | None = None,
) -> list[dict[str, Any]]:
    skills_dir = get_skills_dir()
    if dest_dir:
        base = Path(dest_dir)
    else:
        rel = _TARGET_DIRS.get(target)
        if not rel:
            raise ValueError(f"Unknown target {target!r}. Choose from: {', '.join(_TARGET_DIRS)}")
        root = Path(os.path.expanduser("~")) if global_install else Path.cwd()
        base = root / rel

    selected = names or [s["name"] for s in list_skills()]
    installed: list[dict[str, Any]] = []
    for name in selected:
        src = skills_dir / name
        if not (src / "SKILL.md").is_file():
            raise ValueError(f"Unknown skill: {name}")
        dst = base / name
        dst.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src / "SKILL.md", dst / "SKILL.md")
        installed.append({"name": name, "path": str(dst / "SKILL.md")})
    return installed
