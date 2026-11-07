from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from database import get_supabase_admin
from routers.auth import get_current_user


router = APIRouter()


class ResourceRequestCreate(BaseModel):
    content: str


class FulfillRequest(BaseModel):
    resource_id: int


def public_request(request_row):
    return {
        "id": request_row.get("id"),
        "course_id": request_row.get("course_id"),
        "content": request_row.get("content"),
        "status": request_row.get("status"),
        "fulfilled_resource_id": request_row.get(
            "fulfilled_resource_id"
        ),
        "created_at": request_row.get("created_at"),

        # 실제 requester_id는 frontend에 숨김
        "requester": "Anonymous"
    }


# 자료 요청 작성
@router.post("/courses/{course_id}/requests")
def create_resource_request(
    course_id: int,
    body: ResourceRequestCreate,
    current_user=Depends(get_current_user)
):
    content = body.content.strip()

    if not content:
        raise HTTPException(
            status_code=400,
            detail="Request content is required."
        )

    admin = get_supabase_admin()

    course_response = (
        admin.table("courses")
        .select("id")
        .eq("id", course_id)
        .execute()
    )

    if not course_response.data:
        raise HTTPException(
            status_code=404,
            detail="Course not found."
        )

    response = (
        admin.table("resource_requests")
        .insert({
            "course_id": course_id,
            "requester_id": current_user.id,
            "content": content
        })
        .execute()
    )

    return [
        public_request(row)
        for row in response.data
    ]


# 특정 Course의 자료 요청 목록
@router.get("/courses/{course_id}/requests")
def get_course_requests(
    course_id: int,
    current_user=Depends(get_current_user)
):
    admin = get_supabase_admin()

    response = (
        admin.table("resource_requests")
        .select("*")
        .eq("course_id", course_id)
        .order(
            "created_at",
            desc=True
        )
        .execute()
    )

    return [
        public_request(row)
        for row in response.data
    ]


# 업로드된 Resource로 요청을 해결했다고 표시
@router.patch("/requests/{request_id}/fulfill")
def fulfill_request(
    request_id: int,
    body: FulfillRequest,
    current_user=Depends(get_current_user)
):
    admin = get_supabase_admin()

    request_response = (
        admin.table("resource_requests")
        .select("*")
        .eq("id", request_id)
        .execute()
    )

    if not request_response.data:
        raise HTTPException(
            status_code=404,
            detail="Request not found."
        )

    request_row = request_response.data[0]

    resource_response = (
        admin.table("resources")
        .select(
            "id, course_id, uploader_id"
        )
        .eq("id", body.resource_id)
        .execute()
    )

    if not resource_response.data:
        raise HTTPException(
            status_code=404,
            detail="Resource not found."
        )

    resource = resource_response.data[0]

    # 이 사용자가 실제로 올린 Resource인지 확인
    if str(resource.get("uploader_id")) != str(
        current_user.id
    ):
        raise HTTPException(
            status_code=403,
            detail="You can only use your own uploaded resource."
        )

    # 요청 Course와 Resource Course가 같은지 확인
    if (
        resource.get("course_id")
        != request_row.get("course_id")
    ):
        raise HTTPException(
            status_code=400,
            detail="Resource and request must belong to the same course."
        )

    response = (
        admin.table("resource_requests")
        .update({
            "status": "fulfilled",
            "fulfilled_resource_id": body.resource_id
        })
        .eq("id", request_id)
        .execute()
    )

    return [
        public_request(row)
        for row in response.data
    ]