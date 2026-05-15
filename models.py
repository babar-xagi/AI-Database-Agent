# from sqlmodel import Field, SQLModel


# class Student(SQLModel, table=True):
#     id: int | None = Field(default=None, primary_key=True)
#     name: str = Field(index=True)
#     roll: int = Field(unique=True)
#     dept: str



# models.py
from sqlmodel import SQLModel, Field
from typing import Optional

class Student(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    roll: int = Field(index=True, unique=True)
    dept: str
