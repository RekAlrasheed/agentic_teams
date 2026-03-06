#!/usr/bin/env python3
"""
Navaia Knowledge Base Auto-Cataloger

Scans knowledge/ directory and generates knowledge/INDEX.md with a
structured catalog of all company files, organized by category and agent relevance.

Usage:
    python tools/catalog.py
"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = REPO_ROOT / "knowledge"
INDEX_FILE = KNOWLEDGE_DIR / "INDEX.md"

# File type descriptions
FILE_TYPES = {
    ".md": "Markdown",
    ".txt": "Text",
    ".csv": "CSV",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".html": "HTML",
    ".css": "CSS",
    ".pdf": "PDF",
    ".xlsx": "Excel",
    ".xls": "Excel",
    ".pptx": "PowerPoint",
    ".ppt": "PowerPoint",
    ".docx": "Word",
    ".doc": "Word",
    ".png": "Image (PNG)",
    ".jpg": "Image (JPEG)",
    ".jpeg": "Image (JPEG)",
    ".svg": "Image (SVG)",
    ".gif": "Image (GIF)",
}

# Category → agent mapping
CATEGORY_AGENTS = {
    "company": ["Creative (Muse)", "Admin (Sage)", "PM (Navi)"],
    "sales": ["Creative (Muse)", "Admin (Sage)"],
    "products": ["Technical (Arch)", "Creative (Muse)"],
    "finance": ["Admin (Sage)", "PM (Navi)"],
    "legal": ["Admin (Sage)", "PM (Navi)"],
    "marketing": ["Creative (Muse)", "PM (Navi)"],
    "technical": ["Technical (Arch)"],
    "hr": ["Admin (Sage)", "PM (Navi)"],
    "templates": ["Admin (Sage)", "Creative (Muse)"],
}

# Binary extensions (can't read content)
BINARY_EXTENSIONS = {".pdf", ".xlsx", ".xls", ".pptx", ".ppt", ".docx", ".doc",
                     ".png", ".jpg", ".jpeg", ".svg", ".gif", ".zip", ".tar", ".gz"}


def format_size(size_bytes: int) -> str:
    """Format file size in human-readable form."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def detect_language(text: str) -> str:
    """Simple language detection based on character ranges."""
    arabic_chars = sum(1 for c in text if '\u0600' <= c <= '\u06FF')
    latin_chars = sum(1 for c in text if c.isascii() and c.isalpha())

    if arabic_chars > 0 and latin_chars > 0:
        if arabic_chars > latin_chars * 0.1:
            return "Bilingual"
    if arabic_chars > latin_chars:
        return "Arabic"
    return "English"


def get_summary(filepath: Path) -> str:
    """Generate a brief summary of the file."""
    ext = filepath.suffix.lower()

    if ext in BINARY_EXTENSIONS:
        file_type = FILE_TYPES.get(ext, "Binary")
        size = format_size(filepath.stat().st_size)
        return f"{file_type} file ({size})"

    try:
        content = filepath.read_text(encoding="utf-8", errors="ignore")[:500]
        # Get first meaningful line as summary
        lines = [l.strip() for l in content.split("\n") if l.strip() and not l.startswith("#")]
        if lines:
            summary = lines[0][:150]
            if len(lines[0]) > 150:
                summary += "..."
            return summary
        elif content.strip():
            return content.strip()[:150]
        else:
            return "Empty file"
    except Exception:
        return "Unable to read file"


def get_category(filepath: Path) -> str:
    """Derive category from folder name."""
    rel = filepath.relative_to(KNOWLEDGE_DIR)
    parts = rel.parts
    if len(parts) > 1:
        return parts[0]
    return "uncategorized"


def scan_knowledge_base() -> list[dict]:
    """Scan all files in knowledge/ and collect metadata."""
    entries = []

    for filepath in sorted(KNOWLEDGE_DIR.rglob("*")):
        if filepath.is_dir():
            continue
        if filepath.name == "INDEX.md":
            continue
        if filepath.name == ".gitkeep":
            continue
        if filepath.name.startswith("."):
            continue

        rel_path = filepath.relative_to(REPO_ROOT)
        category = get_category(filepath)
        ext = filepath.suffix.lower()
        file_type = FILE_TYPES.get(ext, ext.upper().lstrip(".") if ext else "Unknown")
        size = format_size(filepath.stat().st_size)
        summary = get_summary(filepath)
        agents = CATEGORY_AGENTS.get(category, ["PM (Navi)"])
        modified = datetime.fromtimestamp(filepath.stat().st_mtime, tz=timezone.utc)

        # Detect language for text files
        language = "English"
        if ext not in BINARY_EXTENSIONS:
            try:
                content = filepath.read_text(encoding="utf-8", errors="ignore")[:1000]
                language = detect_language(content)
            except Exception:
                pass

        entries.append({
            "path": str(rel_path),
            "filename": filepath.name,
            "category": category,
            "file_type": file_type,
            "size": size,
            "summary": summary,
            "agents": agents,
            "language": language,
            "modified": modified.strftime("%Y-%m-%d"),
        })

    return entries


def generate_agent_quick_ref(entries: list[dict]) -> str:
    """Generate quick reference section grouped by agent."""
    agent_files: dict[str, list[str]] = {}

    for entry in entries:
        for agent in entry["agents"]:
            if agent not in agent_files:
                agent_files[agent] = []
            agent_files[agent].append(f"- {entry['path']} — {entry['summary'][:80]}")

    sections = []
    for agent in ["PM (Navi)", "Creative (Muse)", "Technical (Arch)", "Admin (Sage)"]:
        if agent in agent_files:
            sections.append(f"### For {agent}\n" + "\n".join(agent_files[agent][:15]))

    return "\n\n".join(sections)


def generate_index(entries: list[dict]) -> str:
    """Generate the full INDEX.md content."""
    now = datetime.now(timezone.utc).isoformat()

    output = f"""# NAVAIA KNOWLEDGE BASE INDEX

> Auto-generated by tools/catalog.py
> Last updated: {now}
> Total files: {len(entries)}

## Quick Reference by Agent

{generate_agent_quick_ref(entries)}

---

## Full Catalog

"""

    # Group by category
    categories: dict[str, list[dict]] = {}
    for entry in entries:
        cat = entry["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(entry)

    for category in sorted(categories.keys()):
        output += f"### {category}/\n\n"
        for entry in categories[category]:
            output += f"#### {entry['path']}\n"
            output += f"- **Category:** {category.title()}\n"
            output += f"- **Type:** {entry['file_type']} ({entry['size']})\n"
            output += f"- **Summary:** {entry['summary']}\n"
            output += f"- **Use when:** {', '.join(entry['agents'])} need this file\n"
            output += f"- **Language:** {entry['language']}\n"
            output += f"- **Last modified:** {entry['modified']}\n\n"

    if not entries:
        output += "_No files found in knowledge/. Add company files to get started._\n"

    return output


def main():
    print(f"Scanning {KNOWLEDGE_DIR}...")
    entries = scan_knowledge_base()
    index_content = generate_index(entries)
    INDEX_FILE.write_text(index_content, encoding="utf-8")
    print(f"Generated {INDEX_FILE} with {len(entries)} entries.")


if __name__ == "__main__":
    main()
