import copy

from fixtures import EPIC, STORY_FAIL, STORY_PASS
from sync.config import Config
from sync.dor import check_story, render_report
from sync.engine import fallback_description
from sync.markdown import markdown_to_blocks, report_block
from sync.notion_client import _to_notion, parse_item


# --- Notion property mapping -------------------------------------------------

def test_parse_item_from_api_page():
    page = {
        "id": "abc", "url": "https://notion.so/abc",
        "properties": {
            "Name": {"title": [{"plain_text": "Story"}]},
            "ID": {"rich_text": [{"plain_text": "FR-01"}]},
            "Type": {"select": {"name": "User story"}},
            "Status": {"select": {"name": "Approved"}},
            "MoSCoW": {"select": None},
            "Epic": {"relation": [{"id": "e1"}]},
            "KPIs": {"relation": [{"id": "k1"}]},
            "Blocking questions": {"checkbox": True},
            "Example (test data)": {"checkbox": False},
        },
    }
    item = parse_item(page)
    assert (item.key, item.status, item.moscow, item.epic_page_ids, item.kpi_ids, item.blocking_questions) == (
        "FR-01", "Approved", None, ["e1"], ["k1"], True)


def test_sync_cannot_write_client_fields():
    for name in ("MoSCoW", "Approved in", "Accepted in", "Linear status", "Spec synced at"):
        try:
            _to_notion(name, "x")
        except ValueError as exc:
            assert "not allowed" in str(exc)
        else:
            raise AssertionError(f"writing {name} must be refused")


# --- Definition of Ready (client fields only) -----------------------------------

def test_approved_story_passes():
    result = check_story(STORY_PASS, EPIC, Config.from_env())
    assert result.passed
    assert result.warnings == ["Confidence is only 🟡 Assumption."]


def test_missing_client_fields_block():
    result = check_story(STORY_FAIL, EPIC, Config.from_env())
    text = " ".join(result.blocking)
    assert "No client approval" in text and "No prototype version" in text and "Blocking question" in text


def test_no_kpi_is_only_a_warning():
    story = copy.deepcopy(STORY_PASS)
    story.kpi_ids = []
    result = check_story(story, EPIC, Config.from_env())
    assert result.passed
    assert any("No KPI" in w for w in result.warnings)


def test_wont_and_unclassified_never_go_to_linear():
    for moscow in ("Won't (this version)", "Unclassified", None):
        story = copy.deepcopy(STORY_PASS)
        story.moscow = moscow
        assert not check_story(story, EPIC, Config.from_env()).passed


def test_unapproved_epic_blocks():
    epic = copy.deepcopy(EPIC)
    epic.status = "Discovery"
    result = check_story(STORY_PASS, epic, Config.from_env())
    assert any("Epic not approved" in b for b in result.blocking)


def test_report_lists_gaps():
    result = check_story(STORY_PASS, None, Config.from_env())
    title, text = render_report(result, "2026-10-13")
    assert title.endswith("blocked")
    assert "Blocked" in text and "No epic" in text and "*Discovery*" in text


def test_passed_report_says_where_the_spec_goes():
    title, text = render_report(check_story(STORY_PASS, EPIC, Config.from_env()), "2026-10-13", "FRA-40")
    assert title.endswith("passed")
    assert "Sent to Linear as FRA-40: the spec is written there." in text


# --- Markdown helpers ----------------------------------------------------------

def test_markdown_to_blocks_bold_lists_and_todos():
    blocks = markdown_to_blocks("## Title\n\n**Bold** text\n- item\n1. first\n- [x] done\n- [ ] open\n")
    assert [b["type"] for b in blocks] == ["heading_2", "paragraph", "bulleted_list_item",
                                           "numbered_list_item", "to_do", "to_do"]
    assert blocks[1]["paragraph"]["rich_text"][0]["annotations"]["bold"] is True
    assert blocks[4]["to_do"]["checked"] is True


def test_report_block_is_one_toggle_without_nested_headings():
    block = report_block("Definition of Ready check — x", "### Gaps\n1. one")
    assert block["heading_3"]["is_toggleable"] is True
    assert [c["type"] for c in block["heading_3"]["children"]] == ["paragraph", "numbered_list_item"]


def test_fallback_description_has_every_template_heading_in_order():
    text = fallback_description(STORY_PASS)
    positions = [text.index(f"## {h}") for h in ("User story", "Acceptance criteria (Gherkin)", "Developer notes")]
    assert positions == sorted(positions)
    assert STORY_PASS.url in text
