# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Custom tools for the Daily Inspiration Mailer agent.

Tools provide the agent with capabilities to:
- Fetch past stories from Firestore or local JSON (deduplication ledger)
- Save new stories to Firestore or local JSON
- Send stories via email (Gmail SMTP)

When Firestore is not available (no GCP project configured), the tools
automatically fall back to a local JSON file for story storage.
"""

import hashlib
import json
import logging
import os
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from google.adk.tools import ToolContext

from app.config import config

logger = logging.getLogger(__name__)

# Local JSON file path for fallback storage (when Firestore isn't available)
LOCAL_STORIES_FILE = Path(__file__).parent.parent / "stories_ledger.json"


def _use_firestore() -> bool:
    """Check if Firestore is available (GCP project configured)."""
    return bool(config.GCP_PROJECT)


def _load_local_stories() -> list[dict]:
    """Load stories from local JSON file."""
    if LOCAL_STORIES_FILE.exists():
        try:
            with open(LOCAL_STORIES_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []
    return []


def _save_local_stories(stories: list[dict]) -> None:
    """Save stories to local JSON file."""
    with open(LOCAL_STORIES_FILE, "w") as f:
        json.dump(stories, f, indent=2, ensure_ascii=False)


def fetch_past_stories(tool_context: ToolContext) -> dict:
    """Fetch the titles and summaries of all previously sent stories.

    Uses Firestore if GCP is configured, otherwise falls back to a local JSON file.
    This is used to ensure the agent never generates a duplicate story.

    Returns:
        A dict with 'status', 'count', and 'past_stories' (list of past story titles).
    """
    past_stories = []

    if _use_firestore():
        try:
            from google.cloud import firestore

            db = firestore.Client(project=config.GCP_PROJECT)
            stories_ref = db.collection(config.FIRESTORE_COLLECTION)
            docs = stories_ref.order_by(
                "created_at", direction=firestore.Query.DESCENDING
            ).stream()

            for doc in docs:
                data = doc.to_dict()
                past_stories.append(
                    {
                        "title": data.get("title", ""),
                        "moral": data.get("moral", ""),
                        "date_sent": data.get("date_sent", ""),
                    }
                )
        except Exception as e:
            logger.warning(f"Firestore unavailable, using local fallback: {e}")
            past_stories = [
                {"title": s["title"], "moral": s["moral"], "date_sent": s["date_sent"]}
                for s in _load_local_stories()
            ]
    else:
        # Local JSON fallback
        past_stories = [
            {"title": s["title"], "moral": s["moral"], "date_sent": s["date_sent"]}
            for s in _load_local_stories()
        ]

    # Store in agent state for the LLM to reference
    tool_context.state["past_story_titles"] = "\n".join(
        [f"- {s['title']} (moral: {s['moral']})" for s in past_stories]
    )
    tool_context.state["past_story_count"] = len(past_stories)

    storage = "Firestore" if _use_firestore() else "local JSON"
    return {
        "status": "success",
        "storage": storage,
        "count": len(past_stories),
        "past_stories": past_stories,
    }


def save_story(title: str, content: str, moral: str, tool_context: ToolContext) -> dict:
    """Save a generated story to prevent future duplicates.

    Uses Firestore if GCP is configured, otherwise saves to a local JSON file.

    Args:
        title: The title of the motivational story.
        content: The full story text.
        moral: The moral or lesson of the story.

    Returns:
        A dict with 'status' and the saved document 'id'.
    """
    content_hash = hashlib.sha256(content.strip().lower().encode()).hexdigest()
    date_sent = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if _use_firestore():
        try:
            from google.cloud import firestore

            db = firestore.Client(project=config.GCP_PROJECT)
            stories_ref = db.collection(config.FIRESTORE_COLLECTION)

            # Check if hash already exists in Firestore
            dup_query = stories_ref.where("content_hash", "==", content_hash).limit(1).stream()
            if any(dup_query):
                logger.warning(f"Duplicate story detected in Firestore: {title} (hash: {content_hash})")
                return {
                    "status": "error",
                    "error": f"Duplicate story detected (SHA-256 match for hash {content_hash}). Please generate a different story."
                }

            story_doc = {
                "title": title,
                "content": content,
                "moral": moral,
                "content_hash": content_hash,
                "date_sent": date_sent,
                "created_at": firestore.SERVER_TIMESTAMP,
                "topic": config.TOPIC,
                "recipient": config.RECIPIENT_EMAIL,
            }

            doc_ref = stories_ref.add(story_doc)
            doc_id = doc_ref[1].id
            logger.info(f"Story saved to Firestore: {title} (id: {doc_id})")

            return {"status": "success", "storage": "Firestore", "id": doc_id, "title": title}

        except Exception as e:
            logger.warning(f"Firestore save failed, using local fallback: {e}")

    # Duplicate check in Local JSON
    stories = _load_local_stories()
    for s in stories:
        if s.get("content_hash") == content_hash:
            logger.warning(f"Duplicate story detected locally: {title} (hash: {content_hash})")
            return {
                "status": "error",
                "error": f"Duplicate story detected (SHA-256 match for hash {content_hash}). Please generate a different story."
            }

    # Local JSON fallback save
    story_entry = {
        "title": title,
        "content": content,
        "moral": moral,
        "content_hash": content_hash,
        "date_sent": date_sent,
        "topic": config.TOPIC,
        "recipient": config.RECIPIENT_EMAIL,
    }
    stories.append(story_entry)
    _save_local_stories(stories)

    logger.info(f"Story saved locally: {title}")
    return {
        "status": "success",
        "storage": "local JSON",
        "id": content_hash[:12],
        "title": title,
    }


def send_email(subject: str, story_title: str, story_content: str, story_moral: str, tool_context: ToolContext) -> dict:
    """Send the motivational story via email to all active subscribers.

    Args:
        subject: The email subject line.
        story_title: The title of the story.
        story_content: The full story text.
        story_moral: The moral of the story.

    Returns:
        A dict with 'status' indicating success or failure.
    """
    if not config.SENDER_EMAIL or not config.SMTP_PASSWORD:
        return {
            "status": "error",
            "error": "Email credentials not configured. Set SENDER_EMAIL and SMTP_PASSWORD in .env",
        }

    # Fetch subscribers from Firestore or Local Fallback
    recipients = []
    if _use_firestore():
        try:
            from google.cloud import firestore
            db = firestore.Client(project=config.GCP_PROJECT)
            subs_ref = db.collection("subscribers").stream()
            for doc in subs_ref:
                data = doc.to_dict()
                if data.get("email"):
                    recipients.append(data.get("email"))
            logger.info(f"Loaded {len(recipients)} subscribers from Firestore.")
        except Exception as e:
            logger.warning(f"Failed to load subscribers from Firestore: {e}")

    if not recipients:
        # Check Local Fallback
        local_subs_file = Path(__file__).parent.parent / "subscribers_ledger.json"
        if local_subs_file.exists():
            try:
                with open(local_subs_file, "r") as f:
                    recipients = json.load(f)
                logger.info(f"Loaded {len(recipients)} subscribers from local JSON.")
            except Exception as e:
                logger.warning(f"Failed to load local subscribers: {e}")

    # Default to config RECIPIENT_EMAIL if list is empty
    if not recipients and config.RECIPIENT_EMAIL:
        recipients = [config.RECIPIENT_EMAIL]

    if not recipients:
        return {
            "status": "error",
            "error": "No recipients configured or subscribed.",
        }

    # Build HTML email body
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{
                font-family: 'Georgia', serif;
                max-width: 600px;
                margin: 0 auto;
                padding: 20px;
                background-color: #fefae0;
                color: #333;
            }}
            .header {{
                background: linear-gradient(135deg, #ff6b35, #f7c59f);
                color: white;
                padding: 20px;
                border-radius: 12px;
                text-align: center;
                margin-bottom: 20px;
            }}
            .header h1 {{
                margin: 0;
                font-size: 22px;
            }}
            .header p {{
                margin: 5px 0 0 0;
                font-size: 13px;
                opacity: 0.9;
            }}
            .story-title {{
                font-size: 20px;
                color: #2d6a4f;
                text-align: center;
                margin: 20px 0 10px 0;
                font-weight: bold;
            }}
            .story-content {{
                line-height: 1.8;
                font-size: 15px;
                padding: 15px 20px;
                background: white;
                border-radius: 8px;
                border-left: 4px solid #ff6b35;
            }}
            .moral {{
                background: #d4edda;
                padding: 15px;
                border-radius: 8px;
                margin-top: 15px;
                font-style: italic;
                text-align: center;
                color: #155724;
            }}
            .footer {{
                text-align: center;
                margin-top: 20px;
                font-size: 12px;
                color: #888;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🌟 Daily Inspiration 🌟</h1>
            <p>A motivational story just for you!</p>
        </div>
        <div class="story-title">{story_title}</div>
        <div class="story-content">
            {story_content.replace(chr(10), '<br>')}
        </div>
        <div class="moral">
            💡 <strong>Moral:</strong> {story_moral}
        </div>
        <div class="footer">
            <p>Sent with ❤️ by Daily Inspiration Mailer</p>
            <p>{datetime.now(timezone.utc).strftime('%B %d, %Y')}</p>
        </div>
    </body>
    </html>
    """

    success_count = 0
    errors = []

    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as server:
            server.starttls()
            server.login(config.SENDER_EMAIL, config.SMTP_PASSWORD)
            
            for recipient in recipients:
                try:
                    msg = MIMEMultipart("alternative")
                    msg["Subject"] = subject
                    msg["From"] = config.SENDER_EMAIL
                    msg["To"] = recipient

                    # Plain text fallback
                    plain_text = f"{story_title}\n\n{story_content}\n\nMoral: {story_moral}"
                    msg.attach(MIMEText(plain_text, "plain"))
                    msg.attach(MIMEText(html_body, "html"))

                    server.send_message(msg)
                    success_count += 1
                except Exception as sub_err:
                    logger.error(f"Error sending to {recipient}: {sub_err}")
                    errors.append(f"{recipient}: {str(sub_err)}")

        logger.info(f"Emails sent successfully to {success_count}/{len(recipients)} recipients.")

        return {
            "status": "success",
            "recipients_sent": success_count,
            "total_recipients": len(recipients),
            "errors": errors,
            "subject": subject,
        }

    except Exception as e:
        logger.error(f"SMTP connection error: {e}")
        return {
            "status": "error",
            "error": str(e),
        }
