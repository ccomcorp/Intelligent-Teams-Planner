import os
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import msal
import structlog
from cryptography.fernet import Fernet
import json
import redis.asyncio as redis
from fastapi import HTTPException

logger = structlog.get_logger(__name__)

class GraphAuthService:
    """Service for handling Microsoft Graph API authentication"""

    def __init__(self, redis_client: redis.Redis):
        self.client_id = os.getenv("MS_CLIENT_ID")
        self.client_secret = os.getenv("MS_CLIENT_SECRET")
        self.tenant_id = os.getenv("MS_TENANT_ID")
        self.redirect_uri = os.getenv("MS_REDIRECT_URI", "http://localhost:8000/auth/callback")

        if not all([self.client_id, self.client_secret, self.tenant_id]):
            raise ValueError("Missing Microsoft Graph API credentials in environment variables")

        self.authority = f"https://login.microsoftonline.com/{self.tenant_id}"
        self.scopes = ["https://graph.microsoft.com/Tasks.ReadWrite"]

        self.redis_client = redis_client
        self.encryption_key = os.getenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
        self.cipher = Fernet(self.encryption_key.encode())

        logger.info("GraphAuthService initialized", client_id=self.client_id[:8] + "...")

    def get_msal_app(self) -> msal.ConfidentialClientApplication:
        """Create and return MSAL application instance"""
        return msal.ConfidentialClientApplication(
            client_id=self.client_id,
            client_credential=self.client_secret,
            authority=self.authority
        )

    def get_auth_url(self, state: str) -> str:
        """Generate authorization URL for OAuth flow"""
        app = self.get_msal_app()
        auth_url = app.get_authorization_request_url(
            scopes=self.scopes,
            redirect_uri=self.redirect_uri,
            state=state
        )
        logger.info("Generated auth URL", state=state)
        return auth_url

    async def exchange_code_for_tokens(self, code: str, state: str) -> Dict[str, Any]:
        """Exchange authorization code for access and refresh tokens"""
        try:
            app = self.get_msal_app()

            # Exchange code for tokens
            result = app.acquire_token_by_authorization_code(
                code=code,
                scopes=self.scopes,
                redirect_uri=self.redirect_uri
            )

            if "error" in result:
                logger.error("Token exchange failed", error=result.get("error"),
                           description=result.get("error_description"))
                raise HTTPException(status_code=400, detail=f"Token exchange failed: {result.get('error_description')}")

            # Extract tokens
            access_token = result.get("access_token")
            refresh_token = result.get("refresh_token")
            expires_in = result.get("expires_in", 3600)

            if not access_token:
                raise HTTPException(status_code=400, detail="No access token received")

            # Calculate expiration time
            expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

            # Store tokens securely
            user_id = await self._get_user_id_from_token(access_token)
            await self._store_tokens(user_id, access_token, refresh_token, expires_at)

            logger.info("Tokens stored successfully", user_id=user_id, expires_at=expires_at)

            return {
                "user_id": user_id,
                "access_token": access_token,
                "expires_at": expires_at.isoformat(),
                "scopes": result.get("scope", [])
            }

        except Exception as e:
            logger.error("Error during token exchange", error=str(e))
            raise HTTPException(status_code=500, detail=f"Authentication failed: {str(e)}")

    async def get_valid_access_token(self, user_id: str) -> Optional[str]:
        """Get valid access token for user, refreshing if necessary"""
        try:
            # Try to get cached token
            token_data = await self._get_stored_tokens(user_id)
            if not token_data:
                logger.warning("No stored tokens found", user_id=user_id)
                return None

            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")
            expires_at = datetime.fromisoformat(token_data.get("expires_at"))

            # Check if token is still valid (with 5 minute buffer)
            if datetime.utcnow() < expires_at - timedelta(minutes=5):
                logger.debug("Using cached access token", user_id=user_id)
                return access_token

            # Token expired, try to refresh
            if refresh_token:
                logger.info("Refreshing expired token", user_id=user_id)
                new_tokens = await self._refresh_access_token(refresh_token)
                if new_tokens:
                    # Store new tokens
                    new_expires_at = datetime.utcnow() + timedelta(seconds=new_tokens.get("expires_in", 3600))
                    await self._store_tokens(
                        user_id,
                        new_tokens["access_token"],
                        new_tokens.get("refresh_token", refresh_token),
                        new_expires_at
                    )
                    return new_tokens["access_token"]

            logger.warning("Unable to refresh token", user_id=user_id)
            return None

        except Exception as e:
            logger.error("Error getting valid access token", user_id=user_id, error=str(e))
            return None

    async def _refresh_access_token(self, refresh_token: str) -> Optional[Dict[str, Any]]:
        """Refresh access token using refresh token"""
        try:
            app = self.get_msal_app()
            result = app.acquire_token_by_refresh_token(
                refresh_token=refresh_token,
                scopes=self.scopes
            )

            if "error" in result:
                logger.error("Token refresh failed", error=result.get("error"))
                return None

            return result

        except Exception as e:
            logger.error("Error refreshing token", error=str(e))
            return None

    async def _get_user_id_from_token(self, access_token: str) -> str:
        """Extract user ID from access token by calling Graph API"""
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://graph.microsoft.com/v1.0/me",
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                response.raise_for_status()
                user_data = response.json()
                return user_data.get("id") or user_data.get("userPrincipalName")

        except Exception as e:
            logger.error("Error getting user ID from token", error=str(e))
            raise HTTPException(status_code=401, detail="Invalid access token")

    async def _store_tokens(self, user_id: str, access_token: str, refresh_token: Optional[str], expires_at: datetime):
        """Store encrypted tokens in Redis"""
        try:
            token_data = {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_at": expires_at.isoformat(),
                "stored_at": datetime.utcnow().isoformat()
            }

            # Encrypt the token data
            encrypted_data = self.cipher.encrypt(json.dumps(token_data).encode())

            # Store in Redis with TTL (token lifetime + 1 day buffer)
            ttl_seconds = int((expires_at - datetime.utcnow()).total_seconds()) + 86400
            await self.redis_client.setex(
                f"tokens:{user_id}",
                ttl_seconds,
                encrypted_data
            )

            logger.debug("Tokens stored in Redis", user_id=user_id, ttl=ttl_seconds)

        except Exception as e:
            logger.error("Error storing tokens", user_id=user_id, error=str(e))
            raise

    async def _get_stored_tokens(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve and decrypt tokens from Redis"""
        try:
            encrypted_data = await self.redis_client.get(f"tokens:{user_id}")
            if not encrypted_data:
                return None

            # Decrypt the token data
            decrypted_data = self.cipher.decrypt(encrypted_data)
            token_data = json.loads(decrypted_data.decode())

            return token_data

        except Exception as e:
            logger.error("Error retrieving tokens", user_id=user_id, error=str(e))
            return None

    async def revoke_tokens(self, user_id: str) -> bool:
        """Revoke and delete stored tokens for user"""
        try:
            # Delete from Redis
            deleted = await self.redis_client.delete(f"tokens:{user_id}")
            logger.info("Tokens revoked", user_id=user_id, deleted=bool(deleted))
            return bool(deleted)

        except Exception as e:
            logger.error("Error revoking tokens", user_id=user_id, error=str(e))
            return False

    async def validate_token(self, access_token: str) -> bool:
        """Validate access token by calling Graph API"""
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://graph.microsoft.com/v1.0/me",
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=10.0
                )
                return response.status_code == 200

        except Exception as e:
            logger.error("Error validating token", error=str(e))
            return False