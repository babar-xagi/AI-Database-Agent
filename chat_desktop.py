import tkinter as tk
from tkinter import scrolledtext
from sqlmodel import Session, select
from models import Student
from database import engine

import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage

load_dotenv()

# ---------------- LLMs ----------------
gemini = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=os.getenv("GEMINI_API_KEY"),
    temperature=0.3,
)

groq = ChatGroq(
    model="llama-3.3-70b-versatile",
    api_key=os.getenv("GROQ_API_KEY"),
    temperature=0,
)

# ---------------- TOOLS ----------------
def add_student(name, roll, dept):
    with Session(engine) as s:
        if s.exec(select(Student).where(Student.roll == roll)).first():
            return f"Roll {roll} already exists!"
        s.add(Student(name=name.title(), roll=roll, dept=dept.upper()))
        s.commit()
        return f"Added: {name.title()} (Roll {roll}) → {dept.upper()}"


def remove_student(identifier):
    with Session(engine) as s:
        student = None
        if identifier.isdigit():
            student = s.exec(select(Student).where(Student.roll == int(identifier))).first()
        if not student:
            student = s.exec(select(Student).where(Student.name.ilike(f"%{identifier}%"))).first()
        if not student:
            return "Student not found"
        s.delete(student)
        s.commit()
        return f"Removed: {student.name} (Roll {student.roll})"


def update_student(identifier, new_name=None, new_roll=None, new_dept=None):
    with Session(engine) as s:
        student = None
        if identifier.isdigit():
            student = s.exec(select(Student).where(Student.roll == int(identifier))).first()
        if not student:
            student = s.exec(select(Student).where(Student.name.ilike(f"%{identifier}%"))).first()
        if not student:
            return "Student not found"

        if new_name:
            student.name = new_name.title()
        if new_roll:
            if s.exec(select(Student).where(Student.roll == new_roll)).first():
                return "New roll exists!"
            student.roll = new_roll
        if new_dept:
            student.dept = new_dept.upper()

        s.commit()
        return f"Updated → {student.name} (Roll {student.roll}) → {student.dept}"


def search_students(query=""):
    with Session(engine) as s:
        students = s.exec(select(Student)).all()
        if not students:
            return "Database empty"
        result = [
            f"{st.name} (Roll {st.roll}) → {st.dept}"
            for st in students
            if query.lower() in f"{st.name}{st.roll}{st.dept}".lower()
        ]
        return "\n".join(result) if result else "Nothing found"


# ---------------- ROUTER ----------------
def agent_reply(msg):
    msg_low = msg.lower()

    # ADD
    if "add student" in msg_low:
        try:
            parts = msg_low.split()
            name = parts[parts.index("student") + 1]
            roll = int(parts[-2])
            dept = parts[-1]
            return add_student(name, roll, dept)
        except:
            return "Format: add student Ali 12 CS"

    # REMOVE
    if "remove" in msg_low:
        try:
            target = msg_low.split()[-1]
            return remove_student(target)
        except:
            return "Format: remove 12"

    # UPDATE
    if "update" in msg_low:
        try:
            identifier = msg_low.split()[1]
            new_name = None
            new_dept = None

            if "name" in msg_low:
                new_name = msg_low.split("name")[-1].split()[0]
            if "dept" in msg_low:
                new_dept = msg_low.split("dept")[-1].split()[0]

            return update_student(identifier, new_name=new_name, new_dept=new_dept)
        except:
            return "Format: update 12 name Ayesha dept CS"

    # SEARCH
    if "show" in msg_low or "search" in msg_low:
        key = msg_low.split()[-1]
        return search_students(key)

    # Otherwise → choose LLM
    llm = gemini if len(msg) < 50 else groq
    result = llm.invoke([HumanMessage(content=msg)])
    return result.content


# ---------------- Tkinter UI ----------------
root = tk.Tk()
root.title("Student AI Agent Desktop")
root.geometry("520x620")

chat_box = scrolledtext.ScrolledText(root, wrap=tk.WORD, font=("Arial", 12))
chat_box.pack(expand=True, fill="both")
chat_box.config(state="disabled")

entry = tk.Entry(root, font=("Arial", 12))
entry.pack(fill="x", pady=5, padx=5)

def send():
    user_msg = entry.get().strip()
    if not user_msg:
        return

    chat_box.config(state="normal")
    chat_box.insert(tk.END, f"You: {user_msg}\n")
    chat_box.config(state="disabled")
    entry.delete(0, tk.END)

    reply = agent_reply(user_msg)

    chat_box.config(state="normal")
    chat_box.insert(tk.END, f"Agent: {reply}\n\n")
    chat_box.config(state="disabled")
    chat_box.see(tk.END)

send_btn = tk.Button(root, text="Send", command=send, font=("Arial", 12))
send_btn.pack(pady=5)

entry.bind("<Return>", lambda e: send())

root.mainloop()
