# Instructions for Claude Code

## Free Will work (worktrees)

- Exploration happens in a git worktree on a branch named `wt/<linear-id>-<short-name>`, for example `wt/fra-15-price-filter`.
- When working on a `wt/` branch, every Linear issue you create or update gets the label **Origin › Free Will**.
- Never move a Free Will issue to Done, and never open a pull request to `main` for client delivery from a `wt/` branch. Leave it for review.
- Issues on any other branch come from the Notion handoff and get **Origin › Handoff**.
- Only Francella switches an issue from Free Will to Handoff, after the client approves it in Notion.
- Sanity content is shared between worktrees. Do not change the schema or delete content from a `wt/` branch; use a test dataset for experiments.
