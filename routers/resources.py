from fastapi import APIRouter
from pydantic import BaseModel

import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

router = APIRouter()


class Resource(BaseModel):
    title: str
    course: str
    resource_type: str
    description: str
    course_id: int


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