#!/usr/bin/env python3
"""Build the distributable skill zip: dist/mini-me-v<version>.zip

The zip holds one top-level folder, mini-me/, ready to drop into ~/.claude/skills/ or upload as a skill.
Only files a user needs are included: tests, caches, and any profile are left out.

Run:  python3 tools/package_skill.py [--pro-url https://your-store/mini-me-pro]
The Pro URL is written into LICENSING.md inside the zip. It defaults to the GitHub repository.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "mini-me"
DIST = ROOT / "dist"
DEFAULT_PRO_URL = "https://github.com/TOUMO45/Mini-Me"
# sha256 of the official PolyForm Noncommercial 1.0.0 text, from github.com/polyformproject/polyform-licenses@1.0.0
POLYFORM_NC_SHA256 = "c0ea4a896d2c8c394b29f9427589996db826cd501c512279ff0ed3ef48fabbe5"

INCLUDE = [
    "SKILL.md",
    "INSTALL.md",
    "LICENSING.md",
    "LICENSE.md",
    "LICENSE-PRO.md",
    "references/spec.md",
    "references/profile-format.md",
    "references/integration.md",
    "scripts/mini_me.py",
    "scripts/mcp_server.py",
    "templates/profile.template.md",
]


def fail(msg: str) -> None:
    sys.exit(f"package_skill: {msg}")


def version() -> str:
    m = re.search(r'__version__ = "([^"]+)"', (SKILL / "scripts" / "mini_me.py").read_text())
    if not m:
        fail("could not read __version__ from mini_me.py")
    return m.group(1)


def check_licenses() -> None:
    lic = (SKILL / "LICENSE.md").read_text()
    if not lic.startswith("Required Notice: Copyright"):
        fail("LICENSE.md must start with the Required Notice line")
    official = lic.split("\n---\n\n", 1)[-1]
    if hashlib.sha256(official.encode()).hexdigest() != POLYFORM_NC_SHA256:
        fail("the PolyForm Noncommercial 1.0.0 text in LICENSE.md was modified. Restore the official text")
    root = ROOT / "LICENSE.md"
    if not root.exists() or root.read_text() != lic:
        fail("repository LICENSE.md differs from skills/mini-me/LICENSE.md. Keep them identical")
    for f in ("scripts/mini_me.py", "scripts/mcp_server.py"):
        if "SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0 OR LicenseRef-MiniMe-Pro" not in (SKILL / f).read_text():
            fail(f"{f} is missing its SPDX license header")
    if "\nlicense:" not in (SKILL / "SKILL.md").read_text().split("---")[1]:
        fail("SKILL.md frontmatter is missing the license field")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pro-url", default=DEFAULT_PRO_URL, help="where buyers get Mini Me Pro")
    args = ap.parse_args()
    if not re.match(r"^https://\S+$", args.pro_url):
        fail("--pro-url must be an https:// URL")

    missing = [p for p in INCLUDE if not (SKILL / p).exists()]
    if missing:
        fail(f"missing files: {missing}")
    check_licenses()

    DIST.mkdir(exist_ok=True)
    out = DIST / f"mini-me-v{version()}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in INCLUDE:
            text = (SKILL / p).read_text(encoding="utf-8")
            if re.search(r"(?i)password is \w|BEGIN [A-Z ]*PRIVATE KEY", text):
                fail(f"refusing to package {p}: looks like it contains a secret")
            text = text.replace("{{PRO_URL}}", args.pro_url)
            if "{{" in text and "}}" in text and re.search(r"\{\{[A-Z_]+\}\}", text):
                fail(f"unfilled placeholder in {p}")
            info = zipfile.ZipInfo(f"mini-me/{p}", date_time=(2026, 11, 11, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o755 if p.endswith(".py") else 0o644) << 16
            z.writestr(info, text.encode("utf-8"))
    print(f"{out} ({out.stat().st_size:,} bytes, {len(INCLUDE)} files, Pro URL: {args.pro_url})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
