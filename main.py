from fastapi import FastAPI

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
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
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