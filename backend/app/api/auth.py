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
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import create_access_token, create_refresh_token
from app.db.session import get_db
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])

# ── Google OAuth ──────────────────────────────────────────────────────────────

@router.get("/google/login", summary="Initiate Google OAuth flow")
async def google_login(
    redirect_uri: str | None = Query(None),
    integration: bool = Query(False),
    link_token: str | None = Query(None),
) -> RedirectResponse:
    """Redirect the user to Google's OAuth consent screen."""
    scopes = settings.GOOGLE_SCOPES.copy()
    if integration or link_token:
        scopes.extend([
            "https://www.googleapis.com/auth/gmail.modify",
            "https://www.googleapis.com/auth/calendar",
        ])

    # Build state: carry link_token so the callback can attach to the existing user
    state_parts = []
    if integration:
        state_parts.append("integration=true")
    if link_token:
        state_parts.append(f"link_token={link_token}")

    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(scopes),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
    }
    if state_parts:
        params["state"] = "&".join(state_parts)

    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    return RedirectResponse(url)


@router.get("/google/callback", summary="Google OAuth callback")
async def google_callback(
    code: str = Query(...),
    state: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Exchange the auth code for tokens and log the user in."""
    import traceback
    import json
    from urllib.parse import urlencode, quote
    from datetime import timedelta

    try:
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
            error_detail = token_resp.text
            return RedirectResponse(
                f"http://localhost:3000/login?error=google_token_failed&detail={quote(error_detail[:200])}"
            )
        token_data = token_resp.json()

        # Fetch user profile
        async with httpx.AsyncClient() as client:
            userinfo_resp = await client.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {token_data['access_token']}"},
            )
        if userinfo_resp.status_code != 200:
            return RedirectResponse(
                f"http://localhost:3000/login?error=google_userinfo_failed"
            )
        userinfo = userinfo_resp.json()

        # Parse state to detect link_token (linking to existing user)
        state_params: dict[str, str] = {}
        if state:
            for part in state.split("&"):
                if "=" in part:
                    k, v = part.split("=", 1)
                    state_params[k] = v
        link_token = state_params.get("link_token")

        auth_service = AuthService(db)
        expires_in = token_data.get("expires_in", 3600)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        if link_token:
            # ── Link-to-existing-user flow ────────────────────────────────────
            # Attach Google account to the already-logged-in user; don't replace tokens.
            from app.core.security import decode_token
            from jose import JWTError
            try:
                payload = decode_token(link_token)
                user_id = uuid.UUID(payload["sub"])
            except (JWTError, KeyError, ValueError):
                return RedirectResponse("http://localhost:3000/settings?error=invalid_link_token")

            await auth_service.upsert_connected_account(
                user_id=user_id,
                provider="google",
                provider_account_id=userinfo["sub"],
                provider_email=userinfo["email"],
                access_token=token_data["access_token"],
                refresh_token=token_data.get("refresh_token"),
                token_expires_at=expires_at,
                scopes=token_data.get("scope"),
            )
            await db.commit()
            return RedirectResponse("http://localhost:3000/settings?linked=google")

        # ── Normal login flow ─────────────────────────────────────────────────
        user, _ = await auth_service.get_or_create_user(
            email=userinfo["email"],
            full_name=userinfo.get("name"),
            avatar_url=userinfo.get("picture"),
            provider="google",
            provider_user_id=userinfo["sub"],
        )
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
        user_json = quote(json.dumps({
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "avatar_url": user.avatar_url,
            "connected_providers": ["google"],
        }))
        params = urlencode({"access_token": access_token, "refresh_token": refresh_token})
        return RedirectResponse(f"http://localhost:3000/login?{params}&user={user_json}")

    except Exception as exc:
        tb = traceback.format_exc()
        import logging
        logging.getLogger(__name__).error("Google OAuth callback failed:\n%s", tb)
        return RedirectResponse(
            f"http://localhost:3000/login?error=server&detail={quote(str(exc)[:300])}"
        )


# ── Microsoft OAuth ───────────────────────────────────────────────────────────

@router.get("/microsoft/login", summary="Initiate Microsoft OAuth flow")
async def microsoft_login(
    link_token: str | None = Query(None),
) -> RedirectResponse:
    scopes = " ".join(settings.MICROSOFT_SCOPES)
    params: dict[str, str] = {
        "client_id": settings.MICROSOFT_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": settings.MICROSOFT_REDIRECT_URI,
        "scope": scopes,
        "response_mode": "query",
    }
    if link_token:
        params["state"] = link_token
    url = (
        f"https://login.microsoftonline.com/{settings.MICROSOFT_TENANT_ID}"
        f"/oauth2/v2.0/authorize?" + urlencode(params)
    )
    return RedirectResponse(url)


@router.get("/microsoft/callback", summary="Microsoft OAuth callback")
async def microsoft_callback(
    code: str = Query(...),
    state: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
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

    from datetime import timedelta
    from urllib.parse import urlencode, quote
    import json

    auth_service = AuthService(db)
    expires_in = token_data.get("expires_in", 3600)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    # state carries link_token when linking from settings page
    link_token = state if state else None
    if link_token:
        from app.core.security import decode_token
        from jose import JWTError
        try:
            payload = decode_token(link_token)
            user_id = uuid.UUID(payload["sub"])
        except (JWTError, KeyError, ValueError):
            return RedirectResponse("http://localhost:3000/settings?error=invalid_link_token")

        await auth_service.upsert_connected_account(
            user_id=user_id,
            provider="microsoft",
            provider_account_id=ms_user_id,
            provider_email=email,
            access_token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token"),
            token_expires_at=expires_at,
            scopes=token_data.get("scope"),
        )
        await db.commit()
        return RedirectResponse("http://localhost:3000/settings?linked=microsoft")

    # Normal login flow
    user, _ = await auth_service.get_or_create_user(
        email=email, full_name=full_name, avatar_url=None,
        provider="microsoft", provider_user_id=ms_user_id,
    )
    await auth_service.upsert_connected_account(
        user_id=user.id, provider="microsoft", provider_account_id=ms_user_id,
        provider_email=email, access_token=token_data["access_token"],
        refresh_token=token_data.get("refresh_token"),
        token_expires_at=expires_at, scopes=token_data.get("scope"),
    )
    access_token = create_access_token(str(user.id))
    refresh_token = create_refresh_token(str(user.id))
    user_json = quote(json.dumps({
        "id": str(user.id), "email": email, "full_name": full_name,
        "avatar_url": None, "connected_providers": ["microsoft"],
    }))
    params = urlencode({"access_token": access_token, "refresh_token": refresh_token})
    return RedirectResponse(f"http://localhost:3000/login?{params}&user={user_json}")


# ── Slack OAuth ───────────────────────────────────────────────────────────────

@router.get("/slack/login", summary="Initiate Slack OAuth flow")
async def slack_login(
    link_token: str | None = Query(None),
) -> RedirectResponse:
    params: dict[str, str] = {
        "client_id": settings.SLACK_CLIENT_ID,
        "scope": settings.SLACK_SCOPES,
        "redirect_uri": settings.SLACK_REDIRECT_URI,
    }
    if link_token:
        params["state"] = link_token
    url = "https://slack.com/oauth/v2/authorize?" + urlencode(params)
    return RedirectResponse(url)


@router.get("/slack/callback", summary="Slack OAuth callback")
async def slack_callback(
    code: str = Query(...),
    state: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
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
    # Use the BOT token (xoxb-) for posting messages — NOT the user token (xoxp-)
    # The bot token is at data["access_token"]; user token is at authed_user["access_token"]
    bot_token = data.get("access_token", "")
    bot_user_id = data.get("bot_user_id", "")

    # Fetch Slack user profile using the user token (for profile info only)
    user_token = authed_user.get("access_token") or bot_token
    async with httpx.AsyncClient() as client:
        profile_resp = await client.get(
            "https://slack.com/api/users.info",
            headers={"Authorization": f"Bearer {user_token}"},
            params={"user": slack_user_id},
        )
    profile_data = profile_resp.json()
    slack_profile = profile_data.get("user", {}).get("profile", {})
    email = slack_profile.get("email", f"{slack_user_id}@slack.local")
    full_name = slack_profile.get("real_name")
    avatar_url = slack_profile.get("image_192")

    from urllib.parse import urlencode, quote
    import json

    auth_service = AuthService(db)
    link_token = state if state else None

    if link_token:
        from app.core.security import decode_token
        from jose import JWTError
        try:
            payload = decode_token(link_token)
            user_id = uuid.UUID(payload["sub"])
        except (JWTError, KeyError, ValueError):
            return RedirectResponse("http://localhost:3000/settings?error=invalid_link_token")

        await auth_service.upsert_connected_account(
            user_id=user_id, provider="slack",
            provider_account_id=slack_user_id, provider_email=email,
            access_token=bot_token, refresh_token=None,
            token_expires_at=None, scopes=data.get("scope") or settings.SLACK_SCOPES,
        )
        await db.commit()
        return RedirectResponse("http://localhost:3000/settings?linked=slack")

    # Normal login flow
    user, _ = await auth_service.get_or_create_user(
        email=email, full_name=full_name, avatar_url=avatar_url,
        provider="slack", provider_user_id=slack_user_id,
    )
    await auth_service.upsert_connected_account(
        user_id=user.id, provider="slack", provider_account_id=slack_user_id,
        provider_email=email, access_token=bot_token, refresh_token=None,
        token_expires_at=None, scopes=data.get("scope") or settings.SLACK_SCOPES,
    )
    app_access_token = create_access_token(str(user.id))
    refresh_token = create_refresh_token(str(user.id))
    user_json = quote(json.dumps({
        "id": str(user.id), "email": email, "full_name": full_name,
        "avatar_url": avatar_url, "connected_providers": ["slack"],
    }))
    params = urlencode({"access_token": app_access_token, "refresh_token": refresh_token})
    return RedirectResponse(f"http://localhost:3000/login?{params}&user={user_json}")


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


# ── Token refresh endpoint ────────────────────────────────────────────────────

class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/refresh", summary="Refresh access token using a refresh token")
async def refresh_access_token(body: RefreshRequest) -> JSONResponse:
    """
    Accepts a valid refresh token and returns a new access + refresh token pair.
    The old refresh token is invalidated implicitly (short-lived rotation).
    """
    from jose import JWTError
    try:
        payload = __import__("app.core.security", fromlist=["decode_token"]).decode_token(body.refresh_token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is not a refresh token",
        )

    user_id: str | None = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject")

    new_access_token = create_access_token(user_id)
    new_refresh_token = create_refresh_token(user_id)

    return JSONResponse({
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
    })


@router.post("/logout", summary="Invalidate session (client-side token removal)")
async def logout() -> JSONResponse:
    """
    Stateless JWT logout — instructs the client to discard its tokens.
    For true server-side invalidation, implement a Redis token blacklist.
    """
    return JSONResponse({"detail": "Logged out successfully"})
