# Placeholder for backend/api/routes/signals.py
"""
IoT Telemetry & Radar Signal Ingestion API.
Manages real-time data streams from Mumbai municipal ultrasonic water level gauges,
Arabian Sea coastal tide sensors, and IMD Doppler weather radar feeds per TRD Section 6.
"""

from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, status

from backend.api.websocket import ws_manager

signals_router = APIRouter(prefix="/signals", tags=["IoT & Telemetry Signals"])


class IOTReadingIn(BaseModel):
    sensor_id: str = Field(..., description="Unique hardware identifier")
    sensor_type: str = Field(..., description="water_level, rain_gauge, tide_gauge, flow_velocity")
    ward_id: Optional[str] = Field(None, description="Administrative ward ID")
    location_name: str = Field(..., description="Landmark name")
    latitude: float = Field(..., description="WGS84 latitude")
    longitude: float = Field(..., description="WGS84 longitude")
    value: float = Field(..., description="Metric value (meters, mm/h, m/s)")
    unit: str = Field(..., description="Unit of measurement")
    battery_pct: Optional[float] = Field(98.0, description="Battery percentage")
    status: Optional[str] = Field("normal", description="normal, warning, critical, offline")


# Simulated state for Mumbai IoT sensor network
LIVE_SENSORS: Dict[str, Dict[str, Any]] = {
    "SENS-MITHI-01": {
        "sensor_id": "SENS-MITHI-01",
        "name": "Mithi River - BKC Bridge Ultrasonic Gauge",
        "sensor_type": "water_level",
        "ward_id": "MH-BMC-L",
        "location_name": "BKC Connector / Mithi River",
        "latitude": 19.0607,
        "longitude": 72.8683,
        "value": 2.45,
        "unit": "meters",
        "danger_mark": 3.80,
        "warning_mark": 2.70,
        "status": "warning",
        "battery_pct": 94.0,
        "last_updated": datetime.now(timezone.utc).isoformat()
    },
    "SENS-HINDMATA-02": {
        "sensor_id": "SENS-HINDMATA-02",
        "name": "Hindmata Underground Holding Tank Sensor",
        "sensor_type": "water_level",
        "ward_id": "MH-BMC-GN",
        "location_name": "Hindmata Flyover Underpass",
        "latitude": 19.0118,
        "longitude": 72.8427,
        "value": 0.42,
        "unit": "meters",
        "danger_mark": 0.80,
        "warning_mark": 0.35,
        "status": "warning",
        "battery_pct": 89.0,
        "last_updated": datetime.now(timezone.utc).isoformat()
    },
    "SENS-MILAN-03": {
        "sensor_id": "SENS-MILAN-03",
        "name": "Milan Subway Sonar Depth Sensor",
        "sensor_type": "water_level",
        "ward_id": "MH-BMC-HW",
        "location_name": "Milan Subway Santacruz",
        "latitude": 19.0833,
        "longitude": 72.8415,
        "value": 0.15,
        "unit": "meters",
        "danger_mark": 0.60,
        "warning_mark": 0.25,
        "status": "normal",
        "battery_pct": 99.0,
        "last_updated": datetime.now(timezone.utc).isoformat()
    },
    "SENS-ANDHERI-04": {
        "sensor_id": "SENS-ANDHERI-04",
        "name": "Andheri Subway Optical Inundation Sensor",
        "sensor_type": "water_level",
        "ward_id": "MH-BMC-KW",
        "location_name": "Andheri Subway West",
        "latitude": 19.1197,
        "longitude": 72.8468,
        "value": 0.28,
        "unit": "meters",
        "danger_mark": 0.60,
        "warning_mark": 0.30,
        "status": "normal",
        "battery_pct": 92.0,
        "last_updated": datetime.now(timezone.utc).isoformat()
    },
    "SENS-TIDE-COLABA": {
        "sensor_id": "SENS-TIDE-COLABA",
        "name": "Apollo Bunder Coastal Tide Gauge",
        "sensor_type": "tide_gauge",
        "ward_id": "MH-BMC-A",
        "location_name": "Gateway of India / Apollo Bunder",
        "latitude": 18.9220,
        "longitude": 72.8347,
        "value": 3.92,
        "unit": "meters",
        "danger_mark": 4.50,
        "warning_mark": 3.80,
        "status": "warning",
        "battery_pct": 100.0,
        "last_updated": datetime.now(timezone.utc).isoformat()
    },
    "SENS-TIDE-BANDRA": {
        "sensor_id": "SENS-TIDE-BANDRA",
        "name": "Bandra-Worli Sea Link Acoustic Gauge",
        "sensor_type": "tide_gauge",
        "ward_id": "MH-BMC-HW",
        "location_name": "BWSL Toll Plaza Coast",
        "latitude": 19.0368,
        "longitude": 72.8173,
        "value": 3.88,
        "unit": "meters",
        "danger_mark": 4.50,
        "warning_mark": 3.80,
        "status": "warning",
        "battery_pct": 97.0,
        "last_updated": datetime.now(timezone.utc).isoformat()
    },
    "SENS-POWAI-05": {
        "sensor_id": "SENS-POWAI-05",
        "name": "Powai Lake Weir Discharge Sensor",
        "sensor_type": "flow_velocity",
        "ward_id": "MH-BMC-S",
        "location_name": "Powai Lake Spillway",
        "latitude": 19.1274,
        "longitude": 72.9048,
        "value": 28.5,
        "unit": "m3/s",
        "danger_mark": 60.0,
        "warning_mark": 35.0,
        "status": "normal",
        "battery_pct": 95.0,
        "last_updated": datetime.now(timezone.utc).isoformat()
    }
}


@signals_router.get("/live", summary="Get all live IoT telemetry station readings")
async def get_live_sensor_readings():
    """
    Returns latest telemetry from all active water level, tidal, and discharge sensors.
    """
    return {
        "count": len(LIVE_SENSORS),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sensors": list(LIVE_SENSORS.values())
    }


@signals_router.post("/iot", status_code=status.HTTP_201_CREATED, summary="Ingest hardware sensor telemetry")
async def ingest_iot_reading(reading: IOTReadingIn):
    """
    Receives an edge IoT gauge reading, updates internal state, and broadcasts over WebSockets.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    station = LIVE_SENSORS.get(reading.sensor_id, {})

    updated_data = {
        "sensor_id": reading.sensor_id,
        "name": station.get("name", f"Station {reading.sensor_id}"),
        "sensor_type": reading.sensor_type,
        "ward_id": reading.ward_id or station.get("ward_id"),
        "location_name": reading.location_name,
        "latitude": reading.latitude,
        "longitude": reading.longitude,
        "value": reading.value,
        "unit": reading.unit,
        "danger_mark": station.get("danger_mark", 3.0),
        "warning_mark": station.get("warning_mark", 2.0),
        "status": reading.status or ("warning" if reading.value >= station.get("warning_mark", 2.0) else "normal"),
        "battery_pct": reading.battery_pct,
        "last_updated": now_iso
    }
    LIVE_SENSORS[reading.sensor_id] = updated_data

    # Push to live WebSocket subscribers
    await ws_manager.broadcast_sensor(updated_data)

    return {
        "status": "ingested",
        "sensor_id": reading.sensor_id,
        "timestamp": now_iso
    }


@signals_router.get("/tides", summary="Get 24-hour Arabian Sea tidal forecast and spring tide alerts")
async def get_tide_telemetry():
    """
    Provides 24-hour tidal curve for Mumbai coast (Apollo Bunder / Colaba datum).
    Critical flood thresholds: Tide > 4.2m is severe risk; > 4.5m triggers spring tide emergency.
    """
    now = datetime.now(timezone.utc)
    # Generate 12 timestamps around current time
    curve = []
    for h in range(-4, 9):
        t = now + timedelta(hours=h)
        # 12.4 hour semi-diurnal tidal sinusoid peaking at ~4.1m
        cycle_angle = (h + 1) * (2 * 3.14159 / 12.4)
        tide_height = round(2.5 + 1.6 * (1 - (0.5 * (1 + cycle_angle % 2))), 2)
        is_high = tide_height > 3.7
        curve.append({
            "timestamp": t.isoformat(),
            "time_str": t.strftime("%H:%M IST"),
            "height_m": tide_height,
            "stage": "high" if is_high else "low",
            "sluice_gates_status": "closed" if tide_height >= 3.8 else "open"
        })

    current_tide = curve[4]["height_m"]  # at h=0

    return {
        "current_tide_m": current_tide,
        "tidal_stage": "spring_tide" if current_tide >= 4.2 else "high_tide" if current_tide >= 3.8 else "normal",
        "sluice_gates_locked": current_tide >= 3.8,
        "tide_datum": "Mumbai Chart Datum (CD)",
        "curve_24h": curve
    }


@signals_router.get("/radar", summary="Get IMD Doppler weather radar summary for Greater Mumbai")
async def get_radar_summary():
    """
    Synthesizes IMD Doppler weather radar reflectivity (dBZ) and storm cloud motion vectors.
    """
    return {
        "radar_station": "IMD Colaba & Santacruz Doppler Weather Radar (DWR)",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "peak_reflectivity_dbz": 48.5,
        "rain_rate_equivalent_mmh": 54.0,
        "storm_motion_direction": "South-West to North-East (Arabian Sea incoming)",
        "storm_speed_kmh": 22.0,
        "convective_cells": [
            {"cell_id": "CELL-A", "lat": 19.04, "lon": 72.84, "dbz": 51.0, "intensity": "extreme", "area": "Dharavi / Sion"},
            {"cell_id": "CELL-B", "lat": 19.12, "lon": 72.85, "dbz": 46.5, "intensity": "severe", "area": "Andheri Subway / Juhu"},
            {"cell_id": "CELL-C", "lat": 19.07, "lon": 72.88, "dbz": 49.0, "intensity": "severe", "area": "Kurla / BKC"}
        ]
    }
