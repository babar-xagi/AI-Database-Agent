# terminal.py – GEMINI STUDENT AGENT – FINAL + EMOJI + 100% CLEAN OUTPUT

import os
import random
from dotenv import load_dotenv

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

from sqlmodel import Session, select
from database import engine
from models import Student

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    print("ERROR: .env mein GEMINI_API_KEY daal do bhai!")
    exit(1)

# Free + Fast + Working Model
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=api_key,
    temperature=0.3,  # Thoda natural lage
    convert_system_message_to_human=True
)

# ==================== TOOLS ====================

@tool
def calculator(expression: str) -> str:
    """Simple calculator – 25*4, 100+50 etc."""
    try:
        return f"Result: {eval(expression)}"
    except:
        return "Galat expression hai bhai"

@tool
def add_student(name: str, roll: int, dept: str) -> str:
    """Naya student add karo"""
    with Session(engine) as s:
        if s.exec(select(Student).where(Student.roll == roll)).first():
            return f"Roll {roll} pehle se hai!"
        s.add(Student(name=name.title(), roll=roll, dept=dept.upper()))
        s.commit()
        return f"Added: {name.title()} (Roll {roll}) → {dept.upper()}"

@tool
def remove_student(identifier: str) -> str:
    """Student hatao – name ya roll se"""
    with Session(engine) as s:
        student = None
        if identifier.isdigit():
            student = s.exec(select(Student).where(Student.roll == int(identifier))).first()
        if not student:
            student = s.exec(select(Student).where(Student.name.ilike(f"%{identifier}%"))).first()
        if not student: return "Student nahi mila"
        s.delete(student); s.commit()
        return f"Removed: {student.name} (Roll {student.roll})"

@tool
def update_student(identifier: str, new_name: str = None, new_roll: int = None, new_dept: str = None) -> str:
    """Student update karo"""
    with Session(engine) as s:
        student = None
        if identifier.isdigit():
            student = s.exec(select(Student).where(Student.roll == int(identifier))).first()
        if not student:
            student = s.exec(select(Student).where(Student.name.ilike(f"%{identifier}%"))).first()
        if not student: return "Student nahi mila"
        old = f"{student.name} (Roll {student.roll}) → {student.dept}"
        if new_name: student.name = new_name.title()
        if new_roll is not None:
            if s.exec(select(Student).where(Student.roll == new_roll, Student.id != student.id)).first():
                return "Naya roll already taken!"
            student.roll = new_roll
        if new_dept: student.dept = new_dept.upper()
        s.add(student); s.commit()
        return f"Updated → {old} → {student.name} (Roll {student.roll}) → {student.dept}"

@tool
def search_students(query: str = "") -> str:
    """Students dikhao – khali chhodo to sab"""
    with Session(engine) as s:
        students = s.exec(select(Student)).all()
        if not students: return "Database khali hai"
        filtered = [f"{s.name} (Roll {s.roll}) → {s.dept}" for s in students
                    if not query or query.lower() in f"{s.name}{s.roll}{s.dept}".lower()]
        return "\n".join(filtered) if filtered else "Kuch nahi mila"

# ==================== AGENT ====================
tools = [calculator, add_student, remove_student, update_student, search_students]
agent = create_react_agent(llm, tools)

# ==================== CLEAN OUTPUT FUNCTION ====================
def clean_output(content):
    if isinstance(content, list):
        text = ""
        for part in content:
            if isinstance(part, dict) and "text" in part:
                text += part["text"] + " "
        return text.strip()
    return str(content).strip()

# ==================== START ====================
print("="*70)
print("GEMINI STUDENT AGENT LIVE HAI – 100% FREE + EMOJI + CLEAN")
print("Roman Urdu / English mein baat karo – sab samajh aayega!")
print("="*70)

messages = []
names = ["Ali", "Ahmed", "Sara", "Ayesha", "Omar", "Zain", "Hassan", "Fatima", "Hadi", "Noor"]

while True:
    try:
        q = input("\nYou: ").strip()
        if q.lower() in ["bye","exit","quit","tata","chalo"]:
            print("Bye bhai! Data saved hai")
            break
        if not q: continue

        messages.append(HumanMessage(content=q))
        res = agent.invoke({"messages": messages})
        
        # CLEAN + EMOJI WALA OUTPUT
        reply = clean_output(res["messages"][-1].content)
        
        # Auto emoji add kar do
        if "added" in reply.lower() or "add" in q.lower():
            reply += " ✅"
        elif "removed" in reply.lower():
            reply += " ❌"
        elif "updated" in reply.lower():
            reply += " 🔄"
        elif "result" in reply.lower():
            reply += " Calculated"
        elif "database khali" in reply.lower():
            reply += " 🗃️"
        else:
            reply += " ✅"

        print(f"Agent: {reply}\n")
        messages = res["messages"]

    except KeyboardInterrupt:
        print("\nBye bhai!")
        break
    except Exception as e:
        print(f"Error: {e}")
