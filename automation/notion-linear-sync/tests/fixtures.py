"""Example rows from the Notion Product Backlog, as the sync reads them."""

from __future__ import annotations

from sync.models import BacklogItem

EPIC = BacklogItem(page_id="epic-1", url="https://notion.so/epic-1", key="EP-EX01",
                   name="[EXAMPLE] Buyer inquiries and engagement", type="Epic", status="Approved",
                   moscow="Must", example=True)

# Approved by the client: every client field is filled in.
STORY_PASS = BacklogItem(page_id="story-1", url="https://notion.so/story-1", key="FR-EX01",
                         name="[EXAMPLE] Request information about a property", type="User story",
                         status="Approved", moscow="Must", confidence="🟡 Assumption",
                         epic_page_ids=["epic-1"], approved_in_ids=["session-1"],
                         prototype_version="Property page v0.1", kpi_ids=["kpi-1"], example=True)

# Set to Approved too early: no client session, no prototype, a blocking question.
STORY_FAIL = BacklogItem(page_id="story-2", url="https://notion.so/story-2", key="FR-EX02",
                         name="[EXAMPLE] Save favourite properties", type="User story",
                         status="Approved", moscow="Should", confidence="🟡 Assumption",
                         epic_page_ids=["epic-1"], blocking_questions=True, example=True)

# The request as written on the Notion page of STORY_PASS (Markdown, as the Notion client returns it).
STORY_PASS_BODY = """> 🧪 **Test data.** Fictional story.

## User story

As a **buyer**, I want to **send a question from the property page**, so that **an agent replies**.

## User context

The buyer is often abroad, on a phone.

## Why it matters

- **KPI it supports:** inquiries per property per month.

## Client approval

- **Approved in:** [EXAMPLE] Prototype approval

## Out of scope for this version

- Saving inquiries in a CRM

## Open questions

- None blocking.

## Notes from the client

- Prefers a short form.
"""
