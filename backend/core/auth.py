import secrets
from functools import lru_cache

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient, PyJWTError, decode

from .config import AUTH_MODE, AUTH_TOKEN, CLERK_AUDIENCE, CLERK_ISSUER_URL, CLERK_JWKS_URL

security = HTTPBearer(auto_error=False)

@lru_cache(maxsize=1)
def _jwks_client() -> PyJWKClient:
    jwks_url = CLERK_JWKS_URL or (
        f"{CLERK_ISSUER_URL}/.well-known/jwks.json" if CLERK_ISSUER_URL else ""
    )
    if not jwks_url:
        raise RuntimeError(
            "Set CLERK_ISSUER_URL (and optionally CLERK_JWKS_URL) before serving "
            "authenticated API routes."
        )
    return PyJWKClient(jwks_url)


def verify_clerk_token(token: str) -> str:
    try:
        if not CLERK_ISSUER_URL:
            raise RuntimeError("CLERK_ISSUER_URL is required when ANGADGPT_AUTH_MODE=clerk.")
        signing_key = _jwks_client().get_signing_key_from_jwt(token)
        options = {"verify_aud": bool(CLERK_AUDIENCE)}
        claims = decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=CLERK_ISSUER_URL or None,
            audience=CLERK_AUDIENCE or None,
            options=options,
        )
        user_id = claims.get("sub")
        if not user_id:
            raise PyJWTError("Token has no subject")
        return str(user_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired Clerk session.",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Clerk token verification is temporarily unavailable.",
        ) from exc


def authenticate_token(token: str | None) -> str:
    if AUTH_MODE == "local":
        if not AUTH_TOKEN:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="ANGADGPT_AUTH_TOKEN is required in local auth mode.",
            )
        if not token or not secrets.compare_digest(token, AUTH_TOKEN):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized"
            )
        return "local"
    if AUTH_MODE != "clerk":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ANGADGPT_AUTH_MODE must be 'clerk' or 'local'.",
        )
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in is required."
        )
    return verify_clerk_token(token)


def require_auth(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """Return the authenticated Clerk subject (or explicit local user)."""
    return authenticate_token(credentials.credentials if credentials else None)
