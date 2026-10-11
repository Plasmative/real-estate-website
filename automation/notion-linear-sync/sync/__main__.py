"""Command line: python -m sync [--apply] [--exclude-examples]"""

from __future__ import annotations

import argparse
import os
import sys

from .ai_review import ClaudeReviewer, HeuristicReviewer
from .config import Config
from .engine import SyncEngine
from .linear_client import LinearClient
from .notion_client import NotionClient


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync the Notion Product Backlog to Linear.")
    parser.add_argument("--apply", action="store_true", help="Write changes. Without it, this is a dry run.")
    parser.add_argument("--exclude-examples", action="store_true", help="Skip rows marked Example (test data).")
    args = parser.parse_args(argv)

    config = Config.from_env()
    if args.exclude_examples:
        config = Config(**{**config.__dict__, "include_examples": False})
    missing = config.missing_secrets()
    if missing:
        print(f"Missing secrets: {', '.join(missing)}", file=sys.stderr)
        return 2

    notion = NotionClient(config.notion_token, config.notion_version, config.backlog_data_source_id)
    linear = LinearClient(config.linear_api_key, config.linear_team_key, config.linear_project_name,
                          config.linear_new_issue_state)
    reviewer = (ClaudeReviewer(config.anthropic_api_key, config.anthropic_model)
                if config.anthropic_api_key else HeuristicReviewer())

    report = SyncEngine(notion, linear, reviewer, config, apply=args.apply).run()
    summary = report.markdown()
    print(summary)
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as fh:
            fh.write(summary)
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
