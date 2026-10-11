"""Definition of Ready: the checks a story must pass before it goes to Linear.

Deterministic checks are done here in code. Checks that need judgement (is
there a non-happy path, can QA test each Then, is it too big) are delegated to
the reviewer in ai_review.py.
"""

from __future__ import annotations

from .config import Config
from .gherkin import extract_scenarios
from .models import BacklogItem, CheckResult


def check_story(
    item: BacklogItem,
    body_markdown: str,
    epic: BacklogItem | None,
    reviewer,
    config: Config,
) -> CheckResult:
    result = CheckResult()

    # --- Row fields -------------------------------------------------------
    if not item.key:
        result.blocking.append("**No ID.** The row needs a stable ID (FR-xx) before it can be synced.")
    if not item.is_story:
        result.blocking.append(f"**Wrong type.** Only *User story* rows are synced; this row is *{item.type}*.")
    if epic is None:
        result.blocking.append("**No epic.** Link the story to its epic in the *Epic* property.")
    elif not epic.key:
        result.blocking.append("**Epic has no ID.** Give the epic a stable ID (EP-xx) before syncing its stories.")
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
        result.blocking.append("**No prototype version.** Fill *Prototype version* with the version the client approved.")
    if item.blocking_questions:
        result.blocking.append("**Blocking question open.** *Blocking questions* is ticked; resolve it first.")

    # --- Acceptance criteria (structure) ---------------------------------
    scenarios = extract_scenarios(body_markdown)
    if not scenarios:
        result.blocking.append("**No acceptance criteria.** Add Gherkin scenarios in a ```gherkin code block.")
    for scenario in scenarios:
        if scenario.missing:
            result.blocking.append(
                f"**Incomplete scenario \"{scenario.name}\".** Missing: {', '.join(scenario.missing)}."
            )

    # --- Acceptance criteria (judgement) ---------------------------------
    if scenarios:
        verdict = reviewer.review(item.key, body_markdown, scenarios)
        if not verdict.has_unhappy_path:
            result.blocking.append(
                "**Only the happy path.** Add at least one scenario for an error, invalid input or failure."
            )
        for name in verdict.vague_scenarios:
            result.warnings.append(f"Scenario \"{name}\" may be hard for QA to test objectively.")
        if not verdict.covers_bilingual:
            result.warnings.append("No English/Spanish cases (NFR-01).")
        if not verdict.covers_mobile:
            result.warnings.append("No mobile cases.")
        if verdict.too_big or len(scenarios) > 5:
            result.warnings.append("Story looks too big: consider splitting it.")
        result.notes.extend(verdict.notes)
        result.notes.append(f"Acceptance criteria reviewed by: {verdict.source}.")

    # --- Other warnings ---------------------------------------------------
    if item.confidence and "Assumption" in item.confidence:
        result.warnings.append("Confidence is only 🟡 Assumption.")
    if "design system" not in body_markdown.lower() and "components" not in body_markdown.lower():
        result.warnings.append("No design system components named.")

    return result


def render_report(result: CheckResult, date: str, linear_identifier: str | None = None) -> tuple[str, str]:
    """(title, Markdown body) of the report appended to the Notion row as one toggle."""
    title = f"Definition of Ready check — {date} — {'passed' if result.passed else 'blocked'}"
    lines: list[str] = []
    if result.passed:
        where = f" Sent to Linear as {linear_identifier}." if linear_identifier else ""
        lines.append(f"**Passed** with {len(result.warnings)} warning(s).{where}")
    else:
        lines.append(
            "**Blocked. Not sent to Linear.** Status moved back to *Specified*. Nothing was filled in on your behalf."
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
