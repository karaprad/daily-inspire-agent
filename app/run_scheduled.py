#!/usr/bin/env python3
"""Headless scheduled runner for the Daily Inspire Agent.

Usage:
    python -m app.run_scheduled

This script programmatically invokes the agent using InMemoryRunner,
sends the story-generation prompt, and exits. Designed to be called
from cron, GitHub Actions, Cloud Scheduler, or any scheduler.
"""

import asyncio
import logging
import sys

from google.adk.runners import InMemoryRunner
from google.genai import types

from app.agent import root_agent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

PROMPT = "Generate a new unique motivational story for today and email it to all subscribers."


async def run() -> bool:
    """Run the agent and return True if the story was emailed successfully."""
    runner = InMemoryRunner(agent=root_agent, app_name="app")
    user_id = "scheduled_runner"
    session = await runner.session_service.create_session(
        app_name="app", user_id=user_id
    )

    logger.info("🚀 Starting scheduled run...")

    content = types.Content(
        role="user", parts=[types.Part.from_text(PROMPT)]
    )

    final_text = ""
    async for event in runner.run_async(
        user_id=user_id, session_id=session.id, new_message=content
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    final_text += part.text

    logger.info("📝 Agent response:\n%s", final_text)

    # Basic success detection
    success = any(
        keyword in final_text.lower()
        for keyword in ["sent successfully", "email sent", "delivered", "success"]
    )

    if success:
        logger.info("✅ Daily inspiration sent successfully!")
    else:
        logger.warning("⚠️  Run completed but email delivery could not be confirmed.")

    return success


def main():
    success = asyncio.run(run())
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
