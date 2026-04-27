#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List

REQUIRED_DIRS = [
    "00_Inbox",
    "01_Ideas",
    "02_PostDrafts",
    "03_Reels",
    "04_ContentCalendar",
    "05_Prompts",
    "06_Knowledge",
    "07_Assets",
    "08_Posted",
    "Templates",
]

REQUIRED_FILES = [
    "README.md",
    "CONTENT DASHBOARD.md",
    "EDITORIAL BOARD.md",
    "Templates/instagram-post.md",
    "Templates/reel-script.md",
    "05_Prompts/carousel-generator.md",
    "05_Prompts/reel-generator.md",
]

IDEAL_KANBAN_COLUMNS = ["Ideas", "Draft", "Design", "Scheduled", "Posted"]
MIN_DV_SECTIONS = ["Ideas", "Draft", "Scheduled", "Posted"]
FRONTMATTER_KEYS = ["category", "status", "format", "publish", "goal", "tags"]
BOARD_FILE_ALIASES = ["EDITORIAL BOARD.md", "投稿進行ボード.md"]
DASHBOARD_FILE_ALIASES = ["CONTENT DASHBOARD.md", "コンテンツダッシュボード.md"]


@dataclass
class CheckResult:
    present: List[str]
    missing: List[str]


def check_paths(root: Path, relpaths: List[str]) -> CheckResult:
    present: List[str] = []
    missing: List[str] = []
    for rel in relpaths:
        if (root / rel).exists():
            present.append(rel)
        else:
            missing.append(rel)
    return CheckResult(present, missing)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def choose_existing_file(root: Path, aliases: List[str]) -> Path | None:
    for candidate in aliases:
        p = root / candidate
        if p.exists():
            return p
    return None


def discover_vault_dir(hint: str) -> List[Path]:
    """
    Best-effort discovery for Obsidian iCloud vault paths on macOS-like layouts.
    """
    hint_name = Path(hint).name
    roots = [
        Path.home() / "Library/Mobile Documents/iCloud~md~obsidian/Documents",
        Path("/Users") / os.getenv("USER", "") / "Library/Mobile Documents/iCloud~md~obsidian/Documents",
        Path("/Users/magnet/Library/Mobile Documents/iCloud~md~obsidian/Documents"),
        Path("/Users"),
        Path("/home"),
    ]

    found: List[Path] = []
    seen: set[str] = set()
    for root in roots:
        if not root.exists():
            continue
        if root.is_dir() and root.name == hint_name:
            key = str(root.resolve())
            if key not in seen:
                seen.add(key)
                found.append(root)
            continue

        try:
            for p in root.rglob(hint_name):
                if not p.is_dir():
                    continue
                key = str(p.resolve())
                if key in seen:
                    continue
                seen.add(key)
                found.append(p)
                if len(found) >= 10:
                    return found
        except (PermissionError, FileNotFoundError):
            continue
    return found


def detect_kanban(board_text: str) -> tuple[bool, List[str], bool]:
    has_kanban_marker = "kanban-plugin" in board_text.lower() or "```kanban" in board_text.lower()
    found_columns: List[str] = []
    for col in IDEAL_KANBAN_COLUMNS:
        # Detect markdown headings or kanban list labels
        if re.search(rf"^#+\s*{re.escape(col)}\s*$", board_text, flags=re.MULTILINE) or re.search(
            rf"^\s*-\s*{re.escape(col)}\s*$", board_text, flags=re.MULTILINE
        ):
            found_columns.append(col)

    has_wikilink_cards = bool(re.search(r"\[\[[^\]]+\]\]", board_text))
    return has_kanban_marker, found_columns, has_wikilink_cards


def detect_dataview_sections(dashboard_text: str) -> List[str]:
    found: List[str] = []
    lower = dashboard_text.lower()
    for section in MIN_DV_SECTIONS:
        if section.lower() in lower and "```dataview" in lower:
            found.append(section)
    return found


def has_frontmatter_keys(text: str, keys: List[str]) -> bool:
    if not text.startswith("---"):
        return False
    parts = text.split("---", 2)
    if len(parts) < 3:
        return False
    fm = parts[1]
    for k in keys:
        if re.search(rf"^{re.escape(k)}\s*:", fm, flags=re.MULTILINE) is None:
            return False
    return True


def collect_post_note_issues(root: Path) -> tuple[List[str], List[str]]:
    checked: List[str] = []
    invalid: List[str] = []
    for folder in ["01_Ideas", "02_PostDrafts"]:
        dirpath = root / folder
        if not dirpath.exists():
            continue
        for md in sorted(dirpath.glob("*.md")):
            rel = str(md.relative_to(root))
            checked.append(rel)
            if not has_frontmatter_keys(read_text(md), FRONTMATTER_KEYS):
                invalid.append(rel)
    return checked, invalid


def find_candidates(root: Path) -> tuple[List[str], List[str], List[str]]:
    duplicates: List[str] = []
    misplaced: List[str] = []

    name_to_paths: dict[str, List[Path]] = {}
    for p in root.rglob("*.md"):
        name_to_paths.setdefault(p.name, []).append(p)
    for name, paths in name_to_paths.items():
        if len(paths) > 1:
            duplicates.append(f"{name}: " + ", ".join(str(p.relative_to(root)) for p in paths))

    expected_roots = set(REQUIRED_DIRS + ["README.md", "CONTENT DASHBOARD.md", "EDITORIAL BOARD.md"])
    for p in root.iterdir() if root.exists() else []:
        if p.name.startswith("."):
            continue
        if p.name not in expected_roots:
            misplaced.append(str(p.relative_to(root)))

    empty_files: List[str] = []
    for p in root.rglob("*.md"):
        try:
            if p.stat().st_size == 0:
                empty_files.append(str(p.relative_to(root)))
        except FileNotFoundError:
            pass
    return duplicates, empty_files, misplaced


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("target")
    args = parser.parse_args()

    root = Path(args.target).expanduser()
    print(f"Target: {root}")
    if not root.exists():
        print("STATUS: MISSING_TARGET")
        discovered = discover_vault_dir(args.target)
        if discovered:
            print("DISCOVERED_CANDIDATES:")
            for d in discovered:
                print(f"- {d}")
            root = discovered[0]
            print(f"USING_DISCOVERED_TARGET: {root}")
        else:
            print("DISCOVERY_HINT: 共有iCloudパスをこの実行環境から参照できない可能性があります。")
            return 2

    d = check_paths(root, REQUIRED_DIRS)
    f = check_paths(root, REQUIRED_FILES)

    board_file = choose_existing_file(root, BOARD_FILE_ALIASES)
    dash_file = choose_existing_file(root, DASHBOARD_FILE_ALIASES)
    board_text = read_text(board_file) if board_file else ""
    dash_text = read_text(dash_file) if dash_file else ""

    has_kanban, columns, wikilink_cards = detect_kanban(board_text)
    dv_found = detect_dataview_sections(dash_text)

    checked_notes, invalid_notes = collect_post_note_issues(root)
    duplicates, empty_files, misplaced = find_candidates(root)

    print("\n[DIRS]")
    print("PRESENT:", ", ".join(d.present) or "-")
    print("MISSING:", ", ".join(d.missing) or "-")

    print("\n[FILES]")
    print("PRESENT:", ", ".join(f.present) or "-")
    print("MISSING:", ", ".join(f.missing) or "-")
    print("BOARD_FILE_USED:", str(board_file.relative_to(root)) if board_file else "-")
    print("DASHBOARD_FILE_USED:", str(dash_file.relative_to(root)) if dash_file else "-")

    print("\n[KANBAN]")
    print("HAS_KANBAN_MARKER:", has_kanban)
    print("FOUND_COLUMNS:", ", ".join(columns) or "-")
    print("MISSING_COLUMNS:", ", ".join([c for c in IDEAL_KANBAN_COLUMNS if c not in columns]) or "-")
    print("HAS_WIKILINK_CARDS:", wikilink_cards)

    print("\n[DATAVIEW]")
    print("FOUND_SECTIONS:", ", ".join(dv_found) or "-")
    print("MISSING_SECTIONS:", ", ".join([s for s in MIN_DV_SECTIONS if s not in dv_found]) or "-")

    print("\n[POST_NOTES]")
    print("CHECKED_NOTES:", len(checked_notes))
    print("INVALID_FRONTMATTER_NOTES:", ", ".join(invalid_notes) or "-")

    print("\n[CANDIDATES]")
    print("DUPLICATES:", " | ".join(duplicates) or "-")
    print("EMPTY_FILES:", " | ".join(empty_files) or "-")
    print("MISPLACED_AT_ROOT:", ", ".join(misplaced) or "-")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
