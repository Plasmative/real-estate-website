import copy

import pytest

from fakes import FakeLinear, FakeNotion
from fixtures import EPIC, STORY_FAIL, STORY_PASS
from sync.config import Config
from sync.engine import HANDOFF_HEADINGS, SyncEngine
from sync.models import BacklogItem, LinearIssue


@pytest.fixture
def env(monkeypatch):
    for var in ("INCLUDE_EXAMPLES", "LINEAR_NEW_ISSUE_STATE", "LINEAR_HANDOFF_TEMPLATE"):
        monkeypatch.delenv(var, raising=False)
    notion = FakeNotion([copy.deepcopy(EPIC), copy.deepcopy(STORY_PASS), copy.deepcopy(STORY_FAIL)])
    return notion, FakeLinear(), Config.from_env()


def run(env, apply=True):
    notion, linear, config = env
    return SyncEngine(notion, linear, config, apply=apply, today="2026-10-13").run()


def _done(linear, identifier, state=("Done", "completed")):
    linear.issues[identifier].state_name, linear.issues[identifier].state_type = state


def test_dry_run_changes_nothing(env):
    notion, linear, _ = env
    report = run(env, apply=False)
    assert linear.issues == {}
    assert notion.writes == []
    assert notion.reports == {}
    assert report.counts["created"] == 1
    assert report.counts["blocked"] == 1
    assert "DRY RUN" in report.markdown()


def test_approved_story_is_created_from_the_template(env):
    notion, linear, _ = env
    report = run(env)
    assert report.errors == []
    story, epic = notion.items["story-1"], notion.items["epic-1"]
    assert story.status == "In Linear" and epic.status == "In Linear"
    story_issue, epic_issue = linear.issues[story.linear_id], linear.issues[epic.linear_id]
    assert story_issue.title == "[FR-EX01] [EXAMPLE] Request information about a property"
    assert linear.templates_used[story_issue.identifier] == "template-handoff"
    assert story_issue.description == ""  # the template body is used; the spec is not copied
    assert linear.parents[story_issue.identifier] == epic_issue.id
    assert linear.labels[story_issue.identifier] == ("Story", "Handoff")
    assert linear.labels[epic_issue.identifier] == ("Epic", "Handoff")
    assert (story_issue.id, "https://notion.so/story-1") in linear.links
    assert any("Write the spec in this issue" in body for _, body in linear.comments)


def test_sync_only_writes_status_and_link(env):
    notion, _, _ = env
    run(env)
    written = {name for _, values in notion.writes for name in values}
    assert written == {"Status", "Linear ID", "Linear issue"}


def test_missing_template_falls_back_to_its_headings(env):
    notion, linear, _ = env
    linear.template = None
    report = run(env)
    assert report.errors == []
    assert any("template 'Developer handoff' not found" in line for line in report.lines)
    issue = linear.issues[notion.items["story-1"].linear_id]
    assert linear.templates_used[issue.identifier] is None
    for heading in HANDOFF_HEADINGS:
        assert f"## {heading}" in issue.description
    assert "https://notion.so/story-1" in issue.description


def test_story_approved_too_early_goes_back_to_discovery(env):
    notion, _, _ = env
    run(env)
    story = notion.items["story-2"]
    assert story.status == "Discovery" and story.linear_id == ""
    text = notion.reports["story-2"][0]
    assert "No client approval" in text and "No prototype version" in text and "Blocking question open" in text


def test_second_run_creates_no_duplicates(env):
    notion, linear, _ = env
    run(env)
    count = len(linear.issues)
    notion.items["story-1"].status = "Approved"  # moved back by hand
    report = run(env)
    assert len(linear.issues) == count
    assert report.counts["linked"] == 1


def test_issue_created_by_hand_is_linked_not_overwritten(env):
    notion, linear, _ = env
    linear.add(LinearIssue(id="uuid-FRA-7", identifier="FRA-7", title="[FR-EX01] Written by hand",
                           url="https://linear.app/x/issue/FRA-7", description="My spec",
                           state_name="Todo", state_type="unstarted"), ("Story",))
    report = run(env)
    assert report.counts["linked"] == 1
    assert notion.items["story-1"].linear_id == "FRA-7"
    assert linear.issues["FRA-7"].description == "My spec"


def test_done_in_linear_means_awaiting_acceptance(env):
    notion, linear, _ = env
    run(env)
    _done(linear, notion.items["story-1"].linear_id)
    report = run(env)
    assert notion.items["story-1"].status == "Awaiting acceptance"
    assert report.counts["status"] == 1


def test_accepted_rows_are_left_alone(env):
    notion, linear, _ = env
    run(env)
    _done(linear, notion.items["story-1"].linear_id)
    notion.items["story-1"].status = "Accepted"
    before = len(notion.writes)
    run(env)
    assert len(notion.writes) == before


def test_canceled_in_linear_is_reported_not_written(env):
    notion, linear, _ = env
    run(env)
    _done(linear, notion.items["story-1"].linear_id, ("Canceled", "canceled"))
    before = len(notion.writes)
    report = run(env)
    assert len(notion.writes) == before
    assert any("canceled in Linear" in line for line in report.lines)


def test_canceled_issue_with_same_key_blocks(env):
    notion, linear, _ = env
    linear.add(LinearIssue(id="uuid-FRA-9", identifier="FRA-9", title="[FR-EX01] old",
                           url="", state_name="Canceled", state_type="canceled"), ("Story",))
    run(env)
    assert notion.items["story-1"].status == "Discovery"
    assert "is canceled" in notion.reports["story-1"][0]


def test_duplicate_issues_block(env):
    notion, linear, _ = env
    for n in (1, 2):
        linear.add(LinearIssue(id=f"uuid-FRA-{n}", identifier=f"FRA-{n}", title="[FR-EX01] copy",
                               url="", state_name="Todo", state_type="unstarted"), ("Story",))
    run(env)
    assert notion.items["story-1"].status == "Discovery"
    assert "Duplicate issues" in notion.reports["story-1"][0]


def test_examples_can_be_excluded(env, monkeypatch):
    notion, linear, _ = env
    monkeypatch.setenv("INCLUDE_EXAMPLES", "false")
    SyncEngine(notion, linear, Config.from_env(), apply=True).run()
    assert linear.issues == {} and notion.writes == []


def test_one_failing_row_does_not_stop_the_others(env):
    notion, linear, _ = env
    original = linear.find_by_key

    def broken(key):
        if key == "FR-EX02":
            raise RuntimeError("boom")
        return original(key)

    linear.find_by_key = broken
    report = run(env)
    assert any("boom" in e for e in report.errors)
    assert notion.items["story-1"].status == "In Linear"


def test_renamed_issue_is_found_by_linear_id(env):
    notion, linear, _ = env
    run(env)
    linear.issues[notion.items["story-1"].linear_id].title = "Renamed without the key"
    notion.items["story-1"].status = "Approved"
    before = len(linear.issues)
    run(env)
    assert len(linear.issues) == before


def test_missing_labels_stop_the_run_even_in_dry_run(env):
    notion, _, config = env
    report = SyncEngine(notion, FakeLinear(known_labels=("Story",)), config, apply=False).run()
    assert report.errors and "Linear setup check failed" in report.errors[0]


def test_two_stories_under_one_new_epic_create_one_epic(env):
    notion, linear, _ = env
    second = copy.deepcopy(STORY_PASS)
    second.page_id, second.key, second.url = "story-3", "FR-EX03", "https://notion.so/story-3"
    notion.items["story-3"] = second
    run(env)
    assert len([i for i in linear.issues.values() if i.title.startswith("[EP-EX01]")]) == 1


def test_unapproved_epic_blocks_the_story(env):
    notion, _, _ = env
    notion.items["epic-1"].status = "Discovery"
    run(env)
    assert notion.items["story-1"].status == "Discovery"
    assert "Epic not approved" in notion.reports["story-1"][0]


def test_rows_not_approved_are_ignored(env):
    notion, linear, _ = env
    notion.items["story-1"].status = "Idea"
    notion.items["story-2"].status = "Discovery"
    report = run(env)
    assert linear.issues == {} and notion.writes == []
    assert report.counts["blocked"] == 0


def test_non_story_rows_are_never_sent(env):
    notion, linear, _ = env
    notion.items["nfr"] = BacklogItem(page_id="nfr", url="", key="NFR-01", name="Bilingual",
                                      type="Non-functional", status="Approved", moscow="Must")
    run(env)
    assert not any(i.title.startswith("[NFR-01]") for i in linear.issues.values())
