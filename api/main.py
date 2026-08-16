"""
M.O.N.D.A.Y. — FastAPI Multi-Agent Execution Server
=====================================================
Exposes all 5 ML components + Real Worker Agents as REST endpoints
for live demonstration, web site integration, and external execution.

Usage
-----
    pip install -r requirements.txt
    uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
    # Open: http://localhost:8000/docs
"""

from __future__ import annotations

import io
import os
import sys

# Force Windows console stdout/stderr to UTF-8 with errors='replace'
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import warnings
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

# Allow imports from parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path

import json
import queue
import threading
import time

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.planner import MasterPlanner
from core.security import get_action_history
from ml.intent_classifier import predict_intent

warnings.filterwarnings("ignore")

# Global Master Planner Instance
_PLANNER: Optional[MasterPlanner] = None

def get_planner() -> MasterPlanner:
    """Returns global MasterPlanner instance, initializing if needed."""
    global _PLANNER
    if _PLANNER is None:
        _PLANNER = MasterPlanner()
    return _PLANNER


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Pre-load ML models and Master Planner at server startup."""
    print("🚀 M.O.N.D.A.Y. Multi-Agent API starting up — loading engine...")

    try:
        get_planner()
        print("  ✓ Master Planner & Worker Agents online.")
    except Exception as e:
        print(f"  ⚠ Master Planner initialization warning: {e}")

    print("✓ M.O.N.D.A.Y. Engine API ready.\n")
    yield
    print("M.O.N.D.A.Y. API shutting down.")


# ── FastAPI App ────────────────────────────────────────────────────────────────
app = FastAPI(
    title="M.O.N.D.A.Y. Multi-Agent API Engine",
    description=(
        "**Project M.O.N.D.A.Y.** — Modular Operational Neural Desktop Assistant for You\n\n"
        "Full Multi-Agent Execution Engine + 5 Classical ML Components.\n\n"
        "Course: Artificial Intelligence and Machine Learning (24CSE0316)\n"
        "Team: Siddhant Bhatia, Sambhav Sehgal, Samarth Sharma, Shivansh Chandel"
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Classical ML component endpoints (2.2–2.5) — makes all 5 ML models demoable at /docs
from api.ml_router import router as ml_component_router
app.include_router(ml_component_router)


# ── Request Schemas ────────────────────────────────────────────────────────────
class ExecuteRequest(BaseModel):
    command: str = Field(..., example="organize my Downloads folder", description="Natural language command")
    user_approved: bool = Field(
        default=False,
        description=(
            "Deprecated for Tier-2 actions and ignored by them. Per PRD §9 an "
            "irreversible action is approved only by replying to its "
            "confirmation prompt in a following request (e.g. send the command, "
            "then send 'yes'). This flag cannot grant that approval."
        ),
    )


class OrganizeRequest(BaseModel):
    directory: str = Field(default=".", example=".", description="Target folder path to organize by file extension")


class SummarizeRequest(BaseModel):
    filepath_or_text: str = Field(..., example="sample.pdf", description="File path or text snippet")


class SearchRequest(BaseModel):
    query: str = Field(..., example="Next.js 16 features", description="Web search query")


class RememberRequest(BaseModel):
    key: str = Field(..., example="professor email")
    value: str = Field(..., example="priyanka@vitbhopal.ac.in")
    topic: str = Field(default="academics", example="academics")


class RecallRequest(BaseModel):
    query: str = Field(..., example="professor")


class SpeakRequest(BaseModel):
    text: str = Field(..., example="Hello, M.O.N.D.A.Y. online and operational.", description="Text phrase to speak")


class ClassifyRequest(BaseModel):
    command: str = Field(..., example="summarize the quarterly report", description="Natural language command to classify")
    confidence_threshold: float = Field(default=0.65, ge=0.0, le=1.0, description="Below this confidence the command is routed to the LLM planner")



# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/", tags=["Health"])
@app.get("/health", tags=["Health"])
async def root() -> Dict[str, Any]:
    return {
        "engine": "M.O.N.D.A.Y. Multi-Agent System",
        "status": "ONLINE",
        "healthy": True,
        "version": "1.0.0",
        "interactive_app": "http://localhost:8000/app",
        "docs": "http://localhost:8000/docs",
        "agents": ["VoiceAgent", "ComputerAgent", "DocumentAgent", "BrowserAgent", "CommunicationAgent", "MemoryAgent", "HabitAgent"],
    }


#: The front-end libraries `ui/index.html` used to pull from CDNs.
#:
#: This mount is not optional. `/app` returns the HTML with a `FileResponse`,
#: which serves one file and nothing beside it — and **both** entry points go
#: through it: `app.py` points the pywebview window at `http://127.0.0.1:8000/app`
#: rather than opening the file from disk, and the browser-only path is the same
#: URL. Without this, every `vendor/*.js` request 404s, `THREE` is undefined, and
#: the inline script dies before defining `sendCommand` — which is the exact
#: failure vendoring was meant to remove, reintroduced by the fix for it.
_UI_DIR = Path(__file__).resolve().parent.parent / "ui"
if (_UI_DIR / "vendor").is_dir():
    from fastapi.staticfiles import StaticFiles

    app.mount("/vendor", StaticFiles(directory=str(_UI_DIR / "vendor")), name="vendor")


@app.get("/app", tags=["Interactive Desktop GUI"])
async def serve_desktop_app():
    """Serves the living 3D AI Entity Desktop GUI App."""
    from fastapi.responses import FileResponse
    ui_path = _UI_DIR / "index.html"
    if ui_path.exists():
        return FileResponse(str(ui_path))
    raise HTTPException(404, "Desktop UI file not found.")



@app.post("/agent/execute", tags=["Master Planner"])
def execute_command(req: ExecuteRequest) -> Dict[str, Any]:
    """
    **Master Multi-Agent Planner Execution Endpoint**

    Processes any natural language goal through Intent Classifier (2.1), RL Router (2.5),
    Security Tier Check, and dispatches to the correct worker agent.
    """
    planner = get_planner()
    return planner.process_command(req.command, user_approved=req.user_approved)


#: Sent when the pipeline has produced nothing for this long, so a proxy or a
#: browser does not decide a slow answer is a dead connection. A cold model load
#: is minutes, and silence for minutes is indistinguishable from a hang.
_HEARTBEAT_SECONDS = 10.0

#: How long to wait for the pipeline thread after the queue goes quiet. Bounded
#: so a wedged handler cannot pin a request open indefinitely.
_STREAM_TIMEOUT_SECONDS = 600.0


def _sse(event: str, data: Dict[str, Any]) -> str:
    """One Server-Sent Event frame."""
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@app.post("/agent/stream", tags=["Master Planner"])
def stream_command(req: ExecuteRequest) -> StreamingResponse:
    """
    **The same pipeline as `/agent/execute`, reported as it happens.**

    `/agent/execute` answers once, at the end. That is fine for a `psutil`
    reading and wrong for anything slow: loading a 2 GB model takes a minute or
    more on this machine, during which a client that is waiting on a single
    response has nothing to show and no way to tell a slow answer from a hung
    one. The UI's own 15-second abort made that concrete — it cancelled every
    cold-start command before it could finish.

    Emits, as they occur:

    | event | when |
    |---|---|
    | `classified` | component 2.1 has named an intent |
    | `consulting_model` | stage 3 is being asked — the only slow step |
    | `token` | a fragment of a model-written answer |
    | `heartbeat` | nothing has happened for a while; the connection is alive |
    | `result` | the final payload, identical to `/agent/execute`'s |
    | `error` | the pipeline raised; the message says what |

    **The pipeline is not reimplemented here.** `process_command` takes an
    optional sink and is otherwise untouched, so streaming observes the same
    code that answers `/agent/execute` — including the Tier-2 gate, the
    clarification state machine and the RL credit. A parallel streaming
    implementation would have to agree with that one about all three, and two
    implementations that must agree is the defect this repository has found in
    its own code repeatedly.
    """
    planner = get_planner()
    events: "queue.Queue[Any]" = queue.Queue()
    _DONE = object()

    def run() -> None:
        try:
            result = planner.process_command(
                req.command,
                user_approved=req.user_approved,
                on_event=lambda kind, payload: events.put((kind, payload)),
            )
            events.put(("result", result))
        except Exception as exc:  # noqa: BLE001
            events.put(("error", {"error": type(exc).__name__, "message": str(exc)}))
        finally:
            events.put(_DONE)

    worker = threading.Thread(target=run, daemon=True, name="monday-stream")
    worker.start()

    def frames():
        deadline = time.time() + _STREAM_TIMEOUT_SECONDS
        while True:
            if time.time() > deadline:
                yield _sse("error", {"error": "STREAM_TIMEOUT",
                                     "message": "The command did not finish in time."})
                return
            try:
                item = events.get(timeout=_HEARTBEAT_SECONDS)
            except queue.Empty:
                # Still working. Saying so is the difference between "slow" and
                # "dead" for anything between the client and this process.
                yield _sse("heartbeat", {})
                continue
            if item is _DONE:
                return
            kind, payload = item
            yield _sse(kind, payload if isinstance(payload, dict) else {"value": payload})

    return StreamingResponse(
        frames(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Proxies that buffer would defeat the entire point.
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/intent/classify", tags=["2.1 Intent Classifier (CLO04)"])
def classify_intent(req: ClassifyRequest) -> Dict[str, Any]:
    """
    **Component 2.1 — Intent Classification (CLO04)**

    Classifies a command into one of 7 intents using the TF-IDF → Logistic
    Regression pipeline trained on the `datagen/` corpus. Commands below the
    confidence threshold (or classified `unclear`) are flagged for the LLM
    planner rather than dispatched directly.
    """
    if _PLANNER is None:
        raise HTTPException(503, "Planner offline.")

    intent, confidence, fallback = predict_intent(
        _PLANNER.classifier, req.command, confidence_threshold=req.confidence_threshold
    )
    return {
        "command": req.command,
        "predicted_intent": intent,
        "confidence": round(float(confidence), 4),
        "llm_fallback": fallback,
        "confidence_threshold": req.confidence_threshold,
        "clo": "CLO04",
        "component": "2.1 Intent Classifier",
    }


@app.post("/agent/computer/organize", tags=["Computer Agent"])
def organize_folder(req: OrganizeRequest) -> Dict[str, Any]:
    """Organizes files in target folder by file extension into subfolders."""
    if _PLANNER is None:
        raise HTTPException(503, "Planner offline.")
    return _PLANNER.computer_agent.organize_directory(req.directory)


@app.post("/agent/computer/screenshot", tags=["Computer Agent"])
def capture_screenshot() -> Dict[str, Any]:
    """Captures desktop screen to staging directory."""
    if _PLANNER is None:
        raise HTTPException(503, "Planner offline.")
    return _PLANNER.computer_agent.take_screenshot()


@app.get("/agent/computer/health", tags=["Computer Agent"])
def system_health() -> Dict[str, Any]:
    """Returns real CPU, RAM, and Disk hardware status."""
    if _PLANNER is None:
        raise HTTPException(503, "Planner offline.")
    return _PLANNER.computer_agent.get_system_health()


@app.post("/agent/document/summarize", tags=["Document Agent"])
def summarize_doc(req: SummarizeRequest) -> Dict[str, Any]:
    """Summarizes document or text using TF-IDF sentence scoring."""
    if _PLANNER is None:
        raise HTTPException(503, "Planner offline.")
    return _PLANNER.document_agent.summarize_document(req.filepath_or_text)


@app.post("/agent/browser/search", tags=["Browser Agent"])
def web_search(req: SearchRequest) -> Dict[str, Any]:
    """Performs live web search and extracts snippets."""
    if _PLANNER is None:
        raise HTTPException(503, "Planner offline.")
    return _PLANNER.browser_agent.web_search(req.query)


@app.post("/agent/memory/remember", tags=["Memory Agent"])
def store_memory(req: RememberRequest) -> Dict[str, Any]:
    """Stores fact into persistent SQLite memory matrix."""
    if _PLANNER is None:
        raise HTTPException(503, "Planner offline.")
    return _PLANNER.memory_agent.remember(req.key, req.value, req.topic)


@app.post("/agent/memory/recall", tags=["Memory Agent"])
def recall_memory(req: RecallRequest) -> Dict[str, Any]:
    """Recalls facts from persistent memory using TF-IDF similarity."""
    if _PLANNER is None:
        raise HTTPException(503, "Planner offline.")
    return _PLANNER.memory_agent.recall(req.query)


class TrainVoiceRequest(BaseModel):
    reference_audio_path: Optional[str] = Field(default=None, example="ui/mondayvoice.mp3", description="Path to reference audio file")


@app.post("/agent/voice/train", tags=["Voice Agent"])
async def voice_train(req: TrainVoiceRequest) -> Dict[str, Any]:
    """Trains or retrains the voice synthesis model using a reference audio sample."""
    if _PLANNER is None:
        raise HTTPException(503, "Planner offline.")
    return _PLANNER.voice_agent.train_voice(req.reference_audio_path)


class ToggleVoiceRequest(BaseModel):
    enabled: bool = Field(default=True, description="Set True to enable voice output, False to disable")


@app.post("/agent/voice/toggle", tags=["Voice Agent"])
async def voice_toggle(req: ToggleVoiceRequest) -> Dict[str, Any]:
    """Toggles voice synthesis output on or off at runtime."""
    if _PLANNER is None:
        raise HTTPException(503, "Planner offline.")
    _PLANNER.enable_voice = req.enabled
    res = _PLANNER.voice_agent.set_voice_enabled(req.enabled)
    return {"success": True, "enable_voice": res, "message": f"Voice synthesis output {'enabled' if res else 'disabled'}."}


@app.post("/agent/voice/speak", tags=["Voice Agent"])
async def voice_speak(req: SpeakRequest) -> Dict[str, Any]:
    """Synthesizes text, words, or alphabets into spoken speech output using trained voice model."""
    if _PLANNER is None:
        raise HTTPException(503, "Planner offline.")
    return _PLANNER.voice_agent.speak(req.text)


@app.get("/agent/voice/listen", tags=["Voice Agent"])
async def voice_listen(timeout: int = 5) -> Dict[str, Any]:
    """Listens for voice audio input."""
    if _PLANNER is None:
        raise HTTPException(503, "Planner offline.")
    return _PLANNER.voice_agent.listen(timeout_seconds=timeout)



@app.get("/agent/proactive", tags=["Proactive Intelligence"])
async def proactive_suggestions() -> Dict[str, Any]:
    """Generates proactive suggestions using Memory Clustering (2.3) and Habit Mining (2.4)."""
    if _PLANNER is None:
        raise HTTPException(503, "Planner offline.")
    mem_sug = _PLANNER.memory_agent.get_proactive_suggestions()
    hab_sug = _PLANNER.habit_agent.detect_habits_and_suggest()
    return {
        "memory_clustering_suggestions": mem_sug.get("suggestions", []),
        "habit_mining_suggestions": hab_sug.get("suggestions", []),
    }


@app.get("/agent/history", tags=["Audit Log"])
async def action_history(limit: int = 30) -> List[Dict[str, Any]]:
    """Returns the persistent action audit log."""
    return get_action_history(limit=limit)


# ── Classic ML Endpoints ───────────────────────────────────────────────────────

@app.get("/xai/explain", tags=["Component 2.6 — XAI Explainer"])
async def xai_explain_endpoint(command: str = "organize my downloads folder") -> Dict[str, Any]:
    """Returns SHAP feature importance breakdown explaining intent & routing decisions."""
    from ml.xai_explainer import explain_command_intent
    planner = get_planner()
    explanation = explain_command_intent(command)
    return {
        "command": command,
        "key_influencing_features": explanation.get("top_words", []),
        "explanation": explanation,
    }


# ── Entry Point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("API_PORT", "8000")),
        reload=os.getenv("API_RELOAD", "true").lower() == "true",
        log_level=os.getenv("API_LOG_LEVEL", "info"),
    )
