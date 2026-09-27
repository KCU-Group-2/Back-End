from fastapi import FastAPI

import os
from dotenv import load_dotenv
from supabase import create_client

from routers import resources, auth

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

app = FastAPI()

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