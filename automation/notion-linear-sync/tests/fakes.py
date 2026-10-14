"""In-memory stand-ins for Notion and Linear, used by the tests.

They follow the real APIs where it matters:
- Notion keeps blocks in insertion order; reports become real toggle-heading blocks.
- Linear issues have an internal id that is NOT the FRA-xx identifier.
"""

from __future__ import annotations

import copy

from sync.markdown import markdown_to_blocks
from sync.models import BacklogItem, LinearIssue

_PROP_TO_ATTR = {
    "Status": "status",
    "Linear ID": "linear_id",
    "Linear issue": "linear_url",
}


class FakeNotion:
    def __init__(self, items: list[BacklogItem]):
        self.items = {i.page_id: i for i in items}
        self.bodies: dict[str, str] = {}
        self.reports: dict[str, list[str]] = {}
        self.writes: list[tuple[str, dict]] = []
        self.created: list[BacklogItem] = []

    def create_story(self, key, name, linear_id, linear_url, body_markdown):
        page_id = f"page-{key}"
        item = BacklogItem(page_id=page_id, url=f"https://notion.so/{page_id}", key=key, name=name,
                           type="User story", status="Discovery", linear_id=linear_id, linear_url=linear_url)
        self.items[page_id] = item
        markdown_to_blocks(body_markdown)  # must be convertible, like the real client
        self.bodies[page_id] = body_markdown
        self.created.append(item)
        return copy.deepcopy(item)

    def query_backlog(self) -> list[BacklogItem]:
        return [copy.deepcopy(i) for i in self.items.values()]

    def update_properties(self, page_id: str, values: dict) -> None:
        self.writes.append((page_id, values))
        for name, value in values.items():
            setattr(self.items[page_id], _PROP_TO_ATTR[name], value)

    def append_report(self, page_id: str, title: str, body_markdown: str) -> None:
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
        self.templates_used: dict[str, str | None] = {}  # identifier -> template id
        self.template = "template-handoff"  # None simulates a missing template
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
        return self._view(issue) if issue else None

    def template_id(self, name):
        return self.template if name == "Developer handoff" else None

    def create_issue(self, title, description, labels, parent_id, template_id=None):
        self.label_ids(labels)
        self._n += 1
        identifier = f"FRA-{100 + self._n}"
        issue = LinearIssue(id=f"uuid-{identifier}", identifier=identifier, title=title,
                            url=f"https://linear.app/x/issue/{identifier}", description=description or "",
                            state_name="Backlog", state_type="backlog")
        if parent_id:
            self._by_id(parent_id)  # parent must be a real internal id
        self.parents[identifier] = parent_id
        self.templates_used[identifier] = template_id
        return self.add(issue, labels)

    def add_link(self, issue_id, url, title):
        self._by_id(issue_id)
        self.links.append((issue_id, url))

    def comment(self, issue_id, body):
        self._by_id(issue_id)
        self.comments.append((issue_id, body))
