# Notion → Linear sync

Moves user stories from the Notion **Product Backlog** to **Linear** once they pass the
Definition of Ready, and keeps both sides consistent afterwards.

`release v0.1.0 · designed by Francella Fernández & Claude`

## What it does

Each run makes three passes over the Product Backlog:

| Pass | Reads | Writes |
| --- | --- | --- |
| **0. Preflight** | Linear team, project, state, labels | Nothing. Stops the run, even a dry run, if any of them is missing. |
| **1. Ready stories** | Rows with Type *User story* and Status *Ready for dev* | Runs the Definition of Ready. **Blocked:** appends the list of gaps to the row (as a collapsed toggle) and moves it back to *Specified*. **Passed:** creates (or updates) the epic and story issues in Linear, then writes *Linear ID*, *Linear issue*, *Linear status* and, last, *Spec synced at* back to Notion. |
| **2. Spec changes** | Rows *In Linear* | If the spec in Notion changed, comments the diff on the Linear issue and updates its spec section. Developer notes are never touched; if someone is editing the issue at that moment, the update waits for the next run. |
| **3. Status mirror** | Rows with a Linear ID | Copies the Linear status into *Linear status*. When a story is Done in Linear, its row moves to *Awaiting acceptance* (Done is not the same as accepted by the client). |

### Who decides what

- **The script (deterministic):** row fields, epic approval, MoSCoW, client approval, prototype version, blocking questions, Gherkin structure (every scenario has Given, When and Then), duplicates, canceled issues, every read and write.
- **The AI (judgement only):** does at least one scenario cover a non-happy path, can QA test each *Then* objectively, does the story cover English/Spanish and mobile, is it too big. It returns a verdict; it never edits the story. Without `ANTHROPIC_API_KEY`, or if the call fails, a keyword heuristic is used and the report says so.

### Rules it relies on

- **One key per item.** The Linear title starts with the Notion ID (`[FR-03] …`). Before creating anything, the script looks up the row's *Linear ID* (so a renamed issue is still found) and searches Linear for the key: found → update; not found → create. Two issues for the same item, or a canceled one (story or epic), block the story until a person decides.
- **Reports never mix with the spec.** Each Definition of Ready report is one collapsed toggle titled "Definition of Ready check — …"; it is skipped when the page is read, wherever it sits.
- **One owner per field.** The script only writes *Status*, *Linear ID*, *Linear issue*, *Linear status* and *Spec synced at* in Notion; any other property is refused in code.
- **Spec changes by content, not by date.** The spec section in Linear ends with a fingerprint (`spec-hash: …`). A change in Notion changes the fingerprint. Dates are not used, because the sync's own writes change *Last edited*.
- **Dry run by default.** Nothing is written without `--apply`.

## Setup (once)

1. **Notion integration.** In Notion, *Settings → Connections → Develop or manage integrations → New integration* (internal). Copy the token. Then open the **Product Backlog** database, *⋯ → Connections*, and add the integration; without this, the API cannot see the rows.
2. **Linear API key.** In Linear, *Settings → Security & access → Personal API keys → New key*.
3. **Claude API key (optional).** From the Claude Console. Without it, the heuristic reviews the acceptance criteria.
4. **GitHub secrets.** In this repository, *Settings → Secrets and variables → Actions → New repository secret*: `NOTION_TOKEN`, `LINEAR_API_KEY`, and optionally `ANTHROPIC_API_KEY`.
5. **First run, as a dry run.** *Actions → Notion → Linear sync → Run workflow*, with *apply* unticked. Read the summary of the run.
6. **When the dry run looks right**, run it again with *apply* ticked. To let the weekday schedule write too, add the repository variable `SYNC_APPLY` = `true` (*Settings → Secrets and variables → Actions → Variables*). Until then, scheduled runs are dry runs. Scheduled runs always skip rows marked *Example (test data)*.

## Configuration

Defaults match the current workspace; override any of them with a repository variable or environment variable.

| Variable | Default |
| --- | --- |
| `NOTION_BACKLOG_DATA_SOURCE_ID` | `63c22b26-e51b-4691-94c4-cb42b28c0c46` |
| `NOTION_VERSION` | `2025-09-03` |
| `LINEAR_TEAM_KEY` | `FRA` |
| `LINEAR_PROJECT_NAME` | `Real Estate Website MVP` |
| `LINEAR_NEW_ISSUE_STATE` | `Backlog` |
| `ANTHROPIC_MODEL` | `claude-sonnet-5-5` |
| `INCLUDE_EXAMPLES` | `true` |

The Linear team needs the labels **Story** and **Epic** (in the *Type* group) and **Handoff** (in the *Origin* group). Every issue the sync creates gets *Origin › Handoff*, because it came through the approved Notion flow. Work explored with Claude Code in a worktree gets *Origin › Free Will* instead (see the root README).

## Run locally

```bash
cd automation/notion-linear-sync
pip install -r requirements-dev.txt
python -m pytest -q                 # tests, no network needed
export NOTION_TOKEN=… LINEAR_API_KEY=…
python -m sync                      # dry run
python -m sync --apply              # write
```

## Limits

- Not tested yet against the live Notion and Linear APIs (only against in-memory fakes that reproduce the example rows and the APIs' id/ordering behaviour). Do the dry run first.
- The window in which a developer's edit could be overwritten is reduced to the moment between the last read and the write, not closed completely (Linear has no conditional update).
- Pages are converted to Markdown for the common block types (text, headings, lists, to-dos, code, callouts, quotes); others appear as `[unsupported Notion block: …]` in the spec.
- Epics are synced only when one of their stories is; epic specs follow the same change detection afterwards.
