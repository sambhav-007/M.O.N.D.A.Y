# Product Requirements Document
# Project M.O.N.D.A.Y. — Modular Operational Neural Desktop Assistant for You

**Status**: Draft v1.0 — Execution Engine Architecture  
**Owner**: Siddhant Bhatia (Team Lead)  
**Team**: Siddhant Bhatia, Sambhav Sehgal, Samarth Sharma, Shivansh Chandel  
**Target Platforms**: Windows, macOS, Linux (desktop) + Android, iOS (mobile)  
**Document Type**: Product Requirements Document (PRD)

---

## 1. Executive Summary

M.O.N.D.A.Y. is a multi-agent, cross-platform AI assistant that goes beyond conversational Q&A to execute tasks — controlling a desktop OS, automating browsers, managing communication channels, and maintaining long-term memory of the user's life and work.

The product is positioned as a **"personal AI employee"** rather than a simple voice assistant.

---

## 2. Problem Statement

Current assistants (Siri, Google Assistant, Alexa) are single-utterance command executors. They do not:
1. Maintain persistent context across sessions
2. Chain multi-step tasks across apps/services
3. Act on a user's behalf inside arbitrary desktop or web UIs
4. Reason about what the user needs rather than what they literally said

---

## 3. Risk-Tiered Permission Model (§9)

Rather than a single global confirm/no-confirm switch, every action any agent can take is classified into one of two tiers before dispatch:

| Tier | Examples | Behavior |
|------|----------|----------|
| **Tier 1 — Reversible / Low-Risk** | Open app, read file, take screenshot, search web, move file to recoverable/staging location, draft message | Executes **autonomously**, no prompt. Always logged. |
| **Tier 2 — Irreversible / High-Risk** | Delete file, overwrite document, send email/message, submit form, payment/checkout | **Blocks and requests explicit user approval** with estimated ETA before executing. No exceptions. |

### Implementation status

Enforced by `MasterPlanner.require_tier2_approval()` (`core/planner.py`). A gated
action is parked, the user is asked with the ETA predicted by Component 2.2, and
it runs only after an explicitly affirmative reply in a following turn. An
ambiguous answer re-asks rather than guessing.

Approval **cannot** be granted by a flag on the original request. The method
takes no `user_approved` parameter at all, so the bypass cannot be reintroduced
by a caller passing one through. `ExecuteRequest.user_approved` survives for
backwards compatibility and is ignored by Tier-2 actions.

> **Scope of enforcement.** Three Tier-2 actions actually exist and are gated:
> `delete_folder`, `send_email` and `terminate_process`. WhatsApp only prepares
> a message for the user to send; no send action exists. The other policy names
> (`delete_file`, `overwrite_file`, `send_notification`, `send_whatsapp`,
> `execute_shell`, `submit_form`, `modify_system_settings`, `kill_process`) have
> **no implementation**. They are listed so any future implementation is
> gated from its first commit, not as a claim of existing capability.

---

## 4. System Architecture & Agents

```
User Input / CLI / API
         │
         ▼
┌─────────────────────────────────┐
│ Intent Classifier (ML 2.1)       │──High Conf──▶ Direct Agent Dispatch
└─────────────────────────────────┘
         │ Low Conf
         ▼
┌─────────────────────────────────┐
│ Master Planner (LLM + RL 2.5)   │
└─────────────────────────────────┘
         │
         ├────▶ ComputerAgent (OS File Organiser, Screenshot, App Launcher)
         ├────▶ DocumentAgent (PDF/TXT Parser, Summariser, TF-IDF RAG)
         ├────▶ BrowserAgent (DDG Web Search, Page Scraper, Research Synthesiser)
         ├────▶ CommsAgent (Email Drafting, Gated Sending, Desktop Notifications)
         ├────▶ MemoryAgent (SQLite Knowledge Store, Memory Recall, Clustering 2.3)
         └────▶ HabitAgent (Session Action Mining, Apriori/FP-Growth Habits 2.4)
```

---

## 5. Agent Responsibilities

| Agent | Responsibility | Implementation File |
|-------|----------------|---------------------|
| **MasterPlanner** | Intention routing (2.1), RL strategy selection (2.5), task DAG decomposition | `core/planner.py` |
| **ComputerAgent** | File extension categorizer, screenshot capture, app launcher, health stats | `agents/computer_agent.py` |
| **DocumentAgent** | PDF/TXT extraction, extractive summarisation, TF-IDF RAG search | `agents/document_agent.py` |
| **BrowserAgent** | Live web search, HTML body scraping, multi-source research report | `agents/browser_agent.py` |
| **CommunicationAgent** | Email draft creation, gated transmission, desktop notifications | `agents/comms_agent.py` |
| **MemoryAgent** | SQLite relational store, key-value memory recall, proactive suggestions (2.3) | `agents/memory_agent.py` |
| **HabitAgent** | Workflow session logging, association rule mining for automation (2.4) | `agents/habit_agent.py` |
| **VoiceAgent** | Text-to-speech output synthesis, speech recognition listener | `agents/voice_agent.py` |

---

## 6. Desktop Application Shell & Architecture Update

> [!NOTE]
> **Implementation Specification Update**: The desktop interface shell has been implemented as a **Python WebGL Desktop Application (`app.py` & `ui/index.html`)** providing zero-overhead, direct integration with the FastAPI engine (`api/main.py`) and Master Planner. This native WebGL Python shell supersedes legacy experimental Tauri references.

- **Frameless Native OS Window (`app.py`)**: Borderless window execution (`frameless=True`, `easy_drag=True`) with native JavaScript bridge (`DesktopWindowApi`) supporting `✕` close, `—` minimize, and `Esc` keyboard shortcut.
- **Dual Presentation Modes**:
  - **Presence Mode** (Default): Fullscreen 3D WebGL Living Entity with zero app chrome. Entity states (`idle`, `listening`, `thinking`, `speaking`) are communicated 100% visually through an audio-reactive particle field and GLSL Fresnel rim lighting shader. Push-to-talk via Spacebar.
  - **Console Mode**: Full developer diagnostic console with real-time multi-agent execution logs and command input. Toggleable via `Ctrl+``.
- **Multi-Turn Clarification Engine (`pending_clarification`)**:
  - Pauses task execution on ambiguous inputs or unresolved contacts.
  - Prompts the user with numbered candidate options, caches confirmed choices to persistent SQLite memory (`memories.db`), and resumes the paused task seamlessly.
- **Multi-Source Contact Resolution Engine** — ⚠️ **partially active**. The code
  paths exist in `agents/comms_agent.py`, but the first two require dependencies
  that are neither installed nor declared in `requirements.txt`, so at runtime
  resolution falls through to the local sources:
  - Live Google People API (OAuth2 `InstalledAppFlow` storing `data/google_token.json`) — **inactive**, needs `googleapiclient` + `google_auth_oauthlib`.
  - Microsoft Outlook MAPI COM store (`win32com.client.Dispatch("Outlook.Application")`) — **inactive**, needs `pywin32`.
  - Local Windows Contacts (`%USERPROFILE%\Contacts`) — active.
  - SQLite persistent memory matrix — active.
- **Level of Detail (LOD) Quality Selector**: Dynamic runtime particle density switching (High: 8,000 p, Balanced: 4,000 p, Battery Saver: 1,800 p) with integrated FPS counter to ensure smooth performance across all GPU environments.
