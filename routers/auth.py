from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from supabase import create_client
from dotenv import load_dotenv

import os


load_dotenv()


router = APIRouter()

security = HTTPBearer(auto_error=False)


class SignupRequest(BaseModel):
    name: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


def get_supabase():
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")

    if not supabase_url or not supabase_key:
        raise HTTPException(
            status_code=500,
            detail="Supabase configuration is missing."
        )

    return create_client(
        supabase_url,
        supabase_key
    )


# 현재 요청을 보낸 로그인 사용자를 확인하는 함수
def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Login required."
        )

    token = credentials.credentials

    try:
        supabase = get_supabase()

        response = supabase.auth.get_user(token)

        if response.user is None:
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired token."
            )

        return response.user

    except HTTPException:
        raise

    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token."
        )


@router.post("/signup")
def signup(request: SignupRequest):
    email = request.email.strip().lower()
    name = request.name.strip()

    if not email.endswith("@wisc.edu"):
        raise HTTPException(
            status_code=400,
            detail="Please use a wisc.edu email address."
        )

    if len(request.password) < 8:
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 8 characters."
        )

    try:
        supabase = get_supabase()

        response = supabase.auth.sign_up({
            "email": email,
            "password": request.password,
            "options": {
                "data": {
                    "name": name
                }
            }
        })

        if response.user is None:
            raise HTTPException(
                status_code=400,
                detail="Unable to create account."
            )

        return {
            "success": True,
            "message": "Account created successfully.",
            "requires_email_confirmation": response.session is None,
            "user": {
                "id": response.user.id,
                "email": response.user.email,
                "name": name
            }
        }

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )


@router.post("/login")
def login(request: LoginRequest):
    email = request.email.strip().lower()

    try:
        supabase = get_supabase()

        response = supabase.auth.sign_in_with_password({
            "email": email,
            "password": request.password
        })

        if response.user is None or response.session is None:
            raise HTTPException(
                status_code=401,
                detail="Invalid email or password."
            )

        metadata = response.user.user_metadata or {}

        return {
            "success": True,
            "message": "Login successful.",
            "user": {
                "id": response.user.id,
                "email": response.user.email,
                "name": metadata.get("name")
            },
            "access_token": response.session.access_token
        }

    except HTTPException:
        raise

    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password."
        )