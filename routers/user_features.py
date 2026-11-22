from fastapi import APIRouter, Depends, HTTPException

from database import get_supabase_admin
from routers.auth import get_current_user
from routers import resources


router = APIRouter()


def get_current_points(user_id):
    admin = get_supabase_admin()

    response = (
        admin.table("profiles")
        .select("points")
        .eq("user_id", str(user_id))
        .execute()
    )

    if not response.data:
        raise HTTPException(
            status_code=500,
            detail="User point profile was not found."
        )

    return response.data[0]["points"]


# ---------------------------------------------------------
# Current point balance
# ---------------------------------------------------------

@router.get("/me/points")
def get_my_points(
    current_user=Depends(get_current_user)
):
    points = get_current_points(
        current_user.id
    )

    return {
        "points": points
    }


# ---------------------------------------------------------
# Unlock a resource
# ---------------------------------------------------------

@router.post("/resources/{resource_id}/unlock")
def unlock_resource(
    resource_id: int,
    current_user=Depends(get_current_user)
):
    admin = get_supabase_admin()

    resource = resources.get_resource_row(
        resource_id
    )

    if not resource:
        raise HTTPException(
            status_code=404,
            detail="Resource not found."
        )

    moderation_status = resource.get(
        "moderation_status",
        "active"
    )

    if moderation_status == "review":
        raise HTTPException(
            status_code=403,
            detail="This resource is under review and cannot be unlocked."
        )

    if moderation_status == "removed":
        raise HTTPException(
            status_code=404,
            detail="Resource not found."
        )

    response = (
        admin.rpc(
            "unlock_resource",
            {
                "p_user_id": str(
                    current_user.id
                ),
                "p_resource_id": resource_id
            }
        )
        .execute()
    )

    if not response.data:
        raise HTTPException(
            status_code=500,
            detail="Unable to unlock resource."
        )

    result = (
        response.data[0]
        if isinstance(response.data, list)
        else response.data
    )

    status = result.get(
        "result_status"
    )

    if status == "not_found":
        raise HTTPException(
            status_code=404,
            detail="Resource not found."
        )

    if status == "insufficient_points":
        raise HTTPException(
            status_code=400,
            detail=(
                "Not enough points to unlock "
                "this resource."
            )
        )


    return {
        "success": True,
        "status": status,
        "points": result.get(
            "remaining_points"
        ),
        "charged": result.get(
            "charged_points"
        ),
        "resource": resources.public_resource(
            resource,
            current_user
        )
    }


# ---------------------------------------------------------
# My Library
# ---------------------------------------------------------

@router.get("/me/library")
def get_my_library(
    current_user=Depends(get_current_user)
):
    admin = get_supabase_admin()

    user_id = str(
        current_user.id
    )

    # Resources uploaded by this user
    uploaded_response = (
        admin.table("resources")
        .select("*")
        .eq(
            "uploader_id",
            user_id
        )
        .order(
            "created_at",
            desc=True
        )
        .execute()
    )

    uploaded = [
        resources.public_resource(
            row,
            current_user
        )
        for row in uploaded_response.data
    ]

    # Resources this user unlocked
    unlock_response = (
        admin.table("resource_unlocks")
        .select(
            "resource_id, unlocked_at"
        )
        .eq(
            "user_id",
            user_id
        )
        .order(
            "unlocked_at",
            desc=True
        )
        .execute()
    )

    unlock_ids = [
        row["resource_id"]
        for row in unlock_response.data
    ]

    unlocked = []

    if unlock_ids:
        resource_response = (
            admin.table("resources")
            .select("*")
            .in_(
                "id",
                unlock_ids
            )
            .execute()
        )

        resource_by_id = {
            row["id"]: row
            for row
            in resource_response.data
        }

        for resource_id in unlock_ids:
            row = resource_by_id.get(
                resource_id
            )

            if row:
                unlocked.append(
                    resources.public_resource(
                        row,
                        current_user
                    )
                )

    return {
        "uploaded": uploaded,
        "unlocked": unlocked,
        "uploaded_count": len(uploaded),
        "unlocked_count": len(unlocked)
    }