from fastapi import APIRouter
from pydantic import BaseModel

from openai import OpenAI

import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

router = APIRouter()


class Resource(BaseModel):
    title: str
    course: str
    resource_type: str
    description: str
    course_id: int

class ChatRequest(BaseModel):
    question: str


@router.post("/resources")
def create_resource(resource: Resource):
    data = {
        "title": resource.title,
        "course": resource.course,
        "resource_type": resource.resource_type,
        "description": resource.description,
        "course_id": resource.course_id
    }

    response = supabase.table("resources").insert(data).execute()
    return response.data


@router.get("/resources")
def get_resources():
    response = supabase.table("resources").select("*").execute()
    return response.data


@router.get("/resources/{resource_id}")
def get_resource(resource_id: int):
    response = (
        supabase.table("resources")
        .select("*")
        .eq("id", resource_id)
        .execute()
    )
    return response.data


@router.put("/resources/{resource_id}")
def update_resource(resource_id: int, resource: Resource):
    data = {
        "title": resource.title,
        "course": resource.course,
        "resource_type": resource.resource_type,
        "description": resource.description,
        "course_id": resource.course_id
    }

    response = (
        supabase.table("resources")
        .update(data)
        .eq("id", resource_id)
        .execute()
    )

    return response.data


@router.delete("/resources/{resource_id}")
def delete_resource(resource_id: int):
    response = (
        supabase.table("resources")
        .delete()
        .eq("id", resource_id)
        .execute()
    )

    return response.data


@router.post("/resources/{resource_id}/ask")
def ask_resource(resource_id: int, request: ChatRequest):

    response = (
        supabase.table("resources")
        .select("*")
        .eq("id", resource_id)
        .execute()
    )

    if not response.data:
        return {
            "answer": "자료를 찾을 수 없습니다."
        }

    resource = response.data[0]

    title = resource.get("title", "")
    description = resource.get("description", "")

    prompt = f"""
You are a study assistant for university students.

Answer the student's question using ONLY the study resource information provided below.

If the information is not contained in the resource, clearly say that the current resource does not provide enough information to answer the question.

Resource title:
{title}

Resource content:
{description}

Student question:
{request.question}
"""

    ai_response = client.responses.create(
        model="gpt-6-luna",
        input=prompt
    )

    return {
        "answer": ai_response.output_text
    }