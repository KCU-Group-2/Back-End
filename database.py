import os

from dotenv import load_dotenv
from fastapi import HTTPException
from supabase import create_client


load_dotenv()


def get_supabase_admin():
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_secret_key = os.getenv("SUPABASE_SECRET_KEY")

    if not supabase_url or not supabase_secret_key:
        raise HTTPException(
            status_code=500,
            detail="Supabase admin configuration is missing."
        )

    return create_client(
        supabase_url,
        supabase_secret_key
    )