"""Notion → Linear sync for the Product Backlog.

The script moves data; an AI model is used only to judge the quality of
acceptance criteria (see ai_review.py). Everything runs as a dry run unless
--apply is passed.
"""

__version__ = "0.1.0"
