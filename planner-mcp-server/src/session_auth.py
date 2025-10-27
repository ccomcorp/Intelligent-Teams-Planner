"""
Session-based Authentication Management
Handles persistent authentication with session management, timeout, and automatic token refresh
"""

import uuid
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import structlog

from .cache import CacheService
from .auth import AuthService

logger = structlog.get_logger(__name__)

class SessionAuthManager:
    """Manages session-based authentication with persistent tokens"""

    def __init__(self, cache_service: CacheService, auth_service: AuthService):
        self.cache_service = cache_service
        self.auth_service = auth_service

        # Session configuration
        self.SESSION_PREFIX = "session:"
        self.USER_SESSION_PREFIX = "user_session:"
        self.DEFAULT_SESSION_TIMEOUT = 3600 * 8  # 8 hours (or until browser closes)
        self.EXTEND_SESSION_THRESHOLD = 1800  # 30 minutes
        self.BROWSER_ACTIVITY_TIMEOUT = 1800  # 30 minutes of browser inactivity

    async def create_authenticated_session(self, user_id: str, session_timeout: Optional[int] = None) -> Optional[str]:
        """
        Create a new authenticated session for a user
        Returns session_id if successful, None if user is not authenticated
        """
        try:
            # Check if user has valid authentication
            if not await self.auth_service.has_valid_token(user_id):
                logger.warning("Cannot create session for unauthenticated user", user_id=user_id)
                return None

            # Generate unique session ID
            session_id = str(uuid.uuid4())
            timeout = session_timeout or self.DEFAULT_SESSION_TIMEOUT

            # Get user token info for session metadata
            token_info = await self.auth_service.get_token_info(user_id)

            # Create session data
            session_data = {
                "user_id": user_id,
                "session_id": session_id,
                "created_at": datetime.utcnow().isoformat(),
                "last_accessed": datetime.utcnow().isoformat(),
                "expires_at": (datetime.utcnow() + timedelta(seconds=timeout)).isoformat(),
                "timeout_seconds": timeout,
                "user_info": token_info or {},
                "is_active": True
            }

            # Store session data
            await self.cache_service.set(
                f"{self.SESSION_PREFIX}{session_id}",
                session_data,
                ttl=timeout
            )

            # Store user -> session mapping (for logout/cleanup)
            await self.cache_service.set(
                f"{self.USER_SESSION_PREFIX}{user_id}",
                session_id,
                ttl=timeout
            )

            logger.info("Created authenticated session", user_id=user_id, session_id=session_id[:8])
            return session_id

        except Exception as e:
            logger.error("Error creating authenticated session", user_id=user_id, error=str(e))
            return None

    async def validate_session(self, session_id: str, extend_if_needed: bool = True) -> Optional[Dict[str, Any]]:
        """
        Validate a session and optionally extend it if close to expiration
        Returns session data if valid, None if invalid/expired
        """
        try:
            if not session_id:
                return None

            # Get session data
            session_data = await self.cache_service.get(f"{self.SESSION_PREFIX}{session_id}")
            if not session_data:
                logger.debug("Session not found", session_id=session_id[:8])
                return None

            # Check if session is marked as active
            if not session_data.get("is_active", False):
                logger.debug("Session is inactive", session_id=session_id[:8])
                return None

            # Check if session has expired
            expires_at = datetime.fromisoformat(session_data["expires_at"])
            now = datetime.utcnow()

            if now >= expires_at:
                logger.info("Session expired", session_id=session_id[:8], expired_at=expires_at.isoformat())
                await self._cleanup_session(session_id, session_data.get("user_id"))
                return None

            # Update last accessed time
            session_data["last_accessed"] = now.isoformat()

            # Calculate time until expiry for session management
            time_until_expiry = (expires_at - now).total_seconds()

            # Extend session if close to expiration and requested
            if extend_if_needed:
                if time_until_expiry < self.EXTEND_SESSION_THRESHOLD:
                    await self._extend_session(session_id, session_data)
                    # Recalculate time until expiry after extension
                    new_expires_at = datetime.fromisoformat(session_data["expires_at"])
                    time_until_expiry = (new_expires_at - now).total_seconds()

            # Verify user's authentication is still valid
            user_id = session_data.get("user_id")
            if user_id and not await self.auth_service.has_valid_token(user_id):
                logger.warning("User authentication no longer valid", user_id=user_id, session_id=session_id[:8])
                await self._cleanup_session(session_id, user_id)
                return None

            # Update session data in cache
            remaining_ttl = int(time_until_expiry)
            await self.cache_service.set(
                f"{self.SESSION_PREFIX}{session_id}",
                session_data,
                ttl=remaining_ttl
            )

            return session_data

        except Exception as e:
            logger.error("Error validating session", session_id=session_id[:8], error=str(e))
            return None

    async def _extend_session(self, session_id: str, session_data: Dict[str, Any]) -> None:
        """Extend session expiration time"""
        try:
            timeout = session_data.get("timeout_seconds", self.DEFAULT_SESSION_TIMEOUT)
            new_expires_at = datetime.utcnow() + timedelta(seconds=timeout)

            session_data["expires_at"] = new_expires_at.isoformat()
            session_data["extended_at"] = datetime.utcnow().isoformat()

            # Update session in cache with new TTL
            await self.cache_service.set(
                f"{self.SESSION_PREFIX}{session_id}",
                session_data,
                ttl=timeout
            )

            # Update user session mapping
            user_id = session_data.get("user_id")
            if user_id:
                await self.cache_service.set(
                    f"{self.USER_SESSION_PREFIX}{user_id}",
                    session_id,
                    ttl=timeout
                )

            logger.info("Extended session", session_id=session_id[:8], new_expires_at=new_expires_at.isoformat())

        except Exception as e:
            logger.error("Error extending session", session_id=session_id[:8], error=str(e))

    async def invalidate_session(self, session_id: str) -> bool:
        """Manually invalidate a session (logout)"""
        try:
            session_data = await self.cache_service.get(f"{self.SESSION_PREFIX}{session_id}")
            if session_data:
                user_id = session_data.get("user_id")
                await self._cleanup_session(session_id, user_id)
                logger.info("Session invalidated", session_id=session_id[:8], user_id=user_id)
                return True
            return False

        except Exception as e:
            logger.error("Error invalidating session", session_id=session_id[:8], error=str(e))
            return False

    async def invalidate_user_sessions(self, user_id: str) -> bool:
        """Invalidate all sessions for a user"""
        try:
            # Get user's current session
            session_id = await self.cache_service.get(f"{self.USER_SESSION_PREFIX}{user_id}")
            if session_id:
                await self._cleanup_session(session_id, user_id)
                logger.info("All user sessions invalidated", user_id=user_id)
                return True
            return False

        except Exception as e:
            logger.error("Error invalidating user sessions", user_id=user_id, error=str(e))
            return False

    async def _cleanup_session(self, session_id: str, user_id: Optional[str] = None) -> None:
        """Clean up session data from cache"""
        try:
            # Remove session data
            await self.cache_service.delete(f"{self.SESSION_PREFIX}{session_id}")

            # Remove user session mapping if user_id provided
            if user_id:
                await self.cache_service.delete(f"{self.USER_SESSION_PREFIX}{user_id}")

        except Exception as e:
            logger.error("Error cleaning up session", session_id=session_id[:8], error=str(e))

    async def get_authenticated_user_id(self, session_id: str) -> Optional[str]:
        """Get user_id for a valid session"""
        session_data = await self.validate_session(session_id)
        return session_data.get("user_id") if session_data else None

    async def refresh_user_authentication(self, user_id: str) -> bool:
        """Refresh user's authentication tokens"""
        try:
            # This will attempt to refresh the user's tokens
            token = await self.auth_service.get_access_token(user_id)
            return token is not None
        except Exception as e:
            logger.error("Error refreshing user authentication", user_id=user_id, error=str(e))
            return False

    async def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session information for monitoring/debugging"""
        try:
            session_data = await self.validate_session(session_id, extend_if_needed=False)
            if not session_data:
                return None

            # Return safe session info (no sensitive data)
            return {
                "session_id": session_id,
                "user_id": session_data.get("user_id"),
                "created_at": session_data.get("created_at"),
                "last_accessed": session_data.get("last_accessed"),
                "expires_at": session_data.get("expires_at"),
                "is_active": session_data.get("is_active", False),
                "user_name": session_data.get("user_info", {}).get("user_name"),
                "email": session_data.get("user_info", {}).get("email")
            }

        except Exception as e:
            logger.error("Error getting session info", session_id=session_id[:8], error=str(e))
            return None

    async def update_browser_activity(self, session_id: str) -> bool:
        """Update browser activity timestamp for a session to prevent timeout"""
        try:
            session_data = await self.validate_session(session_id, extend_if_needed=True)
            if session_data:
                # Session validation already updates last_accessed time
                # This method serves as a convenient way to "ping" the session
                logger.debug("Browser activity updated", session_id=session_id[:8])
                return True
            return False

        except Exception as e:
            logger.error("Error updating browser activity", session_id=session_id[:8], error=str(e))
            return False