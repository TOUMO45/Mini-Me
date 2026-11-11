#!/usr/bin/env python3
"""Build the distributable skill zip: dist/mini-me-v<version>.zip

The zip holds one top-level folder, mini-me/, ready to drop into ~/.claude/skills/ or upload as a skill.
Only files a user needs are included: tests, caches, and any profile are left out.
Run: python3 tools/package_skill.py
"""
from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "mini-me"
DIST = ROOT / "dist"

INCLUDE = [
    "SKILL.md",
    "INSTALL.md",
    "references/spec.md",
    "references/profile-format.md",
    "references/integration.md",
    "scripts/mini_me.py",
    "scripts/mcp_server.py",
    "templates/profile.template.md",
]


def version() -> str:
    m = re.search(r'__version__ = "([^"]+)"', (SKILL / "scripts" / "mini_me.py").read_text())
    if not m:
        sys.exit("could not read __version__ from mini_me.py")
    return m.group(1)


def main() -> int:
    missing = [p for p in INCLUDE if not (SKILL / p).exists()]
    if missing:
        sys.exit(f"missing files: {missing}")
    for p in INCLUDE:
        if re.search(r"(?i)password is \w|BEGIN [A-Z ]*PRIVATE KEY", (SKILL / p).read_text()):
            sys.exit(f"refusing to package {p}: looks like it contains a secret")
    DIST.mkdir(exist_ok=True)
    out = DIST / f"mini-me-v{version()}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in INCLUDE:
            info = zipfile.ZipInfo(f"mini-me/{p}", date_time=(2026, 11, 11, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o755 if p.endswith(".py") else 0o644) << 16
            z.writestr(info, (SKILL / p).read_bytes())
    print(f"{out} ({out.stat().st_size:,} bytes, {len(INCLUDE)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
