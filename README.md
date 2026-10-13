# Real Estate Website

Bilingual (English / Spanish) website for a real estate business in Costa Rica.

`release v0.1 · designed by Francella Fernández & Claude`

## Repository structure

```
real-estate-website/
├── prototypes/      Approved and draft prototypes. Reference only, not production code.
│   └── property-page/
├── automation/      Project tooling, not part of the website.
│   └── notion-linear-sync/   Moves ready stories from the Notion Product Backlog to Linear.
├── .github/workflows/        Runs the sync on weekdays and on demand.
├── src/             Production code (to be set up by the developer).
├── CLAUDE.md        Rules for Claude Code, including Free Will work in worktrees.
└── README.md
```

## Rules

- **`prototypes/` is reference, not production code.** Prototypes show expected behaviour, content and which design system components to use. How to build each feature is the developer's call.
- **Every prototype has a version and a status** (`draft` or `approved`) in its own README. Approved versions are frozen with a git tag, for example `prototype-v0.1-approved`. Any change after approval is a new version.
- **Requirements and decisions live in Notion**, not here: the product requirements, client sessions, decision log and the developer handoff for each feature. Each handoff links to the prototype version it refers to.
- **Tasks and bugs live in Linear.**

## QA before the pull request

A pull request to `main` means "tested and ready to merge", not "done coding".

1. Build on the issue's branch (or a `wt/` worktree for Free Will work).
2. The branch is published to a preview URL.
3. The issue moves to **In QA**. QA tests the preview against the story's Gherkin scenarios and posts the result as a comment on the Linear issue: pass or fail per scenario, with the device and language tested.
4. Only with QA passed is the pull request opened, linking that comment. The issue moves to **In Review**.
5. Code review and merge.

If QA finds a failure, the issue goes back to **In Progress**.

## Two lanes: Handoff and Free Will

Every Linear issue has exactly one **Origin** label, so you can always tell where the work came from.

| Origin | Where it starts | Can it reach the client? |
| --- | --- | --- |
| **Handoff** | A client request in the Notion Product Backlog, approved and synced to Linear. The sync adds this label automatically. | Yes, through the normal flow. |
| **Free Will** | Exploration with Claude Code in a git worktree, on a branch named `wt/<linear-id>-<short-name>`. | Not until the client approves it (see below). |

Free Will work is free to explore but always traceable: every issue, branch and commit is recorded. Review the Free Will view in Linear once a week and either propose each item to the client or close it.

### The way back: from Free Will to Handoff

1. **Propose.** In Linear, add the label **Propose to client** to the Free Will issue.
2. **The sync brings it to Notion.** On its next run it creates the story in the Product Backlog (next `FR-xx`, Status *Specified*, the issue description as its spec) or, if the story already exists, adds a note to it. It comments the Notion link on the issue and removes *Propose to client*. The issue stays Free Will.
3. **The client decides** in a Client Session. Add that session in *Approved in*, complete the Definition of Ready and move the story to *Ready for dev*.
4. **The sync switches it to Handoff.** When the story passes the Definition of Ready, the issue's Origin changes from Free Will to Handoff automatically and a comment records the approval. From then on it follows the normal flow.

Nobody switches Free Will to Handoff by hand: the label changes only when the client's approval is recorded in Notion.

## Who does what

| Role | Person |
| --- | --- |
| Product / project lead | Francella Fernández |
| UX design and development | plasmativa |
| QA | Rosaelena |
