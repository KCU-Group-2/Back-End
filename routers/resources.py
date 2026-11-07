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


# 일반 사용자에게 보여줄 Resource 정보
# 실제 uploader_id와 pdf_path는 숨긴다.
def public_resource(resource):
    return {
        "id": resource.get("id"),
        "title": resource.get("title"),
        "course": resource.get("course"),
        "resource_type": resource.get("resource_type"),
        "description": resource.get("description"),
        "course_id": resource.get("course_id"),
        "created_at": resource.get("created_at"),

        "uploader": "Anonymous",

        "has_pdf": bool(
            resource.get("pdf_path")
        ),

        "pdf_filename": resource.get(
            "pdf_filename"
        )
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


def check_resource_owner(
    resource,
    current_user
):
    uploader_id = resource.get(
        "uploader_id"
    )

    # 기존 Resource에는 uploader_id가
    # NULL일 수 있으므로 새 Resource부터 검사
    if uploader_id is not None:
        if str(uploader_id) != str(
            current_user.id
        ):
            raise HTTPException(
                status_code=403,
                detail=(
                    "You can only modify "
                    "your own resource."
                )
            )


# PDF 없이 Resource만 생성하는 기존 API
@router.post("/resources")
def create_resource(
    resource: Resource,
    current_user=Depends(
        get_current_user
    )
):
    admin = get_supabase_admin()

    data = {
        "title": resource.title.strip(),
        "course": resource.course.strip(),
        "resource_type":
            resource.resource_type.strip(),
        "description":
            resource.description.strip(),
        "course_id":
            resource.course_id,

        "uploader_id":
            current_user.id
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


# Resource 정보 + PDF 업로드
@router.post("/resources/upload")
async def create_resource_with_pdf(
    title: str = Form(...),
    course: str = Form(...),
    resource_type: str = Form(...),
    description: str = Form(""),
    course_id: int = Form(...),
    pdf_file: UploadFile = File(...),
    current_user=Depends(
        get_current_user
    )
):
    filename = (
        pdf_file.filename
        or "resource.pdf"
    )

    if not filename.lower().endswith(
        ".pdf"
    ):
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
            detail=(
                "PDF file must be "
                "20 MB or smaller."
            )
        )

    if not file_bytes.startswith(b"%PDF"):
        raise HTTPException(
            status_code=400,
            detail=(
                "The uploaded file is "
                "not a valid PDF."
            )
        )

    admin = get_supabase_admin()

    storage_path = (
        f"{current_user.id}/"
        f"{uuid4()}.pdf"
    )

    uploaded = False
    temporary_path = None

    try:
        # PDF bytes를 임시 파일로 저장
        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".pdf"
        ) as temp_file:
            temp_file.write(file_bytes)
            temporary_path = (
                temp_file.name
            )

        # Supabase Storage에 업로드
        with open(
            temporary_path,
            "rb"
        ) as stored_pdf:
            (
                admin.storage
                .from_(PDF_BUCKET)
                .upload(
                    path=storage_path,
                    file=stored_pdf,
                    file_options={
                        "content-type":
                            "application/pdf",
                        "upsert": "false"
                    }
                )
            )

        uploaded = True

        resource_data = {
            "title":
                title.strip(),

            "course":
                course.strip(),

            "resource_type":
                resource_type.strip(),

            "description":
                description.strip(),

            "course_id":
                course_id,

            "uploader_id":
                current_user.id,

            "pdf_path":
                storage_path,

            "pdf_filename":
                filename
        }

        response = (
            admin.table("resources")
            .insert(resource_data)
            .execute()
        )

        if not response.data:
            raise RuntimeError(
                "Resource database "
                "record was not created."
            )

        return [
            public_resource(row)
            for row in response.data
        ]

    except Exception as e:
        # PDF upload 후 DB insert 실패 시
        # Storage에 올라간 PDF도 삭제
        if uploaded:
            try:
                (
                    admin.storage
                    .from_(PDF_BUCKET)
                    .remove(
                        [storage_path]
                    )
                )
            except Exception:
                pass

        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to upload resource: "
                f"{str(e)}"
            )
        )

    finally:
        # 임시 파일 삭제
        if (
            temporary_path
            and os.path.exists(
                temporary_path
            )
        ):
            os.remove(
                temporary_path
            )


@router.get("/resources")
def get_resources(
    current_user=Depends(
        get_current_user
    )
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


@router.get(
    "/resources/{resource_id}"
)
def get_resource(
    resource_id: int,
    current_user=Depends(
        get_current_user
    )
):
    resource = get_resource_row(
        resource_id
    )

    return [
        public_resource(resource)
    ]


@router.put(
    "/resources/{resource_id}"
)
def update_resource(
    resource_id: int,
    resource: Resource,
    current_user=Depends(
        get_current_user
    )
):
    admin = get_supabase_admin()

    old_resource = get_resource_row(
        resource_id
    )

    check_resource_owner(
        old_resource,
        current_user
    )

    data = {
        "title":
            resource.title.strip(),

        "course":
            resource.course.strip(),

        "resource_type":
            resource.resource_type.strip(),

        "description":
            resource.description.strip(),

        "course_id":
            resource.course_id
    }

    response = (
        admin.table("resources")
        .update(data)
        .eq(
            "id",
            resource_id
        )
        .execute()
    )

    return [
        public_resource(row)
        for row in response.data
    ]


@router.delete(
    "/resources/{resource_id}"
)
def delete_resource(
    resource_id: int,
    current_user=Depends(
        get_current_user
    )
):
    admin = get_supabase_admin()

    resource = get_resource_row(
        resource_id
    )

    check_resource_owner(
        resource,
        current_user
    )

    pdf_path = resource.get(
        "pdf_path"
    )

    (
        admin.table("resources")
        .delete()
        .eq(
            "id",
            resource_id
        )
        .execute()
    )

    # DB 삭제 후 Storage PDF도 삭제
    if pdf_path:
        try:
            (
                admin.storage
                .from_(PDF_BUCKET)
                .remove(
                    [pdf_path]
                )
            )
        except Exception:
            pass

    return {
        "success": True
    }


# PDF 열기용 signed URL
@router.get(
    "/resources/{resource_id}/pdf"
)
def get_resource_pdf(
    resource_id: int,
    current_user=Depends(
        get_current_user
    )
):
    admin = get_supabase_admin()

    resource = get_resource_row(
        resource_id
    )

    pdf_path = resource.get(
        "pdf_path"
    )

    if not pdf_path:
        raise HTTPException(
            status_code=404,
            detail=(
                "This resource does "
                "not have a PDF."
            )
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
            or signed.get(
                "signed_url"
            )
        )

    else:
        url = (
            getattr(
                signed,
                "signedURL",
                None
            )
            or getattr(
                signed,
                "signedUrl",
                None
            )
            or getattr(
                signed,
                "signed_url",
                None
            )
        )

    if not url:
        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to create "
                "PDF URL."
            )
        )

    return {
        "url": url,
        "filename":
            resource.get(
                "pdf_filename"
            )
    }


# 기존 chatbot API 유지
@router.post(
    "/resources/{resource_id}/ask"
)
def ask_resource(
    resource_id: int,
    request: ChatRequest,
    current_user=Depends(
        get_current_user
    )
):
    if client is None:
        raise HTTPException(
            status_code=500,
            detail=(
                "OpenAI configuration "
                "is missing."
            )
        )

    admin = get_supabase_admin()

    response = (
        admin.table("resources")
        .select("*")
        .eq(
            "id",
            resource_id
        )
        .execute()
    )

    if not response.data:
        return {
            "answer":
                "자료를 찾을 수 없습니다."
        }

    resource = response.data[0]

    title = resource.get(
        "title",
        ""
    )

    description = resource.get(
        "description",
        ""
    )

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

    ai_response = (
        client.responses.create(
            model="gpt-6-luna",
            input=prompt
        )
    )

    return {
        "answer":
            ai_response.output_text
    }