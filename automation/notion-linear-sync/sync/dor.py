"""Definition of Ready: what the client side must have before a story goes to Linear.

Only the fields Notion owns are checked: the request, its scope and the client's
approval. The developer spec (Gherkin, edge cases, design) is written in the Linear
issue and reviewed there, so it is not checked here.
"""

from __future__ import annotations

from .config import Config
from .models import BacklogItem, CheckResult


def check_story(item: BacklogItem, epic: BacklogItem | None, config: Config) -> CheckResult:
    result = CheckResult()

    if not item.key:
        result.blocking.append("**No ID.** The row needs a stable ID (FR-xx) before it can be sent to Linear.")
    if not item.is_story:
        result.blocking.append(f"**Wrong type.** Only *User story* rows are sent; this row is *{item.type}*.")
    if epic is None:
        result.blocking.append("**No epic.** Link the story to its epic in the *Epic* property.")
    elif not epic.key:
        result.blocking.append("**Epic has no ID.** Give the epic a stable ID (EP-xx) before sending its stories.")
    elif epic.status not in config.approved_epic_statuses:
        result.blocking.append(
            f"**Epic not approved.** Epic {epic.key} is *{epic.status}*. The MVP scope sign-off "
            "(recorded in the Decision Log) moves the epic to *Approved*."
        )
    if item.moscow not in config.sendable_moscow:
        result.blocking.append(
            f"**MoSCoW is {item.moscow or 'empty'}.** Only Must, Should or Could stories go to Linear."
        )
    if not item.approved_in_ids:
        result.blocking.append("**No client approval.** *Approved in* must link the Client Session where it was approved.")
    if not item.prototype_version.strip():
        result.blocking.append("**No prototype version.** Fill *Prototype version* with what the client approved.")
    if item.blocking_questions:
        result.blocking.append("**Blocking question open.** *Blocking questions* is ticked; resolve it first.")

    if not item.kpi_ids:
        result.warnings.append("No KPI linked: results cannot be measured after launch.")
    if item.confidence and "Assumption" in item.confidence:
        result.warnings.append("Confidence is only 🟡 Assumption.")

    return result


def render_report(result: CheckResult, date: str, linear_identifier: str | None = None) -> tuple[str, str]:
    """(title, Markdown body) of the report appended to the Notion row as one toggle."""
    title = f"Definition of Ready check — {date} — {'passed' if result.passed else 'blocked'}"
    lines: list[str] = []
    if result.passed:
        where = f" Sent to Linear as {linear_identifier}: the spec is written there." if linear_identifier else ""
        lines.append(f"**Passed** with {len(result.warnings)} warning(s).{where}")
    else:
        lines.append(
            "**Blocked. Not sent to Linear.** Status moved back to *Discovery*. Nothing was filled in on your behalf."
        )
        lines.append("### Blocking gaps")
        lines.extend(f"{i}. {gap}" for i, gap in enumerate(result.blocking, 1))
    if result.warnings:
        lines.append("### Warnings (do not block)")
        lines.extend(f"- {w}" for w in result.warnings)
    if result.notes:
        lines.append("### Notes")
        lines.extend(f"- {n}" for n in result.notes)
    return title, "\n".join(lines)
