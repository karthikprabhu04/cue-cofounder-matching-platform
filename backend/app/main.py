import html
import os
import secrets
import smtplib
from email.message import EmailMessage
from typing import Annotated

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from .database import (
    COMMITMENT_LEVELS,
    LOOKING_FOR_OPTIONS,
    ROOT_DIR,
    SKILLS,
    UPLOADS_DIR,
    compute_match_score,
    contact_unlocked,
    create_connect_request,
    create_otp,
    create_session,
    delete_session,
    get_all_profiles,
    get_connect_request,
    get_or_create_user,
    get_profile,
    get_request_between_users,
    get_usage_count,
    get_user_by_token,
    increment_usage,
    init_db,
    list_accepted_connections,
    list_connect_requests,
    seed_demo_data,
    update_profile_photo_path,
    update_request_status,
    upsert_profile,
    validate_email,
    validate_profile_payload,
    consume_otp,
)
from .schemas import ConnectRequestCreate, ConnectRequestRespond, EmailRequest, OtpVerifyRequest, ProfileUpsertRequest


FRONTEND_DIR = ROOT_DIR / "frontend"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
load_dotenv(ROOT_DIR / ".env")

PROFILE_VIEW_LIMIT = 25
CONNECT_REQUEST_LIMIT = 10
MAX_UPLOAD_SIZE = 4 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}

app = FastAPI(title="Cambridge Co-founder Platform", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/app", StaticFiles(directory=FRONTEND_DIR), name="frontend")
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")


@app.on_event("startup")
def startup() -> None:
    init_db()
    seed_demo_data()


def smtp_settings() -> dict[str, str | int | bool]:
    return {
        "host": os.getenv("SMTP_HOST", "").strip(),
        "port": int(os.getenv("SMTP_PORT", "587")),
        "username": os.getenv("SMTP_USERNAME", "").strip(),
        "password": os.getenv("SMTP_PASSWORD", "").strip(),
        "from_email": os.getenv("SMTP_FROM_EMAIL", "").strip(),
        "from_name": os.getenv("SMTP_FROM_NAME", "Cambridge Co-founder Platform").strip(),
        "use_tls": os.getenv("SMTP_USE_TLS", "true").strip().lower() != "false",
        "dev_mode": os.getenv("OTP_DEV_MODE", "true").strip().lower() != "false",
    }


def otp_email_enabled() -> bool:
    settings = smtp_settings()
    return all(
        [
            settings["host"],
            settings["username"],
            settings["password"],
            settings["from_email"],
        ]
    )


def send_otp_email(email: str, code: str) -> None:
    settings = smtp_settings()
    if not otp_email_enabled():
        raise RuntimeError("SMTP is not configured")

    message = EmailMessage()
    message["Subject"] = f"{code} is your Cambridge Co-founder Platform sign-in code"
    message["From"] = f"{settings['from_name']} <{settings['from_email']}>"
    message["To"] = email
    message.set_content(
        "\n".join(
            [
                "Your Cambridge Co-founder Platform sign-in code is:",
                "",
                code,
                "",
                "It expires in 10 minutes.",
                "If you did not request this, you can ignore this email.",
            ]
        )
    )

    with smtplib.SMTP(str(settings["host"]), int(settings["port"])) as server:
        if settings["use_tls"]:
            server.starttls()
        server.login(str(settings["username"]), str(settings["password"]))
        server.send_message(message)


def serialize_user(user: dict, profile: dict | None) -> dict:
    return {
        "id": user["id"],
        "email": user["email"],
        "is_demo": bool(user["is_demo"]),
        "profile_complete": bool(profile),
        "profile": profile,
    }


def get_bearer_token(authorization: Annotated[str | None, Header()] = None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return authorization.replace("Bearer ", "", 1).strip()


def current_user(token: Annotated[str, Depends(get_bearer_token)]) -> dict:
    user = get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    user["token"] = token
    return user


def require_profile(user: dict) -> dict:
    profile = get_profile(user["id"])
    if not profile:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Complete your profile first")
    return profile


def usage_snapshot(user_id: int, is_demo: bool = False) -> dict:
    return {
        "profile_views_remaining": max(0, PROFILE_VIEW_LIMIT - get_usage_count(user_id, "profile_view")),
        "connect_requests_remaining": 0 if is_demo else max(0, CONNECT_REQUEST_LIMIT - get_usage_count(user_id, "connect_request")),
    }


def ensure_can_edit_profile(user: dict) -> None:
    if user["is_demo"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Demo profile is read-only")


def profile_summary(candidate: dict, score: int, reasons: list[str]) -> dict:
    return {
        "user_id": candidate["user_id"],
        "name": f"{candidate['first_name']} {candidate['last_name']}",
        "college": candidate["college"],
        "course": candidate["course"],
        "year": candidate["year"],
        "what_have_you_built": candidate["what_have_you_built"],
        "skills": candidate["skills"],
        "commitment_level": candidate["commitment_level"],
        "avatar_url": candidate["avatar_url"],
        "score": score,
        "match_reasons": reasons[:3],
        "is_demo_profile": bool(candidate.get("is_demo")),
    }


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "skills": sorted(SKILLS),
        "commitment_levels": sorted(COMMITMENT_LEVELS),
        "looking_for_options": sorted(LOOKING_FOR_OPTIONS),
        "otp_email_enabled": otp_email_enabled(),
    }


@app.get("/api/avatars/default/{user_id}")
def default_avatar(user_id: int, initials: str = "C") -> Response:
    trimmed = "".join(ch for ch in initials.upper() if ch.isalpha())[:2] or "C"
    palette = [
        ("#153b33", "#dbe9e5"),
        ("#473322", "#efe2d2"),
        ("#2f3c2c", "#dfe8d9"),
        ("#3b2630", "#f0dde5"),
    ]
    bg, fg = palette[user_id % len(palette)]
    svg = f"""
    <svg xmlns="http://www.w3.org/2000/svg" width="240" height="240" viewBox="0 0 240 240" role="img" aria-label="{html.escape(trimmed)}">
      <rect width="240" height="240" rx="24" fill="{bg}" />
      <text x="50%" y="55%" dominant-baseline="middle" text-anchor="middle"
            font-family="Inter, Arial, sans-serif" font-size="92" font-weight="700" fill="{fg}">
        {html.escape(trimmed)}
      </text>
    </svg>
    """.strip()
    return Response(content=svg, media_type="image/svg+xml")


@app.post("/api/auth/request-otp")
def request_otp(payload: EmailRequest) -> dict:
    try:
        email = validate_email(payload.email)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    code = create_otp(email)
    settings = smtp_settings()

    if otp_email_enabled():
        try:
            send_otp_email(email, code)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to send OTP email: {exc}") from exc
        return {
            "message": f"OTP sent to {email}",
            "email": email,
            "delivery_mode": "email",
        }

    if settings["dev_mode"]:
        return {
            "message": "OTP generated for local MVP mode",
            "dev_code": code,
            "email": email,
            "delivery_mode": "dev",
        }

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="SMTP is not configured. Set SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, and SMTP_FROM_EMAIL.",
    )


@app.post("/api/auth/verify-otp")
def verify_otp(payload: OtpVerifyRequest) -> dict:
    try:
        email = validate_email(payload.email)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if not consume_otp(email, payload.code.strip()):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired OTP")

    user = get_or_create_user(email)
    token = create_session(user["id"])
    profile = get_profile(user["id"])
    return {"token": token, "user": serialize_user(user, profile), "limits": usage_snapshot(user["id"], bool(user["is_demo"]))}


@app.post("/api/auth/demo-login")
def demo_login() -> dict:
    user = get_or_create_user("demo@cambridgecofounder.local", is_demo=True)
    token = create_session(user["id"])
    profile = get_profile(user["id"])
    return {
        "token": token,
        "user": serialize_user(user, profile),
        "limits": usage_snapshot(user["id"], True),
        "demo_notice": "Demo users can browse but cannot send real requests or unlock contact details.",
    }


@app.post("/api/auth/logout")
def logout(user: Annotated[dict, Depends(current_user)]) -> dict:
    delete_session(user["token"])
    return {"ok": True}


@app.get("/api/me")
def me(user: Annotated[dict, Depends(current_user)]) -> dict:
    profile = get_profile(user["id"])
    return {"user": serialize_user(user, profile), "limits": usage_snapshot(user["id"], bool(user["is_demo"]))}


@app.put("/api/me/profile")
def save_profile(payload: ProfileUpsertRequest, user: Annotated[dict, Depends(current_user)]) -> dict:
    ensure_can_edit_profile(user)

    try:
        cleaned = validate_profile_payload(payload.model_dump(), user["email"])
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    profile = upsert_profile(user["id"], cleaned)
    return {"profile": profile, "user": serialize_user(user, profile)}


@app.post("/api/me/profile-photo")
async def upload_profile_photo(
    user: Annotated[dict, Depends(current_user)],
    photo: UploadFile = File(...),
) -> dict:
    ensure_can_edit_profile(user)
    profile = require_profile(user)

    if photo.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Upload a JPG, PNG, or WebP image")

    content = await photo.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty")
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Image must be 4MB or smaller")

    extension = ALLOWED_IMAGE_TYPES[photo.content_type]
    safe_name = f"user-{user['id']}-{secrets.token_hex(8)}{extension}"
    target_path = UPLOADS_DIR / safe_name
    target_path.write_bytes(content)

    updated_profile = update_profile_photo_path(profile["user_id"], safe_name)
    return {"profile": updated_profile, "user": serialize_user(user, updated_profile)}


@app.get("/api/feed")
def feed(user: Annotated[dict, Depends(current_user)]) -> dict:
    viewer_profile = require_profile(user)
    candidates = get_all_profiles(exclude_user_id=user["id"])
    ranked: list[dict] = []
    for candidate in candidates:
        score, reasons = compute_match_score(viewer_profile, candidate)
        ranked.append(profile_summary(candidate, score, reasons))

    ranked.sort(key=lambda item: (-item["score"], item["name"]))
    return {"items": ranked, "limits": usage_snapshot(user["id"], bool(user["is_demo"]))}


@app.get("/api/profiles/{target_user_id}")
def profile_detail(target_user_id: int, user: Annotated[dict, Depends(current_user)]) -> dict:
    viewer_profile = require_profile(user)
    all_profiles = {profile["user_id"]: profile for profile in get_all_profiles()}
    target_profile = all_profiles.get(target_user_id)

    if not target_profile:
        if target_user_id == user["id"]:
            target_profile = get_profile(user["id"])
        if not target_profile:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")

    if target_user_id != user["id"]:
        count = get_usage_count(user["id"], "profile_view")
        if count >= PROFILE_VIEW_LIMIT:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Daily profile view limit reached")
        increment_usage(user["id"], "profile_view")

    unlocked = False if user["is_demo"] else contact_unlocked(user["id"], target_user_id)
    score, reasons = compute_match_score(viewer_profile, target_profile)
    detail = {
        "user_id": target_profile["user_id"],
        "full_name": f"{target_profile['first_name']} {target_profile['last_name']}",
        "college": target_profile["college"],
        "course": target_profile["course"],
        "year": target_profile["year"],
        "what_have_you_built": target_profile["what_have_you_built"],
        "skills": target_profile["skills"],
        "commitment_level": target_profile["commitment_level"],
        "looking_for": target_profile["looking_for"],
        "avatar_url": target_profile["avatar_url"],
        "linkedin_url": target_profile["linkedin_url"] if unlocked else None,
        "cam_email": target_profile["cam_email"] if unlocked else None,
        "contact_unlocked": unlocked,
        "is_demo_profile": bool(target_profile.get("is_demo")),
        "match_reasons": reasons[:3],
        "match_score": score,
    }
    return {"profile": detail, "limits": usage_snapshot(user["id"], bool(user["is_demo"]))}


@app.get("/api/requests")
def requests_overview(user: Annotated[dict, Depends(current_user)]) -> dict:
    require_profile(user)
    return {"requests": list_connect_requests(user["id"]), "limits": usage_snapshot(user["id"], bool(user["is_demo"]))}


@app.post("/api/requests")
def send_connect_request(payload: ConnectRequestCreate, user: Annotated[dict, Depends(current_user)]) -> dict:
    if user["is_demo"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Demo users cannot send requests")

    require_profile(user)
    target_profile = get_profile(payload.recipient_user_id)
    if not target_profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipient not found")
    if payload.recipient_user_id == user["id"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot connect with yourself")

    count = get_usage_count(user["id"], "connect_request")
    if count >= CONNECT_REQUEST_LIMIT:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Daily connect request limit reached")

    message = payload.message.strip()
    if len(message) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message must be at least 8 characters")

    existing = get_request_between_users(user["id"], payload.recipient_user_id)
    if existing and existing["status"] == "pending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A pending request already exists")
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You have already contacted this user")

    created = create_connect_request(user["id"], payload.recipient_user_id, message)
    increment_usage(user["id"], "connect_request")
    return {"request": created, "limits": usage_snapshot(user["id"], bool(user["is_demo"]))}


@app.post("/api/requests/{request_id}/respond")
def respond_to_request(
    request_id: int,
    payload: ConnectRequestRespond,
    user: Annotated[dict, Depends(current_user)],
) -> dict:
    if user["is_demo"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Demo users cannot respond to requests")

    require_profile(user)
    request = get_connect_request(request_id)
    if not request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    if request["recipient_user_id"] != user["id"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the recipient can respond")
    if request["status"] != "pending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Request has already been handled")

    updated = update_request_status(request_id, payload.status)
    return {"request": updated}


@app.get("/api/connections")
def accepted_connections(user: Annotated[dict, Depends(current_user)]) -> dict:
    require_profile(user)
    items = list_accepted_connections(user["id"])
    if user["is_demo"]:
        for item in items:
            item["counterparty"]["linkedin_url"] = None
            item["counterparty"]["cam_email"] = None
    return {"items": items}


@app.get("/")
def landing() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/{full_path:path}")
def spa_fallback(full_path: str) -> FileResponse:
    if full_path.startswith("api/") or full_path.startswith("app/") or full_path.startswith("uploads/"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return FileResponse(FRONTEND_DIR / "index.html")
