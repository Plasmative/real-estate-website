"""Configuration, read from environment variables.

Secrets (NOTION_TOKEN, LINEAR_API_KEY, ANTHROPIC_API_KEY) come from GitHub
Actions secrets. Everything else has a default matching the current workspace
and can be overridden with an environment variable of the same name.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


@dataclass(frozen=True)
class Config:
    # Notion
    notion_token: str | None
    notion_version: str
    backlog_data_source_id: str

    # Linear
    linear_api_key: str | None
    linear_team_key: str
    linear_project_name: str
    linear_new_issue_state: str

    # AI review (optional: without a key, a keyword heuristic is used instead)
    anthropic_api_key: str | None
    anthropic_model: str

    # Behaviour
    include_examples: bool = True
    # Type label plus Origin › Handoff: everything the sync creates came through
    # the approved Notion flow. Exploration from worktrees is Origin › Free Will.
    story_labels: tuple[str, ...] = ("Story", "Handoff")
    epic_labels: tuple[str, ...] = ("Epic", "Handoff")
    sendable_moscow: tuple[str, ...] = ("Must", "Should", "Could")
    approved_epic_statuses: tuple[str, ...] = field(
        default=("Approved", "Ready for dev", "In Linear", "Awaiting acceptance", "Accepted")
    )

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            notion_token=_env("NOTION_TOKEN"),
            notion_version=_env("NOTION_VERSION", "2025-09-03"),
            backlog_data_source_id=_env(
                "NOTION_BACKLOG_DATA_SOURCE_ID", "63c22b26-e51b-4691-94c4-cb42b28c0c46"
            ),
            linear_api_key=_env("LINEAR_API_KEY"),
            linear_team_key=_env("LINEAR_TEAM_KEY", "FRA"),
            linear_project_name=_env("LINEAR_PROJECT_NAME", "Real Estate Website MVP"),
            linear_new_issue_state=_env("LINEAR_NEW_ISSUE_STATE", "Backlog"),
            anthropic_api_key=_env("ANTHROPIC_API_KEY"),
            anthropic_model=_env("ANTHROPIC_MODEL", "claude-sonnet-5-5"),
            include_examples=_env("INCLUDE_EXAMPLES", "true").lower() == "true",
        )

    def missing_secrets(self) -> list[str]:
        missing = []
        if not self.notion_token:
            missing.append("NOTION_TOKEN")
        if not self.linear_api_key:
            missing.append("LINEAR_API_KEY")
        return missing
