"""The way back for Free Will work: Linear proposal -> Notion row -> client approval -> Handoff."""

import copy

import pytest

from fakes import FakeLinear, FakeNotion
from fixtures import EPIC, STORY_PASS
from sync.config import Config
from sync.engine import SyncEngine, _next_story_key
from sync.models import BacklogItem, LinearIssue

FREE_WILL_SPEC = """> Explored in a worktree.

## User story

As a **buyer on my phone**, I want **a menu**, so that **I can move around**.

## Acceptance criteria

```gherkin
Scenario: Open the menu
  Given I am on any page
  When I tap the menu button
  Then I see the main sections
```

- [ ] Tested at 390 px
"""


def free_will_issue(identifier="FRA-50", labels=("Story", "Free Will", "Propose to client")):
    issue = LinearIssue(id=f"uuid-{identifier}", identifier=identifier, title="[UX-01] Mobile navigation menu",
                        url=f"https://linear.app/x/issue/{identifier}", description=FREE_WILL_SPEC,
                        state_name="In Progress", state_type="started")
    return issue, labels


@pytest.fixture
def env(monkeypatch):
    for var in ("INCLUDE_EXAMPLES", "LINEAR_NEW_ISSUE_STATE"):
        monkeypatch.delenv(var, raising=False)
    real_story = BacklogItem(page_id="fr-07", url="https://notion.so/fr-07", key="FR-07", name="Old story",
                             type="User story", status="Discovery")
    notion = FakeNotion([copy.deepcopy(EPIC), real_story])
    return notion, FakeLinear(), Config.from_env()


def run(env, apply=True):
    notion, linear, config = env
    return SyncEngine(notion, linear, config, apply=apply, today="2026-10-13").run()


def test_proposal_without_row_creates_a_request_row(env):
    notion, linear, _ = env
    linear.add(*free_will_issue())
    report = run(env)
    assert report.errors == []
    assert report.counts["proposed"] == 1
    [row] = notion.created
    assert row.key == "FR-08"  # next after FR-07; example keys do not count
    assert row.name == "Mobile navigation menu"  # [UX-01] prefix dropped
    assert row.status == "Discovery" and row.linear_id == "FRA-50"
    body = notion.bodies[row.page_id]
    assert "Gherkin" not in body and "Then I see" not in body  # the spec stays in Linear
    assert "FRA-50" in body
    assert "Sync note — proposed from Free Will FRA-50" in notion.reports[row.page_id][0]
    assert linear.labels["FRA-50"] == ("Story", "Free Will")  # proposal label consumed, still Free Will
    assert "Proposed to the client" in linear.comments[0][1]


def test_proposal_with_existing_row_only_adds_a_note(env):
    notion, linear, _ = env
    linear.add(*free_will_issue())
    notion.items["fr-07"].linear_id = "FRA-50"
    notion.items["fr-07"].status = "Idea"
    report = run(env)
    assert report.errors == []
    assert notion.created == []
    assert notion.items["fr-07"].status == "Discovery"  # raised so it can be approved
    assert "fr-07" in notion.reports
    assert linear.labels["FRA-50"] == ("Story", "Free Will")


def test_proposal_dry_run_writes_nothing(env):
    notion, linear, _ = env
    linear.add(*free_will_issue())
    report = run(env, apply=False)
    assert report.counts["proposed"] == 1
    assert notion.created == [] and notion.writes == [] and notion.reports == {}
    assert linear.comments == []
    assert "Propose to client" in linear.labels["FRA-50"]
    assert any("would create Notion row FR-08" in line for line in report.lines)


def test_proposal_label_on_handoff_issue_is_just_removed(env):
    notion, linear, _ = env
    linear.add(*free_will_issue(labels=("Story", "Handoff", "Propose to client")))
    report = run(env)
    assert report.counts["proposed"] == 0
    assert notion.created == []
    assert linear.labels["FRA-50"] == ("Story", "Handoff")


def test_approved_free_will_story_switches_to_handoff(monkeypatch):
    for var in ("INCLUDE_EXAMPLES", "LINEAR_NEW_ISSUE_STATE"):
        monkeypatch.delenv(var, raising=False)
    story = copy.deepcopy(STORY_PASS)  # approved by the client
    story.linear_id = "FRA-50"
    notion = FakeNotion([copy.deepcopy(EPIC), story])
    linear = FakeLinear()
    linear.add(*free_will_issue(labels=("Story", "Free Will")))
    report = SyncEngine(notion, linear, Config.from_env(), apply=True).run()
    assert report.errors == []
    assert linear.labels["FRA-50"] == ("Story", "Handoff")
    assert any("Approved by the client" in body for _, body in linear.comments)
    assert notion.items["story-1"].status == "In Linear"
    assert linear.issues["FRA-50"].description == FREE_WILL_SPEC  # the explored spec is kept


def test_next_story_key():
    items = [BacklogItem(page_id=str(n), url="", key=k, name="", type="User story", status="Idea")
             for n, k in enumerate(["FR-01", "FR-12", "FR-EX02", "EP-03", ""])]
    assert _next_story_key(items) == "FR-13"
    assert _next_story_key([]) == "FR-01"
