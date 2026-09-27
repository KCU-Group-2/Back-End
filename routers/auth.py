from fastapi import APIRouter
from pydantic import BaseModel


router = APIRouter()


DEMO_USER = {
    "id": "demo-user-1",
    "email": "test@wisc.edu",
    "password": "studyswap123",
    "name": "StudySwap Test User"
}


class LoginRequest(BaseModel):
    email: str
    password: str


def authenticate_user(email: str, password: str):
    if (
        email == DEMO_USER["email"]
        and password == DEMO_USER["password"]
    ):
        return {
            "id": DEMO_USER["id"],
            "email": DEMO_USER["email"],
            "name": DEMO_USER["name"]
        }

    return None


@router.post("/login")
def login(login_request: LoginRequest):
    user = authenticate_user(
        login_request.email,
        login_request.password
    )

    if user is None:
        return {
            "success": False,
            "message": "Invalid email or password"
        }

    return {
        "success": True,
        "user": user
    }