from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from supabase import create_client
from dotenv import load_dotenv
import os


load_dotenv()


router = APIRouter()


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

    return create_client(supabase_url, supabase_key)

'''
회원가입 하는 코드 (supabase 사용)
frontend에서 회원가입 정보가 오면 → 형식 확인 → 이메일/비밀번호 검사 
    → Supabase에 실제 계정 생성 → 결과를 frontend에 돌려주는 코드
'''
@router.post("/signup")
def signup(request: SignupRequest):
    email = request.email.strip().lower()
    name = request.name.strip()

    # 에러 400은 HTTP에서 흔히 사용자가 보낸 요청에 문제가 있다는 뜻
    if not email.endswith("@wisc.edu"):
        raise HTTPException(
            status_code=400,
            detail="Please use a wisc.edu email address."
        )

    # 비밀번호 길이가 8글자보다 짧은지 확인
    if len(request.password) < 8:
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 8 characters."
        )

    try:
        '''
        create_client(supabase_url, supabase_key)가 Supabase Client 객체를 생성해서 
        return하고, supabase 변수가 그 Client 객체를 가리킨다. 그다음 supabase 변수를 
        이용해서 Supabase의 auth, database 같은 기능을 사용할 수 있다.
        '''
        supabase = get_supabase()

        '''
        Supabase Auth(사용자 인증)야, 새 사용자 계정 만들어줘 라는 뜻. 
        Supabase에서 sign_up 하면 user(언에 id, email) 그리고 
        session(사용자가 지금 로그인된 상태임을 유지해주는 정보) 이 담긴 꾸러미 return 해줌
        '''
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

        # 새 dictionary 만들어서 frontend에 반환. Backend가 frontend에게
        # 회원가입 성공했다고 결과 보냄
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

    # 위의 try: 안에서 에러가 생겼을 때 어떻게 처리할지 정하는 부분
    # 내용을 바꾸지 않고 그대로 frontend로 보냄
    except HTTPException:
        raise

    # 그 외에 예상 못 한 다른 에러가 발생하면 그 에러를 e라는 변수에 저장하고, 
    # 그 에러를 FastAPI용 HTTP 에러 형태로 바꿔서 frontend에 보냄
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )

'''
frontend에서 이메일/비밀번호를 받아서 → Supabase에 “이 계정 맞아?”라고 물어보고 
    → 맞으면 로그인 성공 정보를 frontend에 돌려주는 코드
'''
@router.post("/login")
def login(request: LoginRequest):
    email = request.email.strip().lower()

    try:
        '''
        create_client(supabase_url, supabase_key) return함.
        create_client(supabase_url, supabase_key)가 Supabase Client 객체를 생성해서 
        return하고, supabase 변수가 그 Client 객체를 가리킨다. 그다음 supabase 변수를 
        이용해서 Supabase의 auth, database 같은 기능을 사용할 수 있다.
        '''
        supabase = get_supabase()

        # 보통 response.user, response.session 들어있음
        response = supabase.auth.sign_in_with_password({
            "email": email,
            "password": request.password
        })

        if response.user is None or response.session is None:
            raise HTTPException(
                status_code=401,
                detail="Invalid email or password."
            )

        return {
            "success": True,
            "message": "Login successful.",
            "user": {
                "id": response.user.id,
                "email": response.user.email,
                "name": response.user.user_metadata.get("name")
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