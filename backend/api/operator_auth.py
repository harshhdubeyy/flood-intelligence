"""Authentication for operator-only flood report verification actions."""

import hmac
import json
import logging
import re
from typing import Dict, Optional

from fastapi import Depends, Header, HTTPException, status

from backend.config import Settings, get_settings

logger = logging.getLogger("fip.api.operator_auth")
OPERATOR_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")
MIN_TOKEN_LENGTH = 32


def parse_operator_tokens(raw_tokens: str) -> Dict[str, str]:
    """Parse configured operator IDs and high-entropy bearer tokens."""
    try:
        tokens = json.loads(raw_tokens)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("FLOOD_OPERATOR_TOKENS must be a JSON object.") from exc
    if not isinstance(tokens, dict) or not tokens:
        raise ValueError("FLOOD_OPERATOR_TOKENS must contain at least one operator.")

    parsed: Dict[str, str] = {}
    seen_token_values = set()
    for operator_id, token in tokens.items():
        if not isinstance(operator_id, str) or not OPERATOR_ID_PATTERN.fullmatch(operator_id):
            raise ValueError("FLOOD_OPERATOR_TOKENS contains an invalid operator ID.")
        if (
            not isinstance(token, str)
            or len(token) < MIN_TOKEN_LENGTH
            or not token.isascii()
        ):
            raise ValueError(
                "Each operator token must contain at least 32 ASCII characters."
            )
        if token in seen_token_values:
            raise ValueError("Each operator must have a unique token.")
        seen_token_values.add(token)
        parsed[operator_id] = token
    return parsed


async def require_verification_operator(
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
    settings: Settings = Depends(get_settings),
) -> str:
    """Return the configured operator ID or fail closed."""
    try:
        operator_tokens = parse_operator_tokens(settings.flood_operator_tokens)
    except ValueError as exc:
        logger.error("Operator verification authentication is unavailable: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Operator verification is not configured.",
        ) from exc

    scheme, separator, supplied_token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not separator or not supplied_token:
        logger.warning("Operator authentication rejected: bearer token was not supplied.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Operator bearer token required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    matched_operators = (
        [
            operator_id
            for operator_id, configured_token in operator_tokens.items()
            if hmac.compare_digest(supplied_token, configured_token)
        ]
        if supplied_token.isascii()
        else []
    )
    if len(matched_operators) != 1:
        logger.warning("Operator authentication rejected: credentials did not match a configured operator.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid operator credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return matched_operators[0]
