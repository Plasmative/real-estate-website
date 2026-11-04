"""Markdown -> Notion blocks, for the reports and notes the sync appends to a Product Backlog row.

The sync no longer reads page content or copies the spec: the spec lives in Linear.
"""

from __future__ import annotations

import re

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
