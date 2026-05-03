"""
OAuth authentication routes.
Supports Google, Microsoft (MSAL), and Slack OAuth 2.0 flows.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import create_access_token, create_refresh_token
from app.db.session import get_db
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])

# ── Google OAuth ──────────────────────────────────────────────────────────────

@router.get("/google/login", summary="Initiate Google OAuth flow")
async def google_login(redirect_uri: str | None = Query(None)) -> RedirectResponse:
    """Redirect the user to Google's OAuth consent screen."""
    scopes = " ".join(settings.GOOGLE_SCOPES)
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": scopes,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    return RedirectResponse(url)


@router.get("/google/callback", summary="Google OAuth callback")
async def google_callback(
    code: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Exchange the auth code for tokens and log the user in."""
    # Exchange code for tokens
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
    if token_resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to exchange Google auth code",
        )
    token_data = token_resp.json()

    # Fetch user profile
    async with httpx.AsyncClient() as client:
        userinfo_resp = await client.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {token_data['access_token']}"},
        )
    if userinfo_resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to fetch Google user info",
        )
    userinfo = userinfo_resp.json()

    auth_service = AuthService(db)
    user, _ = await auth_service.get_or_create_user(
        email=userinfo["email"],
        full_name=userinfo.get("name"),
        avatar_url=userinfo.get("picture"),
        provider="google",
        provider_user_id=userinfo["sub"],
    )

    # Compute expiry
    expires_in = token_data.get("expires_in", 3600)
    expires_at = datetime.now(timezone.utc).replace(microsecond=0)
    from datetime import timedelta
    expires_at = expires_at + timedelta(seconds=expires_in)

    await auth_service.upsert_connected_account(
        user_id=user.id,
        provider="google",
        provider_account_id=userinfo["sub"],
        provider_email=userinfo["email"],
        access_token=token_data["access_token"],
        refresh_token=token_data.get("refresh_token"),
        token_expires_at=expires_at,
        scopes=token_data.get("scope"),
    )

    access_token = create_access_token(str(user.id))
    refresh_token = create_refresh_token(str(user.id))

    return JSONResponse({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "avatar_url": user.avatar_url,
        },
    })


# ── Microsoft OAuth ───────────────────────────────────────────────────────────

@router.get("/microsoft/login", summary="Initiate Microsoft OAuth flow")
async def microsoft_login() -> RedirectResponse:
    scopes = " ".join(settings.MICROSOFT_SCOPES)
    params = {
        "client_id": settings.MICROSOFT_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": settings.MICROSOFT_REDIRECT_URI,
        "scope": scopes,
        "response_mode": "query",
    }
    url = (
        f"https://login.microsoftonline.com/{settings.MICROSOFT_TENANT_ID}"
        f"/oauth2/v2.0/authorize?" + urlencode(params)
    )
    return RedirectResponse(url)


@router.get("/microsoft/callback", summary="Microsoft OAuth callback")
async def microsoft_callback(
    code: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            f"https://login.microsoftonline.com/{settings.MICROSOFT_TENANT_ID}/oauth2/v2.0/token",
            data={
                "client_id": settings.MICROSOFT_CLIENT_ID,
                "client_secret": settings.MICROSOFT_CLIENT_SECRET,
                "code": code,
                "redirect_uri": settings.MICROSOFT_REDIRECT_URI,
                "grant_type": "authorization_code",
                "scope": " ".join(settings.MICROSOFT_SCOPES),
            },
        )
    if token_resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Microsoft token exchange failed")
    token_data = token_resp.json()

    # Fetch Microsoft Graph profile
    async with httpx.AsyncClient() as client:
        profile_resp = await client.get(
            "https://graph.microsoft.com/v1.0/me",
            headers={"Authorization": f"Bearer {token_data['access_token']}"},
        )
    profile = profile_resp.json()
    email = profile.get("mail") or profile.get("userPrincipalName", "")
    full_name = profile.get("displayName")
    ms_user_id = profile.get("id", "")

    auth_service = AuthService(db)
    user, _ = await auth_service.get_or_create_user(
        email=email,
        full_name=full_name,
        avatar_url=None,
        provider="microsoft",
        provider_user_id=ms_user_id,
    )

    expires_in = token_data.get("expires_in", 3600)
    from datetime import timedelta
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    await auth_service.upsert_connected_account(
        user_id=user.id,
        provider="microsoft",
        provider_account_id=ms_user_id,
        provider_email=email,
        access_token=token_data["access_token"],
        refresh_token=token_data.get("refresh_token"),
        token_expires_at=expires_at,
        scopes=token_data.get("scope"),
    )

    access_token = create_access_token(str(user.id))
    refresh_token = create_refresh_token(str(user.id))

    return JSONResponse({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "email": email,
            "full_name": full_name,
            "avatar_url": None,
        },
    })


# ── Slack OAuth ───────────────────────────────────────────────────────────────

@router.get("/slack/login", summary="Initiate Slack OAuth flow")
async def slack_login() -> RedirectResponse:
    params = {
        "client_id": settings.SLACK_CLIENT_ID,
        "scope": settings.SLACK_SCOPES,
        "redirect_uri": settings.SLACK_REDIRECT_URI,
    }
    url = "https://slack.com/oauth/v2/authorize?" + urlencode(params)
    return RedirectResponse(url)


@router.get("/slack/callback", summary="Slack OAuth callback")
async def slack_callback(
    code: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://slack.com/api/oauth.v2.access",
            data={
                "client_id": settings.SLACK_CLIENT_ID,
                "client_secret": settings.SLACK_CLIENT_SECRET,
                "code": code,
                "redirect_uri": settings.SLACK_REDIRECT_URI,
            },
        )
    data = token_resp.json()
    if not data.get("ok"):
        raise HTTPException(status_code=400, detail=f"Slack OAuth failed: {data.get('error')}")

    authed_user = data.get("authed_user", {})
    slack_user_id = authed_user.get("id", "")
    access_token = authed_user.get("access_token") or data.get("access_token", "")

    # Fetch Slack user profile
    async with httpx.AsyncClient() as client:
        profile_resp = await client.get(
            "https://slack.com/api/users.info",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"user": slack_user_id},
        )
    profile_data = profile_resp.json()
    slack_profile = profile_data.get("user", {}).get("profile", {})
    email = slack_profile.get("email", f"{slack_user_id}@slack.local")
    full_name = slack_profile.get("real_name")
    avatar_url = slack_profile.get("image_192")

    auth_service = AuthService(db)
    user, _ = await auth_service.get_or_create_user(
        email=email,
        full_name=full_name,
        avatar_url=avatar_url,
        provider="slack",
        provider_user_id=slack_user_id,
    )

    await auth_service.upsert_connected_account(
        user_id=user.id,
        provider="slack",
        provider_account_id=slack_user_id,
        provider_email=email,
        access_token=access_token,
        refresh_token=None,
        token_expires_at=None,
        scopes=authed_user.get("scope") or settings.SLACK_SCOPES,
    )

    app_access_token = create_access_token(str(user.id))
    refresh_token = create_refresh_token(str(user.id))

    return JSONResponse({
        "access_token": app_access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "email": email,
            "full_name": full_name,
            "avatar_url": avatar_url,
        },
    })


# ── Me endpoint ───────────────────────────────────────────────────────────────

@router.get("/me", summary="Get current user profile")
async def get_me(
    db: AsyncSession = Depends(get_db),
    current_user_id: uuid.UUID = Depends(
        __import__("app.dependencies", fromlist=["get_current_user_id"]).get_current_user_id
    ),
) -> JSONResponse:
    auth_service = AuthService(db)
    user = await auth_service.get_user_by_id(current_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    accounts = await auth_service.list_connected_accounts(current_user_id)
    return JSONResponse({
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "avatar_url": user.avatar_url,
        "connected_providers": [a.provider for a in accounts],
    })
