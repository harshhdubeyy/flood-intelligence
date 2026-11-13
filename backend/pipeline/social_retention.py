"""Provider-specific opt-in policies for social data retention and collection."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import FrozenSet, Optional

from backend.config import Settings

SUPPORTED_FIELDS = frozenset(
    {
        "external_post_id",
        "original_url",
        "text_content",
        "posted_at",
        "matched_keywords",
        "location",
        "media_references",
    }
)


@dataclass(frozen=True)
class ProviderRetentionPolicy:
    platform: str
    approved: bool
    retention_days: Optional[int]
    reconcile_interval_hours: Optional[int]
    allowed_fields: FrozenSet[str]
    lifecycle_enabled: bool
    tombstone_key_configured: bool

    @property
    def can_collect(self) -> bool:
        return (
            self.lifecycle_enabled
            and self.approved
            and self.retention_days is not None
            and self.reconcile_interval_hours is not None
            and "external_post_id" in self.allowed_fields
            and self.tombstone_key_configured
        )

    def expiration_at(self, collected_at: datetime) -> Optional[datetime]:
        if self.retention_days is None:
            return None
        return collected_at + timedelta(days=self.retention_days)


def provider_retention_policy(
    settings: Settings, platform: str
) -> ProviderRetentionPolicy:
    if platform not in {"reddit", "x"}:
        raise ValueError(f"Unsupported social provider: {platform}")
    prefix = "social_reddit" if platform == "reddit" else "social_x"
    allowed_fields = frozenset(getattr(settings, f"{prefix}_allowed_fields"))
    if not allowed_fields.issubset(SUPPORTED_FIELDS):
        allowed_fields = frozenset()
    return ProviderRetentionPolicy(
        platform=platform,
        approved=getattr(settings, f"{prefix}_policy_approved"),
        retention_days=getattr(settings, f"{prefix}_retention_days"),
        reconcile_interval_hours=getattr(
            settings, f"{prefix}_reconcile_interval_hours"
        ),
        allowed_fields=allowed_fields,
        lifecycle_enabled=settings.social_lifecycle_enabled,
        tombstone_key_configured=(
            len(settings.social_tombstone_hmac_key.encode("utf-8")) >= 32
        ),
    )


def collection_policy_ready(settings: Settings, platform: str) -> bool:
    return (
        settings.social_collection_enabled
        and provider_retention_policy(settings, platform).can_collect
    )
