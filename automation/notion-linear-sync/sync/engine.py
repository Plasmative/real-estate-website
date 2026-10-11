"""The sync itself: a preflight and three passes over the Product Backlog.

0. Preflight      -> read-only check that the Linear team, project, state and labels exist.
1. Ready stories  -> Definition of Ready -> create or update the Linear issue (or block it).
2. Spec changes   -> if a synced row's spec changed in Notion, comment the diff on Linear and update the spec section.
3. Status mirror  -> copy the Linear status into Notion; Done moves a story to *Awaiting acceptance*.

Writes only happen with apply=True. In a dry run every write is reported as
"would …" and nothing changes in Notion or Linear.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .config import Config
from .dor import check_story, render_report
from .markdown import build_description, extract_developer_notes, extract_hash, extract_spec_text, render_spec, spec_hash
from .models import BacklogItem, LinearIssue
from .notion_client import norm_id

SYNCED_STATUSES = ("In Linear",)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class Report:
    apply: bool
    lines: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    counts: dict = field(default_factory=lambda: {"created": 0, "updated": 0, "blocked": 0, "mirrored": 0, "spec_changes": 0})

    def add(self, line: str) -> None:
        self.lines.append(line)

    def markdown(self) -> str:
        mode = "APPLIED" if self.apply else "DRY RUN (nothing was written)"
        out = [f"# Notion → Linear sync — {mode}", ""]
        out.append(
            "| Created | Updated | Blocked | Spec changes | Status mirrored | Errors |\n|---|---|---|---|---|---|\n"
            f"| {self.counts['created']} | {self.counts['updated']} | {self.counts['blocked']} | "
            f"{self.counts['spec_changes']} | {self.counts['mirrored']} | {len(self.errors)} |"
        )
        out.append("")
        out.extend(f"- {line}" for line in self.lines or ["Nothing to do."])
        if self.errors:
            out.append("")
            out.append("## Errors")
            out.extend(f"- {e}" for e in self.errors)
        return "\n".join(out) + "\n"


class SyncEngine:
    def __init__(self, notion, linear, reviewer, config: Config, apply: bool = False, today: str | None = None):
        self.notion = notion
        self.linear = linear
        self.reviewer = reviewer
        self.config = config
        self.apply = apply
        self.today = today or datetime.now(timezone.utc).date().isoformat()
        self.report = Report(apply=apply)
        self._bodies: dict[str, str] = {}
        self._epic_issues: dict[str, LinearIssue] = {}  # epic key -> issue, resolved once per run

    # -- helpers ------------------------------------------------------------
    def _body(self, item: BacklogItem) -> str:
        if item.page_id not in self._bodies:
            self._bodies[item.page_id] = self.notion.page_markdown(item.page_id)
        return self._bodies[item.page_id]

    def _write_notion(self, item: BacklogItem, values: dict, why: str) -> None:
        if self.apply:
            self.notion.update_properties(item.page_id, values)
        else:
            self.report.add(f"would set {values} on {item.key} ({why})")

    def _title(self, item: BacklogItem) -> str:
        return f"[{item.key}] {item.name}"

    def _spec(self, item: BacklogItem) -> str:
        return render_spec(item.key, item.url, self._body(item), item.example)

    def _candidates(self, item: BacklogItem) -> tuple[list[LinearIssue], str | None]:
        """Linear issues for this row: the one its Linear ID points to, plus any titled '[KEY] …'.

        Returns (issues, problem). Looking up the Linear ID first means a renamed
        issue is still found, so it is updated instead of duplicated.
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
            self.linear.label_ids(tuple(self.config.story_labels) + tuple(self.config.epic_labels))
        except Exception as exc:  # noqa: BLE001
            self.report.errors.append(f"Linear setup check failed: {exc}")
            return self.report

        items = self.notion.query_backlog()
        if not self.config.include_examples:
            items = [i for i in items if not i.example]
        by_page = {norm_id(i.page_id): i for i in items}
        handled: set[str] = set()

        for item in items:
            if item.is_story and item.status == "Ready for dev":
                self._guard(self._sync_ready_story, item, by_page, handled)

        for item in items:
            if item.linear_id and item.page_id not in handled and item.status in SYNCED_STATUSES:
                self._guard(self._check_spec_change, item)

        for item in items:
            if item.linear_id and item.page_id not in handled:
                self._guard(self._mirror_status, item)

        return self.report

    def _guard(self, fn, item: BacklogItem, *args) -> None:
        try:
            fn(item, *args)
        except Exception as exc:  # noqa: BLE001 - one bad row must not stop the others
            self.report.errors.append(f"{item.key or item.page_id}: {type(exc).__name__}: {exc}")

    # -- pass 1: ready stories ------------------------------------------------
    def _sync_ready_story(self, item: BacklogItem, by_page: dict, handled: set) -> None:
        handled.add(item.page_id)
        epic = by_page.get(norm_id(item.epic_page_ids[0])) if item.epic_page_ids else None
        result = check_story(item, self._body(item), epic, self.reviewer, self.config)

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
            self._write_notion(item, {"Status": "Specified"}, "Definition of Ready failed")
            return

        epic_issue = self._ensure_epic(epic, epic_existing, handled) if epic else None
        spec_current = True
        if existing:
            issue = existing[0]
            spec_current = self._update_spec(item, issue, reason="re-sent from Ready for dev") != "postponed"
            if self.apply:
                self.linear.add_link(issue.id, item.url, f"Notion Product Backlog — {item.key}")
            self.report.counts["updated"] += 1
            self.report.add(f"🔁 {item.key} already in Linear as {issue.identifier}: "
                            f"{'updated' if self.apply else 'would be updated'} (no duplicate created)")
        else:
            if self.apply:
                issue = self.linear.create_issue(
                    self._title(item), build_description(self._spec(item)), self.config.story_labels,
                    epic_issue.id if epic_issue and epic_issue.id else None,
                )
                self.linear.add_link(issue.id, item.url, f"Notion Product Backlog — {item.key}")
                if result.warnings:
                    self.linear.comment(issue.id, "**Definition of Ready passed with warnings**\n\n"
                                        + "\n".join(f"- {w}" for w in result.warnings))
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
            "Linear status": issue.state_name or self.linear.new_issue_state,
        }, "synced")
        # Spec synced at is written last, after every other write to the row,
        # and only when Linear really holds the current spec.
        if spec_current:
            self._write_notion(item, {"Spec synced at": now_iso()}, "sync time")

    def _ensure_epic(self, epic: BacklogItem, existing: list[LinearIssue], handled: set) -> LinearIssue:
        if epic.key in self._epic_issues:
            return self._epic_issues[epic.key]
        handled.add(epic.page_id)
        if existing:
            issue = existing[0]
        elif self.apply:
            issue = self.linear.create_issue(self._title(epic), build_description(self._spec(epic)),
                                             self.config.epic_labels, None)
            self.linear.add_link(issue.id, epic.url, f"Notion Product Backlog — {epic.key}")
            self.report.add(f"✅ epic {epic.key} created in Linear as {issue.identifier}")
        else:
            issue = LinearIssue(id="", identifier="(new epic issue)", title=self._title(epic), url="",
                                state_name=self.linear.new_issue_state)
            self.report.add(f"✅ epic {epic.key} would be created in Linear")
        if epic.linear_id != issue.identifier or epic.status != "In Linear":
            self._write_notion(epic, {"Status": "In Linear", "Linear ID": issue.identifier,
                                      "Linear issue": issue.url, "Linear status": issue.state_name}, "epic linked")
            self._write_notion(epic, {"Spec synced at": now_iso()}, "sync time")
        self._epic_issues[epic.key] = issue
        return issue

    # -- spec updates (used by pass 1 and pass 2) -----------------------------
    def _update_spec(self, item: BacklogItem, issue: LinearIssue, reason: str) -> str:
        """Replace the spec section if it changed, then comment the diff.

        Returns "unchanged", "updated" (or would be, in a dry run) or "postponed".
        """
        spec = self._spec(item)
        new_hash = spec_hash(self._body(item).strip())
        old_hash = extract_hash(issue.description)
        if old_hash == new_hash:
            return "unchanged"
        if old_hash is None:
            reason = "no fingerprint yet: spec section adopted by the sync"
        self.report.counts["spec_changes"] += 1
        diff = "\n".join(list(difflib.unified_diff(
            extract_spec_text(issue.description).splitlines(), spec.splitlines(),
            "Linear (before)", "Notion (now)", lineterm=""))[:80])
        if not self.apply:
            self.report.add(f"✏️ {item.key} ({issue.identifier}): {reason} — would update the spec section and comment the diff")
            return "updated"
        # Re-read right before writing: if someone edited the issue meanwhile, do not overwrite.
        fresh = self.linear.get_issue(issue.identifier)
        if fresh is None or fresh.description != issue.description:
            self.report.add(f"⏸️ {item.key} ({issue.identifier}): issue was being edited; spec update postponed to the next run")
            self.report.counts["spec_changes"] -= 1
            return "postponed"
        # Update first, comment second: if the update fails, no misleading comment is left behind.
        self.linear.update_description(issue.id, build_description(spec, extract_developer_notes(issue.description)))
        self.linear.comment(issue.id, f"**Spec changed in Notion** ({reason}).\n\n```diff\n{diff}\n```")
        self.report.add(f"✏️ {item.key} ({issue.identifier}): {reason} — spec section updated, diff commented")
        return "updated"

    # -- pass 2: spec changed in Notion ---------------------------------------
    def _check_spec_change(self, item: BacklogItem) -> None:
        issue = self.linear.get_issue(item.linear_id)
        if issue is None:
            self.report.errors.append(f"{item.key}: Linear issue {item.linear_id} not found")
            return
        if self._update_spec(item, issue, reason="spec edited in Notion") == "updated":
            self._write_notion(item, {"Spec synced at": now_iso()}, "spec re-synced")

    # -- pass 3: Linear status -> Notion ----------------------------------------
    def _mirror_status(self, item: BacklogItem) -> None:
        issue = self.linear.get_issue(item.linear_id)
        if issue is None:
            self.report.errors.append(f"{item.key}: Linear issue {item.linear_id} not found")
            return
        values: dict = {}
        if issue.state_name and issue.state_name != item.linear_status:
            values["Linear status"] = issue.state_name
        if item.is_story and issue.state_type == "completed" and item.status == "In Linear":
            values["Status"] = "Awaiting acceptance"
        if values:
            self.report.counts["mirrored"] += 1
            self.report.add(f"🔄 {item.key} ({issue.identifier}): {values}")
            self._write_notion(item, values, "mirrored from Linear")


def _short(text: str) -> str:
    return text.split(".**")[0].replace("**", "") if ".**" in text else text.replace("**", "")
