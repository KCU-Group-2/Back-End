from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# frontend가 backend로 요청을 보낼 수 있게 허용해주는 FastAPI 기능
from fastapi.middleware.cors import CORSMiddleware



import os
from dotenv import load_dotenv
from supabase import create_client

from routers import resources, auth

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# frontend에서 오는 요청을 허용할지 말지 검사하는 기능을 app에 추가
app = FastAPI()

class CourseCreate(BaseModel):
    subject: str
    course_number: str
    title: str
    description: str = ""

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "http://127.0.0.1:3000",
        "http://localhost:3000",
        "http://127.0.0.1:5501",
        "http://localhost:5501",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(resources.router)
app.include_router(auth.router)

@app.get("/")
def home():
    return {"message": "StudySwap API is running"}

@app.post("/courses")
def create_course(course: CourseCreate):
    subject = course.subject.strip().upper()
    course_number = course.course_number.strip()
    title = course.title.strip()
    description = course.description.strip()

    if not subject or not course_number or not title:
        raise HTTPException(
            status_code=400,
            detail="Subject, course number, and title are required."
        )

    existing = (
        supabase.table("courses")
        .select("id")
        .eq("subject", subject)
        .eq("course_number", course_number)
        .execute()
    )

    if existing.data:
        raise HTTPException(
            status_code=409,
            detail="This course already exists."
        )

    response = (
        supabase.table("courses")
        .insert({
            "subject": subject,
            "course_number": course_number,
            "title": title,
            "description": description
        })
        .execute()
    )

    return response.data

@app.get("/courses")
def get_courses():
    response = supabase.table("courses").select("*").execute()
    return response.data

@app.get("/courses/search")
def search_courses(q: str):
    response = (
        supabase.table("courses")
        .select("*")
        .or_(f"subject.ilike.%{q}%,course_number.ilike.%{q}%,title.ilike.%{q}%,description.ilike.%{q}%")
        .execute()
    )
    return response.data

@app.get("/courses/{course_id}/resources")
def get_course_resources(course_id: int):
    response = (
        supabase.table("resources")
        .select("*")
        .eq("course_id", course_id)
        .execute()
    )
    return response.data