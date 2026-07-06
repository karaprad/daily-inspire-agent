# 🌟 Daily Inspiration Mailer

> **Capstone Project** — AI Agents: Intensive Vibe Coding  
> **Track**: Concierge Agents — Safe and useful personal assistants for everyday life

An **ambient AI agent** built with [Google ADK](https://adk.dev/) that generates and emails unique, culturally relevant motivational stories to Indian kids every day. No story ever repeats — a Firestore ledger ensures every tale is fresh and inspiring.

---

## 🎯 What It Does

Every day at a scheduled time, this agent:

1. **Checks the story ledger** — Queries Firestore for all previously sent stories
2. **Generates a unique story** — Uses Gemini to craft an original motivational story featuring an Indian kid performing a good deed
3. **Saves to the ledger** — Stores the story in Firestore (with a SHA-256 content hash) to prevent repeats
4. **Emails the story** — Sends a beautifully formatted HTML email to the configured recipient

### Why It's a Concierge Agent

- **Simplifies everyday life** — Parents/teachers get daily, curated, age-appropriate stories without effort
- **Personalized** — Stories are culturally relevant with Indian names, places, festivals, and values
- **Secure** — No PII in story content; credentials in environment variables/Secret Manager; prompt injection defenses
- **Autonomous** — Runs on a schedule with zero human intervention

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Cloud Scheduler                          │
│                 (Daily 7:00 AM IST)                         │
└─────────────┬───────────────────────────────────────────────┘
              │ Pub/Sub trigger
              ▼
┌─────────────────────────────────────────────────────────────┐
│              FastAPI /trigger/pubsub                         │
└─────────────┬───────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────┐
│           Root Agent (daily_inspire_agent)                   │
│           Coordinator — delegates to sub-agent              │
└─────────────┬───────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────┐
│            Story Generator (LlmAgent)                       │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 1. fetch_past_stories() → Firestore                  │   │
│  │ 2. Generate unique story (Gemini + state injection)   │   │
│  │ 3. save_story() → Firestore (with SHA-256 hash)      │   │
│  │ 4. send_email() → Gmail SMTP (HTML formatted)         │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────┐
│  Firestore "stories" collection    │    Gmail SMTP           │
│  (deduplication ledger)            │    (email delivery)     │
└────────────────────────────────────┴────────────────────────┘
```

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **ADK Agent + Tools** (not Workflow graph) | Cleaner for tool-calling flow; LLM orchestrates the sequence |
| **Firestore** for story ledger | Serverless, free-tier, perfect for document storage |
| **SHA-256 content hash** | Robust dedup beyond just title matching |
| **State injection** `{past_story_titles}` | LLM naturally avoids repeats without explicit checks |
| **Gmail SMTP** (not API) | Simpler setup, no OAuth complexity for the prototype |
| **Safety rules in instruction** | Age-appropriate content enforcement + prompt injection defense |

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/getting-started/installation/) package manager
- Google Cloud project with:
  - Firestore enabled (Native mode)
  - Vertex AI API enabled
- Gmail account with [App Password](https://myaccount.google.com/apppasswords) enabled

### 1. Clone and Install

```bash
cd capstone/daily-inspire-agent
uv sync
```

### 2. Configure Environment

Edit the `.env` file with your credentials:

```bash
# GCP (auto-detected if using gcloud auth)
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=global
GOOGLE_GENAI_USE_VERTEXAI=True

# Email
SENDER_EMAIL=your-email@gmail.com
SMTP_PASSWORD=your-gmail-app-password
RECIPIENT_EMAIL=recipient@gmail.com
```

### 3. Authenticate with GCP

```bash
gcloud auth application-default login
gcloud config set project your-project-id
```

### 4. Enable Firestore

```bash
gcloud firestore databases create --location=nam5 --type=firestore-native
```

### 5. Run Locally

```bash
# Quick smoke test
agents-cli run "Generate and send today's motivational story"

# Interactive playground
agents-cli playground
```

### 6. Deploy (Optional)

```bash
# Add deployment target
agents-cli scaffold enhance . --deployment-target agent_runtime

# Deploy
agents-cli deploy
```

---

## 📧 Email Preview

The agent sends beautifully formatted HTML emails with:
- 🌟 Gradient header with "Daily Inspiration" branding
- 📖 Story content with serif typography for readability
- 💡 Highlighted moral/lesson in a green callout
- 📅 Date stamp in the footer

---

## 🔒 Security & Safety

| Measure | Implementation |
|---------|---------------|
| **Child-safe content** | LLM instruction constrains to age 10-14 appropriate themes |
| **No PII exposure** | Email addresses only in env vars, never in story content |
| **Prompt injection defense** | Safety rules in instruction reject manipulation attempts |
| **Credential security** | SMTP password in env vars locally, Secret Manager in production |
| **Content moderation** | Gemini's built-in safety filters active |
| **Deduplication** | SHA-256 hash + title matching prevents repeat stories |

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|-----------|
| Agent Framework | [Google ADK](https://adk.dev/) 2.x |
| LLM | Gemini (via Vertex AI) |
| Story Storage | Google Cloud Firestore |
| Email Delivery | Gmail SMTP |
| CLI Tooling | [agents-cli](https://pypi.org/project/google-agents-cli/) |
| Deployment | Agent Runtime (Vertex AI) |
| Language | Python 3.11+ |

---

## 📁 Project Structure

```
daily-inspire-agent/
├── app/
│   ├── __init__.py          # Module exports
│   ├── agent.py             # Agent definitions (root + story generator)
│   ├── config.py            # Configuration (env vars + defaults)
│   ├── tools.py             # Custom tools (Firestore, Email)
│   ├── fast_api_app.py      # FastAPI serving app
│   └── app_utils/           # Telemetry, typing utilities
├── tests/                   # Eval datasets, unit & integration tests
├── .env                     # Environment configuration
├── pyproject.toml           # Dependencies
├── Dockerfile               # Container build
├── AGENTS.md                # Agent coding guidelines
├── agents-cli-manifest.yaml # CLI configuration
└── README.md                # This file
```

---

## 📚 Course References

This project applies principles from the [AI Agents: Intensive Vibe Coding](https://www.youtube.com/playlist?list=PLqFaTIg4myu8AFXUjrVhDkUGp0A9kK8CX) course:

- **Day 1** — [The New SDLC with Vibe Coding](https://www.kaggle.com/whitepaper-the-new-SDLC-with-vibe-coding) — Agent-first development workflow
- **Day 2** — [Agent Tools and Interoperability](https://www.kaggle.com/whitepaper-agent-tools-and-interoperability) — Custom tool design (Firestore, Email)
- **Day 3** — [Agent Skills](https://www.kaggle.com/whitepaper-agent-skills) — ADK patterns and multi-agent coordination
- **Day 4** — [Security and Evaluation](https://www.kaggle.com/whitepaper-vibe-coding-agent-security-and-evaluation) — Safety guardrails, prompt injection defense
- **Day 5** — [Spec-Driven Production-Grade Development](https://www.kaggle.com/whitepaper-spec-driven-production-grade-development-in-the-age-of-vibe-coding) — Production deployment patterns

---

## 📄 License

Apache License 2.0
