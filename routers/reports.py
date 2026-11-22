import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from database import get_supabase_admin
from routers.auth import get_current_user

router = APIRouter()


class ReportCreate(BaseModel):
    reason: str
    details: str | None = None


def require_admin(current_user):
    admin_emails = {
        email.strip().lower()
        for email in os.getenv("ADMIN_EMAILS", "").split(",")
        if email.strip()
    }

    user_email = (getattr(current_user, "email", None) or "").lower()

    if user_email not in admin_emails:
        raise HTTPException(status_code=403, detail="Admin access required.")


# ---------------------------------------------------------
# Submit report
# ---------------------------------------------------------

@router.post("/resources/{resource_id}/report")
def report_resource(
    resource_id: int,
    report: ReportCreate,
    current_user=Depends(get_current_user)
):
    admin = get_supabase_admin()

    reporter_profile = (
        admin.table("profiles")
        .select("reporting_restricted")
        .eq("user_id", str(current_user.id))
        .execute()
    )

    if (
        reporter_profile.data
        and reporter_profile.data[0].get(
            "reporting_restricted"
        )
    ):
        raise HTTPException(
            status_code=403,
            detail="Your reporting access has been restricted."
        )

    resource_response = (
        admin.table("resources")
        .select("*")
        .eq("id", resource_id)
        .execute()
    )

    if not resource_response.data:
        raise HTTPException(status_code=404, detail="Resource not found.")

    resource = resource_response.data[0]

    if resource.get("moderation_status") == "removed":
        raise HTTPException(
            status_code=400,
            detail="This resource has already been removed."
        )

    # Only users who unlocked the resource may report it.
    unlock_response = (
        admin.table("resource_unlocks")
        .select("resource_id")
        .eq("user_id", current_user.id)
        .eq("resource_id", resource_id)
        .execute()
    )

    if not unlock_response.data:
        raise HTTPException(
            status_code=403,
            detail="You can only report resources you have unlocked."
        )

    # One report per user per resource.
    existing_report = (
        admin.table("resource_reports")
        .select("id")
        .eq("resource_id", resource_id)
        .eq("reporter_id", current_user.id)
        .execute()
    )

    if existing_report.data:
        raise HTTPException(
            status_code=400,
            detail="You already reported this resource."
        )

    admin.table("resource_reports").insert({
        "resource_id": resource_id,
        "reporter_id": current_user.id,
        "reason": report.reason.strip(),
        "details": report.details.strip() if report.details else None
    }).execute()

    # Count pending reports from distinct users.
    report_count_response = (
        admin.table("resource_reports")
        .select("reporter_id")
        .eq("resource_id", resource_id)
        .eq("status", "pending")
        .execute()
    )

    distinct_reporters = {
        row["reporter_id"]
        for row in report_count_response.data
    }

    report_count = len(distinct_reporters)

    # 3 different reporters -> review, stop normal availability.
    if report_count >= 3:
        (
            admin.table("resources")
            .update({"moderation_status": "review"})
            .eq("id", resource_id)
            .execute()
        )

    return {
        "message": "Report submitted.",
        "report_count": report_count,
        "under_review": report_count >= 3
    }


# ---------------------------------------------------------
# Admin: list resources under review
# ---------------------------------------------------------

@router.get("/admin/reports/review")
def get_review_resources(
    current_user=Depends(get_current_user)
):
    require_admin(current_user)

    admin = get_supabase_admin()

    resources_response = (
        admin.table("resources")
        .select("*")
        .eq("moderation_status", "review")
        .execute()
    )

    results = []

    for resource in resources_response.data:
        reports_response = (
            admin.table("resource_reports")
            .select("*")
            .eq("resource_id", resource["id"])
            .eq("status", "pending")
            .execute()
        )

        results.append({
            "resource": resource,
            "reports": reports_response.data,
            "report_count": len(reports_response.data)
        })

    return results


# ---------------------------------------------------------
# Admin: approve report / remove resource
# ---------------------------------------------------------

@router.post("/admin/resources/{resource_id}/approve-report")
def approve_report(
    resource_id: int,
    current_user=Depends(get_current_user)
):
    require_admin(current_user)

    admin = get_supabase_admin()

    resource_response = (
        admin.table("resources")
        .select("*")
        .eq("id", resource_id)
        .execute()
    )

    if not resource_response.data:
        raise HTTPException(status_code=404, detail="Resource not found.")

    resource = resource_response.data[0]

    if resource.get("moderation_status") == "removed":
        raise HTTPException(
            status_code=400,
            detail="Resource has already been removed."
        )

    uploader_id = resource.get("uploader_id")

    if uploader_id:
        uploader_profile = (
            admin.table("profiles")
            .select("violation_count")
            .eq("user_id", uploader_id)
            .execute()
        )

        if uploader_profile.data:
            new_violation_count = (
                uploader_profile.data[0].get(
                    "violation_count",
                    0
                )
                + 1
            )

            profile_update = {
                "violation_count":
                    new_violation_count
            }

            if new_violation_count >= 3:
                profile_update[
                    "upload_restricted"
                ] = True

            (
                admin.table("profiles")
                .update(profile_update)
                .eq("user_id", uploader_id)
                .execute()
            )

    # -----------------------------------------------------
    # Refund everyone who unlocked this resource
    # -----------------------------------------------------

    unlock_response = (
        admin.table("resource_unlocks")
        .select("user_id, points_spent")
        .eq("resource_id", resource_id)
        .execute()
    )

    refunded_users = 0
    total_refunded = 0

    for unlock in unlock_response.data:
        user_id = unlock["user_id"]
        refund_amount = unlock["points_spent"]

        profile_response = (
            admin.table("profiles")
            .select("points")
            .eq("user_id", user_id)
            .execute()
        )

        if profile_response.data:
            current_points = profile_response.data[0]["points"]

            (
                admin.table("profiles")
                .update({
                    "points": current_points + refund_amount
                })
                .eq("user_id", user_id)
                .execute()
            )

            admin.table("point_transactions").insert({
                "user_id": user_id,
                "amount": refund_amount,
                "transaction_type": "resource_refund",
                "resource_id": resource_id
            }).execute()

            refunded_users += 1
            total_refunded += refund_amount

    # -----------------------------------------------------
    # Claw back points uploader earned from this resource
    # resource_upload = +20
    # request_fulfilled = possibly +10
    # -----------------------------------------------------

    clawback_amount = 0

    if uploader_id:
        reward_response = (
            admin.table("point_transactions")
            .select("amount, transaction_type")
            .eq("user_id", uploader_id)
            .eq("resource_id", resource_id)
            .execute()
        )

        earned_amount = sum(
            row["amount"]
            for row in reward_response.data
            if row["transaction_type"]
            in ("resource_upload", "request_fulfilled")
            and row["amount"] > 0
        )

        if earned_amount > 0:
            profile_response = (
                admin.table("profiles")
                .select("points")
                .eq("user_id", uploader_id)
                .execute()
            )

            if profile_response.data:
                current_points = profile_response.data[0]["points"]

                # Points cannot go below zero.
                clawback_amount = min(
                    current_points,
                    earned_amount
                )

                (
                    admin.table("profiles")
                    .update({
                        "points": current_points - clawback_amount
                    })
                    .eq("user_id", uploader_id)
                    .execute()
                )

                if clawback_amount > 0:
                    admin.table("point_transactions").insert({
                        "user_id": uploader_id,
                        "amount": -clawback_amount,
                        "transaction_type": "resource_moderation_clawback",
                        "resource_id": resource_id
                    }).execute()

    # Mark reports approved.
    (
        admin.table("resource_reports")
        .update({"status": "approved"})
        .eq("resource_id", resource_id)
        .eq("status", "pending")
        .execute()
    )

    # Remove/hide resource.
    (
        admin.table("resources")
        .update({"moderation_status": "removed"})
        .eq("id", resource_id)
        .execute()
    )

    return {
        "message": "Resource removed and refunds processed.",
        "resource_id": resource_id,
        "refunded_users": refunded_users,
        "total_refunded": total_refunded,
        "uploader_points_clawed_back": clawback_amount
    }


# ---------------------------------------------------------
# Admin: reject reports / restore resource
# ---------------------------------------------------------

@router.post("/admin/resources/{resource_id}/reject-report")
def reject_report(
    resource_id: int,
    current_user=Depends(get_current_user)
):
    require_admin(current_user)

    admin = get_supabase_admin()

    resource_response = (
        admin.table("resources")
        .select("id")
        .eq("id", resource_id)
        .execute()
    )

    if not resource_response.data:
        raise HTTPException(status_code=404, detail="Resource not found.")

    pending_reports = (
        admin.table("resource_reports")
        .select("reporter_id")
        .eq("resource_id", resource_id)
        .eq("status", "pending")
        .execute()
    )

    reporter_ids = {
        row["reporter_id"]
        for row in pending_reports.data
    }

    for reporter_id in reporter_ids:
        profile_response = (
            admin.table("profiles")
            .select("false_report_count")
            .eq("user_id", reporter_id)
            .execute()
        )

        if not profile_response.data:
            continue

        new_false_count = (
            profile_response.data[0].get(
                "false_report_count",
                0
            )
            + 1
        )

        profile_update = {
            "false_report_count": new_false_count
        }

        if new_false_count >= 3:
            profile_update["reporting_restricted"] = True

        (
            admin.table("profiles")
            .update(profile_update)
            .eq("user_id", reporter_id)
            .execute()
        )

    (
        admin.table("resource_reports")
        .update({"status": "rejected"})
        .eq("resource_id", resource_id)
        .eq("status", "pending")
        .execute()
    )

    (
        admin.table("resources")
        .update({"moderation_status": "active"})
        .eq("id", resource_id)
        .execute()
    )

    return {
        "message": "Reports rejected. Resource restored.",
        "resource_id": resource_id
    }