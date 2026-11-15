#!/usr/bin/env python3
"""Check Markdown prose wrapping without penalizing structural content."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
MAX_LINE_LENGTH = 80
SKIP_DIRECTORIES = {
    ".git",
    ".ruff_cache",
    ".state",
    ".venv",
    "socket-vmnet-shim",
}
REFERENCE_LINK = re.compile(r"^\[[^]]+\]:\s+\S")
INLINE_LINK = re.compile(r"(?<!!)\[[^]]+\]\(([^)\s]+)(?:\s+['\"][^)]*['\"])?\)")
LINK_DEFINITION = re.compile(r"^\[[^]]+\]:\s+(\S+)", re.MULTILINE)


def documentation_files() -> list[Path]:
    return sorted(
        path
        for path in ROOT.rglob("*.md")
        if not SKIP_DIRECTORIES.intersection(path.relative_to(ROOT).parts)
    )


def exempt_line(line: str, fence: str | None) -> bool:
    stripped = line.lstrip()
    return bool(
        fence
        or stripped.startswith("|")
        or stripped.startswith(("http://", "https://"))
        or REFERENCE_LINK.match(stripped)
    )


def violations(path: Path) -> list[tuple[int, int]]:
    problems = []
    fence: str | None = None
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.lstrip()
        marker = next((item for item in ("```", "~~~") if stripped.startswith(item)), None)
        if marker:
            if fence is None:
                fence = marker
            elif fence == marker:
                fence = None
            continue
        if len(line) > MAX_LINE_LENGTH and not exempt_line(line, fence):
            problems.append((number, len(line)))
    return problems


def heading_anchors(path: Path) -> set[str]:
    anchors = set()
    duplicates: dict[str, int] = {}
    fence: str | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.lstrip()
        marker = next((item for item in ("```", "~~~") if stripped.startswith(item)), None)
        if marker:
            if fence is None:
                fence = marker
            elif fence == marker:
                fence = None
            continue
        if fence or not stripped.startswith("#"):
            continue
        match = re.match(r"^#{1,6}\s+(.+?)\s*#*$", stripped)
        if not match:
            continue
        heading = re.sub(r"[`*_~]", "", match.group(1)).lower()
        heading = re.sub(r"[^\w\s-]", "", heading)
        base = re.sub(r"\s+", "-", heading.strip())
        count = duplicates.get(base, 0)
        duplicates[base] = count + 1
        anchors.add(base if count == 0 else f"{base}-{count}")
    return anchors


def link_violations(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    destinations = INLINE_LINK.findall(text) + LINK_DEFINITION.findall(text)
    problems = []
    for destination in destinations:
        if destination.startswith(("http://", "https://", "mailto:")):
            continue
        location, separator, anchor = destination.partition("#")
        target = (path.parent / unquote(location)).resolve() if location else path
        if not target.exists():
            problems.append(f"{path.relative_to(ROOT)}: missing link target {destination!r}")
            continue
        if separator and anchor and target.suffix.lower() == ".md":
            decoded_anchor = unquote(anchor).lower()
            if decoded_anchor not in heading_anchors(target):
                problems.append(
                    f"{path.relative_to(ROOT)}: missing heading {anchor!r} in "
                    f"{target.relative_to(ROOT)}"
                )
    return problems


def main() -> int:
    found = False
    for path in documentation_files():
        if path != ROOT / "README.md":
            for number, length in violations(path):
                found = True
                relative = path.relative_to(ROOT)
                print(f"{relative}:{number}: prose line is {length} characters (maximum 80)")
        for problem in link_violations(path):
            found = True
            print(problem)
    if found:
        print(
            "Fix documentation links or prose wrapping, tables, fenced code, "
            "raw URLs, link definitions, and the top-level README are wrap-exempt."
        )
        return 1
    print("Markdown wrapping and local links OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
