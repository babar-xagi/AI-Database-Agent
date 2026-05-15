import asyncio
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from agent_core import (
    ask_agent,
    create_student_record,
    delete_student_record,
    list_students,
    update_student_record,
)


app = FastAPI(title="AI Database Student Agent", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

chat_sessions: dict[str, list] = {}


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str | None = None


class StudentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    roll: int = Field(ge=0)
    dept: str = Field(min_length=1, max_length=40)


class StudentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    roll: int | None = Field(default=None, ge=0)
    dept: str | None = Field(default=None, min_length=1, max_length=40)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/health")
async def health():
    return {"status": "ok", "students": len(list_students())}


@app.get("/api/students")
async def students(query: str = ""):
    return {"students": list_students(query)}


@app.post("/api/students", status_code=201)
async def add_student(payload: StudentCreate):
    try:
        student = create_student_record(payload.name, payload.roll, payload.dept)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"student": student, "students": list_students()}


@app.patch("/api/students/{student_id}")
async def edit_student(student_id: int, payload: StudentUpdate):
    if payload.name is None and payload.roll is None and payload.dept is None:
        raise HTTPException(status_code=400, detail="Send at least one field to update.")
    try:
        student = update_student_record(
            student_id,
            name=payload.name,
            roll=payload.roll,
            dept=payload.dept,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"student": student, "students": list_students()}


@app.delete("/api/students/{student_id}")
async def remove_student(student_id: int):
    try:
        student = delete_student_record(student_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"student": student, "students": list_students()}


@app.post("/api/chat")
async def chat(payload: ChatRequest):
    session_id = payload.session_id or uuid4().hex
    history = chat_sessions.get(session_id, [])
    try:
        reply, messages = await ask_agent(payload.message, history)
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Agent request timed out. Check internet/API key and try again.") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Agent request failed: {exc}") from exc
    chat_sessions[session_id] = messages
    return {
        "session_id": session_id,
        "reply": reply,
        "students": list_students(),
    }


@app.websocket("/ws")
async def websocket_chat(websocket: WebSocket):
    await websocket.accept()
    session_id = uuid4().hex
    chat_sessions[session_id] = []
    await websocket.send_json(
        {
            "type": "ready",
            "session_id": session_id,
            "reply": "Student Agent connected. Roman Urdu ya English, dono chalegi.",
            "students": list_students(),
        }
    )

    try:
        while True:
            payload = await websocket.receive_json()
            message = str(payload.get("message", "")).strip()
            if not message:
                continue
            if message.lower() in {"bye", "exit", "quit", "tata", "chalo"}:
                await websocket.send_json(
                    {
                        "type": "bye",
                        "reply": "Bye bhai! Data saved hai.",
                        "students": list_students(),
                    }
                )
                break

            try:
                reply, messages = await ask_agent(message, chat_sessions.get(session_id, []))
            except asyncio.TimeoutError:
                await websocket.send_json(
                    {
                        "type": "error",
                        "reply": "Agent request timed out. Check internet/API key and try again.",
                        "students": list_students(),
                    }
                )
                continue
            except Exception as exc:
                await websocket.send_json(
                    {
                        "type": "error",
                        "reply": f"Agent request failed: {exc}",
                        "students": list_students(),
                    }
                )
                continue
            chat_sessions[session_id] = messages
            await websocket.send_json(
                {
                    "type": "message",
                    "session_id": session_id,
                    "reply": reply,
                    "students": list_students(),
                }
            )
    except WebSocketDisconnect:
        pass
    finally:
        chat_sessions.pop(session_id, None)
