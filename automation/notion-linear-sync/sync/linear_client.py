"""Minimal Linear GraphQL client."""

from __future__ import annotations

import time

import requests

from .models import LinearIssue

LINEAR_API = "https://api.linear.app/graphql"

ISSUE_FIELDS = "id identifier title url description state { name type } labels { nodes { id name } }"


def _issue(node: dict) -> LinearIssue:
    state = node.get("state") or {}
    return LinearIssue(
        id=node["id"],
        identifier=node["identifier"],
        title=node.get("title", ""),
        url=node.get("url", ""),
        description=node.get("description") or "",
        state_name=state.get("name", ""),
        state_type=state.get("type", ""),
        labels={n["name"]: n["id"] for n in ((node.get("labels") or {}).get("nodes") or [])},
    )


class LinearClient:
    def __init__(self, api_key: str, team_key: str, project_name: str, new_issue_state: str,
                 session: requests.Session | None = None):
        self.session = session or requests.Session()
        # Personal API keys go in the Authorization header as-is (no "Bearer").
        self.session.headers.update({"Authorization": api_key, "Content-Type": "application/json"})
        self.team_key = team_key
        self.project_name = project_name
        self.new_issue_state = new_issue_state
        self._ctx: dict | None = None

    # -- HTTP ---------------------------------------------------------------
    def _gql(self, query: str, variables: dict | None = None) -> dict:
        for attempt in range(4):
            response = self.session.post(LINEAR_API, json={"query": query, "variables": variables or {}}, timeout=60)
            if response.status_code == 429 and attempt < 3:
                time.sleep(2 ** attempt)
                continue
            payload = response.json() if response.content else {}
            if response.status_code >= 400 or payload.get("errors"):
                raise RuntimeError(f"Linear API error: {response.status_code} {payload.get('errors') or response.text[:500]}")
            return payload["data"]
        raise RuntimeError("Linear API kept being rate limited")

    # -- Context: team, project, states, labels ------------------------------
    def context(self) -> dict:
        if self._ctx is None:
            data = self._gql(
                """query($key: String!, $project: String!) {
                  teams(filter: { key: { eq: $key } }) {
                    nodes { id key states { nodes { id name type } } }
                  }
                  projects(filter: { name: { eq: $project } }) { nodes { id name } }
                }""",
                {"key": self.team_key, "project": self.project_name},
            )
            teams = data["teams"]["nodes"]
            if not teams:
                raise RuntimeError(f"Linear team with key {self.team_key} not found")
            team = teams[0]
            projects = data["projects"]["nodes"]
            if not projects:
                raise RuntimeError(f"Linear project '{self.project_name}' not found")
            states = {s["name"]: s["id"] for s in team["states"]["nodes"]}
            if self.new_issue_state not in states:
                raise RuntimeError(f"Linear state '{self.new_issue_state}' not found in team {self.team_key}")
            self._ctx = {
                "team_id": team["id"],
                "project_id": projects[0]["id"],
                "state_id": states[self.new_issue_state],
                "labels": {},
            }
        return self._ctx

    def label_ids(self, names: tuple[str, ...]) -> list[str]:
        """Label IDs by name: the team's own label first, else a workspace label. Retired labels are ignored."""
        ctx = self.context()
        wanted = [n for n in names if n not in ctx["labels"]]
        if wanted:
            data = self._gql(
                """query($names: [String!]) {
                  issueLabels(filter: { name: { in: $names } }, first: 50) {
                    nodes { id name retiredAt team { id } }
                  }
                }""",
                {"names": wanted},
            )
            for node in data["issueLabels"]["nodes"]:
                if node.get("retiredAt"):
                    continue
                team = (node.get("team") or {}).get("id")
                if team == ctx["team_id"] or (team is None and node["name"] not in ctx["labels"]):
                    ctx["labels"][node["name"]] = node["id"]
        missing = [n for n in names if n not in ctx["labels"]]
        if missing:
            raise RuntimeError(f"Linear labels not found for team {self.team_key}: {missing}")
        return [ctx["labels"][n] for n in names]

    # -- Reads ----------------------------------------------------------------
    def find_by_key(self, key: str) -> list[LinearIssue]:
        """Issues whose title starts with '[KEY]'. Includes archived and canceled ones."""
        data = self._gql(
            f"""query($team: ID!, $prefix: String!) {{
              issues(filter: {{ team: {{ id: {{ eq: $team }} }}, title: {{ startsWith: $prefix }} }},
                     includeArchived: true, first: 10) {{ nodes {{ {ISSUE_FIELDS} }} }}
            }}""",
            {"team": self.context()["team_id"], "prefix": f"[{key}]"},
        )
        return [_issue(n) for n in data["issues"]["nodes"]]

    def find_by_label(self, label: str) -> list[LinearIssue]:
        """Open issues of the team (not completed or canceled) that carry this label."""
        data = self._gql(
            f"""query($team: ID!, $label: String!) {{
              issues(filter: {{ team: {{ id: {{ eq: $team }} }},
                                labels: {{ name: {{ eq: $label }} }},
                                state: {{ type: {{ nin: ["completed", "canceled"] }} }} }},
                     first: 50) {{ nodes {{ {ISSUE_FIELDS} }} }}
            }}""",
            {"team": self.context()["team_id"], "label": label},
        )
        return [_issue(n) for n in data["issues"]["nodes"]]

    def get_issue(self, identifier: str) -> LinearIssue | None:
        try:
            data = self._gql(f"query($id: String!) {{ issue(id: $id) {{ {ISSUE_FIELDS} }} }}", {"id": identifier})
        except RuntimeError as exc:
            # Linear answers an unknown issue with an "Entity not found" GraphQL error.
            if "not found" in str(exc).lower():
                return None
            raise
        node = data.get("issue")
        return _issue(node) if node else None

    # -- Writes ---------------------------------------------------------------
    def create_issue(self, title: str, description: str, labels: tuple[str, ...], parent_id: str | None) -> LinearIssue:
        ctx = self.context()
        issue_input = {
            "teamId": ctx["team_id"],
            "projectId": ctx["project_id"],
            "stateId": ctx["state_id"],
            "title": title,
            "description": description,
            "labelIds": self.label_ids(labels),
        }
        if parent_id:
            issue_input["parentId"] = parent_id
        data = self._gql(
            f"""mutation($input: IssueCreateInput!) {{
              issueCreate(input: $input) {{ success issue {{ {ISSUE_FIELDS} }} }}
            }}""",
            {"input": issue_input},
        )
        return _issue(data["issueCreate"]["issue"])

    def update_description(self, issue_id: str, description: str) -> None:
        self._gql(
            """mutation($id: String!, $description: String!) {
              issueUpdate(id: $id, input: { description: $description }) { success }
            }""",
            {"id": issue_id, "description": description},
        )

    def set_labels(self, issue: LinearIssue, add: tuple[str, ...] = (), remove: tuple[str, ...] = ()) -> None:
        """Add and remove labels by name, keeping every other label the issue has."""
        keep = [label_id for name, label_id in issue.labels.items() if name not in remove]
        new_ids = [i for i in self.label_ids(tuple(add)) if i not in keep] if add else []
        self._gql(
            """mutation($id: String!, $labels: [String!]) {
              issueUpdate(id: $id, input: { labelIds: $labels }) { success }
            }""",
            {"id": issue.id, "labels": keep + new_ids},
        )

    def add_link(self, issue_id: str, url: str, title: str) -> None:
        self._gql(
            """mutation($id: String!, $url: String!, $title: String) {
              attachmentLinkURL(issueId: $id, url: $url, title: $title) { success }
            }""",
            {"id": issue_id, "url": url, "title": title},
        )

    def comment(self, issue_id: str, body: str) -> None:
        self._gql(
            """mutation($id: String!, $body: String!) {
              commentCreate(input: { issueId: $id, body: $body }) { success }
            }""",
            {"id": issue_id, "body": body},
        )
