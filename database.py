

import os
from sqlmodel import SQLModel, create_engine


BASE_DIR = os.path.dirname(os.path.abspath(__file__))     
DB_PATH = os.path.join(BASE_DIR, "university.db")         

DATABASE_URL = f"sqlite:///{DB_PATH}"                     


engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False}  # required for Tkinter + threads
)

# -----------------------------
# Initialize DB & Tables
# -----------------------------
def init_db():
    """
    Creates all tables if they do not exist.
    Call this once when your app starts.
    """
    SQLModel.metadata.create_all(engine)
    print(f"Database initialized at: {DB_PATH}")

# For manual testing
if __name__ == "__main__":
    init_db()
