from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agent_core import ask_agent, list_students


app = FastAPI(title="Hybrid Student Agent API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

chat_sessions: dict[str, list] = {}


class Query(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str | None = None


@app.get("/")
async def home():
    return {"status": "running", "message": "Hybrid Student Agent API"}


@app.get("/students")
async def students(query: str = ""):
    return {"students": list_students(query)}


@app.post("/chat")
async def chat(q: Query):
    session_id = q.session_id or uuid4().hex
    try:
        reply, messages = await ask_agent(q.message, chat_sessions.get(session_id, []))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Agent request failed: {exc}") from exc

    chat_sessions[session_id] = messages
    return {
        "session_id": session_id,
        "response": reply,
        "students": list_students(),
    }
