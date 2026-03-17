from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import AUTH_TOKEN

security = HTTPBearer(auto_error=False)


def require_auth(credentials: HTTPAuthorizationCredentials = Depends(security)) -> None:
    if not AUTH_TOKEN:
        return
    if not credentials or credentials.credentials != AUTH_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )

