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
└── README.md
```

## Rules

- **`prototypes/` is reference, not production code.** Prototypes show expected behaviour, content and which design system components to use. How to build each feature is the developer's call.
- **Every prototype has a version and a status** (`draft` or `approved`) in its own README. Approved versions are frozen with a git tag, for example `prototype-v0.1-approved`. Any change after approval is a new version.
- **Requirements and decisions live in Notion**, not here: the product requirements, client sessions, decision log and the developer handoff for each feature. Each handoff links to the prototype version it refers to.
- **Tasks and bugs live in Linear.**

## Who does what

| Role | Person |
| --- | --- |
| Product / project lead | Francella Fernández |
| UX design and development | plasmativa |
| QA | Rosaelena |
