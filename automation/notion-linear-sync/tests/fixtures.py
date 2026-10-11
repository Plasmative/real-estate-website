"""The example rows from the Notion Product Backlog, as the API would return their blocks."""

from __future__ import annotations

from sync.models import BacklogItem


def rt(text: str, bold: bool = False) -> list[dict]:
    return [{"type": "text", "plain_text": text, "text": {"content": text}, "annotations": {"bold": bold}}]


def heading(text: str, level: int = 2) -> dict:
    key = f"heading_{level}"
    return {"type": key, key: {"rich_text": rt(text)}}


def para(text: str) -> dict:
    return {"type": "paragraph", "paragraph": {"rich_text": rt(text)}}


def bullet(text: str) -> dict:
    return {"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": rt(text)}}


def code(text: str, language: str = "gherkin") -> dict:
    return {"type": "code", "code": {"language": language, "rich_text": rt(text)}}


def callout(text: str, emoji: str = "🧪") -> dict:
    return {"type": "callout", "callout": {"rich_text": rt(text), "icon": {"type": "emoji", "emoji": emoji}}}


EPIC = BacklogItem(page_id="epic-1", url="https://notion.so/epic-1", key="EP-EX01",
                   name="[EXAMPLE] Buyer inquiries and engagement", type="Epic", status="Approved",
                   moscow="Must", example=True)

GOOD_GHERKIN = """Scenario: Inquiry sent successfully
  Given I am on the page of the property "Hacienda Mirador del Pacífico"
  When I fill in my name, email and message
  And I click "Request information"
  Then I see a confirmation message in the page's language
  And the agent receives an email with my details and the property reference GU-0100

Scenario: Invalid email
  Given I typed an email with an invalid format
  When I click "Request information"
  Then I see an error message under the email field explaining how to fix it
  And the inquiry is not sent

Scenario: Sending fails
  Given the email service is not available
  When I click "Request information"
  Then I see a message asking me to try again or contact the agent by phone"""

STORY_PASS = BacklogItem(page_id="story-1", url="https://notion.so/story-1", key="FR-EX01",
                         name="[EXAMPLE] Request information about a property", type="User story",
                         status="Ready for dev", moscow="Must", confidence="🟡 Assumption",
                         epic_page_ids=["epic-1"], approved_in_ids=["session-1"], prototype_version="v0.1",
                         example=True)

STORY_PASS_BLOCKS = [
    callout("Test data. Fictional story built to pass the Definition of Ready."),
    heading("User story"),
    para("As a buyer interested in a property, I want to send a question from the property page."),
    heading("Acceptance criteria"),
    code(GOOD_GHERKIN),
    heading("Edge cases"),
    bullet("Mobile and desktop: the form works on a 390 px wide screen."),
    bullet("English and Spanish (NFR-01): labels, errors and confirmation in both languages."),
    heading("Design and references"),
    bullet("Design system components: TextField, Button (primary)"),
]

STORY_FAIL = BacklogItem(page_id="story-2", url="https://notion.so/story-2", key="FR-EX02",
                         name="[EXAMPLE] Save favourite properties", type="User story",
                         status="Ready for dev", moscow="Should", confidence="🟡 Assumption",
                         epic_page_ids=["epic-1"], blocking_questions=True, example=True)

STORY_FAIL_BLOCKS = [
    heading("User story"),
    para("As a buyer comparing several properties, I want to save the ones I like."),
    heading("Acceptance criteria"),
    code("Scenario: Save a property\n  Given I am on the page of a property\n  When I click \"Save\"\n  Then the property appears in my saved list"),
]

EPIC_BLOCKS = [para("Groups the stories that let a buyer contact the business.")]
