"""
Health check schema models.
"""

from datetime import datetime
from typing import Dict, Any
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Schema model for service health status and telemetry."""
    status: str = Field(..., description="Overall system health status: ok | degraded | unhealthy")
    timestamp: datetime = Field(..., description="UTC timestamp of the health check")
    version: str = Field(..., description="Current application and API version")
    services: Dict[str, Any] = Field(default_factory=dict, description="Status of auxiliary connected services")
