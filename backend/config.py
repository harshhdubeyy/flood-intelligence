"""
Configuration management for the Flood Intelligence Platform backend.

Uses Pydantic Settings (v2) to validate and load all environment variables
without direct calls to `os.environ`.
"""

from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings and environment configuration."""

    # App & Runtime
    app_name: str = "Flood Intelligence Platform"
    environment: str = Field(default="development", alias="ENVIRONMENT")
    debug: bool = Field(default=True, alias="DEBUG")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    cors_origins: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://floodintelligence.in"
    ]

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://fip_user:fip_password@localhost:5432/fip_db",
        alias="DATABASE_URL"
    )
    database_sync_url: str = Field(
        default="postgresql://fip_user:fip_password@localhost:5432/fip_db",
        alias="DATABASE_SYNC_URL"
    )

    # Redis
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        alias="REDIS_URL"
    )

    # Kafka
    kafka_bootstrap_servers: str = Field(
        default="localhost:29092",
        alias="KAFKA_BOOTSTRAP_SERVERS"
    )
    kafka_topic_weather: str = Field(default="weather-raw", alias="KAFKA_TOPIC_WEATHER")
    kafka_topic_social: str = Field(default="social-posts-raw", alias="KAFKA_TOPIC_SOCIAL")
    kafka_topic_reports: str = Field(default="citizen-reports-raw", alias="KAFKA_TOPIC_REPORTS")
    kafka_topic_risk_scores: str = Field(default="risk-scores-out", alias="KAFKA_TOPIC_RISK_SCORES")
    kafka_topic_alerts: str = Field(default="alerts-dispatched", alias="KAFKA_TOPIC_ALERTS")

    # Security & Auth
    jwt_secret_key: str = Field(
        default="super-secret-jwt-signing-key-change-in-production-min32chars",
        alias="JWT_SECRET_KEY"
    )
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_access_token_expire_minutes: int = Field(default=60, alias="JWT_ACCESS_TOKEN_EXPIRE_MINUTES")
    flood_operator_tokens: str = Field(default="", alias="FLOOD_OPERATOR_TOKENS")

    # External APIs
    openweathermap_api_key: str = Field(default="", alias="OPENWEATHERMAP_API_KEY")
    opentopography_api_key: str = Field(default="", alias="OPENTOPOGRAPHY_API_KEY")
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")

    # Storage
    aws_access_key_id: str = Field(default="", alias="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: str = Field(default="", alias="AWS_SECRET_ACCESS_KEY")
    aws_region: str = Field(default="ap-south-1", alias="AWS_REGION")
    aws_s3_bucket_name: str = Field(default="mumbai-flood-reports", alias="AWS_S3_BUCKET_NAME")
    verification_evidence_storage: str = Field(
        default="local", alias="VERIFICATION_EVIDENCE_STORAGE"
    )
    verification_evidence_local_dir: str = Field(
        default="/tmp/flood_verification_evidence",
        alias="VERIFICATION_EVIDENCE_LOCAL_DIR",
    )
    verification_evidence_s3_bucket: str = Field(
        default="", alias="VERIFICATION_EVIDENCE_S3_BUCKET"
    )

    cloudinary_cloud_name: str = Field(default="", alias="CLOUDINARY_CLOUD_NAME")
    cloudinary_api_key: str = Field(default="", alias="CLOUDINARY_API_KEY")
    cloudinary_api_secret: str = Field(default="", alias="CLOUDINARY_API_SECRET")

    # Notifications
    twilio_account_sid: str = Field(default="", alias="TWILIO_ACCOUNT_SID")
    twilio_auth_token: str = Field(default="", alias="TWILIO_AUTH_TOKEN")
    twilio_whatsapp_number: str = Field(default="whatsapp:+14155238886", alias="TWILIO_WHATSAPP_NUMBER")

    gupshup_api_key: str = Field(default="", alias="GUPSHUP_API_KEY")
    gupshup_app_name: str = Field(default="mumbai_flood_alerts", alias="GUPSHUP_APP_NAME")

    alert_dispatch_enabled: bool = Field(default=False, alias="ALERT_DISPATCH_ENABLED")
    alert_default_radius_km: float = Field(default=5.0, alias="ALERT_DEFAULT_RADIUS_KM")
    alert_location_freshness_hours: int = Field(default=72, alias="ALERT_LOCATION_FRESHNESS_HOURS")
    vapid_private_key: str = Field(default="", alias="VAPID_PRIVATE_KEY")
    vapid_public_key: str = Field(default="", alias="VAPID_PUBLIC_KEY")
    vapid_claims_email: str = Field(
        default="mailto:disaster-management@mcgm.gov.in", alias="VAPID_CLAIMS_EMAIL"
    )
    fcm_server_key: str = Field(default="", alias="FCM_SERVER_KEY")
    alert_max_retries: int = Field(default=3, alias="ALERT_MAX_RETRIES")
    alert_retry_backoff_seconds: float = Field(default=1.0, alias="ALERT_RETRY_BACKOFF_SECONDS")
    alert_rate_limit_per_second: int = Field(default=50, alias="ALERT_RATE_LIMIT_PER_SECOND")

    # Social Media
    twitter_bearer_token: str = Field(default="", alias="TWITTER_BEARER_TOKEN")
    reddit_client_id: str = Field(default="", alias="REDDIT_CLIENT_ID")
    reddit_client_secret: str = Field(default="", alias="REDDIT_CLIENT_SECRET")
    reddit_user_agent: str = Field(default="FloodIntelligenceBot/1.0", alias="REDDIT_USER_AGENT")
    social_collection_enabled: bool = Field(
        default=False, alias="SOCIAL_COLLECTION_ENABLED"
    )
    social_lifecycle_enabled: bool = Field(
        default=False, alias="SOCIAL_LIFECYCLE_ENABLED"
    )
    social_lifecycle_dry_run: bool = Field(
        default=True, alias="SOCIAL_LIFECYCLE_DRY_RUN"
    )
    social_tombstone_hmac_key: str = Field(
        default="", alias="SOCIAL_TOMBSTONE_HMAC_KEY"
    )
    social_reddit_policy_approved: bool = Field(
        default=False, alias="SOCIAL_REDDIT_POLICY_APPROVED"
    )
    social_reddit_retention_days: Optional[int] = Field(
        default=None, gt=0, alias="SOCIAL_REDDIT_RETENTION_DAYS"
    )
    social_reddit_reconcile_interval_hours: Optional[int] = Field(
        default=None, gt=0, alias="SOCIAL_REDDIT_RECONCILE_INTERVAL_HOURS"
    )
    social_reddit_allowed_fields: List[str] = Field(
        default_factory=list, alias="SOCIAL_REDDIT_ALLOWED_FIELDS"
    )
    social_x_policy_approved: bool = Field(
        default=False, alias="SOCIAL_X_POLICY_APPROVED"
    )
    social_x_retention_days: Optional[int] = Field(
        default=None, gt=0, alias="SOCIAL_X_RETENTION_DAYS"
    )
    social_x_reconcile_interval_hours: Optional[int] = Field(
        default=None, gt=0, alias="SOCIAL_X_RECONCILE_INTERVAL_HOURS"
    )
    social_x_allowed_fields: List[str] = Field(
        default_factory=list, alias="SOCIAL_X_ALLOWED_FIELDS"
    )

    # Computer Vision & YOLO Inference
    flood_yolo_model_path: str = Field(
        default="backend/models/cv/best_flood_yolo.pt",
        alias="FLOOD_YOLO_MODEL_PATH"
    )
    flood_yolo_conf_threshold: float = Field(
        default=0.25,
        alias="FLOOD_YOLO_CONF_THRESHOLD"
    )
    flood_yolo_device: str = Field(
        default="cpu",
        alias="FLOOD_YOLO_DEVICE"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )


def get_settings() -> Settings:
    """Return cached application configuration instance."""
    return Settings()
