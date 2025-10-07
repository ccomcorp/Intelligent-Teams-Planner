"""
Security and authentication middleware for MCPO Proxy
Task 5: Security and authentication integration
"""

import re
import time
import hashlib
from typing import Dict, Any, List, Optional, Set

from fastapi import Request
from fastapi.security import HTTPBearer
import structlog

logger = structlog.get_logger(__name__)


class SecurityMiddleware:
    """Comprehensive security middleware for authentication and authorization"""

    def __init__(self):
        self.bearer_scheme = HTTPBearer(auto_error=False)
        self.blocked_ips: Set[str] = set()
        self.rate_limit_cache: Dict[str, List[float]] = {}

    def extract_bearer_token(self, authorization: str) -> Optional[str]:
        """Extract Bearer token from Authorization header"""
        try:
            if not authorization:
                return None

            # Handle both "Bearer token" and just "token" formats
            if authorization.startswith("Bearer "):
                return authorization[7:]  # Remove "Bearer " prefix
            elif authorization.startswith("bearer "):
                return authorization[7:]  # Handle lowercase
            else:
                # Assume it's just the token without Bearer prefix
                return authorization

        except Exception as e:
            logger.warning("Failed to extract bearer token", error=str(e))
            return None

    def validate_bearer_token(self, token: str) -> Dict[str, Any]:
        """
        Validate Bearer token format and structure
        In production, this would validate against a token service
        """
        try:
            if not token or len(token) < 10:
                return {"valid": False, "error": "Token too short"}

            # Basic token format validation
            if not re.match(r'^[a-zA-Z0-9._-]+$', token):
                return {"valid": False, "error": "Invalid token format"}

            # For now, accept any well-formed token
            # In production, validate against JWT or OAuth service
            return {
                "valid": True,
                "user_id": self._extract_user_id_from_token(token),
                "scopes": ["read", "write", "execute"],
                "expires_at": None  # Would be extracted from JWT
            }

        except Exception as e:
            logger.error("Token validation error", error=str(e))
            return {"valid": False, "error": "Token validation failed"}

    def _extract_user_id_from_token(self, token: str) -> str:
        """Extract user ID from token (simplified for demo)"""
        # In production, this would parse JWT claims
        # For now, use a hash of the token as user ID
        return hashlib.md5(token.encode()).hexdigest()[:8]

    def validate_cors_origin(self, origin: str, allowed_origins: List[str]) -> bool:
        """Validate CORS origin against allowed list"""
        try:
            if not origin:
                return False

            # Check exact matches
            if origin in allowed_origins:
                return True

            # Check wildcard matches
            for allowed in allowed_origins:
                if allowed == "*":
                    return True
                if allowed.startswith("*."):
                    domain_pattern = allowed[2:]  # Remove "*."
                    if origin.endswith("." + domain_pattern) or origin == domain_pattern:
                        return True

            return False

        except Exception as e:
            logger.error("CORS validation error", origin=origin, error=str(e))
            return False

    def check_rate_limit(
        self,
        client_id: str,
        max_requests: int = 100,
        window_seconds: int = 60
    ) -> Dict[str, Any]:
        """Check if client is within rate limits"""
        try:
            current_time = time.time()
            window_start = current_time - window_seconds

            # Clean old entries
            if client_id in self.rate_limit_cache:
                self.rate_limit_cache[client_id] = [
                    timestamp for timestamp in self.rate_limit_cache[client_id]
                    if timestamp > window_start
                ]
            else:
                self.rate_limit_cache[client_id] = []

            # Check current count
            current_count = len(self.rate_limit_cache[client_id])

            if current_count >= max_requests:
                return {
                    "allowed": False,
                    "current_count": current_count,
                    "limit": max_requests,
                    "reset_time": window_start + window_seconds,
                    "retry_after": int(window_seconds - (current_time - min(self.rate_limit_cache[client_id])))
                }

            # Add current request
            self.rate_limit_cache[client_id].append(current_time)

            return {
                "allowed": True,
                "current_count": current_count + 1,
                "limit": max_requests,
                "remaining": max_requests - current_count - 1,
                "reset_time": current_time + window_seconds
            }

        except Exception as e:
            logger.error("Rate limit check error", client_id=client_id, error=str(e))
            # Allow request on error to prevent DoS
            return {"allowed": True, "current_count": 0, "limit": max_requests}

    def sanitize_input(self, data: Any) -> Any:
        """Sanitize input data to prevent injection attacks"""
        try:
            if isinstance(data, str):
                # Remove potential script injections
                data = re.sub(r'<script[^>]*>.*?</script>', '', data, flags=re.IGNORECASE | re.DOTALL)
                data = re.sub(r'javascript:', '', data, flags=re.IGNORECASE)
                data = re.sub(r'on\w+\s*=', '', data, flags=re.IGNORECASE)
                return data.strip()

            elif isinstance(data, dict):
                return {key: self.sanitize_input(value) for key, value in data.items()}

            elif isinstance(data, list):
                return [self.sanitize_input(item) for item in data]

            else:
                return data

        except Exception as e:
            logger.error("Input sanitization error", error=str(e))
            return data

    def get_client_identifier(self, request: Request) -> str:
        """Get unique client identifier for rate limiting"""
        try:
            # Try to get real IP from headers (when behind proxy)
            forwarded_for = request.headers.get("X-Forwarded-For")
            if forwarded_for:
                return forwarded_for.split(",")[0].strip()

            real_ip = request.headers.get("X-Real-IP")
            if real_ip:
                return real_ip

            # Fall back to direct client IP
            return request.client.host if request.client else "unknown"

        except Exception as e:
            logger.error("Error getting client identifier", error=str(e))
            return "unknown"

    def is_suspicious_request(self, request: Request) -> Dict[str, Any]:
        """Detect potentially suspicious requests"""
        try:
            suspicion_score = 0
            reasons = []

            # Check user agent
            user_agent = request.headers.get("User-Agent", "")
            if not user_agent or len(user_agent) < 10:
                suspicion_score += 20
                reasons.append("Missing or short User-Agent")

            # Check for common attack patterns in URL
            url_path = str(request.url.path).lower()
            attack_patterns = [
                "../", "etc/passwd", "admin", "wp-admin", ".env",
                "config", "backup", "sql", "dump"
            ]
            for pattern in attack_patterns:
                if pattern in url_path:
                    suspicion_score += 30
                    reasons.append(f"Suspicious URL pattern: {pattern}")

            # Check request size
            content_length = request.headers.get("Content-Length")
            if content_length and int(content_length) > 10_000_000:  # 10MB
                suspicion_score += 25
                reasons.append("Unusually large request")

            # Check for rapid requests (basic check)
            client_ip = self.get_client_identifier(request)
            if client_ip in self.rate_limit_cache:
                recent_requests = len([
                    t for t in self.rate_limit_cache[client_ip]
                    if time.time() - t < 10  # Last 10 seconds
                ])
                if recent_requests > 50:
                    suspicion_score += 40
                    reasons.append("Very high request rate")

            return {
                "is_suspicious": suspicion_score > 50,
                "suspicion_score": suspicion_score,
                "reasons": reasons,
                "client_ip": client_ip
            }

        except Exception as e:
            logger.error("Error in suspicious request detection", error=str(e))
            return {"is_suspicious": False, "suspicion_score": 0, "reasons": []}


class AuthenticationHandler:
    """Handle authentication workflows and token management"""

    def __init__(self, security_middleware: SecurityMiddleware):
        self.security = security_middleware

    async def authenticate_request(self, request: Request) -> Dict[str, Any]:
        """Authenticate incoming request"""
        try:
            # Extract authorization header
            auth_header = request.headers.get("Authorization")
            x_teams_auth = request.headers.get("X-Teams-Auth-Token")

            # Try different authentication methods
            token = None
            auth_method = "none"

            if auth_header:
                token = self.security.extract_bearer_token(auth_header)
                auth_method = "bearer"
            elif x_teams_auth:
                token = x_teams_auth
                auth_method = "teams_header"

            if not token:
                return {
                    "authenticated": False,
                    "error": "No authentication token provided",
                    "auth_method": auth_method
                }

            # Validate token
            validation_result = self.security.validate_bearer_token(token)

            if not validation_result["valid"]:
                return {
                    "authenticated": False,
                    "error": validation_result.get("error", "Invalid token"),
                    "auth_method": auth_method
                }

            return {
                "authenticated": True,
                "user_id": validation_result["user_id"],
                "scopes": validation_result["scopes"],
                "auth_method": auth_method,
                "token_hash": hashlib.sha256(token.encode()).hexdigest()[:16]
            }

        except Exception as e:
            logger.error("Authentication error", error=str(e))
            return {
                "authenticated": False,
                "error": "Authentication processing failed",
                "auth_method": "unknown"
            }

    def create_secure_headers(self, request: Request) -> Dict[str, str]:
        """Create secure headers for MCP server requests"""
        try:
            headers = {}

            # Forward authentication token
            auth_header = request.headers.get("Authorization")
            x_teams_auth = request.headers.get("X-Teams-Auth-Token")

            if auth_header:
                headers["Authorization"] = auth_header
            elif x_teams_auth:
                headers["X-Teams-Auth-Token"] = x_teams_auth

            # Add proxy identification
            headers["X-Forwarded-By"] = "MCPO-Proxy"
            headers["X-Proxy-Version"] = "2.0.0"

            # Forward client IP for logging
            client_ip = self.security.get_client_identifier(request)
            headers["X-Original-Client-IP"] = client_ip

            # Add correlation ID for tracing
            correlation_id = request.headers.get("X-Correlation-ID") or f"proxy_{int(time.time())}"
            headers["X-Correlation-ID"] = correlation_id

            return headers

        except Exception as e:
            logger.error("Error creating secure headers", error=str(e))
            return {}


class SecurityValidator:
    """Validate security requirements and policies"""

    def __init__(self):
        self.security_policy = {
            "require_authentication": True,
            "allowed_origins": [
                "http://localhost:3000",
                "http://openwebui:8080",
                "https://*.openwebui.com"
            ],
            "rate_limits": {
                "default": {"requests": 100, "window": 60},
                "authenticated": {"requests": 1000, "window": 60},
                "system": {"requests": 10000, "window": 60}
            },
            "blocked_user_agents": [
                "bot", "crawler", "spider", "scraper"
            ],
            "max_request_size": 10_000_000,  # 10MB
            "require_secure_headers": True
        }

    def validate_security_policy(self, request: Request, auth_result: Dict[str, Any]) -> Dict[str, Any]:
        """Validate request against security policy"""
        try:
            violations = []
            security_level = "low"

            # Check authentication requirement
            if self.security_policy["require_authentication"] and not auth_result["authenticated"]:
                violations.append("Authentication required but not provided")
                security_level = "high"

            # Check user agent
            user_agent = request.headers.get("User-Agent", "").lower()
            for blocked_agent in self.security_policy["blocked_user_agents"]:
                if blocked_agent in user_agent:
                    violations.append(f"Blocked user agent pattern: {blocked_agent}")
                    security_level = "medium"

            # Check request size
            content_length = request.headers.get("Content-Length")
            if content_length and int(content_length) > self.security_policy["max_request_size"]:
                violations.append("Request size exceeds limit")
                security_level = "high"

            return {
                "policy_compliant": len(violations) == 0,
                "violations": violations,
                "security_level": security_level,
                "policy_version": "1.0"
            }

        except Exception as e:
            logger.error("Security policy validation error", error=str(e))
            return {
                "policy_compliant": False,
                "violations": ["Policy validation failed"],
                "security_level": "high"
            }

    def get_rate_limit_for_user(self, auth_result: Dict[str, Any]) -> Dict[str, int]:
        """Get appropriate rate limits based on user authentication status"""
        if auth_result.get("authenticated"):
            if "system" in auth_result.get("scopes", []):
                return self.security_policy["rate_limits"]["system"]
            else:
                return self.security_policy["rate_limits"]["authenticated"]
        else:
            return self.security_policy["rate_limits"]["default"]


# Security middleware integration for FastAPI dependency injection
security_middleware = SecurityMiddleware()
auth_handler = AuthenticationHandler(security_middleware)
security_validator = SecurityValidator()
