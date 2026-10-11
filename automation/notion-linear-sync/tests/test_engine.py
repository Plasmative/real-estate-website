import copy

import pytest

from fakes import FakeLinear, FakeNotion
from fixtures import (
    EPIC, EPIC_BLOCKS, STORY_FAIL, STORY_FAIL_BLOCKS, STORY_PASS, STORY_PASS_BLOCKS, bullet,
)
from sync.ai_review import HeuristicReviewer
from sync.config import Config
from sync.engine import SyncEngine
from sync.markdown import NOTES_HEADING
from sync.models import LinearIssue


@pytest.fixture
def env(monkeypatch):
    for var in ("INCLUDE_EXAMPLES", "LINEAR_NEW_ISSUE_STATE"):
        monkeypatch.delenv(var, raising=False)
    notion = FakeNotion(
        [copy.deepcopy(EPIC), copy.deepcopy(STORY_PASS), copy.deepcopy(STORY_FAIL)],
        {"epic-1": copy.deepcopy(EPIC_BLOCKS), "story-1": copy.deepcopy(STORY_PASS_BLOCKS),
         "story-2": copy.deepcopy(STORY_FAIL_BLOCKS)},
    )
    return notion, FakeLinear(), Config.from_env()


def run(env, apply=True):
    notion, linear, config = env
    return SyncEngine(notion, linear, HeuristicReviewer(), config, apply=apply, today="2026-10-11").run()


def test_dry_run_changes_nothing(env):
    notion, linear, _ = env
    report = run(env, apply=False)
    assert linear.issues == {}
    assert notion.writes == []
    assert notion.reports == {}
    assert report.counts["created"] == 1
    assert report.counts["blocked"] == 1
    assert "DRY RUN" in report.markdown()


def test_passing_story_creates_epic_and_story(env):
    notion, linear, _ = env
    report = run(env)
    assert report.errors == []
    story = notion.items["story-1"]
    epic = notion.items["epic-1"]
    assert story.status == "In Linear"
    assert epic.status == "In Linear"
    story_issue = linear.issues[story.linear_id]
    epic_issue = linear.issues[epic.linear_id]
    assert story_issue.title == "[FR-EX01] [EXAMPLE] Request information about a property"
    assert linear.parents[story_issue.identifier] == epic_issue.id
    assert linear.labels[story_issue.identifier] == ("Story",)
    assert linear.labels[epic_issue.identifier] == ("Epic",)
    assert "spec-hash:" in story_issue.description
    assert NOTES_HEADING in story_issue.description
    assert (story_issue.id, "https://notion.so/story-1") in linear.links
    # Spec synced at is the very last write on the story row.
    story_writes = [values for page, values in notion.writes if page == "story-1"]
    assert list(story_writes[-1]) == ["Spec synced at"]
    # Passing report appended to Notion; warnings commented on Linear.
    assert "Passed" in notion.reports["story-1"][0]
    assert any(issue == story_issue.id for issue, _ in linear.comments)


def test_failing_story_is_blocked_and_reported(env):
    notion, linear, _ = env
    run(env)
    story = notion.items["story-2"]
    assert story.status == "Specified"
    assert not story.linear_id
    assert not any(i.title.startswith("[FR-EX02]") for i in linear.issues.values())
    report = notion.reports["story-2"][0]
    for gap in ("No client approval", "No prototype version", "Blocking question open", "Only the happy path"):
        assert gap in report


def test_second_run_creates_no_duplicates(env):
    notion, linear, _ = env
    run(env)
    created = set(linear.issues)
    # Someone sets the story back to Ready for dev: the sync must update, not create.
    notion.items["story-1"].status = "Ready for dev"
    report = run(env)
    assert set(linear.issues) == created
    assert report.counts["updated"] == 1
    assert report.counts["created"] == 0


def test_unchanged_spec_is_left_alone(env):
    notion, linear, _ = env
    run(env)
    comments_before = len(linear.comments)
    report = run(env)  # the appended DoR report must not count as a spec change
    assert report.counts["spec_changes"] == 0
    assert len(linear.comments) == comments_before


def test_spec_change_comments_diff_and_keeps_developer_notes(env):
    notion, linear, _ = env
    run(env)
    issue = linear.issues[notion.items["story-1"].linear_id]
    issue.description = issue.description.replace(
        "*Free section: write technical notes here. The sync never overwrites it.*", "Use the Resend API.")
    notion.blocks["story-1"].append(bullet("Clicking twice in a row sends one inquiry."))
    report = run(env)
    assert report.counts["spec_changes"] == 1
    body = linear.comments[-1][1]
    assert "Spec changed in Notion" in body and "+- Clicking twice in a row sends one inquiry." in body
    assert "Clicking twice in a row" in issue.description
    assert "Use the Resend API." in issue.description


def test_done_in_linear_means_awaiting_acceptance(env):
    notion, linear, _ = env
    run(env)
    issue = linear.issues[notion.items["story-1"].linear_id]
    issue.state_name, issue.state_type = "Done", "completed"
    run(env)
    assert notion.items["story-1"].linear_status == "Done"
    assert notion.items["story-1"].status == "Awaiting acceptance"


def test_issue_created_by_hand_is_adopted_without_losing_text(env):
    notion, linear, _ = env
    epic_issue = linear.add(LinearIssue(id="uuid-9", identifier="FRA-9", title="[EP-EX01] Epic", url="u",
                                        description="## Notes\n\nKeep me", state_name="Backlog", state_type="backlog"))
    linear.add(LinearIssue(id="uuid-10", identifier="FRA-10", title="[FR-EX01] Story", url="u",
                           description="Old spec\n\n## Developer notes\n\nMy notes", state_name="Backlog",
                           state_type="backlog"))
    story = notion.items["story-1"]
    story.status, story.linear_id = "In Linear", "FRA-10"
    epic = notion.items["epic-1"]
    epic.status, epic.linear_id = "In Linear", "FRA-9"
    report = run(env)
    assert report.counts["spec_changes"] == 2
    assert "My notes" in linear.issues["FRA-10"].description
    assert "Keep me" in linear.issues["FRA-9"].description
    assert all("adopted" in body for _, body in linear.comments)
    assert set(linear.issues) == {"FRA-9", "FRA-10"}
    assert epic_issue.identifier == "FRA-9"


def test_canceled_issue_with_same_key_blocks(env):
    notion, linear, _ = env
    linear.add(LinearIssue(id="uuid-50", identifier="FRA-50", title="[FR-EX01] old", url="u",
                           state_name="Canceled", state_type="canceled"))
    run(env)
    assert notion.items["story-1"].status == "Specified"
    assert "is canceled" in notion.reports["story-1"][0]


def test_duplicate_issues_block(env):
    notion, linear, _ = env
    for n in (51, 52):
        linear.add(LinearIssue(id=f"uuid-{n}", identifier=f"FRA-{n}", title="[FR-EX01] dup", url="u",
                               state_name="Backlog", state_type="backlog"))
    run(env)
    assert notion.items["story-1"].status == "Specified"
    assert "Duplicate issues in Linear" in notion.reports["story-1"][0]


def test_examples_can_be_excluded(env, monkeypatch):
    notion, linear, _ = env
    monkeypatch.setenv("INCLUDE_EXAMPLES", "false")
    report = SyncEngine(notion, linear, HeuristicReviewer(), Config.from_env(), apply=True).run()
    assert linear.issues == {}
    assert report.counts == {"created": 0, "updated": 0, "blocked": 0, "mirrored": 0, "spec_changes": 0}


def test_one_failing_row_does_not_stop_the_others(env):
    notion, linear, _ = env

    def boom(page_id):
        if page_id == "story-2":
            raise RuntimeError("Notion is down for this page")
        return FakeNotion.page_markdown(notion, page_id)

    notion.page_markdown = boom
    report = run(env)
    assert any("FR-EX02" in e for e in report.errors)
    assert notion.items["story-1"].status == "In Linear"


# --- regressions found in review ------------------------------------------------

def test_renamed_issue_is_found_by_linear_id_not_duplicated(env):
    notion, linear, _ = env
    run(env)
    story = notion.items["story-1"]
    linear.issues[story.linear_id].title = "Inquiry form"  # developer renamed it
    first_id = story.linear_id
    story.status = "Ready for dev"
    report = run(env)
    assert notion.items["story-1"].linear_id == first_id
    assert report.counts["created"] == 0 and report.counts["updated"] == 1
    assert len(linear.issues) == 2  # epic + story, nothing new


def test_edit_added_below_a_report_is_still_detected(env):
    notion, linear, _ = env
    run(env)  # appends a report at the bottom of the page
    notion.blocks["story-1"].append(bullet("New requirement written after the report."))
    report = run(env)
    assert report.counts["spec_changes"] == 1
    assert "New requirement written after the report." in linear.issues[notion.items["story-1"].linear_id].description


def test_developer_text_kept_when_notes_heading_deleted(env):
    notion, linear, _ = env
    run(env)
    issue = linear.issues[notion.items["story-1"].linear_id]
    head, _ = issue.description.split("## Developer notes")
    issue.description = head.rstrip().removesuffix("---").rstrip() + "\n\nUse the Resend API, see PR #4."
    notion.blocks["story-1"].append(bullet("Another requirement."))
    run(env)
    assert "Use the Resend API, see PR #4." in issue.description


def test_canceled_epic_blocks_the_story(env):
    notion, linear, _ = env
    linear.add(LinearIssue(id="uuid-70", identifier="FRA-70", title="[EP-EX01] epic", url="u",
                           state_name="Canceled", state_type="canceled"))
    run(env)
    assert notion.items["story-1"].status == "Specified"
    assert "FRA-70 (EP-EX01) is canceled" in notion.reports["story-1"][0]


def test_spec_update_waits_if_issue_is_being_edited(env):
    notion, linear, _ = env
    run(env)
    identifier = notion.items["story-1"].linear_id
    notion.blocks["story-1"].append(bullet("Change."))
    linear.edit_during_next_read = identifier  # first read returns the old text; then someone types
    report = run(env)
    assert "Typed meanwhile." in linear.issues[identifier].description
    assert "Change." not in linear.issues[identifier].description
    assert any("postponed" in line for line in report.lines)
    run(env)  # next run applies it
    assert "Change." in linear.issues[identifier].description


def test_dry_run_of_spec_change_and_mirror_writes_nothing(env):
    notion, linear, _ = env
    run(env)
    identifier = notion.items["story-1"].linear_id
    notion.blocks["story-1"].append(bullet("Change."))
    linear.issues[identifier].state_name, linear.issues[identifier].state_type = "Done", "completed"
    writes, comments = len(notion.writes), len(linear.comments)
    description = linear.issues[identifier].description
    report = run(env, apply=False)
    assert report.counts["spec_changes"] == 1 and report.counts["mirrored"] == 1
    assert len(notion.writes) == writes and len(linear.comments) == comments
    assert linear.issues[identifier].description == description


def test_missing_labels_stop_the_run_even_in_dry_run(env):
    notion, _, config = env
    linear = FakeLinear(known_labels=("Story",))
    report = SyncEngine(notion, linear, HeuristicReviewer(), config, apply=False).run()
    assert report.errors and "Epic" in report.errors[0]
    assert report.counts["created"] == 0


def test_two_stories_under_one_new_epic_create_one_epic(env):
    notion, linear, _ = env
    second = copy.deepcopy(STORY_PASS)
    second.page_id, second.key, second.name, second.url = "story-3", "FR-EX03", "Second story", "https://notion.so/story-3"
    notion.items["story-3"] = second
    notion.blocks["story-3"] = copy.deepcopy(STORY_PASS_BLOCKS)
    report = run(env)
    epics = [i for i in linear.issues.values() if i.title.startswith("[EP-EX01]")]
    assert len(epics) == 1
    assert report.counts["created"] == 2
    assert linear.parents[notion.items["story-3"].linear_id] == epics[0].id


def test_postponed_update_does_not_stamp_sync_time(env):
    notion, linear, _ = env
    run(env)
    story = notion.items["story-1"]
    stamped = story.spec_synced_at
    notion.blocks["story-1"].append(bullet("Change."))
    linear.edit_during_next_read = story.linear_id
    story.status = "Ready for dev"  # pass 1 path
    run(env)
    assert notion.items["story-1"].spec_synced_at == stamped


def test_epic_without_id_blocks(env):
    notion, linear, _ = env
    notion.items["epic-1"].key = ""
    run(env)
    assert notion.items["story-1"].status == "Specified"
    assert "Epic has no ID" in notion.reports["story-1"][0]
    assert linear.issues == {}
