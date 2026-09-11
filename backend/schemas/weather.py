"""
Pydantic schemas for weather snapshots and forecast telemetry.
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict


class WeatherSnapshotBase(BaseModel):
    """Base weather telemetry properties."""
    ward_id: Optional[str] = Field(None, description="Ward identifier (e.g., MH-BMC-GN)")
    source: str = Field(default="open-meteo", description="Provider source: openweathermap or open-meteo")
    rainfall_1h_mm: float = Field(default=0.0, description="Precipitation in last 1 hour in mm")
    rainfall_3h_mm: float = Field(default=0.0, description="Precipitation in last 3 hours in mm")
    rainfall_24h_mm: float = Field(default=0.0, description="Precipitation in last 24 hours in mm")
    wind_speed_kmh: float = Field(default=0.0, description="Sustained wind velocity in km/h")
    humidity_pct: float = Field(default=0.0, description="Relative humidity percentage")
    tide_height_m: Optional[float] = Field(None, description="Active Arabian Sea tidal water level in meters")


class WeatherSnapshotCreate(WeatherSnapshotBase):
    """Schema used during ingestion pipeline insertion."""
    pass


class WeatherSnapshotResponse(WeatherSnapshotBase):
    """API response model for latest weather reading."""
    id: int
    fetched_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WeatherForecastItem(BaseModel):
    """Hourly forecast prediction entry from Open-Meteo."""
    timestamp: datetime
    rain_mm: float
    wind_speed_kmh: float
    temperature_c: Optional[float] = None


class WeatherForecastResponse(BaseModel):
    """24-48h forward precipitation forecast for a ward."""
    ward_id: str
    forecast_rain_6h_mm: float
    forecast_rain_12h_mm: float
    forecast_rain_24h_mm: float
    hourly: List[WeatherForecastItem]


class IngestionStatusResponse(BaseModel):
    """Execution status for asynchronous ingestion jobs."""
    status: str
    wards_updated: int
    total_snapshots_recorded: int
    source: str
    message: str
