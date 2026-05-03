"""
Auth service — handles user lookup/creation and OAuth account linking.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember, WorkspaceRole
from app.models.connected_account import ConnectedAccount
from app.services.token_vault import token_vault


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_user_by_email(self, email: str) -> User | None:
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_user_by_id(self, user_id: uuid.UUID) -> User | None:
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_or_create_user(
        self,
        email: str,
        full_name: str | None,
        avatar_url: str | None,
        provider: str,
        provider_user_id: str,
    ) -> tuple[User, bool]:
        """
        Retrieve an existing user or create a new one from OAuth data.
        Returns (user, created) tuple.
        """
        user = await self.get_user_by_email(email)
        if user:
            # Update profile info from OAuth provider
            user.full_name = full_name or user.full_name
            user.avatar_url = avatar_url or user.avatar_url
            user.is_verified = True
            self.db.add(user)
            return user, False

        # Create new user
        user = User(
            email=email,
            full_name=full_name,
            avatar_url=avatar_url,
            primary_provider=provider,
            provider_user_id=provider_user_id,
            is_active=True,
            is_verified=True,
        )
        self.db.add(user)
        await self.db.flush()  # get the ID without committing

        # Auto-create a personal workspace
        slug = email.split("@")[0].lower().replace(".", "-")[:50]
        workspace = Workspace(name=f"{full_name or email}'s Workspace", slug=slug)
        self.db.add(workspace)
        await self.db.flush()

        member = WorkspaceMember(
            workspace_id=workspace.id,
            user_id=user.id,
            role=WorkspaceRole.OWNER,
        )
        self.db.add(member)
        return user, True

    async def upsert_connected_account(
        self,
        user_id: uuid.UUID,
        provider: str,
        provider_account_id: str,
        provider_email: str | None,
        access_token: str,
        refresh_token: str | None,
        token_expires_at: datetime | None,
        scopes: str | None,
    ) -> ConnectedAccount:
        """Create or update the connected account for a provider."""
        result = await self.db.execute(
            select(ConnectedAccount).where(
                ConnectedAccount.user_id == user_id,
                ConnectedAccount.provider == provider,
            )
        )
        account = result.scalar_one_or_none()

        if account is None:
            account = ConnectedAccount(user_id=user_id, provider=provider)

        account.provider_account_id = provider_account_id
        account.provider_email = provider_email
        account.encrypted_access_token = token_vault.store(access_token)
        account.encrypted_refresh_token = token_vault.safe_store(refresh_token)
        account.token_expires_at = token_expires_at
        account.scopes = scopes
        account.updated_at = datetime.now(timezone.utc)

        self.db.add(account)
        await self.db.flush()
        return account

    async def get_connected_account(
        self, user_id: uuid.UUID, provider: str
    ) -> ConnectedAccount | None:
        result = await self.db.execute(
            select(ConnectedAccount).where(
                ConnectedAccount.user_id == user_id,
                ConnectedAccount.provider == provider,
            )
        )
        return result.scalar_one_or_none()

    async def list_connected_accounts(
        self, user_id: uuid.UUID
    ) -> list[ConnectedAccount]:
        result = await self.db.execute(
            select(ConnectedAccount).where(ConnectedAccount.user_id == user_id)
        )
        return list(result.scalars().all())
