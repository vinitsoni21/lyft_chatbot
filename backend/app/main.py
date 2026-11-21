import logging
from contextlib import asynccontextmanager
from typing import Annotated, Optional

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, StringConstraints

from . import config, db, llm_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()  # schema is created automatically on startup
    yield


app = FastAPI(title="LLM Chatbot", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],  # lets the browser send X-Simulate-Failure
)


class ChatRequest(BaseModel):
    session_id: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
    system_prompt: Optional[str] = None


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    """Never leak a stack trace or an HTML error page."""
    logger.exception("Unhandled error")
    return JSONResponse(status_code=500, content={"detail": "internal server error"})


@app.get("/health")
async def health():
    if not db.check_db():
        raise HTTPException(status_code=503, detail="database unreachable")
    if not config.LLM_API_KEYS:
        raise HTTPException(status_code=503, detail="key pool not loaded")
    return {"status": "ok", "keys_configured": len(config.LLM_API_KEYS), "cache_enabled": True}


@app.post("/chat")
async def chat(body: ChatRequest, x_simulate_failure: Optional[str] = Header(default=None)):
    new_prompt = (body.system_prompt or "").strip() or None
    system_prompt = (
        new_prompt or db.get_system_prompt(body.session_id) or config.DEFAULT_SYSTEM_PROMPT
    )

    history = db.get_history(body.session_id)
    messages = llm_service.build_messages(system_prompt, history, body.message)
    simulate = llm_service.parse_simulation(x_simulate_failure)

    try:
        result = await llm_service.get_reply(messages, simulate)
    except llm_service.AllProvidersUnavailable:
        # Nothing is saved on failure, so history stays clean
        raise HTTPException(status_code=503, detail="all providers unavailable")

    db.add_exchange(body.session_id, body.message, result["reply"], result["metadata"])
    if new_prompt:
        db.set_system_prompt(body.session_id, new_prompt)

    return {
        "session_id": body.session_id,
        "reply": result["reply"],
        "metadata": result["metadata"],
    }


@app.get("/sessions/{session_id}/messages")
async def get_messages(session_id: str):
    if not db.session_exists(session_id):
        raise HTTPException(status_code=404, detail="session not found")
    return {"session_id": session_id, "messages": db.get_history(session_id)}