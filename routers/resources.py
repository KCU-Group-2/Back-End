from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile
)

from pydantic import BaseModel
from openai import OpenAI

from uuid import uuid4

import os
import tempfile

from dotenv import load_dotenv

from database import get_supabase_admin
from routers.auth import get_current_user


load_dotenv()


router = APIRouter()


PDF_BUCKET = "resource-pdfs"
MAX_PDF_SIZE = 20 * 1024 * 1024


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = (
    OpenAI(api_key=OPENAI_API_KEY)
    if OPENAI_API_KEY
    else None
)


class Resource(BaseModel):
    title: str
    course: str
    resource_type: str
    description: str
    course_id: int


class ChatRequest(BaseModel):
    question: str


# 일반 사용자에게 보여줄 Resource 형태
# uploader_id와 pdf_path는 숨긴다.
def public_resource(resource):
    return {
        "id": resource.get("id"),
        "title": resource.get("title"),
        "course": resource.get("course"),
        "resource_type": resource.get("resource_type"),
        "description": resource.get("description"),
        "course_id": resource.get("course_id"),
        "created_at": resource.get("created_at"),

        # 일반 사용자에게 실제 이름/ID를 보여주지 않음
        "uploader": "Anonymous",

        # PDF가 있는지만 frontend에 알려줌
        "has_pdf": bool(resource.get("pdf_path")),

        # 파일 이름은 보여줘도 됨
        "pdf_filename": resource.get("pdf_filename")
    }


def get_resource_row(resource_id: int):
    admin = get_supabase_admin()

    response = (
        admin.table("resources")
        .select("*")
        .eq("id", resource_id)
        .execute()
    )

    if not response.data:
        raise HTTPException(
            status_code=404,
            detail="Resource not found."
        )

    return response.data[0]


def check_resource_owner(resource, current_user):
    uploader_id = resource.get("uploader_id")

    # 기존 legacy resource에는 uploader_id가 없을 수 있으므로
    # uploader_id가 있는 새 resource부터 ownership 확인
    if uploader_id is not None:
        if str(uploader_id) != str(current_user.id):
            raise HTTPException(
                status_code=403,
                detail="You can only modify your own resource."
            )


# 기존 JSON Resource 생성 API
# PDF 없이 Resource만 만드는 기존 기능도 유지한다.
@router.post("/resources")
def create_resource(
    resource: Resource,
    current_user=Depends(get_current_user)
):
    admin = get_supabase_admin()

    data = {
        "title": resource.title.strip(),
        "course": resource.course.strip(),
        "resource_type": resource.resource_type.strip(),
        "description": resource.description.strip(),
        "course_id": resource.course_id,
        "uploader_id": current_user.id
    }

    response = (
        admin.table("resources")
        .insert(data)
        .execute()
    )

    return [
        public_resource(row)
        for row in response.data
    ]


# PDF와 Resource 정보를 같이 업로드하는 API
@router.post("/resources/upload")
async def create_resource_with_pdf(
    title: str = Form(...),
    course: str = Form(...),
    resource_type: str = Form(...),
    description: str = Form(""),
    course_id: int = Form(...),
    pdf_file: UploadFile = File(...),
    current_user=Depends(get_current_user)
):
    filename = pdf_file.filename or "resource.pdf"

    if not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are allowed."
        )

    file_bytes = await pdf_file.read()

    if len(file_bytes) == 0:
        raise HTTPException(
            status_code=400,
            detail="PDF file is empty."
        )

    if len(file_bytes) > MAX_PDF_SIZE:
        raise HTTPException(
            status_code=413,
            detail="PDF file must be 20 MB or smaller."
        )

    # 실제 PDF 파일인지 간단히 검사
    if not file_bytes.startswith(b"%PDF"):
        raise HTTPException(
            status_code=400,
            detail="The uploaded file is not a valid PDF."
        )

    admin = get_supabase_admin()

    # 같은 파일 이름이 충돌하지 않도록 UUID 사용
    storage_path = (
        f"{current_user.id}/"
        f"{uuid4()}.pdf"
    )

    uploaded = False

    temporary_path = None

    try:
        # 먼저 업로드된 PDF를 임시 파일로 저장
        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".pdf"
        ) as temp_file:
            temp_file.write(file_bytes)
            temporary_path = temp_file.name

        # 실제 파일을 열어서 Supabase Storage에 업로드
        with open(temporary_path, "rb") as pdf_file:
            admin.storage.from_(PDF_BUCKET).upload(
                path=storage_path,
                file=pdf_file,
                file_options={
                    "content-type": "application/pdf",
                    "upsert": "false"
                }
            )

        uploaded = True

        resource_data = {
            "title": title.strip(),
            "course": course.strip(),
            "resource_type": resource_type.strip(),
            "description": description.strip(),
            "course_id": course_id,

            # 실제 uploader ID는 DB 내부에 저장
            "uploader_id": current_user.id,

            # Storage 안의 PDF 위치
            "pdf_path": storage_path,

            # 원래 파일 이름
            "pdf_filename": filename
        }

        response = (
            admin.table("resources")
            .insert(resource_data)
            .execute()
        )

        if not response.data:
            raise RuntimeError(
                "Resource database record was not created."
            )

        return [
            public_resource(row)
            for row in response.data
        ]

    except Exception as e:
        # PDF만 올라가고 DB 저장이 실패하면
        # Storage의 PDF를 다시 삭제
        if uploaded:
            try:
                admin.storage.from_(PDF_BUCKET).remove(
                    [storage_path]
                )
            except Exception:
                pass

        raise HTTPException(
            status_code=500,
            detail=f"Unable to upload resource: {str(e)}"
        )

    finally:
        # Mac에 임시로 만든 PDF 파일 삭제
        if temporary_path and os.path.exists(temporary_path):
            os.remove(temporary_path)


@router.get("/resources")
def get_resources(
    current_user=Depends(get_current_user)
):
    admin = get_supabase_admin()

    response = (
        admin.table("resources")
        .select("*")
        .execute()
    )

    return [
        public_resource(row)
        for row in response.data
    ]


@router.get("/resources/{resource_id}")
def get_resource(
    resource_id: int,
    current_user=Depends(get_current_user)
):
    resource = get_resource_row(resource_id)

    return [
        public_resource(resource)
    ]


@router.put("/resources/{resource_id}")
def update_resource(
    resource_id: int,
    resource: Resource,
    current_user=Depends(get_current_user)
):
    admin = get_supabase_admin()

    old_resource = get_resource_row(resource_id)

    check_resource_owner(
        old_resource,
        current_user
    )

    data = {
        "title": resource.title.strip(),
        "course": resource.course.strip(),
        "resource_type": resource.resource_type.strip(),
        "description": resource.description.strip(),
        "course_id": resource.course_id
    }

    response = (
        admin.table("resources")
        .update(data)
        .eq("id", resource_id)
        .execute()
    )

    return [
        public_resource(row)
        for row in response.data
    ]


@router.delete("/resources/{resource_id}")
def delete_resource(
    resource_id: int,
    current_user=Depends(get_current_user)
):
    admin = get_supabase_admin()

    resource = get_resource_row(resource_id)

    check_resource_owner(
        resource,
        current_user
    )

    pdf_path = resource.get("pdf_path")

    (
        admin.table("resources")
        .delete()
        .eq("id", resource_id)
        .execute()
    )

    # DB 삭제 후 Storage 파일도 삭제
    if pdf_path:
        try:
            admin.storage.from_(PDF_BUCKET).remove(
                [pdf_path]
            )
        except Exception:
            # DB 삭제는 성공했기 때문에
            # Storage cleanup 실패로 전체 요청을 실패시키지는 않음
            pass

    return {
        "success": True
    }


# Resource의 PDF를 열기 위한 임시 signed URL 생성
@router.get("/resources/{resource_id}/pdf")
def get_resource_pdf(
    resource_id: int,
    current_user=Depends(get_current_user)
):
    admin = get_supabase_admin()

    resource = get_resource_row(resource_id)

    pdf_path = resource.get("pdf_path")

    if not pdf_path:
        raise HTTPException(
            status_code=404,
            detail="This resource does not have a PDF."
        )

    signed = (
        admin.storage
        .from_(PDF_BUCKET)
        .create_signed_url(
            pdf_path,
            600
        )
    )

    url = None

    if isinstance(signed, dict):
        url = (
            signed.get("signedURL")
            or signed.get("signedUrl")
            or signed.get("signed_url")
        )
    else:
        url = (
            getattr(signed, "signedURL", None)
            or getattr(signed, "signedUrl", None)
            or getattr(signed, "signed_url", None)
        )

    if not url:
        raise HTTPException(
            status_code=500,
            detail="Unable to create PDF URL."
        )

    return {
        "url": url,
        "filename": resource.get("pdf_filename")
    }


# 기존 chatbot API
@router.post("/resources/{resource_id}/ask")
def ask_resource(
    resource_id: int,
    request: ChatRequest,
    current_user=Depends(get_current_user)
):
    if client is None:
        raise HTTPException(
            status_code=500,
            detail="OpenAI configuration is missing."
        )

    resource = get_resource_row(resource_id)

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