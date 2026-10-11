"""Conversions between Notion blocks and Markdown, and the synced spec section.

Only the block types used in Product Backlog pages are converted; anything
else is skipped with a placeholder so nothing is silently invented.
"""

from __future__ import annotations

import hashlib
import re

SPEC_HEADING = "## Spec — synced from Notion, do not edit"
NOTES_HEADING = "## Developer notes"
NOTES_PLACEHOLDER = "*Free section: write technical notes here. The sync never overwrites it.*"
REPORT_TITLE_PREFIX = "Definition of Ready check"
HASH_PATTERN = re.compile(r"spec-hash:\s*([0-9a-f]{12})")
HASH_LINE = re.compile(r"^.*spec-hash:\s*[0-9a-f]{12}.*$", re.M)


def _block_text(block: dict) -> str:
    btype = block.get("type", "")
    return "".join(rt.get("plain_text", "") or rt.get("text", {}).get("content", "")
                   for rt in block.get(btype, {}).get("rich_text", []))


def is_report_block(block: dict) -> bool:
    """A Definition of Ready report the sync appended: a toggle (heading) titled 'Definition of Ready check …'.

    Reports are toggles so they can be skipped as one block, wherever new
    content is added on the page afterwards.
    """
    btype = block.get("type", "")
    data = block.get(btype, {})
    toggle = btype == "toggle" or (btype.startswith("heading_") and data.get("is_toggleable"))
    return bool(toggle) and _block_text(block).strip().startswith(REPORT_TITLE_PREFIX)


# ---------------------------------------------------------------------------
# Notion blocks -> Markdown
# ---------------------------------------------------------------------------

def rich_text_to_md(rich_text: list[dict]) -> str:
    parts = []
    for rt in rich_text or []:
        text = rt.get("plain_text") or rt.get("text", {}).get("content", "")
        annotations = rt.get("annotations") or {}
        href = rt.get("href") or (rt.get("text", {}).get("link") or {}).get("url")
        if annotations.get("code"):
            text = f"`{text}`"
        if annotations.get("bold") and text.strip():
            text = f"**{text}**"
        if annotations.get("italic") and text.strip():
            text = f"*{text}*"
        if href:
            text = f"[{text}]({href})"
        parts.append(text)
    return "".join(parts)


def blocks_to_markdown(blocks: list[dict], depth: int = 0) -> str:
    """Convert a list of Notion block objects (with optional 'children') to Markdown."""
    lines: list[str] = []
    indent = "  " * depth
    numbered = 0
    for block in blocks:
        if is_report_block(block):
            continue  # sync reports are not part of the spec
        btype = block.get("type")
        data = block.get(btype, {}) if btype else {}
        text = rich_text_to_md(data.get("rich_text", []))
        if btype != "numbered_list_item":
            numbered = 0

        if btype == "paragraph":
            lines.append(f"{indent}{text}" if text else "")
        elif btype in ("heading_1", "heading_2", "heading_3"):
            level = int(btype[-1])
            lines.append(f"{'#' * level} {text}")
        elif btype == "bulleted_list_item":
            lines.append(f"{indent}- {text}")
        elif btype == "numbered_list_item":
            numbered += 1
            lines.append(f"{indent}{numbered}. {text}")
        elif btype == "to_do":
            mark = "x" if data.get("checked") else " "
            lines.append(f"{indent}- [{mark}] {text}")
        elif btype == "code":
            language = data.get("language", "") or ""
            code = "".join(rt.get("plain_text", "") for rt in data.get("rich_text", []))
            lines.append(f"```{language}")
            lines.extend(code.splitlines())
            lines.append("```")
        elif btype == "quote":
            lines.append(f"> {text}")
        elif btype == "callout":
            icon = (data.get("icon") or {}).get("emoji", "")
            lines.append(f"> {icon} {text}".rstrip())
        elif btype == "divider":
            lines.append("---")
        elif btype == "toggle":
            lines.append(f"{indent}- {text}")
        else:
            lines.append(f"{indent}[unsupported Notion block: {btype}]")

        children = block.get("children")
        if children:
            child_md = blocks_to_markdown(children, depth + 1)
            if btype == "callout":
                child_md = "\n".join(f"> {line}" if line else ">" for line in child_md.splitlines())
            lines.append(child_md)
        # Blank line between block groups keeps the Markdown readable.
        if btype not in ("bulleted_list_item", "numbered_list_item", "to_do"):
            lines.append("")
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip() + "\n"


# ---------------------------------------------------------------------------
# Markdown -> Notion blocks (used for the reports the sync appends)
# ---------------------------------------------------------------------------

_BOLD = re.compile(r"\*\*(.+?)\*\*")


def md_inline_to_rich_text(text: str) -> list[dict]:
    rich: list[dict] = []
    pos = 0
    for match in _BOLD.finditer(text):
        if match.start() > pos:
            rich.append({"type": "text", "text": {"content": text[pos:match.start()]}})
        rich.append(
            {"type": "text", "text": {"content": match.group(1)}, "annotations": {"bold": True}}
        )
        pos = match.end()
    if pos < len(text):
        rich.append({"type": "text", "text": {"content": text[pos:]}})
    # Notion limits one rich_text item to 2000 characters.
    for item in rich:
        item["text"]["content"] = item["text"]["content"][:2000]
    return rich


def markdown_to_blocks(markdown: str) -> list[dict]:
    blocks: list[dict] = []
    for raw in markdown.splitlines():
        line = raw.rstrip()
        if not line:
            continue
        if line.startswith("### "):
            btype, text = "heading_3", line[4:]
        elif line.startswith("## "):
            btype, text = "heading_2", line[3:]
        elif line.startswith("# "):
            btype, text = "heading_1", line[2:]
        elif line.startswith(("- ", "* ")):
            btype, text = "bulleted_list_item", line[2:]
        elif re.match(r"^\d+\. ", line):
            btype, text = "numbered_list_item", line.split(". ", 1)[1]
        else:
            btype, text = "paragraph", line
        blocks.append({"object": "block", "type": btype, btype: {"rich_text": md_inline_to_rich_text(text)}})
    return blocks


def report_block(title: str, body_markdown: str) -> dict:
    """One collapsible block holding a whole report, so it never mixes with the spec."""
    children = markdown_to_blocks(body_markdown)
    # Nested toggles are not needed; flatten inner headings to bold paragraphs.
    for child in children:
        if child["type"].startswith("heading_"):
            text = child[child["type"]]["rich_text"]
            for rt in text:
                rt.setdefault("annotations", {})["bold"] = True
            child.clear()
            child.update({"object": "block", "type": "paragraph", "paragraph": {"rich_text": text}})
    return {
        "object": "block",
        "type": "heading_3",
        "heading_3": {"rich_text": md_inline_to_rich_text(title), "is_toggleable": True, "children": children},
    }


# ---------------------------------------------------------------------------
# The spec section in a Linear issue
# ---------------------------------------------------------------------------

def spec_hash(spec_markdown: str) -> str:
    """Fingerprint of the spec, robust to Linear re-formatting the Markdown."""
    normalized = re.sub(r"\s+", " ", spec_markdown).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]


def render_spec(item_key: str, notion_url: str, body_markdown: str, example: bool) -> str:
    spec_body = body_markdown.strip()
    parts = []
    if example:
        parts.append("> 🧪 **Test data.** Example row used to test the sync. Cancel when the test is over.\n")
    parts.append(SPEC_HEADING)
    parts.append("")
    parts.append(f"Source of truth: [{item_key} in the Notion Product Backlog]({notion_url})")
    parts.append("")
    parts.append(spec_body)
    parts.append("")
    parts.append(f"`spec-hash: {spec_hash(spec_body)}`")
    return "\n".join(parts).strip()


def build_description(spec_section: str, developer_notes: str | None = None) -> str:
    notes = developer_notes if developer_notes and developer_notes.strip() else NOTES_PLACEHOLDER
    return f"{spec_section}\n\n---\n\n{NOTES_HEADING}\n\n{notes.strip()}\n"


def extract_hash(description: str) -> str | None:
    match = HASH_PATTERN.search(description or "")
    return match.group(1) if match else None


def extract_developer_notes(description: str) -> str:
    """Text a developer owns, which the sync must keep.

    - With a '## Developer notes' heading: everything after it.
    - Without it but with a synced spec: everything after the spec-hash line.
    - Without either: the whole description (it was written by hand).
    The placeholder text is not considered notes.
    """
    if not description:
        return ""
    idx = description.find(NOTES_HEADING)
    if idx != -1:
        notes = description[idx + len(NOTES_HEADING):].strip()
    else:
        match = HASH_LINE.search(description)
        if match:
            notes = description[match.end():].strip()
            notes = re.sub(r"^(?:-{3,}|\*{3,})\s*", "", notes).strip()
        else:
            notes = description.strip()
            if notes:
                notes = "Previous description, kept by the sync:\n\n" + notes
    return "" if notes == NOTES_PLACEHOLDER else notes


def extract_spec_text(description: str) -> str:
    """The spec part of an issue description, used to show a diff when it changes."""
    if not description:
        return ""
    start = description.find(SPEC_HEADING)
    end = description.find(NOTES_HEADING)
    if start == -1:
        return ""
    chunk = description[start:end if end != -1 else None]
    return chunk.rstrip().removesuffix("---").rstrip()
