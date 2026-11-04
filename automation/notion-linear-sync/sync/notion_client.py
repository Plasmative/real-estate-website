"""Minimal Notion API client for the Product Backlog data source."""

from __future__ import annotations

import time

import requests

from .markdown import markdown_to_blocks, report_block
from .models import BacklogItem

NOTION_API = "https://api.notion.com/v1"


def _plain(rich_text: list[dict] | None) -> str:
    return "".join(rt.get("plain_text", "") for rt in rich_text or [])


def _select(prop: dict | None) -> str | None:
    value = (prop or {}).get("select")
    return value.get("name") if value else None


def norm_id(page_id: str) -> str:
    return page_id.replace("-", "").lower()


def parse_item(page: dict) -> BacklogItem:
    props = page.get("properties", {})
    return BacklogItem(
        page_id=page["id"],
        url=page.get("url", ""),
        key=_plain(props.get("ID", {}).get("rich_text")).strip(),
        name=_plain(props.get("Name", {}).get("title")).strip(),
        type=_select(props.get("Type")) or "",
        status=_select(props.get("Status")) or "",
        moscow=_select(props.get("MoSCoW")),
        confidence=_select(props.get("Confidence")),
        epic_page_ids=[r["id"] for r in props.get("Epic", {}).get("relation", [])],
        approved_in_ids=[r["id"] for r in props.get("Approved in", {}).get("relation", [])],
        prototype_version=_plain(props.get("Prototype version", {}).get("rich_text")).strip(),
        blocking_questions=bool(props.get("Blocking questions", {}).get("checkbox")),
        linear_id=_plain(props.get("Linear ID", {}).get("rich_text")).strip(),
        linear_url=props.get("Linear issue", {}).get("url") or "",
        kpi_ids=[r["id"] for r in props.get("KPIs", {}).get("relation", [])],
        example=bool(props.get("Example (test data)", {}).get("checkbox")),
    )


class NotionClient:
    def __init__(self, token: str, version: str, data_source_id: str, session: requests.Session | None = None):
        self.data_source_id = data_source_id
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Notion-Version": version,
                "Content-Type": "application/json",
            }
        )

    # -- HTTP ---------------------------------------------------------------
    def _request(self, method: str, path: str, **kwargs) -> dict:
        for attempt in range(4):
            response = self.session.request(method, f"{NOTION_API}{path}", timeout=60, **kwargs)
            if response.status_code == 429 and attempt < 3:  # rate limited
                time.sleep(float(response.headers.get("Retry-After", 1)))
                continue
            if response.status_code >= 400:
                raise RuntimeError(f"Notion {method} {path} failed: {response.status_code} {response.text[:500]}")
            return response.json()
        raise RuntimeError(f"Notion {method} {path} kept being rate limited")

    # -- Reads ----------------------------------------------------------------
    def query_backlog(self) -> list[BacklogItem]:
        items: list[BacklogItem] = []
        body: dict = {"page_size": 100}
        while True:
            data = self._request("POST", f"/data_sources/{self.data_source_id}/query", json=body)
            items.extend(parse_item(p) for p in data.get("results", []) if p.get("object") == "page")
            if not data.get("has_more"):
                return items
            body["start_cursor"] = data["next_cursor"]

    # -- Writes ---------------------------------------------------------------
    def update_properties(self, page_id: str, values: dict) -> None:
        """values: logical names -> Python values (see _to_notion)."""
        properties = {name: _to_notion(name, value) for name, value in values.items()}
        self._request("PATCH", f"/pages/{page_id}", json={"properties": properties})

    def create_story(self, key: str, name: str, linear_id: str, linear_url: str, body_markdown: str) -> BacklogItem:
        """New User story row in the Product Backlog, Status Discovery, waiting for the client."""
        blocks = markdown_to_blocks(body_markdown)
        page = self._request("POST", "/pages", json={
            "parent": {"type": "data_source_id", "data_source_id": self.data_source_id},
            "properties": {
                "Name": {"title": [{"type": "text", "text": {"content": name[:2000]}}]},
                "ID": {"rich_text": [{"type": "text", "text": {"content": key}}]},
                "Type": {"select": {"name": "User story"}},
                "Status": _to_notion("Status", "Discovery"),
                "Source": {"select": {"name": "Team"}},
                "Linear ID": _to_notion("Linear ID", linear_id),
                "Linear issue": _to_notion("Linear issue", linear_url),
            },
            "children": blocks[:100],  # API limit per call
        })
        for start in range(100, len(blocks), 100):
            self._request("PATCH", f"/blocks/{page['id']}/children", json={"children": blocks[start:start + 100]})
        return parse_item(page)

    def append_report(self, page_id: str, title: str, body_markdown: str) -> None:
        """Append a report as one collapsible heading."""
        block = report_block(title, body_markdown)
        block["heading_3"]["children"] = block["heading_3"]["children"][:100]  # API limit per call
        self._request("PATCH", f"/blocks/{page_id}/children", json={"children": [block]})


_SELECT_PROPS = {"Status"}
_TEXT_PROPS = {"Linear ID"}
_URL_PROPS = {"Linear issue"}


def _to_notion(name: str, value):
    if name in _SELECT_PROPS:
        return {"select": {"name": value} if value else None}
    if name in _TEXT_PROPS:
        return {"rich_text": [{"type": "text", "text": {"content": value}}] if value else []}
    if name in _URL_PROPS:
        return {"url": value or None}
    raise ValueError(f"The sync is not allowed to write the Notion property '{name}'")
