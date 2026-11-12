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
HOLDER = "Copyright (c) 2026 Kamari Fatima Zuhra"
SPDX_HEADER = "SPDX-License-Identifier: MIT"

# The MIT License body (SPDX "MIT"), compared with whitespace normalized.
MIT_BODY = """Permission is hereby granted, free of charge, to any person obtaining a copy of this software and
associated documentation files (the "Software"), to deal in the Software without restriction, including
without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the
following conditions: The above copyright notice and this permission notice shall be included in all copies
or substantial portions of the Software. THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR
PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE."""

INCLUDE = [
    "SKILL.md",
    "INSTALL.md",
    "LICENSE",
    "references/spec.md",
    "references/profile-format.md",
    "references/integration.md",
    "scripts/mini_me.py",
    "scripts/mcp_server.py",
    "templates/profile.template.md",
]


def fail(msg: str) -> None:
    sys.exit(f"package_skill: {msg}")


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def version() -> str:
    m = re.search(r'__version__ = "([^"]+)"', (SKILL / "scripts" / "mini_me.py").read_text())
    if not m:
        fail("could not read __version__ from mini_me.py")
    return m.group(1)


def check_license() -> None:
    lic = (SKILL / "LICENSE").read_text()
    lines = lic.strip().splitlines()
    if lines[0].strip() != "MIT License" or lines[2].strip() != HOLDER:
        fail(f"LICENSE must start with 'MIT License' and '{HOLDER}'")
    if norm("\n".join(lines[3:])) != norm(MIT_BODY):
        fail("LICENSE body is not the standard MIT text")
    root = ROOT / "LICENSE"
    if not root.exists() or root.read_text() != lic:
        fail("repository LICENSE differs from skills/mini-me/LICENSE. Keep them identical")
    for f in ("scripts/mini_me.py", "scripts/mcp_server.py"):
        if SPDX_HEADER not in (SKILL / f).read_text():
            fail(f"{f} is missing '{SPDX_HEADER}'")
    if "\nlicense: MIT" not in (SKILL / "SKILL.md").read_text().split("---")[1]:
        fail("SKILL.md frontmatter must declare 'license: MIT'")


def main() -> int:
    missing = [p for p in INCLUDE if not (SKILL / p).exists()]
    if missing:
        fail(f"missing files: {missing}")
    check_license()
    DIST.mkdir(exist_ok=True)
    out = DIST / f"mini-me-v{version()}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in INCLUDE:
            text = (SKILL / p).read_text(encoding="utf-8")
            if re.search(r"(?i)password is \w|BEGIN [A-Z ]*PRIVATE KEY", text):
                fail(f"refusing to package {p}: looks like it contains a secret")
            info = zipfile.ZipInfo(f"mini-me/{p}", date_time=(2026, 11, 12, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o755 if p.endswith(".py") else 0o644) << 16
            z.writestr(info, text.encode("utf-8"))
    print(f"{out} ({out.stat().st_size:,} bytes, {len(INCLUDE)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
