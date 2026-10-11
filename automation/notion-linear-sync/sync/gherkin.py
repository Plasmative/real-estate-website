"""Deterministic parsing of Gherkin acceptance criteria from a story's Markdown."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_CODE_BLOCK = re.compile(r"```([^\n]*)\n(.*?)```", re.S)
_SCENARIO = re.compile(r"^\s*(Scenario Outline|Scenario|Example)\s*:\s*(.*)$", re.I)
_STEP = re.compile(r"^\s*(Given|When|Then|And|But)\b", re.I)


@dataclass
class Scenario:
    name: str
    steps: list[str] = field(default_factory=list)

    def keywords(self) -> set[str]:
        """Main keywords, with And/But resolved to the keyword before them."""
        found: set[str] = set()
        current = None
        for step in self.steps:
            word = _STEP.match(step).group(1).capitalize()
            if word in ("And", "But"):
                word = current
            if word:
                found.add(word)
                current = word
        return found

    @property
    def missing(self) -> list[str]:
        return [k for k in ("Given", "When", "Then") if k not in self.keywords()]

    @property
    def text(self) -> str:
        return "\n".join([f"Scenario: {self.name}", *self.steps])


def extract_scenarios(markdown: str) -> list[Scenario]:
    """Scenarios from ```gherkin code blocks, or any code block containing 'Scenario:'."""
    scenarios: list[Scenario] = []
    for language, code in _CODE_BLOCK.findall(markdown):
        if language.strip().lower() != "gherkin" and "scenario" not in code.lower():
            continue
        current: Scenario | None = None
        for line in code.splitlines():
            head = _SCENARIO.match(line)
            if head:
                current = Scenario(name=head.group(2).strip())
                scenarios.append(current)
            elif current is not None and _STEP.match(line):
                current.steps.append(line.strip())
    return scenarios
