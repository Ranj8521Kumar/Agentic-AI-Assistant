"""
Integrations management routes.
Lists connected accounts and handles OAuth callback for additional providers (Jira, Notion).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import get_current_user_id
from app.services.auth_service import AuthService

router = APIRouter(prefix="/integrations", tags=["Integrations"])


@router.get("", summary="List all connected integrations for the current user")
async def list_integrations(
    db: AsyncSession = Depends(get_db),
    current_user_id: uuid.UUID = Depends(get_current_user_id),
) -> JSONResponse:
    auth_service = AuthService(db)
    accounts = await auth_service.list_connected_accounts(current_user_id)
    return JSONResponse([
        {
            "provider": a.provider,
            "provider_email": a.provider_email,
            "connected_at": a.created_at.isoformat(),
            "scopes": a.scopes,
        }
        for a in accounts
    ])


@router.delete("/{provider}", summary="Disconnect an integration")
async def disconnect_integration(
    provider: str,
    db: AsyncSession = Depends(get_db),
    current_user_id: uuid.UUID = Depends(get_current_user_id),
) -> JSONResponse:
    from sqlalchemy import delete
    from app.models.connected_account import ConnectedAccount
    from app.services.audit_service import AuditService

    result = await db.execute(
        delete(ConnectedAccount).where(
            ConnectedAccount.user_id == current_user_id,
            ConnectedAccount.provider == provider,
        ).returning(ConnectedAccount.id)
    )
    deleted = result.fetchone()
    if not deleted:
        raise HTTPException(status_code=404, detail=f"No connected {provider} account found")

    audit = AuditService(db)
    await audit.log(
        action=f"integrations.disconnect.{provider}",
        user_id=current_user_id,
    )
    await db.commit()
    return JSONResponse({"disconnected": provider})


@router.get("/jira/connect", summary="Connect Jira via API token")
async def jira_connect(
    api_token: str,
    email: str,
    db: AsyncSession = Depends(get_db),
    current_user_id: uuid.UUID = Depends(get_current_user_id),
) -> JSONResponse:
    """
    Jira uses basic auth (email + API token), not OAuth.
    The user provides their Atlassian API token from the UI.
    """
    auth_service = AuthService(db)
    await auth_service.upsert_connected_account(
        user_id=current_user_id,
        provider="jira",
        provider_account_id=email,
        provider_email=email,
        access_token=f"{email}:{api_token}",  # combined for basic auth in tool
        refresh_token=None,
        token_expires_at=None,
        scopes="read:jira-work write:jira-work",
    )
    await db.commit()
    return JSONResponse({"connected": "jira", "email": email})


@router.get("/notion/connect", summary="Connect Notion via integration token")
async def notion_connect(
    token: str,
    db: AsyncSession = Depends(get_db),
    current_user_id: uuid.UUID = Depends(get_current_user_id),
) -> JSONResponse:
    """
    Notion uses a static integration token from the user's Notion workspace settings.
    """
    auth_service = AuthService(db)
    await auth_service.upsert_connected_account(
        user_id=current_user_id,
        provider="notion",
        provider_account_id="notion",
        provider_email=None,
        access_token=token,
        refresh_token=None,
        token_expires_at=None,
        scopes="read write",
    )
    await db.commit()
    return JSONResponse({"connected": "notion"})
