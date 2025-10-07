"""
Authentication service for Microsoft Graph API integration
"""

import os
import json
import secrets
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from urllib.parse import urlencode

import msal
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
import structlog

from .cache import CacheService

logger = structlog.get_logger(__name__)

class AuthenticationError(Exception):
    """Authentication related errors"""
    pass

class AuthService:
    """Microsoft Graph API authentication service"""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        tenant_id: str,
        cache_service: CacheService,
        redirect_uri: str = None
    ):
        if not all([client_id, client_secret, tenant_id]):
            raise ValueError("client_id, client_secret, and tenant_id are required")

        self.client_id = client_id
        self.client_secret = client_secret
        self.tenant_id = tenant_id
        self.cache_service = cache_service

        # Default redirect URI for development
        self.redirect_uri = redirect_uri or "http://localhost:8888/auth/callback"

        # Microsoft Graph API scopes for Teams and Planner (Full functionality)
        # Using the correct MSAL scope format for Microsoft Graph
        self.scopes = [
            # Core Microsoft Graph permissions
            "User.Read",
            "Group.Read.All",
            "Group.ReadWrite.All",
            # Planner permissions
            "Tasks.Read",
            "Tasks.ReadWrite",
            # Teams permissions
            "Team.ReadBasic.All",
            "TeamMember.Read.All",
            "Channel.ReadBasic.All",
            # Additional useful permissions
            "Mail.Read",
            "Calendars.Read"
        ]

        # Encryption for token storage
        encryption_key = os.getenv("ENCRYPTION_KEY")
        if not encryption_key or len(encryption_key) != 32:
            raise ValueError("ENCRYPTION_KEY must be exactly 32 characters")

        # Derive a proper Fernet key from the password
        salt = b"intelligent_teams_planner_salt"
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(encryption_key.encode()))
        self.cipher = Fernet(key)

        # MSAL app configuration
        self.authority = f"https://login.microsoftonline.com/{tenant_id}"
        self.app = msal.ConfidentialClientApplication(
            client_id=client_id,
            client_credential=client_secret,
            authority=self.authority
        )

    async def get_login_url(self, user_id: str, state: str = None) -> str:
        """Generate OAuth login URL"""
        try:
            # Generate state parameter for security
            if not state:
                state = secrets.token_urlsafe(32)

            # Cache state for verification
            await self.cache_service.set(
                f"oauth_state:{state}",
                {"user_id": user_id, "created_at": datetime.utcnow().isoformat()},
                ttl=600  # 10 minutes
            )

            # Generate authorization URL
            auth_url = self.app.get_authorization_request_url(
                scopes=self.scopes,
                state=state,
                redirect_uri=self.redirect_uri
            )

            logger.info("Generated login URL", user_id=user_id, state=state[:10])
            return auth_url

        except Exception as e:
            logger.error("Error generating login URL", error=str(e))
            raise AuthenticationError(f"Failed to generate login URL: {str(e)}")

    async def handle_callback(self, code: str, state: str, user_id: str = None) -> bool:
        """Handle OAuth callback and exchange code for tokens"""
        try:
            # Verify state parameter
            cached_state = await self.cache_service.get(f"oauth_state:{state}")
            if not cached_state:
                logger.error("Invalid or expired state parameter", state=state[:10])
                raise AuthenticationError("Invalid or expired authentication request")

            # Use user_id from state if not provided
            if not user_id:
                user_id = cached_state.get("user_id", "default")

            # Exchange code for tokens
            result = self.app.acquire_token_by_authorization_code(
                code,
                scopes=self.scopes,
                redirect_uri=self.redirect_uri
            )

            if "error" in result:
                logger.error("Token exchange failed", error=result.get("error_description"))
                raise AuthenticationError(f"Token exchange failed: {result.get('error_description')}")

            # Extract token information
            access_token = result.get("access_token")
            refresh_token = result.get("refresh_token")
            expires_in = result.get("expires_in", 3600)
            id_token_claims = result.get("id_token_claims", {})

            if not access_token:
                raise AuthenticationError("No access token received")

            # Prepare token data
            token_data = {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_at": (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat(),
                "user_id": id_token_claims.get("oid", user_id),
                "user_name": id_token_claims.get("name", ""),
                "email": id_token_claims.get("preferred_username", ""),
                "tenant_id": id_token_claims.get("tid", self.tenant_id),
                "created_at": datetime.utcnow().isoformat()
            }

            # Encrypt and store tokens
            await self._store_encrypted_tokens(user_id, token_data)

            # Clean up state
            await self.cache_service.delete(f"oauth_state:{state}")

            logger.info("Authentication successful", user_id=user_id)
            return True

        except AuthenticationError:
            raise
        except Exception as e:
            logger.error("Error handling auth callback", error=str(e))
            raise AuthenticationError(f"Callback handling failed: {str(e)}")

    async def get_access_token(self, user_id: str) -> Optional[str]:
        """Get valid access token for user"""
        try:
            # Try to get cached token first
            cached_token = await self.cache_service.get(f"access_token:{user_id}")
            if cached_token:
                return cached_token

            # Get stored token data
            token_data = await self._get_decrypted_tokens(user_id)
            if not token_data:
                logger.info("No stored tokens found", user_id=user_id)
                return None

            # Check if token is still valid
            expires_at = datetime.fromisoformat(token_data["expires_at"])
            if datetime.utcnow() < expires_at - timedelta(minutes=5):  # 5 min buffer
                # Token is still valid, cache it
                ttl = int((expires_at - datetime.utcnow()).total_seconds()) - 300  # 5 min buffer
                if ttl > 0:
                    await self.cache_service.set(
                        f"access_token:{user_id}",
                        token_data["access_token"],
                        ttl=ttl
                    )
                return token_data["access_token"]

            # Token expired, try to refresh
            if token_data.get("refresh_token"):
                return await self._refresh_access_token(user_id, token_data)

            logger.info("Token expired and no refresh token available", user_id=user_id)
            return None

        except Exception as e:
            logger.error("Error getting access token", user_id=user_id, error=str(e))
            return None

    async def _refresh_access_token(self, user_id: str, token_data: Dict[str, Any]) -> Optional[str]:
        """Refresh access token using refresh token"""
        try:
            result = self.app.acquire_token_by_refresh_token(
                token_data["refresh_token"],
                scopes=self.scopes
            )

            if "error" in result:
                logger.error("Token refresh failed", error=result.get("error_description"))
                # Clear invalid tokens
                await self.clear_tokens(user_id)
                return None

            # Update token data
            access_token = result.get("access_token")
            refresh_token = result.get("refresh_token", token_data["refresh_token"])  # Keep old if new not provided
            expires_in = result.get("expires_in", 3600)

            updated_token_data = {
                **token_data,
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_at": (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }

            # Store updated tokens
            await self._store_encrypted_tokens(user_id, updated_token_data)

            # Cache new access token
            await self.cache_service.set(
                f"access_token:{user_id}",
                access_token,
                ttl=expires_in - 300  # 5 min buffer
            )

            logger.info("Token refreshed successfully", user_id=user_id)
            return access_token

        except Exception as e:
            logger.error("Error refreshing token", user_id=user_id, error=str(e))
            await self.clear_tokens(user_id)
            return None

    async def has_valid_token(self, user_id: str) -> bool:
        """Check if user has valid authentication"""
        token = await self.get_access_token(user_id)
        return token is not None

    async def get_token_info(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get token information for user"""
        try:
            token_data = await self._get_decrypted_tokens(user_id)
            if not token_data:
                return None

            return {
                "user_id": token_data.get("user_id"),
                "user_name": token_data.get("user_name"),
                "email": token_data.get("email"),
                "tenant_id": token_data.get("tenant_id"),
                "expires_at": token_data.get("expires_at"),
                "created_at": token_data.get("created_at")
            }

        except Exception as e:
            logger.error("Error getting token info", user_id=user_id, error=str(e))
            return None

    async def clear_tokens(self, user_id: str):
        """Clear all tokens for user"""
        try:
            # Clear from cache
            await self.cache_service.delete(f"access_token:{user_id}")

            # Clear from persistent storage (this would integrate with database)
            # For now, we'll use cache for simplicity
            await self.cache_service.delete(f"stored_tokens:{user_id}")

            logger.info("Tokens cleared", user_id=user_id)

        except Exception as e:
            logger.error("Error clearing tokens", user_id=user_id, error=str(e))

    async def _store_encrypted_tokens(self, user_id: str, token_data: Dict[str, Any]):
        """Store encrypted tokens"""
        try:
            # Encrypt token data
            encrypted_data = self.cipher.encrypt(json.dumps(token_data).encode())

            # Store in cache (in production, this should go to database)
            await self.cache_service.set(
                f"stored_tokens:{user_id}",
                encrypted_data.decode(),
                ttl=86400 * 30  # 30 days
            )

        except Exception as e:
            logger.error("Error storing encrypted tokens", user_id=user_id, error=str(e))
            raise AuthenticationError(f"Failed to store tokens: {str(e)}")

    async def _get_decrypted_tokens(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get and decrypt stored tokens"""
        try:
            # Get from cache (in production, this should come from database)
            encrypted_data = await self.cache_service.get(f"stored_tokens:{user_id}")
            if not encrypted_data:
                return None

            # Decrypt token data
            decrypted_data = self.cipher.decrypt(encrypted_data.encode())
            return json.loads(decrypted_data.decode())

        except Exception as e:
            logger.error("Error decrypting tokens", user_id=user_id, error=str(e))
            # Clear corrupted data
            await self.cache_service.delete(f"stored_tokens:{user_id}")
            return None

    async def get_user_info(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user information from Microsoft Graph"""
        try:
            access_token = await self.get_access_token(user_id)
            if not access_token:
                return None

            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://graph.microsoft.com/v1.0/me",
                    headers={"Authorization": f"Bearer {access_token}"}
                )

                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error("Failed to get user info", status_code=response.status_code)
                    return None

        except Exception as e:
            logger.error("Error getting user info", user_id=user_id, error=str(e))
            return None

    def is_token_expired(self, token_data: Dict[str, Any]) -> bool:
        """Check if token is expired"""
        try:
            expires_at = datetime.fromisoformat(token_data["expires_at"])
            return datetime.utcnow() >= expires_at
        except (KeyError, ValueError):
            return True