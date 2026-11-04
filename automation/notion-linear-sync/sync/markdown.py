"""Conversions between Notion blocks and Markdown.

Notion blocks -> Markdown: the request on a Product Backlog row, copied once into the new Linear issue.
Markdown -> Notion blocks: the reports and notes the sync appends to a row.
"""

from __future__ import annotations

import re

# Titles of the toggles the sync appends to a Notion page. They are never part of the request.
REPORT_TITLE_PREFIXES = ("Definition of Ready check", "Sync note")


def _block_text(block: dict) -> str:
    btype = block.get("type", "")
    return "".join(rt.get("plain_text", "") or rt.get("text", {}).get("content", "")
                   for rt in block.get(btype, {}).get("rich_text", []))


def is_report_block(block: dict) -> bool:
    """A report the sync appended: a toggle (heading) titled 'Definition of Ready check …' or 'Sync note …'."""
    btype = block.get("type", "")
    data = block.get(btype, {})
    toggle = btype == "toggle" or (btype.startswith("heading_") and data.get("is_toggleable"))
    return bool(toggle) and _block_text(block).strip().startswith(REPORT_TITLE_PREFIXES)


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
    """Convert Notion block objects (with optional 'children') to Markdown. Reports are skipped."""
    lines: list[str] = []
    indent = "  " * depth
    numbered = 0
    for block in blocks:
        if is_report_block(block):
            continue
        btype = block.get("type")
        data = block.get(btype, {}) if btype else {}
        text = rich_text_to_md(data.get("rich_text", []))
        if btype != "numbered_list_item":
            numbered = 0

        if btype == "paragraph":
            lines.append(f"{indent}{text}" if text else "")
        elif btype in ("heading_1", "heading_2", "heading_3"):
            lines.append(f"{'#' * int(btype[-1])} {text}")
        elif btype == "bulleted_list_item":
            lines.append(f"{indent}- {text}")
        elif btype == "numbered_list_item":
            numbered += 1
            lines.append(f"{indent}{numbered}. {text}")
        elif btype == "to_do":
            lines.append(f"{indent}- [{'x' if data.get('checked') else ' '}] {text}")
        elif btype == "code":
            code = "".join(rt.get("plain_text") or rt.get("text", {}).get("content", "")
                           for rt in data.get("rich_text", []))
            lines.append(f"```{data.get('language', '') or ''}")
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
        if btype not in ("bulleted_list_item", "numbered_list_item", "to_do"):
            lines.append("")
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip() + "\n"


# ---------------------------------------------------------------------------
# Markdown -> Notion blocks
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
    """Headings, bullets, numbered items, to-dos and paragraphs. Enough for the sync's own notes."""
    blocks: list[dict] = []
    for raw in markdown.splitlines():
        line = raw.rstrip()
        if not line:
            continue
        todo = re.match(r"^[-*] \[( |x|X)\] (.*)$", line)
        if todo:
            blocks.append({"object": "block", "type": "to_do",
                           "to_do": {"rich_text": md_inline_to_rich_text(todo.group(2)),
                                     "checked": todo.group(1).lower() == "x"}})
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
    """One collapsible block holding a whole report, so it stays apart from the request text."""
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
