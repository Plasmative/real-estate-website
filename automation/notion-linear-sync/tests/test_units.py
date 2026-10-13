import copy
import json

import requests

from fakes import FixedReviewer
from fixtures import EPIC, GOOD_GHERKIN, STORY_PASS, STORY_PASS_BLOCKS, code, para
from sync.ai_review import ClaudeReviewer, Verdict, heuristic_review
from sync.config import Config
from sync.dor import check_story, render_report
from sync.gherkin import extract_scenarios
from sync.markdown import (
    blocks_to_markdown, build_description, extract_developer_notes, extract_hash, markdown_to_blocks,
    render_spec, report_block, spec_hash,
)
from sync.notion_client import _to_notion, parse_item


# --- Gherkin ---------------------------------------------------------------

def test_scenarios_parsed_and_and_steps_resolved():
    scenarios = extract_scenarios(f"```gherkin\n{GOOD_GHERKIN}\n```")
    assert [s.name for s in scenarios] == ["Inquiry sent successfully", "Invalid email", "Sending fails"]
    assert all(not s.missing for s in scenarios)


def test_missing_then_is_detected():
    scenarios = extract_scenarios("```gherkin\nScenario: Broken\n  Given a page\n  When I click\n```")
    assert scenarios[0].missing == ["Then"]


def test_code_block_without_language_still_found():
    assert len(extract_scenarios("```\nScenario: A\n Given x\n When y\n Then z\n```")) == 1


# --- Markdown ---------------------------------------------------------------

def test_blocks_to_markdown_keeps_gherkin_code():
    md = blocks_to_markdown(STORY_PASS_BLOCKS)
    assert "```gherkin" in md and "Scenario: Invalid email" in md
    assert "## Acceptance criteria" in md
    assert "- Design system components: TextField, Button (primary)" in md


def test_unsupported_block_is_marked_not_dropped():
    assert "[unsupported Notion block: table]" in blocks_to_markdown([{"type": "table", "table": {}}])


def test_hash_ignores_whitespace_reformatting():
    assert spec_hash("a  b\n\nc") == spec_hash("a b c")
    assert spec_hash("a b c") != spec_hash("a b d")


def test_report_toggle_is_skipped_wherever_it_sits():
    report = report_block("Definition of Ready check — 2026-10-11 — passed", "## Notes\n- ok")
    report["children"] = report["heading_3"].pop("children")
    blocks = [para("Before"), report, para("Added after the report")]
    md = blocks_to_markdown(blocks)
    assert "Before" in md and "Added after the report" in md
    assert "Definition of Ready" not in md and "ok" not in md


def test_description_round_trip_keeps_notes():
    spec = render_spec("FR-1", "https://n", "Body", example=False)
    desc = build_description(spec, "My notes")
    assert extract_hash(desc) == spec_hash("Body")
    assert extract_developer_notes(desc) == "My notes"


def test_markdown_to_blocks_bold_and_lists():
    blocks = markdown_to_blocks("## Title\n1. **Gap.** fix it\n- warn")
    assert [b["type"] for b in blocks] == ["heading_2", "numbered_list_item", "bulleted_list_item"]
    rich = blocks[1]["numbered_list_item"]["rich_text"]
    assert rich[0]["annotations"]["bold"] is True and rich[0]["text"]["content"] == "Gap."


# --- Notion property mapping -------------------------------------------------

def test_parse_item_from_api_page():
    page = {
        "id": "abc", "url": "https://notion.so/abc",
        "properties": {
            "Name": {"title": [{"plain_text": "Story"}]},
            "ID": {"rich_text": [{"plain_text": "FR-01"}]},
            "Type": {"select": {"name": "User story"}},
            "Status": {"select": {"name": "Ready for dev"}},
            "MoSCoW": {"select": None},
            "Epic": {"relation": [{"id": "e1"}]},
            "Blocking questions": {"checkbox": True},
            "Example (test data)": {"checkbox": False},
        },
    }
    item = parse_item(page)
    assert (item.key, item.type, item.moscow, item.epic_page_ids, item.blocking_questions) == (
        "FR-01", "User story", None, ["e1"], True)


def test_sync_cannot_write_product_fields():
    try:
        _to_notion("MoSCoW", "Must")
    except ValueError as exc:
        assert "not allowed" in str(exc)
    else:
        raise AssertionError("writing MoSCoW must be refused")


# --- Definition of Ready ------------------------------------------------------

def _story_md():
    return blocks_to_markdown(STORY_PASS_BLOCKS)


def test_ai_saying_no_unhappy_path_blocks():
    reviewer = FixedReviewer(Verdict(has_unhappy_path=False, source="ai"))
    result = check_story(STORY_PASS, _story_md(), EPIC, reviewer, Config.from_env())
    assert not result.passed
    assert any("Only the happy path" in b for b in result.blocking)


def test_ai_vague_scenarios_and_coverage_become_warnings():
    verdict = Verdict(has_unhappy_path=True, vague_scenarios=["Sending fails"], covers_bilingual=False,
                      covers_mobile=True, source="ai", notes=["Then step is vague"])
    result = check_story(STORY_PASS, _story_md(), EPIC, FixedReviewer(verdict), Config.from_env())
    assert result.passed
    assert any("Sending fails" in w for w in result.warnings)
    assert "No English/Spanish cases (NFR-01)." in result.warnings
    assert "Acceptance criteria reviewed by: ai." in result.notes


def test_unapproved_epic_blocks():
    epic = copy.deepcopy(EPIC)
    epic.status = "Discovery"
    result = check_story(STORY_PASS, _story_md(), epic, FixedReviewer(Verdict(True)), Config.from_env())
    assert any("Epic not approved" in b for b in result.blocking)


def test_reviewer_not_called_without_scenarios():
    reviewer = FixedReviewer(Verdict(True))
    md = blocks_to_markdown([para("No criteria yet")])
    result = check_story(STORY_PASS, md, EPIC, reviewer, Config.from_env())
    assert reviewer.calls == 0
    assert any("No acceptance criteria" in b for b in result.blocking)


def test_report_lists_gaps():
    result = check_story(STORY_PASS, blocks_to_markdown([code("Scenario: A\n Given x\n When y")]), None,
                         FixedReviewer(Verdict(True)), Config.from_env())
    title, text = render_report(result, "2026-10-11")
    assert title.endswith("blocked")
    assert "Blocked" in text and "No epic" in text and "Missing: Then" in text


# --- Claude reviewer ------------------------------------------------------------

class _Resp:
    def __init__(self, payload, status=200):
        self._payload, self.status_code = payload, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def json(self):
        return self._payload


class _Session:
    def __init__(self, response):
        self.response, self.calls = response, []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def test_claude_reviewer_parses_json_and_sends_expected_request():
    answer = {"has_unhappy_path": True, "vague_scenarios": [], "covers_bilingual": True,
              "covers_mobile": False, "too_big": False, "notes": ["ok"]}
    session = _Session(_Resp({"content": [{"type": "text", "text": "Here:\n" + json.dumps(answer)}]}))
    verdict = ClaudeReviewer("key", "claude-sonnet-5-5", session=session).review("FR-1", "body", [])
    assert verdict.source == "ai" and verdict.covers_mobile is False
    url, kwargs = session.calls[0]
    assert url == "https://api.anthropic.com/v1/messages"
    assert kwargs["headers"]["anthropic-version"] == "2023-06-01"
    assert kwargs["json"]["model"] == "claude-sonnet-5-5"


def test_claude_failure_falls_back_to_heuristic():
    scenarios = extract_scenarios(f"```gherkin\n{GOOD_GHERKIN}\n```")
    verdict = ClaudeReviewer("key", "m", session=_Session(_Resp({}, status=500))).review("FR-1", "body", scenarios)
    assert verdict.source == "heuristic"
    assert verdict.has_unhappy_path is True
    assert "AI review failed" in verdict.notes[0]


def test_heuristic_spots_happy_path_only():
    scenarios = extract_scenarios("```gherkin\nScenario: Save\n Given a page\n When I click Save\n Then it is saved\n```")
    assert heuristic_review("", scenarios).has_unhappy_path is False


def test_markdown_to_blocks_keeps_code_and_todos():
    from sync.markdown import blocks_to_markdown, markdown_to_blocks
    md = "## Spec\n\n```gherkin\nScenario: A\n  Given x\n```\n\n```astro\n<div/>\n```\n\n- [x] done\n- [ ] open\n"
    blocks = markdown_to_blocks(md)
    assert [b["type"] for b in blocks] == ["heading_2", "code", "code", "to_do", "to_do"]
    assert blocks[1]["code"]["language"] == "gherkin"
    assert blocks[2]["code"]["language"] == "plain text"  # not a Notion language
    back = blocks_to_markdown(blocks)
    assert "```gherkin\nScenario: A\n  Given x\n```" in back
    assert "- [x] done" in back and "- [ ] open" in back
