import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from backend.api.operator_auth import parse_operator_tokens, require_verification_operator
from backend.api.routes.reports import _validate_image_payload
from backend.config import Settings
from backend.schemas.report import ReportVerificationRequest


def test_operator_token_configuration_maps_stable_operator_ids():
    token = "t" * 40

    assert parse_operator_tokens('{"field-operator-1":"' + token + '"}') == {
        "field-operator-1": token
    }


@pytest.mark.parametrize(
    "raw_tokens",
    [
        "",
        "not-json",
        "[]",
        '{"bad id":"' + ("x" * 40) + '"}',
        '{"operator-a":"short"}',
        '{"operator-a":"' + ("é" * 40) + '"}',
        '{"operator-a":"' + ("x" * 40) + '","operator-b":"' + ("x" * 40) + '"}',
    ],
)
def test_operator_token_configuration_rejects_invalid_values(raw_tokens: str):
    with pytest.raises(ValueError):
        parse_operator_tokens(raw_tokens)


def test_verification_decision_requires_reason_for_rejection_and_review():
    with pytest.raises(ValidationError):
        ReportVerificationRequest(action="reject")
    with pytest.raises(ValidationError):
        ReportVerificationRequest(action="review", reason="  ")


def test_verification_decision_requires_paired_coordinates_and_timezone():
    with pytest.raises(ValidationError):
        ReportVerificationRequest(action="confirm", latitude=19.1)
    with pytest.raises(ValidationError):
        ReportVerificationRequest(
            action="confirm",
            event_timestamp="2024-07-01T10:00:00",
        )


def test_confirmed_decision_preserves_unknown_measured_depth():
    decision = ReportVerificationRequest(
        action="confirm",
        event_timestamp="2024-07-01T10:00:00+05:30",
        latitude=19.1,
        longitude=72.8,
        water_depth="knee",
    )

    assert decision.water_depth == "knee"
    assert decision.water_depth_m is None


def test_operator_evidence_upload_rejects_mismatched_image_content():
    with pytest.raises(HTTPException) as rejected:
        _validate_image_payload("evidence.jpg", b"not an image" * 10)
    assert rejected.value.status_code == 415


@pytest.mark.asyncio
async def test_operator_authentication_fails_closed_and_resolves_named_operator():
    settings = Settings(
        FLOOD_OPERATOR_TOKENS='{"field-operator-1":"' + ("t" * 40) + '"}'
    )

    assert await require_verification_operator(
        authorization="Bearer " + ("t" * 40),
        settings=settings,
    ) == "field-operator-1"
    with pytest.raises(HTTPException) as unauthorized:
        await require_verification_operator(
            authorization="Bearer wrong-token",
            settings=settings,
        )
    assert unauthorized.value.status_code == 401


@pytest.mark.asyncio
async def test_operator_authentication_is_unavailable_without_configuration():
    with pytest.raises(HTTPException) as unavailable:
        await require_verification_operator(
            authorization="Bearer " + ("t" * 40),
            settings=Settings(FLOOD_OPERATOR_TOKENS=""),
        )
    assert unavailable.value.status_code == 503


@pytest.mark.asyncio
async def test_non_ascii_bearer_token_is_rejected_without_auth_error():
    settings = Settings(
        FLOOD_OPERATOR_TOKENS='{"field-operator-1":"' + ("t" * 40) + '"}'
    )

    with pytest.raises(HTTPException) as unauthorized:
        await require_verification_operator(
            authorization="Bearer " + ("é" * 40),
            settings=settings,
        )

    assert unauthorized.value.status_code == 401
