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

"""Configuration for the Daily Inspiration Mailer agent."""

import os
from pydantic import BaseModel, Field


class AgentConfig(BaseModel):
    """Agent configuration loaded from environment variables."""

    # Email configuration
    RECIPIENT_EMAIL: str = Field(
        default_factory=lambda: os.environ.get("RECIPIENT_EMAIL", "")
    )
    SENDER_EMAIL: str = Field(
        default_factory=lambda: os.environ.get("SENDER_EMAIL", "")
    )
    SMTP_PASSWORD: str = Field(
        default_factory=lambda: os.environ.get("SMTP_PASSWORD", "")
    )
    SMTP_HOST: str = Field(
        default_factory=lambda: os.environ.get("SMTP_HOST", "smtp.gmail.com")
    )
    SMTP_PORT: int = Field(
        default_factory=lambda: int(os.environ.get("SMTP_PORT", "587"))
    )

    # Story configuration
    TOPIC: str = Field(
        default="Motivational story for a 12 year old Indian kid with a good deed"
    )
    STORY_LENGTH: str = Field(default="300-500 words")
    ENABLE_WEB_SEARCH: bool = Field(
        default_factory=lambda: os.environ.get("ENABLE_WEB_SEARCH", "true").lower()
        == "true"
    )

    # GCP / Firestore configuration
    GCP_PROJECT: str = Field(
        default_factory=lambda: os.environ.get("GOOGLE_CLOUD_PROJECT", "")
    )
    FIRESTORE_COLLECTION: str = Field(default="stories")

    # Model configuration
    MODEL_NAME: str = Field(default="gemini-2.5-flash")


config = AgentConfig()
