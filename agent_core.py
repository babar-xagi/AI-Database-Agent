import ast
import asyncio
import operator
import os
import re
from collections.abc import Iterable
from difflib import get_close_matches

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from sqlmodel import Session, select

from database import engine, init_db
from models import Student


load_dotenv()
init_db()


SYSTEM_PROMPT = """
You are a friendly student database assistant for a university app.
Users may speak English or Roman Urdu. Keep replies short and clear.
Use the database tools for every student add, remove, update, list, or search request.
For requests like "show all CS students", call search_students with query="CS".
For requests like "update smaina roll 902", update the closest matching student name.
Never invent database results; use the tools.
"""

_ALLOWED_CALC_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _normalize_name(name: str) -> str:
    return " ".join(name.strip().split()).title()


def _normalize_dept(dept: str) -> str:
    return " ".join(dept.strip().split()).upper()


def _find_student(session: Session, identifier: str) -> Student | None:
    target = str(identifier).strip()
    if not target:
        return None

    if target.isdigit():
        student = session.exec(select(Student).where(Student.roll == int(target))).first()
        if student:
            return student

    exact = session.exec(select(Student).where(Student.name.ilike(target))).first()
    if exact:
        return exact

    partial = session.exec(select(Student).where(Student.name.ilike(f"%{target}%"))).first()
    if partial:
        return partial

    students = session.exec(select(Student)).all()
    names = [student.name for student in students]
    matches = get_close_matches(target.lower(), [name.lower() for name in names], n=1, cutoff=0.72)
    if matches:
        matched = matches[0]
        return next((student for student in students if student.name.lower() == matched), None)

    return None


def _eval_math(node: ast.AST) -> float | int:
    if isinstance(node, ast.Expression):
        return _eval_math(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_CALC_OPS:
        return _ALLOWED_CALC_OPS[type(node.op)](_eval_math(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_CALC_OPS:
        left = _eval_math(node.left)
        right = _eval_math(node.right)
        return _ALLOWED_CALC_OPS[type(node.op)](left, right)
    raise ValueError("Only simple math expressions are supported.")


@tool
def calculator(expression: str) -> str:
    """Calculate a simple math expression such as 25*4 or 100+50."""
    try:
        parsed = ast.parse(expression, mode="eval")
        result = _eval_math(parsed)
        return f"Result: {result}"
    except Exception:
        return "Invalid math expression."


@tool
def add_student(name: str, roll: int, dept: str) -> str:
    """Add a new student with name, roll number, and department."""
    clean_name = _normalize_name(name)
    clean_dept = _normalize_dept(dept)

    with Session(engine) as session:
        if session.exec(select(Student).where(Student.roll == roll)).first():
            return f"Roll {roll} already exists."
        student = Student(name=clean_name, roll=roll, dept=clean_dept)
        session.add(student)
        session.commit()
        return f"Added: {clean_name} (Roll {roll}) -> {clean_dept}"


@tool
def remove_student(identifier: str) -> str:
    """Remove a student by roll number or name."""
    with Session(engine) as session:
        student = _find_student(session, identifier)
        if not student:
            return "Student not found."
        name = student.name
        roll = student.roll
        session.delete(student)
        session.commit()
        return f"Removed: {name} (Roll {roll})"


@tool
def update_student(
    identifier: str,
    new_name: str | None = None,
    new_roll: int | None = None,
    new_dept: str | None = None,
) -> str:
    """Update a student's name, roll number, or department."""
    with Session(engine) as session:
        student = _find_student(session, identifier)
        if not student:
            return "Student not found."

        if new_roll is not None:
            existing = session.exec(
                select(Student).where(Student.roll == new_roll, Student.id != student.id)
            ).first()
            if existing:
                return f"Roll {new_roll} is already taken."
            student.roll = new_roll

        if new_name:
            student.name = _normalize_name(new_name)
        if new_dept:
            student.dept = _normalize_dept(new_dept)

        session.add(student)
        session.commit()
        session.refresh(student)
        return f"Updated: {student.name} (Roll {student.roll}) -> {student.dept}"


@tool
def search_students(query: str = "") -> str:
    """Search students by name, roll number, or department. Use an empty query to list all students."""
    needle = str(query or "").strip().lower()
    with Session(engine) as session:
        students = session.exec(select(Student).order_by(Student.dept, Student.roll)).all()
        if needle:
            students = [
                student
                for student in students
                if needle in f"{student.name} {student.roll} {student.dept}".lower()
            ]
        if not students:
            return "No students found."
        return "\n".join(f"{student.name} (Roll {student.roll}) -> {student.dept}" for student in students)


def list_students(query: str = "") -> list[dict]:
    needle = str(query or "").strip().lower()
    with Session(engine) as session:
        students = session.exec(select(Student).order_by(Student.dept, Student.roll)).all()
        if needle:
            students = [
                student
                for student in students
                if needle in f"{student.name} {student.roll} {student.dept}".lower()
            ]
        return [student.model_dump() for student in students]


def count_students(query: str = "") -> int:
    return len(list_students(query))


def create_student_record(name: str, roll: int, dept: str) -> dict:
    message = add_student.invoke({"name": name, "roll": roll, "dept": dept})
    if "already exists" in message.lower():
        raise ValueError(message)
    with Session(engine) as session:
        student = session.exec(select(Student).where(Student.roll == roll)).one()
        return student.model_dump()


def update_student_record(
    student_id: int,
    name: str | None = None,
    roll: int | None = None,
    dept: str | None = None,
) -> dict:
    with Session(engine) as session:
        student = session.get(Student, student_id)
        if not student:
            raise LookupError("Student not found.")

        if roll is not None:
            existing = session.exec(select(Student).where(Student.roll == roll, Student.id != student_id)).first()
            if existing:
                raise ValueError(f"Roll {roll} is already taken.")
            student.roll = roll
        if name is not None:
            student.name = _normalize_name(name)
        if dept is not None:
            student.dept = _normalize_dept(dept)

        session.add(student)
        session.commit()
        session.refresh(student)
        return student.model_dump()


def delete_student_record(student_id: int) -> dict:
    with Session(engine) as session:
        student = session.get(Student, student_id)
        if not student:
            raise LookupError("Student not found.")
        payload = student.model_dump()
        session.delete(student)
        session.commit()
        return payload


def clean_output(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, dict):
        return str(content.get("text") or content.get("content") or content).strip()
    if isinstance(content, Iterable):
        pieces: list[str] = []
        for part in content:
            if isinstance(part, dict):
                pieces.append(str(part.get("text") or part.get("content") or ""))
            else:
                pieces.append(str(part))
        return " ".join(piece for piece in pieces if piece).strip()
    return str(content).strip()


def _build_gemini_agent():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
    llm = ChatGoogleGenerativeAI(
        model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        google_api_key=api_key,
        temperature=0.3,
        retries=2,
        request_timeout=float(os.getenv("GEMINI_REQUEST_TIMEOUT_SECONDS", "25")),
    )
    return create_agent(
        llm,
        [calculator, add_student, remove_student, update_student, search_students],
        system_prompt=SYSTEM_PROMPT,
    )


def _build_groq_agent():
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return None
    llm = ChatGroq(
        model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        api_key=api_key,
        temperature=0,
        timeout=float(os.getenv("GROQ_REQUEST_TIMEOUT_SECONDS", "25")),
        max_retries=1,
    )
    return create_agent(
        llm,
        [calculator, add_student, remove_student, update_student, search_students],
        system_prompt=SYSTEM_PROMPT,
    )


gemini_agent = _build_gemini_agent()
groq_agent = _build_groq_agent()


def _format_students(students: list[dict], query: str = "") -> str:
    if not students:
        return f"No students found{f' for {query}' if query else ''}."
    lines = [f"{student['name']} (Roll {student['roll']}) -> {student['dept']}" for student in students]
    return "\n".join(lines)


def _extract_roll(message: str) -> int | None:
    match = re.search(r"\broll(?:\s*(?:number|no|#))?\s*[:#-]?\s*(\d+)\b", message, flags=re.I)
    if match:
        return int(match.group(1))
    numbers = re.findall(r"\b\d+\b", message)
    return int(numbers[-1]) if numbers else None


def _extract_dept(message: str) -> str | None:
    patterns = [
        r"\b(?:dept|department|class|in)\s+([a-zA-Z][a-zA-Z ]{0,30}?)(?=\s+roll|\s+\d+|$)",
        r"\b([a-zA-Z]{2,20})\s+(?:department|dept)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, message, flags=re.I)
        if match:
            dept = match.group(1).strip()
            if dept.lower() not in {"new", "student", "roll"}:
                return dept
    return None


def _local_reply(message: str) -> str | None:
    raw = message.strip()
    lower = raw.lower()
    if not raw:
        return ""

    if lower in {"hi", "hy", "hello", "salam", "assalam o alaikum", "assalamu alaikum"}:
        return "Hello! Student database ke liye command bhej dein."

    if any(word in lower for word in ("total", "count", "kitne", "number of")) and "student" in lower:
        dept = _extract_dept(raw)
        if not dept and " cs" in f" {lower} ":
            dept = "CS"
        total = count_students(dept or "")
        label = f" in {dept.upper()}" if dept else ""
        return f"Total students{label}: {total}"

    if any(word in lower for word in ("show", "list", "search", "dikhao")) and "student" in lower:
        dept = _extract_dept(raw)
        query = dept or ""
        if not query:
            tokens = re.sub(r"[^\w\s]", " ", lower).split()
            ignored = {"show", "list", "search", "all", "student", "students", "again", "dikhao", "sare", "sab"}
            useful = [token for token in tokens if token not in ignored]
            query = " ".join(useful)
        return _format_students(list_students(query), query)

    if "remove" in lower or "delete" in lower or "hata" in lower:
        roll = _extract_roll(raw)
        if roll is not None:
            return remove_student.invoke({"identifier": str(roll)})
        cleaned = re.sub(r"\b(remove|delete|student|hata|karo|kar|do)\b", " ", raw, flags=re.I).strip()
        if cleaned:
            return remove_student.invoke({"identifier": cleaned})

    if "update" in lower:
        cleaned = re.sub(r"[^\w\s]", " ", raw)
        words = cleaned.split()
        try:
            identifier = words[words.index("update") + 1]
        except (ValueError, IndexError):
            return None
        new_roll = _extract_roll(raw)
        new_dept = _extract_dept(raw)
        new_name = None
        name_match = re.search(r"\bname\s+([a-zA-Z][a-zA-Z ]{0,40}?)(?=\s+roll|\s+dept|\s+department|$)", raw, flags=re.I)
        if name_match:
            new_name = name_match.group(1).strip()
        if new_roll is not None or new_dept or new_name:
            return update_student.invoke(
                {
                    "identifier": identifier,
                    "new_name": new_name,
                    "new_roll": new_roll,
                    "new_dept": new_dept,
                }
            )

    if "add" in lower and "student" in lower:
        roll = _extract_roll(raw)
        add_dept = re.search(r"\bin\s+([a-zA-Z]{2,20})\b", raw, flags=re.I)
        dept = add_dept.group(1) if add_dept else _extract_dept(raw)
        if roll is None:
            return "Roll number missing. Example: add new student in CS Basit roll 105"
        text_without_roll = re.sub(r"\broll(?:\s*(?:number|no|#))?\s*[:#-]?\s*\d+\b", " ", raw, flags=re.I)
        cleaned = re.sub(r"\b(add|new|student|students|in|dept|department|class)\b", " ", text_without_roll, flags=re.I)
        if dept:
            cleaned = re.sub(rf"\b{re.escape(dept)}\b", " ", cleaned, flags=re.I)
        name = " ".join(cleaned.split())
        if not dept:
            tokens = name.split()
            if len(tokens) >= 2:
                dept = tokens[-1]
                name = " ".join(tokens[:-1])
        if not name or not dept:
            return "Name ya department missing. Example: add new student in CS Basit roll 105"
        return add_student.invoke({"name": name, "roll": roll, "dept": dept})

    return None


def _is_quota_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "429" in text or "quota" in text or "rate limit" in text or "resource_exhausted" in text


async def _ask_llm(agent_to_use, messages: list) -> list:
    timeout = float(os.getenv("AGENT_TIMEOUT_SECONDS", "45"))
    result = await asyncio.wait_for(agent_to_use.ainvoke({"messages": messages}), timeout=timeout)
    return result["messages"]


async def ask_agent(message: str, history: list | None = None) -> tuple[str, list]:
    local = _local_reply(message)
    if local is not None:
        return local, list(history or [])

    messages = list(history or [])
    messages.append(HumanMessage(content=message.strip()))

    if not gemini_agent and not groq_agent:
        return "No LLM key found. Add GEMINI_API_KEY or GROQ_API_KEY in .env.", messages

    try:
        if gemini_agent:
            messages = await _ask_llm(gemini_agent, messages)
        else:
            messages = await _ask_llm(groq_agent, messages)
    except Exception as exc:
        if not _is_quota_error(exc) or not groq_agent:
            raise
        messages = list(history or [])
        messages.append(HumanMessage(content=message.strip()))
        messages = await _ask_llm(groq_agent, messages)

    reply = ""
    for candidate in reversed(messages):
        if getattr(candidate, "type", None) in {"ai", "assistant"}:
            reply = clean_output(candidate.content)
            break

    return reply or "No response.", messages
