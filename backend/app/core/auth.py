import logging
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, jwk as jose_jwk, JWTError
import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)
bearer_scheme = HTTPBearer()

_jwks_cache: list | None = None


async def _get_jwks() -> list:
    """Fetch and cache Supabase's public JWKS keys."""
    global _jwks_cache
    if _jwks_cache is not None:
        return _jwks_cache
    url = f"{settings.supabase_url}/auth/v1/.well-known/jwks.json"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, timeout=10)
        resp.raise_for_status()
    _jwks_cache = resp.json().get("keys", [])
    logger.info("Loaded %d JWKS key(s) from Supabase", len(_jwks_cache))
    return _jwks_cache


async def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    global _jwks_cache
    token = credentials.credentials
    try:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        alg = header.get("alg", "ES256")

        keys = await _get_jwks()
        key_data = next((k for k in keys if k.get("kid") == kid), None)

        if key_data is None:
            # Keys may have rotated — bust cache and retry once
            _jwks_cache = None
            keys = await _get_jwks()
            key_data = next((k for k in keys if k.get("kid") == kid), None)

        if key_data is None:
            raise JWTError(f"No public key found for kid={kid}")

        # Extract PEM from JWK — more reliable than passing raw dict for EC keys
        public_pem = jose_jwk.construct(key_data, algorithm=alg).public_key().to_pem()

        payload = jwt.decode(
            token,
            public_pem,
            algorithms=[alg],
            options={"verify_aud": False},
        )
        return payload

    except JWTError as e:
        logger.error("JWT verification failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


async def get_current_user_id(payload: dict = Depends(verify_token)) -> str:
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing user ID",
        )
    return user_id
