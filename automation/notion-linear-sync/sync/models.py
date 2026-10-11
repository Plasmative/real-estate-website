"""Plain data objects shared by the clients and the engine."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BacklogItem:
    """One row of the Notion Product Backlog."""

    page_id: str
    url: str
    key: str  # stable ID: EP-xx, FR-xx, NFR-xx
    name: str
    type: str  # Epic | User story | Non-functional
    status: str
    moscow: str | None = None
    confidence: str | None = None
    epic_page_ids: list[str] = field(default_factory=list)
    approved_in_ids: list[str] = field(default_factory=list)
    prototype_version: str = ""
    blocking_questions: bool = False
    linear_id: str = ""
    linear_url: str = ""
    linear_status: str | None = None
    example: bool = False

    @property
    def is_story(self) -> bool:
        return self.type == "User story"

    @property
    def is_epic(self) -> bool:
        return self.type == "Epic"


@dataclass
class LinearIssue:
    id: str  # Linear internal UUID
    identifier: str  # e.g. FRA-10
    title: str
    url: str
    description: str = ""
    state_name: str = ""
    state_type: str = ""  # backlog | unstarted | started | completed | canceled | triage


@dataclass
class CheckResult:
    """Outcome of the Definition of Ready for one story."""

    blocking: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.blocking
