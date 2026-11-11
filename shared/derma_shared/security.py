"""Chỉ verify JWT; identity (Spring) mới phát token."""

import jwt

from derma_shared.settings import settings


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
