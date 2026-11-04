# Notion → Linear sync

Opens the Linear issue for a client request once the client approves it in the Notion
**Product Backlog**, and tells Notion when the work is done so the client can accept it.

`release v0.2.0 · designed by Francella Fernández & Claude`

## Who owns what

- **Notion** holds what the client asked for and decided: the request, MoSCoW, *Approved in*, *Prototype version*, *Accepted in*, the KPI.
- **Linear** holds the developer spec (Gherkin, edge cases, design, technical notes), status, cycles and milestones. The issue is created from the **Developer handoff** template.
- The sync **never copies or compares the spec**. It writes only *Status*, *Linear ID* and *Linear issue* on existing Notion rows.

## What it does

Each run makes one pass over Linear and two over the Product Backlog:

| Pass | Reads | Writes |
| --- | --- | --- |
| **0. Preflight** | Linear team, project, state, labels, template | Nothing. Stops the run, even a dry run, if the team, project, state or labels are missing. A missing template is only a warning: new issues then get its headings as plain text. |
| **P. Free Will proposals** | Open Linear issues labelled *Propose to client* | Only for issues that are *Free Will*. If no Notion row has that *Linear ID*, creates one: next free `FR-xx` key, Type *User story*, Status *Discovery*, with a short note pointing to the issue (the spec stays in Linear). If a row exists and is *Idea*, raises it to *Discovery*. Either way, appends a collapsed "Sync note", removes *Propose to client* and comments the Notion link on the issue. |
| **1. Approved stories** | Rows with Type *User story* and Status *Approved* | Runs the Definition of Ready. **Blocked:** appends the gaps (collapsed) and moves the row back to *Discovery*. **Passed:** creates the epic issue if needed and the story issue from the *Developer handoff* template, links the Notion row and comments that the spec is to be written there. If an issue for that ID already exists, it is linked, never overwritten; a *Free Will* one switches to *Handoff*. Writes *Status* = *In Linear*, *Linear ID* and *Linear issue*. |
| **2. Status** | Story rows *In Linear* | Done in Linear → *Awaiting acceptance* (Done is not accepted by the client). Canceled in Linear → reported, not written: decide *Out of scope* or *Change requested* with the client. |

### Definition of Ready (client side only)

Blocks: no ID, not a user story, no epic or epic not *Approved*, MoSCoW not Must/Should/Could, no *Approved in*, no *Prototype version*, *Blocking questions* ticked, duplicate or canceled issue for the same ID.
Warns: no KPI linked, confidence only 🟡 Assumption.

The developer spec is reviewed in Linear (PR review against the Gherkin), not by the sync.

### Rules it relies on

- **One key per item.** The Linear title starts with the Notion ID (`[FR-03] …`). Before creating anything, the script looks up the row's *Linear ID* (so a renamed issue is still found) and searches Linear for the key. Two issues for the same item, or a canceled one, block the story until a person decides.
- **Free Will never reaches the client by itself.** The Origin label switches to Handoff only when the row passes the Definition of Ready, which requires *Approved in*.
- **Dry run by default.** Nothing is written without `--apply`.

## Setup (once)

1. **Notion integration.** In Notion, *Settings → Connections → Develop or manage integrations → New integration* (internal). Copy the token. Then open the **Product Backlog** database, *⋯ → Connections*, and add the integration.
2. **Linear API key.** In Linear, *Settings → Security & access → Personal API keys → New key*.
3. **Linear template.** *Settings → Teams → FRA → Templates → New template* named **Developer handoff**, with the sections User story · User context · Why it matters · Client approval · Acceptance criteria (Gherkin) · Edge cases · Out of scope · Design and references · Dependencies · Open questions · Definition of done · Developer notes.
4. **GitHub secrets.** *Settings → Secrets and variables → Actions → New repository secret*: `NOTION_TOKEN` and `LINEAR_API_KEY`. (`ANTHROPIC_API_KEY` is no longer used and can be deleted.)
5. **First run, as a dry run.** *Actions → Notion → Linear sync → Run workflow*, with *apply* unticked. Read the summary.
6. **When the dry run looks right**, run it again with *apply* ticked. To let the weekday schedule write too, add the repository variable `SYNC_APPLY` = `true`. Scheduled runs always skip rows marked *Example (test data)*.

## Configuration

| Variable | Default |
| --- | --- |
| `NOTION_BACKLOG_DATA_SOURCE_ID` | `63c22b26-e51b-4691-94c4-cb42b28c0c46` |
| `NOTION_VERSION` | `2025-09-03` |
| `LINEAR_TEAM_KEY` | `FRA` |
| `LINEAR_PROJECT_NAME` | `Real Estate Website MVP` |
| `LINEAR_NEW_ISSUE_STATE` | `Backlog` |
| `LINEAR_HANDOFF_TEMPLATE` | `Developer handoff` |
| `INCLUDE_EXAMPLES` | `true` |

The Linear team needs the labels **Story** and **Epic** (in the *Type* group), **Handoff** and **Free Will** (in the *Origin* group) and **Propose to client** (no group).

## Run locally

```bash
cd automation/notion-linear-sync
pip install -r requirements-dev.txt
python -m pytest -q                 # tests, no network needed
export NOTION_TOKEN=… LINEAR_API_KEY=…
python -m sync                      # dry run
python -m sync --apply              # write
```

## Changelog

- **v0.2.0** — The spec moves to Linear. Stories are sent when *Approved* (no more *Specified* / *Ready for dev*), from the *Developer handoff* template. Removed: Gherkin checks and the Claude review, spec-hash change detection, the *Linear status* and *Spec synced at* fields. Decision: Decision Log "Notion = requests, Linear = spec"; issue FRA-30.
- **v0.1.0** — First version: spec written in Notion and copied to Linear.

## Limits

- Tested against in-memory fakes of the Notion and Linear APIs. Do a dry run after any change.
- Epics are created in Linear only when one of their stories is sent.
