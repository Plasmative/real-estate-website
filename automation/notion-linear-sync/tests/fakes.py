"""In-memory stand-ins for Notion and Linear, used by the tests.

They follow the real APIs where it matters:
- Notion keeps blocks in insertion order; reports become real toggle-heading blocks.
- Linear issues have an internal id that is NOT the FRA-xx identifier.
"""

from __future__ import annotations

import copy

from sync.markdown import blocks_to_markdown, report_block
from sync.models import BacklogItem, LinearIssue

_PROP_TO_ATTR = {
    "Status": "status",
    "Linear ID": "linear_id",
    "Linear issue": "linear_url",
    "Linear status": "linear_status",
    "Spec synced at": "spec_synced_at",
}


class FakeNotion:
    def __init__(self, items: list[BacklogItem], blocks_by_page: dict[str, list[dict]]):
        self.items = {i.page_id: i for i in items}
        self.blocks = blocks_by_page
        self.reports: dict[str, list[str]] = {}
        self.writes: list[tuple[str, dict]] = []
        self.created: list[BacklogItem] = []

    def create_story(self, key, name, linear_id, linear_url, body_markdown):
        from sync.markdown import markdown_to_blocks
        page_id = f"page-{key}"
        item = BacklogItem(page_id=page_id, url=f"https://notion.so/{page_id}", key=key, name=name,
                           type="User story", status="Specified", linear_id=linear_id, linear_url=linear_url)
        self.items[page_id] = item
        self.blocks[page_id] = markdown_to_blocks(body_markdown)
        self.created.append(item)
        return copy.deepcopy(item)

    def query_backlog(self) -> list[BacklogItem]:
        return [copy.deepcopy(i) for i in self.items.values()]

    def page_markdown(self, page_id: str) -> str:
        return blocks_to_markdown(self.blocks.get(page_id, []))

    def update_properties(self, page_id: str, values: dict) -> None:
        self.writes.append((page_id, values))
        for name, value in values.items():
            setattr(self.items[page_id], _PROP_TO_ATTR[name], value)

    def append_report(self, page_id: str, title: str, body_markdown: str) -> None:
        block = report_block(title, body_markdown)
        block["heading_3"]["rich_text"] = [{"plain_text": title, "text": {"content": title}}]
        block["children"] = block["heading_3"].pop("children")
        self.blocks.setdefault(page_id, []).append(block)
        self.reports.setdefault(page_id, []).append(title + "\n" + body_markdown)


class FakeLinear:
    new_issue_state = "Backlog"

    def __init__(self, known_labels=("Story", "Epic", "Handoff", "Free Will", "Propose to client")):
        self.issues: dict[str, LinearIssue] = {}  # by identifier
        self.parents: dict[str, str | None] = {}
        self.labels: dict[str, tuple[str, ...]] = {}
        self.links: list[tuple[str, str]] = []
        self.comments: list[tuple[str, str]] = []
        self.known_labels = set(known_labels)
        self.edit_during_next_read: str | None = None  # simulate a developer typing meanwhile
        self._n = 0

    def _by_id(self, issue_id: str) -> LinearIssue:
        for issue in self.issues.values():
            if issue.id == issue_id:
                return issue
        raise KeyError(f"unknown internal id {issue_id} (identifier passed instead of id?)")

    def add(self, issue: LinearIssue, labels: tuple[str, ...] = ()) -> LinearIssue:
        self.issues[issue.identifier] = issue
        if labels or issue.identifier not in self.labels:
            self.labels[issue.identifier] = tuple(labels)
        return issue

    def _view(self, issue: LinearIssue) -> LinearIssue:
        view = copy.deepcopy(issue)
        view.labels = {name: f"label-{name}" for name in self.labels.get(issue.identifier, ())}
        return view

    def find_by_label(self, label):
        return [self._view(i) for i in self.issues.values()
                if label in self.labels.get(i.identifier, ()) and i.state_type not in ("completed", "canceled")]

    def set_labels(self, issue, add=(), remove=()):
        self.label_ids(tuple(add))
        current = [n for n in self.labels.get(issue.identifier, ()) if n not in remove]
        self.labels[issue.identifier] = tuple(current + [n for n in add if n not in current])

    def label_ids(self, names):
        missing = [n for n in names if n not in self.known_labels]
        if missing:
            raise RuntimeError(f"Linear labels not found: {missing}")
        return [f"label-{n}" for n in names]

    def find_by_key(self, key: str) -> list[LinearIssue]:
        return [self._view(i) for i in self.issues.values() if i.title.startswith(f"[{key}]")]

    def get_issue(self, identifier: str) -> LinearIssue | None:
        issue = self.issues.get(identifier)
        if issue and self.edit_during_next_read == identifier:
            self.edit_during_next_read = None
            snapshot = self._view(issue)
            issue.description += "\nTyped meanwhile."
            return snapshot
        return self._view(issue) if issue else None

    def create_issue(self, title, description, labels, parent_id):
        self.label_ids(labels)
        self._n += 1
        identifier = f"FRA-{100 + self._n}"
        issue = LinearIssue(id=f"uuid-{identifier}", identifier=identifier, title=title,
                            url=f"https://linear.app/x/issue/{identifier}", description=description,
                            state_name="Backlog", state_type="backlog")
        if parent_id:
            self._by_id(parent_id)  # parent must be a real internal id
        self.parents[identifier] = parent_id
        return self.add(issue, labels)

    def update_description(self, issue_id, description):
        self._by_id(issue_id).description = description

    def add_link(self, issue_id, url, title):
        self._by_id(issue_id)
        self.links.append((issue_id, url))

    def comment(self, issue_id, body):
        self._by_id(issue_id)
        self.comments.append((issue_id, body))


class FixedReviewer:
    """Returns a preset verdict, to test how the Definition of Ready uses it."""

    def __init__(self, verdict):
        self.verdict = verdict
        self.calls = 0

    def review(self, story_key, body_markdown, scenarios):
        self.calls += 1
        return self.verdict
