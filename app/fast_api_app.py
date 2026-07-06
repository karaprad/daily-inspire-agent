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
import os

import google.auth
from fastapi import FastAPI
from google.adk.cli.fast_api import get_fast_api_app
from google.cloud import logging as google_cloud_logging

from app.app_utils.telemetry import setup_telemetry
from app.app_utils.typing import Feedback

setup_telemetry()

# Try setting up GCP logging; fall back to local logging if credentials are not found
try:
    _, project_id = google.auth.default()
    logging_client = google_cloud_logging.Client()
    logger = logging_client.logger(__name__)
    otel_to_cloud = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "True").lower() == "true"
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO)
    class LocalLogger:
        def log_struct(self, data, severity="INFO"):
            logging.info(f"Feedback structure (Severity {severity}): {data}")
    logger = LocalLogger()
    otel_to_cloud = False

allow_origins = (
    os.getenv("ALLOW_ORIGINS", "").split(",") if os.getenv("ALLOW_ORIGINS") else ["*"]
)

# Artifact bucket for ADK (created by Terraform, passed via env var)
logs_bucket_name = os.environ.get("LOGS_BUCKET_NAME")

AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# In-memory session configuration - no persistent storage
session_service_uri = None

artifact_service_uri = f"gs://{logs_bucket_name}" if logs_bucket_name else None

app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    web=True,
    artifact_service_uri=artifact_service_uri,
    allow_origins=allow_origins,
    session_service_uri=session_service_uri,
    otel_to_cloud=otel_to_cloud,
)
app.title = "daily-inspire-agent"
app.description = "API for interacting with the Agent daily-inspire-agent"

from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/feedback")
def collect_feedback(feedback: Feedback) -> dict[str, str]:
    """Collect and log feedback.

    Args:
        feedback: The feedback data to log

    Returns:
        Success message
    """
    logger.log_struct(feedback.model_dump(), severity="INFO")
    return {"status": "success"}


import json
from fastapi import HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

class SubscribeRequest(BaseModel):
    email: str

@app.get("/api/stories")
def get_stories():
    """Fetches all stories from Firestore or the local JSON fallback."""
    from app.tools import _use_firestore, _load_local_stories, config
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
                past_stories.append({
                    "title": data.get("title", ""),
                    "content": data.get("content", ""),
                    "moral": data.get("moral", ""),
                    "date_sent": data.get("date_sent", ""),
                    "topic": data.get("topic", "")
                })
            return past_stories
        except Exception as e:
            pass
            
    # Local fallback
    local_stories = _load_local_stories()
    return [{
        "title": s.get("title", ""),
        "content": s.get("content", ""),
        "moral": s.get("moral", ""),
        "date_sent": s.get("date_sent", ""),
        "topic": s.get("topic", "")
    } for s in reversed(local_stories)]


@app.post("/api/subscribe")
def subscribe(request: SubscribeRequest):
    """Subscribes an email to the daily story mailing list."""
    from app.tools import _use_firestore, config
    email = request.email.strip().lower()
    
    import re
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        raise HTTPException(status_code=400, detail="Invalid email address.")
        
    if _use_firestore():
        try:
            from google.cloud import firestore
            db = firestore.Client(project=config.GCP_PROJECT)
            subs_ref = db.collection("subscribers")
            
            dup = subs_ref.where("email", "==", email).limit(1).stream()
            if any(dup):
                return {"status": "already_subscribed", "message": "You are already subscribed!"}
                
            subs_ref.add({
                "email": email,
                "subscribed_at": firestore.SERVER_TIMESTAMP
            })
            return {"status": "success", "message": "Successfully subscribed!"}
        except Exception as e:
            pass
            
    # Local fallback
    local_subs_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "subscribers_ledger.json")
    subs = []
    if os.path.exists(local_subs_file):
        try:
            with open(local_subs_file, "r") as f:
                subs = json.load(f)
        except Exception:
            pass
            
    if email in subs:
        return {"status": "already_subscribed", "message": "You are already subscribed!"}
        
    subs.append(email)
    try:
        with open(local_subs_file, "w") as f:
            json.dump(subs, f, indent=2)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write subscription: {e}")
        
    return {"status": "success", "message": "Successfully subscribed!"}


@app.get("/api/stats")
def get_stats():
    """Fetches total story counts and subscriber counts."""
    from app.tools import _use_firestore, _load_local_stories, config
    
    # Get stories count
    stories_count = 0
    if _use_firestore():
        try:
            from google.cloud import firestore
            db = firestore.Client(project=config.GCP_PROJECT)
            stories_ref = db.collection(config.FIRESTORE_COLLECTION)
            stories_count = len(list(stories_ref.select([]).stream()))
        except Exception:
            pass
    if stories_count == 0:
        stories_count = len(_load_local_stories())
        
    # Get subscribers count
    subs_count = 0
    if _use_firestore():
        try:
            from google.cloud import firestore
            db = firestore.Client(project=config.GCP_PROJECT)
            subs_ref = db.collection("subscribers")
            subs_count = len(list(subs_ref.select([]).stream()))
        except Exception:
            pass
    if subs_count == 0:
        local_subs_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "subscribers_ledger.json")
        if os.path.exists(local_subs_file):
            try:
                with open(local_subs_file, "r") as f:
                    subs_count = len(json.load(f))
            except Exception:
                pass
        else:
            subs_count = 1 if config.RECIPIENT_EMAIL else 0
            
    return {"stories_count": stories_count, "subscribers_count": subs_count}


DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Daily Inspiration Story Archive & Subscription</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Outfit:wght@600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #090514;
            --surface: rgba(255, 255, 255, 0.03);
            --border: rgba(255, 255, 255, 0.08);
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --accent: #ff6b35;
            --accent-glow: rgba(255, 107, 53, 0.35);
            --purple-accent: #a855f7;
            --purple-glow: rgba(168, 85, 247, 0.35);
            --success: #10b981;
            --success-glow: rgba(16, 185, 129, 0.25);
        }
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }
        body {
            background-color: var(--bg);
            color: var(--text-primary);
            font-family: 'Inter', sans-serif;
            line-height: 1.6;
            overflow-x: hidden;
            min-height: 100vh;
            position: relative;
        }
        .glow {
            position: fixed;
            width: 450px;
            height: 450px;
            border-radius: 50%;
            pointer-events: none;
            filter: blur(130px);
            opacity: 0.18;
            z-index: 0;
        }
        .glow-1 {
            background: var(--accent);
            top: -150px;
            left: -100px;
        }
        .glow-2 {
            background: var(--purple-accent);
            bottom: -150px;
            right: -100px;
        }
        
        header {
            position: relative;
            z-index: 10;
            max-width: 1200px;
            margin: 0 auto;
            padding: 40px 20px 20px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }
        .logo h1 {
            font-family: 'Outfit', sans-serif;
            font-size: 1.8rem;
            font-weight: 800;
            background: linear-gradient(135deg, #fff 0%, var(--accent) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .logo p {
            font-size: 0.85rem;
            color: var(--text-secondary);
            margin-top: 3px;
        }

        .stats-container {
            display: flex;
            gap: 15px;
        }
        .stat-badge {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 8px 16px;
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 0.85rem;
            color: var(--text-secondary);
        }
        .stat-badge span.number {
            font-weight: 700;
            color: var(--text-primary);
        }

        main {
            position: relative;
            z-index: 10;
            max-width: 1200px;
            margin: 40px auto;
            padding: 0 20px;
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 40px;
        }

        @media (max-width: 900px) {
            main {
                grid-template-columns: 1fr;
            }
        }

        .subscribe-card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 20px;
            padding: 30px;
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.25);
            align-self: start;
            position: sticky;
            top: 40px;
            transition: border-color 0.3s ease;
        }
        .subscribe-card:hover {
            border-color: rgba(255, 107, 53, 0.25);
        }
        .subscribe-card h2 {
            font-family: 'Outfit', sans-serif;
            font-size: 1.4rem;
            margin-bottom: 12px;
            color: var(--text-primary);
        }
        .subscribe-card p {
            font-size: 0.9rem;
            color: var(--text-secondary);
            margin-bottom: 24px;
            line-height: 1.5;
        }
        .form-group {
            margin-bottom: 16px;
        }
        .form-group label {
            display: block;
            font-size: 0.8rem;
            color: var(--text-secondary);
            margin-bottom: 6px;
            text-transform: uppercase;
            font-weight: 600;
            letter-spacing: 0.5px;
        }
        .form-group input {
            width: 100%;
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid var(--border);
            color: var(--text-primary);
            border-radius: 12px;
            padding: 12px 16px;
            font-size: 0.95rem;
            transition: all 0.3s ease;
        }
        .form-group input:focus {
            outline: none;
            border-color: var(--accent);
            box-shadow: 0 0 10px var(--accent-glow);
            background: rgba(255, 255, 255, 0.05);
        }
        .btn-subscribe {
            width: 100%;
            background: linear-gradient(135deg, var(--accent) 0%, #e0531f 100%);
            color: white;
            border: none;
            border-radius: 12px;
            padding: 14px;
            font-weight: 600;
            font-size: 1rem;
            cursor: pointer;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px var(--accent-glow);
        }
        .btn-subscribe:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px var(--accent-glow);
        }
        
        .msg {
            margin-top: 15px;
            padding: 12px;
            border-radius: 8px;
            font-size: 0.85rem;
            display: none;
            text-align: center;
        }
        .msg-success {
            background: rgba(16, 185, 129, 0.1);
            border: 1px solid var(--success);
            color: #6ee7b7;
        }
        .msg-error {
            background: rgba(239, 68, 68, 0.1);
            border: 1px solid #ef4444;
            color: #fca5a5;
        }

        .archive-title {
            font-family: 'Outfit', sans-serif;
            font-size: 1.5rem;
            margin-bottom: 24px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .stories-grid {
            display: flex;
            flex-direction: column;
            gap: 20px;
        }
        .story-card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 24px;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }
        .story-card:hover {
            border-color: rgba(255, 255, 255, 0.15);
            transform: translateY(-4px);
            box-shadow: 0 8px 30px rgba(168, 85, 247, 0.08);
        }
        .card-meta {
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 0.75rem;
            color: var(--text-secondary);
            margin-bottom: 12px;
        }
        .card-title {
            font-family: 'Outfit', sans-serif;
            font-size: 1.25rem;
            color: var(--text-primary);
            margin-bottom: 10px;
            font-weight: 700;
        }
        .card-moral {
            background: rgba(16, 185, 129, 0.05);
            border: 1px solid rgba(16, 185, 129, 0.15);
            color: #34d399;
            padding: 8px 12px;
            border-radius: 8px;
            font-size: 0.8rem;
            font-style: italic;
            margin-bottom: 16px;
        }
        .btn-read {
            align-self: flex-start;
            background: transparent;
            border: 1px solid var(--border);
            color: var(--text-primary);
            padding: 8px 16px;
            border-radius: 8px;
            font-size: 0.85rem;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.3s ease;
        }
        .btn-read:hover {
            background: rgba(255, 255, 255, 0.05);
            border-color: var(--text-secondary);
        }

        .empty-state {
            text-align: center;
            padding: 80px 20px;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 16px;
        }
        .empty-icon {
            font-size: 3rem;
            margin-bottom: 15px;
            opacity: 0.5;
        }

        dialog {
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%) scale(0.95);
            width: 90%;
            max-width: 650px;
            background: rgba(15, 11, 24, 0.94);
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 20px;
            padding: 30px;
            color: var(--text-primary);
            box-shadow: 0 20px 50px rgba(0,0,0,0.5);
            backdrop-filter: blur(25px);
            -webkit-backdrop-filter: blur(25px);
            opacity: 0;
            display: flex;
            flex-direction: column;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            transition-behavior: allow-discrete;
        }
        dialog[open] {
            opacity: 1;
            transform: translate(-50%, -50%) scale(1);
            @starting-style {
                opacity: 0;
                transform: translate(-50%, -50%) scale(0.95);
            }
        }
        dialog::backdrop {
            background: rgba(9, 7, 16, 0.85);
            backdrop-filter: blur(8px);
            opacity: 0;
            transition: all 0.3s ease-out;
            transition-behavior: allow-discrete;
        }
        dialog[open]::backdrop {
            opacity: 1;
            @starting-style {
                opacity: 0;
            }
        }
        .dialog-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            border-bottom: 1px solid rgba(255,255,255,0.06);
            padding-bottom: 12px;
        }
        .dialog-header h3 {
            font-family: 'Outfit', sans-serif;
            font-size: 1.4rem;
        }
        .close-btn {
            background: rgba(255,255,255,0.05);
            border: none;
            color: white;
            width: 32px;
            height: 32px;
            border-radius: 50%;
            font-size: 1rem;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.3s ease;
        }
        .close-btn:hover {
            background: rgba(255,255,255,0.12);
            transform: rotate(90deg);
        }
        .dialog-body {
            max-height: 400px;
            overflow-y: auto;
            font-size: 0.95rem;
            line-height: 1.8;
            color: #cbd5e1;
            margin-bottom: 20px;
            padding-right: 8px;
        }
        .dialog-moral {
            background: rgba(16, 185, 129, 0.08);
            border: 1px solid rgba(16, 185, 129, 0.2);
            color: #10b981;
            padding: 12px 16px;
            border-radius: 12px;
            font-size: 0.9rem;
            font-style: italic;
        }
        
        .loading-spinner {
            border: 3px solid rgba(255, 255, 255, 0.1);
            border-top: 3px solid var(--accent);
            border-radius: 50%;
            width: 24px;
            height: 24px;
            animation: spin 1s linear infinite;
            margin: 20px auto;
            display: none;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
    </style>
</head>
<body>
    <div class="glow glow-1"></div>
    <div class="glow glow-2"></div>

    <header>
        <div class="logo">
            <h1>🌟 Inspiration Ledger</h1>
            <p>Daily Motivational Stories Archive</p>
        </div>
        <div class="stats-container">
            <div class="stat-badge">
                📖 Stories: <span class="number" id="stories-count">0</span>
            </div>
            <div class="stat-badge">
                👥 Subscribers: <span class="number" id="subs-count">0</span>
            </div>
        </div>
    </header>

    <main>
        <section>
            <h2 class="archive-title">📖 Motivational Story Feed</h2>
            <div class="loading-spinner" id="stories-spinner"></div>
            <div class="stories-grid" id="stories-grid"></div>
        </section>

        <section>
            <div class="subscribe-card">
                <h2>📬 Join Mailing List</h2>
                <p>Subscribe to receive unique, child-safe motivational stories emailed daily. Never repeats!</p>
                
                <form id="subscribe-form">
                    <div class="form-group">
                        <label for="email">Email Address</label>
                        <input type="email" id="email" placeholder="e.g. arjun@gmail.com" required>
                    </div>
                    <button type="submit" class="btn-subscribe" id="btn-submit">
                        Subscribe Now
                    </button>
                </form>
                
                <div class="msg msg-success" id="success-msg">Successfully subscribed!</div>
                <div class="msg msg-error" id="error-msg">Failed to subscribe.</div>
            </div>
        </section>
    </main>

    <dialog id="story-dialog">
        <div class="dialog-header">
            <h3 id="dialog-title">Story Title</h3>
            <button class="close-btn" onclick="closeDialog()">&times;</button>
        </div>
        <div class="dialog-body" id="dialog-content"></div>
        <div class="dialog-moral" id="dialog-moral"></div>
    </dialog>

    <script>
        const storiesGrid = document.getElementById('stories-grid');
        const storiesSpinner = document.getElementById('stories-spinner');
        const subscribeForm = document.getElementById('subscribe-form');
        const emailInput = document.getElementById('email');
        const successMsg = document.getElementById('success-msg');
        const errorMsg = document.getElementById('error-msg');
        const btnSubmit = document.getElementById('btn-submit');
        const storiesCount = document.getElementById('stories-count');
        const subsCount = document.getElementById('subs-count');
        const storyDialog = document.getElementById('story-dialog');

        async function fetchStats() {
            try {
                const res = await fetch('/api/stats');
                if (res.ok) {
                    const stats = await res.json();
                    storiesCount.textContent = stats.stories_count;
                    subsCount.textContent = stats.subscribers_count;
                }
            } catch (err) {
                console.error(err);
            }
        }

        async function fetchStories() {
            storiesSpinner.style.display = 'block';
            storiesGrid.innerHTML = '';
            
            try {
                const res = await fetch('/api/stories');
                storiesSpinner.style.display = 'none';
                
                if (res.ok) {
                    const stories = await res.json();
                    if (stories.length === 0) {
                        storiesGrid.innerHTML = `
                            <div class="empty-state">
                                <div class="empty-icon">✨</div>
                                <h3>No stories generated yet</h3>
                                <p>Stories will appear here once the scheduled agent runs.</p>
                            </div>
                        `;
                    } else {
                        stories.forEach(story => {
                            const dateStr = story.date_sent || 'Recently';
                            const card = document.createElement('div');
                            card.className = 'story-card';
                            card.innerHTML = `
                                <div class="card-meta">
                                    <span>🌟 Topic: ${story.topic || 'Motivation'}</span>
                                    <span>📅 ${dateStr}</span>
                                </div>
                                <h3 class="card-title">${escapeHtml(story.title)}</h3>
                                <div class="card-moral">💡 Moral: ${escapeHtml(story.moral)}</div>
                                <button class="btn-read" onclick="openStory('${escapeHtml(story.title)}', '${escapeHtml(story.content)}', '${escapeHtml(story.moral)}')">
                                    Read Full Story
                                </button>
                            `;
                            storiesGrid.appendChild(card);
                        });
                    }
                } else {
                    storiesGrid.innerHTML = '<p class="msg-error" style="display:block">Failed to load stories.</p>';
                }
            } catch (err) {
                storiesSpinner.style.display = 'none';
                storiesGrid.innerHTML = '<p class="msg-error" style="display:block">Error connecting to api.</p>';
            }
        }

        function escapeHtml(str) {
            if (!str) return '';
            return str
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/"/g, "&quot;")
                .replace(/'/g, "&#039;")
                .replace(/\\n/g, "\n");
        }

        function openStory(title, content, moral) {
            document.getElementById('dialog-title').textContent = title;
            document.getElementById('dialog-content').innerHTML = content.replace(/\\n/g, '<br><br>').replace(/\n/g, '<br><br>');
            document.getElementById('dialog-moral').innerHTML = `💡 <strong>Moral:</strong> ${moral}`;
            storyDialog.showModal();
        }

        function closeDialog() {
            storyDialog.close();
        }

        subscribeForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            successMsg.style.display = 'none';
            errorMsg.style.display = 'none';
            btnSubmit.disabled = true;
            btnSubmit.textContent = 'Subscribing...';

            const email = emailInput.value;

            try {
                const res = await fetch('/api/subscribe', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email })
                });

                btnSubmit.disabled = false;
                btnSubmit.textContent = 'Subscribe Now';

                if (res.ok) {
                    const data = await res.json();
                    if (data.status === 'success' || data.status === 'already_subscribed') {
                        successMsg.textContent = data.message;
                        successMsg.style.display = 'block';
                        emailInput.value = '';
                        fetchStats();
                    } else {
                        errorMsg.textContent = data.message || 'Failed to subscribe.';
                        errorMsg.style.display = 'block';
                    }
                } else {
                    const data = await res.json();
                    errorMsg.textContent = data.detail || 'Invalid email or server error.';
                    errorMsg.style.display = 'block';
                }
            } catch (err) {
                btnSubmit.disabled = false;
                btnSubmit.textContent = 'Subscribe Now';
                errorMsg.textContent = 'Failed to connect to the server.';
                errorMsg.style.display = 'block';
            }
        });

        fetchStats();
        fetchStories();
    </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    """Serves the glassmorphic inspiration story archive dashboard."""
    return HTMLResponse(content=DASHBOARD_HTML)


# Main execution
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
