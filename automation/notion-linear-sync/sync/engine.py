"""The sync itself: a preflight, one pass over Linear and two passes over the Product Backlog.

Notion holds what the client asked for and decided; Linear holds the developer spec.
The sync never copies or compares the spec: it only opens the Linear issue and moves the
client-facing status.

0. Preflight        -> read-only check that the Linear team, project, state, labels and template exist.
P. Proposals        -> Free Will issues labelled "Propose to client" get a Notion row to be approved
                       (created if missing), a note on that row and a comment on the issue.
1. Approved stories -> Definition of Ready (client fields only) -> create the Linear issue from the
                       "Developer handoff" template (or link the one that already exists), or block it.
                       An approved Free Will issue switches its Origin label to Handoff.
2. Status           -> Linear Done moves a story to *Awaiting acceptance*; a canceled issue is reported.

Writes only happen with apply=True. In a dry run every write is reported as
"would …" and nothing changes in Notion or Linear.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .config import Config
from .dor import check_story, render_report
from .models import BacklogItem, LinearIssue
from .notion_client import norm_id

# Fallback description when the Linear template is missing: same headings, same order.
HANDOFF_HEADINGS = (
    "User story", "User context", "Why it matters", "Client approval", "Acceptance criteria (Gherkin)",
    "Edge cases", "Out of scope", "Design and references", "Dependencies", "Open questions",
    "Definition of done", "Developer notes",
)


@dataclass
class Report:
    apply: bool
    lines: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    counts: dict = field(default_factory=lambda: {"created": 0, "linked": 0, "blocked": 0, "status": 0,
                                                  "proposed": 0})

    def add(self, line: str) -> None:
        self.lines.append(line)

    def markdown(self) -> str:
        mode = "APPLIED" if self.apply else "DRY RUN (nothing was written)"
        out = [f"# Notion → Linear sync — {mode}", ""]
        out.append(
            "| Proposed | Created | Linked | Blocked | Status moved | Errors |\n"
            "|---|---|---|---|---|---|\n"
            f"| {self.counts['proposed']} | {self.counts['created']} | {self.counts['linked']} | "
            f"{self.counts['blocked']} | {self.counts['status']} | {len(self.errors)} |"
        )
        out.append("")
        out.extend(f"- {line}" for line in self.lines or ["Nothing to do."])
        if self.errors:
            out.append("")
            out.append("## Errors")
            out.extend(f"- {e}" for e in self.errors)
        return "\n".join(out) + "\n"


def fallback_description(item: BacklogItem) -> str:
    """Used only when the 'Developer handoff' template is not found in Linear."""
    parts = [f"> Request and client approval: [{item.key} in the Notion Product Backlog]({item.url}). "
             "The 'Developer handoff' template was not found, so these are its headings."]
    for heading in HANDOFF_HEADINGS:
        parts.append(f"## {heading}\n\n_To be written._")
    return "\n\n".join(parts) + "\n"


class SyncEngine:
    def __init__(self, notion, linear, config: Config, apply: bool = False, today: str | None = None):
        self.notion = notion
        self.linear = linear
        self.config = config
        self.apply = apply
        self.today = today or datetime.now(timezone.utc).date().isoformat()
        self.report = Report(apply=apply)
        self.template_id: str | None = None
        self._epic_issues: dict[str, LinearIssue] = {}  # epic key -> issue, resolved once per run

    # -- helpers ------------------------------------------------------------
    def _write_notion(self, item: BacklogItem, values: dict, why: str) -> None:
        if self.apply:
            self.notion.update_properties(item.page_id, values)
        else:
            self.report.add(f"would set {values} on {item.key} ({why})")

    def _title(self, item: BacklogItem) -> str:
        return f"[{item.key}] {item.name}"

    def _candidates(self, item: BacklogItem) -> tuple[list[LinearIssue], str | None]:
        """Linear issues for this row: the one its Linear ID points to, plus any titled '[KEY] …'.

        Returns (issues, problem). Looking up the Linear ID first means a renamed
        issue is still found, so it is linked instead of duplicated.
        """
        found: dict[str, LinearIssue] = {}
        if item.linear_id:
            linked = self.linear.get_issue(item.linear_id)
            if linked:
                found[linked.identifier] = linked
        if item.key:
            for issue in self.linear.find_by_key(item.key):
                if issue.title.startswith(f"[{item.key}]"):
                    found.setdefault(issue.identifier, issue)
        issues = list(found.values())
        if len(issues) > 1:
            return issues, (f"**Duplicate issues in Linear for {item.key}:** "
                            + ", ".join(i.identifier for i in issues)
                            + ". Keep one, cancel the others and remove the ID from their titles.")
        if issues and issues[0].state_type == "canceled":
            return issues, (f"**Linear issue {issues[0].identifier} ({item.key}) is canceled.** Reopen it in Linear, "
                            "or remove the ID from its title if this item should start over.")
        return issues, None

    # -- entry point ----------------------------------------------------------
    def run(self) -> Report:
        try:  # read-only: fails early (even in a dry run) if team, project, state or labels are wrong
            self.linear.label_ids(tuple(self.config.story_labels) + tuple(self.config.epic_labels)
                                  + (self.config.free_will_label, self.config.propose_label))
        except Exception as exc:  # noqa: BLE001
            self.report.errors.append(f"Linear setup check failed: {exc}")
            return self.report
        try:
            self.template_id = self.linear.template_id(self.config.handoff_template)
        except Exception as exc:  # noqa: BLE001
            self.report.errors.append(f"Could not look up the Linear template: {exc}")
        if not self.template_id:
            self.report.add(f"⚠️ Linear template '{self.config.handoff_template}' not found: new issues get "
                            "its headings as plain text. Create it in Settings → Teams → Templates.")

        items = self.notion.query_backlog()
        if not self.config.include_examples:
            items = [i for i in items if not i.example]
        by_page = {norm_id(i.page_id): i for i in items}
        handled: set[str] = set()

        try:
            proposals = self.linear.find_by_label(self.config.propose_label)
        except Exception as exc:  # noqa: BLE001
            proposals = []
            self.report.errors.append(f"Could not list '{self.config.propose_label}' issues: {exc}")
        for issue in proposals:
            try:
                self._propose(issue, items, handled)
            except Exception as exc:  # noqa: BLE001 - one bad issue must not stop the others
                self.report.errors.append(f"{issue.identifier}: {type(exc).__name__}: {exc}")

        for item in items:
            if item.is_story and item.status == "Approved" and item.page_id not in handled:
                self._guard(self._send_approved_story, item, by_page, handled)

        for item in items:
            if item.linear_id and item.page_id not in handled and item.is_story and item.status == "In Linear":
                self._guard(self._follow_status, item)

        return self.report

    def _guard(self, fn, item: BacklogItem, *args) -> None:
        try:
            fn(item, *args)
        except Exception as exc:  # noqa: BLE001 - one bad row must not stop the others
            self.report.errors.append(f"{item.key or item.page_id}: {type(exc).__name__}: {exc}")

    # -- pass 1: approved stories ---------------------------------------------
    def _send_approved_story(self, item: BacklogItem, by_page: dict, handled: set) -> None:
        handled.add(item.page_id)
        epic = by_page.get(norm_id(item.epic_page_ids[0])) if item.epic_page_ids else None
        result = check_story(item, epic, self.config)

        existing, problem = self._candidates(item)
        if problem:
            result.blocking.append(problem)
        epic_existing: list[LinearIssue] = []
        if epic is not None and epic.key not in self._epic_issues:
            epic_existing, epic_problem = self._candidates(epic)
            if epic_problem:
                result.blocking.append(epic_problem)

        if not result.passed:
            self.report.counts["blocked"] += 1
            self.report.add(f"⛔ {item.key} blocked: " + "; ".join(_short(b) for b in result.blocking))
            if self.apply:
                self.notion.append_report(item.page_id, *render_report(result, self.today))
            self._write_notion(item, {"Status": "Discovery"}, "Definition of Ready failed")
            return

        epic_issue = self._ensure_epic(epic, epic_existing, handled) if epic else None
        if existing:
            issue = existing[0]
            self._promote_to_handoff(item, issue)
            if self.apply:
                self.linear.add_link(issue.id, item.url, f"Notion Product Backlog — {item.key}")
            self.report.counts["linked"] += 1
            self.report.add(f"🔗 {item.key} already in Linear as {issue.identifier}: "
                            f"{'linked' if self.apply else 'would be linked'} (no duplicate created)")
        else:
            if self.apply:
                issue = self.linear.create_issue(
                    self._title(item),
                    None if self.template_id else fallback_description(item),
                    self.config.story_labels,
                    epic_issue.id if epic_issue and epic_issue.id else None,
                    self.template_id,
                )
                self.linear.add_link(issue.id, item.url, f"Notion Product Backlog — {item.key}")
                note = (f"**Approved by the client** ({item.key}, prototype {item.prototype_version}). "
                        "Write the spec in this issue, following the template sections. "
                        "The Notion row keeps only the request and the client's decisions.")
                if result.warnings:
                    note += "\n\n**Warnings**\n" + "\n".join(f"- {w}" for w in result.warnings)
                self.linear.comment(issue.id, note)
            else:
                issue = LinearIssue(id="", identifier="(new issue)", title=self._title(item), url="",
                                    state_name=self.linear.new_issue_state)
            self.report.counts["created"] += 1
            self.report.add(f"✅ {item.key} {'created' if self.apply else 'would be created'} in Linear as "
                            f"{issue.identifier} under {epic_issue.identifier if epic_issue else 'no epic'} "
                            f"({len(result.warnings)} warning(s))")

        if self.apply:
            self.notion.append_report(item.page_id, *render_report(result, self.today, issue.identifier))
        self._write_notion(item, {
            "Status": "In Linear",
            "Linear ID": issue.identifier,
            "Linear issue": issue.url,
        }, "sent to Linear")

    def _ensure_epic(self, epic: BacklogItem, existing: list[LinearIssue], handled: set) -> LinearIssue:
        if epic.key in self._epic_issues:
            return self._epic_issues[epic.key]
        handled.add(epic.page_id)
        if existing:
            issue = existing[0]
        elif self.apply:
            issue = self.linear.create_issue(
                self._title(epic),
                f"Epic. Client request and scope: [{epic.key} in the Notion Product Backlog]({epic.url}).\n",
                self.config.epic_labels, None, None)
            self.linear.add_link(issue.id, epic.url, f"Notion Product Backlog — {epic.key}")
            self.report.add(f"✅ epic {epic.key} created in Linear as {issue.identifier}")
        else:
            issue = LinearIssue(id="", identifier="(new epic issue)", title=self._title(epic), url="",
                                state_name=self.linear.new_issue_state)
            self.report.add(f"✅ epic {epic.key} would be created in Linear")
        if epic.linear_id != issue.identifier or epic.status != "In Linear":
            self._write_notion(epic, {"Status": "In Linear", "Linear ID": issue.identifier,
                                      "Linear issue": issue.url}, "epic linked")
        self._epic_issues[epic.key] = issue
        return issue

    def _promote_to_handoff(self, item: BacklogItem, issue: LinearIssue) -> None:
        """A Free Will issue whose Notion row passed the Definition of Ready (so the client approved it)."""
        if self.config.free_will_label not in issue.labels:
            return
        self.report.add(f"🤝 {item.key} ({issue.identifier}): client approved — Origin "
                        f"{'switched' if self.apply else 'would switch'} from Free Will to Handoff")
        if self.apply:
            self.linear.set_labels(issue, add=(self.config.handoff_label,),
                                   remove=(self.config.free_will_label, self.config.propose_label))
            self.linear.comment(issue.id, f"**Approved by the client in Notion** ({item.key}). "
                                "Origin switched from Free Will to Handoff: this work can now go to the client.")

    # -- pass P: Free Will proposals --------------------------------------------
    def _propose(self, issue: LinearIssue, items: list[BacklogItem], handled: set) -> None:
        label = self.config.propose_label
        if self.config.free_will_label not in issue.labels:
            self.report.add(f"↩️ {issue.identifier}: has '{label}' but is not Free Will — label "
                            f"{'removed' if self.apply else 'would be removed'}, nothing else done")
            if self.apply:
                self.linear.set_labels(issue, remove=(label,))
            return
        rows = [i for i in items if i.linear_id == issue.identifier]
        if len(rows) > 1:
            self.report.errors.append(f"{issue.identifier}: several Notion rows have this Linear ID: "
                                      + ", ".join(r.key or r.page_id for r in rows) + ". Keep one.")
            return
        self.report.counts["proposed"] += 1
        note_title = f"Sync note — proposed from Free Will {issue.identifier} ({self.today})"
        note = (f"This item started as exploration in Linear: [{issue.identifier}]({issue.url}). "
                "The developer spec stays in that issue.\n\n"
                "**To approve it:** show it to the client, add the Client Session in *Approved in* and the "
                "*Prototype version*, then move Status to *Approved*. The sync then switches the Linear issue "
                "to Handoff.")

        if rows:
            row = rows[0]
            handled.add(row.page_id)  # never send it to Linear in this same run
            self.report.add(f"📨 {issue.identifier}: proposed to the client through existing row {row.key}")
            if row.status == "Idea":
                self._write_notion(row, {"Status": "Discovery"}, "proposed from Free Will")
            if self.apply:
                self.notion.append_report(row.page_id, note_title, note)
        else:
            key = _next_story_key(items)
            name = re.sub(r"^\[[^\]]+\]\s*", "", issue.title).strip() or issue.title
            body = (f"Proposed from exploration in [{issue.identifier}]({issue.url}). "
                    "Write here what the client asked for or decided; the spec stays in Linear.")
            self.report.add(f"📨 {issue.identifier}: {'created' if self.apply else 'would create'} "
                            f"Notion row {key} '{name}' (Discovery) for client approval")
            if not self.apply:
                return
            row = self.notion.create_story(key, name, issue.identifier, issue.url, body)
            items.append(row)
            handled.add(row.page_id)
            self.notion.append_report(row.page_id, note_title, note)

        if not self.apply:
            return
        self.linear.set_labels(issue, remove=(label,))
        self.linear.comment(issue.id, f"**Proposed to the client** in Notion as [{row.key}]({row.url}). "
                            "It stays Free Will until the client approves it there.")

    # -- pass 2: Linear status -> Notion ----------------------------------------
    def _follow_status(self, item: BacklogItem) -> None:
        issue = self.linear.get_issue(item.linear_id)
        if issue is None:
            self.report.errors.append(f"{item.key}: Linear issue {item.linear_id} not found")
            return
        if issue.state_type == "completed":
            self.report.counts["status"] += 1
            self.report.add(f"🔄 {item.key} ({issue.identifier}) is Done in Linear: "
                            f"{'moved' if self.apply else 'would move'} to Awaiting acceptance")
            self._write_notion(item, {"Status": "Awaiting acceptance"}, "Done in Linear")
        elif issue.state_type == "canceled":
            self.report.add(f"⚠️ {item.key} ({issue.identifier}) was canceled in Linear. Decide with the client: "
                            "*Out of scope* or *Change requested* in Notion.")


def _next_story_key(items: list[BacklogItem]) -> str:
    """Next free FR-xx key. Example keys (FR-EX01) do not count."""
    numbers = [int(m.group(1)) for i in items if (m := re.fullmatch(r"FR-(\d+)", i.key or ""))]
    return f"FR-{max(numbers, default=0) + 1:02d}"


def _short(text: str) -> str:
    return text.split(".**")[0].replace("**", "") if ".**" in text else text.replace("**", "")
