from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import httpx
from jwt import PyJWKClient
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import User, UserRole

bearer = HTTPBearer(auto_error=False)


def issue_demo_token(user: User, role: str) -> str:
    return jwt.encode(
        {"sub": str(user.id), "role": role, "demo": True, "exp": datetime.now(timezone.utc) + timedelta(hours=12)},
        settings.demo_auth_secret,
        algorithm="HS256",
    )


def issue_access_code_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": str(user.id), "email": user.email, "name": user.display_name,
         "role": "farmer", "iss": "terravanta-access-code", "aud": "terravanta-api",
         "iat": now, "exp": now + timedelta(hours=12)},
        settings.demo_auth_secret,
        algorithm="HS256",
    )


def verified_supabase_user(access_token: str, expected_user_id: UUID) -> dict:
    """Load the provider's current identity before creating a Terravanta account."""
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise HTTPException(status_code=503, detail="Supabase account verification is not configured")
    try:
        response = httpx.get(
            f"{settings.supabase_url.rstrip('/')}/auth/v1/user",
            headers={"apikey": settings.supabase_anon_key, "Authorization": f"Bearer {access_token}"},
            timeout=5,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Supabase account verification is temporarily unavailable") from exc

    if response.status_code in {401, 403}:
        raise HTTPException(status_code=401, detail="Supabase session is invalid or expired")
    if response.status_code != 200:
        raise HTTPException(status_code=503, detail="Supabase account verification is temporarily unavailable")
    try:
        user = response.json()
        provider_user_id = UUID(user["id"])
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=503, detail="Supabase returned an invalid account profile") from exc
    if provider_user_id != expected_user_id:
        raise HTTPException(status_code=401, detail="Supabase session identity does not match the account")
    if not (user.get("email_confirmed_at") or user.get("confirmed_at")):
        raise HTTPException(status_code=403, detail="Confirm your email address before creating a Terravanta account")
    if not user.get("email"):
        raise HTTPException(status_code=422, detail="A verified email address is required to create a Terravanta account")
    return user


def current_identity(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> dict:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Sign in to continue")
    token = credentials.credentials
    if settings.temp_access_auth_enabled:
        try:
            return jwt.decode(
                token, settings.demo_auth_secret, algorithms=["HS256"],
                issuer="terravanta-access-code", audience="terravanta-api",
            )
        except Exception:
            if not settings.supabase_url:
                raise HTTPException(status_code=401, detail="Invalid or expired access code session")
    if settings.supabase_url:
        try:
            header = jwt.get_unverified_header(token)
            algorithm = header.get("alg")
            if algorithm not in {"ES256", "RS256", "EdDSA"}:
                raise ValueError("Unsupported Supabase signing algorithm")
            key = PyJWKClient(settings.effective_supabase_jwks_url, timeout=5).get_signing_key_from_jwt(token).key
            return jwt.decode(
                token,
                key,
                algorithms=[algorithm],
                audience="authenticated",
                issuer=f"{settings.supabase_url.rstrip('/')}/auth/v1",
            )
        except Exception as jwks_error:
            if settings.supabase_anon_key:
                try:
                    response = httpx.get(
                        f"{settings.supabase_url.rstrip('/')}/auth/v1/user",
                        headers={"apikey": settings.supabase_anon_key, "Authorization": f"Bearer {token}"},
                        timeout=5,
                    )
                    if response.status_code == 200:
                        supabase_user = response.json()
                        return {
                            "sub": supabase_user["id"],
                            "email": supabase_user.get("email"),
                            "user_metadata": supabase_user.get("user_metadata") or {},
                            "demo": False,
                        }
                except (httpx.HTTPError, KeyError, ValueError):
                    pass
            if settings.app_env == "production" or not settings.enable_synthetic_data:
                raise HTTPException(status_code=401, detail="Invalid or expired access token") from jwks_error

    if settings.app_env == "production" or not settings.enable_synthetic_data:
        raise HTTPException(status_code=503, detail="Configure Supabase Auth before real account access")
    try:
        return jwt.decode(token, settings.demo_auth_secret, algorithms=["HS256"])
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired access token") from exc


def current_user(
    identity: dict = Depends(current_identity),
    db: Session = Depends(get_db),
) -> User:
    try:
        user_id = UUID(identity["sub"])
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=401, detail="Invalid account identity") from exc
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Account is not onboarded in Terravanta")
    return user


def user_roles(db: Session, user: User) -> set[str]:
    return {row.role for row in db.query(UserRole.role).filter(UserRole.user_id == user.id).all()}


def user_role(db: Session, user: User) -> str:
    roles = user_roles(db, user)
    for role in ("platform_admin", "farmer", "veterinarian", "cooperative_admin"):
        if role in roles:
            return role
    return "unassigned"


def require_role(db: Session, user: User, *roles: str) -> str:
    assigned = user_roles(db, user)
    if not assigned.intersection(roles):
        raise HTTPException(status_code=403, detail="This action is not permitted for your role")
    return next(role for role in roles if role in assigned)
