"""
Safe Evacuation & Emergency Responder Routing API.
Calculates flood-aware shortest paths using weighted Dijkstra/A* routing across
Mumbai's road network, avoiding submerged subways, flooded arterial roads, and high-risk wards per TRD Section 12.
"""

import heapq
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, status

routing_router = APIRouter(prefix="/routing", tags=["Emergency Routing"])


class RouteRequest(BaseModel):
    origin_id: str = Field(..., description="Starting landmark / station ID")
    destination_id: str = Field(..., description="Destination landmark / relief hospital ID")
    vehicle_type: str = Field("standard_ambulance", description="standard_ambulance, ndrf_high_axle_truck, rescue_boat, light_vehicle")
    avoid_waterlogging: bool = Field(True, description="Strictly avoid waterlogged sectors")


# Mumbai Road Network Nodes (Coordinates & Elevation)
MUMBAI_NODES: Dict[str, Dict[str, Any]] = {
    "NODE_FORT_HQ": {"name": "BMC Disaster Control Room (Fort)", "lat": 18.9322, "lon": 72.8335, "elevation_m": 12.0, "ward": "MH-BMC-A", "type": "command_hq"},
    "NODE_DADAR_TT": {"name": "Dadar TT Circle (Elevated Hub)", "lat": 19.0178, "lon": 72.8478, "elevation_m": 11.5, "ward": "MH-BMC-GN", "type": "transit_hub"},
    "NODE_KEM_HOSPITAL": {"name": "KEM Hospital Parel", "lat": 19.0028, "lon": 72.8423, "elevation_m": 14.0, "ward": "MH-BMC-FS", "type": "hospital"},
    "NODE_HINDMATA": {"name": "Hindmata Junction (Low Basin)", "lat": 19.0118, "lon": 72.8427, "elevation_m": 4.5, "ward": "MH-BMC-GN", "type": "waterlogged_hotspot"},
    "NODE_SION_CIRCLE": {"name": "Sion Circle / Gandhi Market", "lat": 19.0392, "lon": 72.8619, "elevation_m": 5.2, "ward": "MH-BMC-FN", "type": "waterlogged_hotspot"},
    "NODE_KURLA_STATION": {"name": "Kurla West / Kamani", "lat": 19.0688, "lon": 72.8797, "elevation_m": 4.2, "ward": "MH-BMC-L", "type": "waterlogged_hotspot"},
    "NODE_BKC_CONNECTOR": {"name": "BKC Elevated Flyover", "lat": 19.0585, "lon": 72.8660, "elevation_m": 13.0, "ward": "MH-BMC-L", "type": "elevated_corridor"},
    "NODE_BANDRA_STATION": {"name": "Bandra West Station", "lat": 19.0544, "lon": 72.8402, "elevation_m": 9.0, "ward": "MH-BMC-HW", "type": "transit_hub"},
    "NODE_MILAN_SUBWAY": {"name": "Milan Subway (Santacruz)", "lat": 19.0833, "lon": 72.8415, "elevation_m": 3.8, "ward": "MH-BMC-HW", "type": "subway_bottleneck"},
    "NODE_WEH_SANTACRUZ": {"name": "Western Express Highway (Santacruz Flyover)", "lat": 19.0810, "lon": 72.8520, "elevation_m": 15.0, "ward": "MH-BMC-HE", "type": "elevated_corridor"},
    "NODE_NANAVATI_HOSP": {"name": "Nanavati Max Hospital Vile Parle", "lat": 19.0975, "lon": 72.8420, "elevation_m": 12.5, "ward": "MH-BMC-KW", "type": "hospital"},
    "NODE_ANDHERI_SUBWAY": {"name": "Andheri Subway (Low Crossing)", "lat": 19.1197, "lon": 72.8468, "elevation_m": 3.2, "ward": "MH-BMC-KW", "type": "subway_bottleneck"},
    "NODE_ANDHERI_FLYOVER": {"name": "Gokhale Bridge / WEH Elevated", "lat": 19.1170, "lon": 72.8550, "elevation_m": 16.0, "ward": "MH-BMC-KE", "type": "elevated_corridor"},
    "NODE_CHEMBUR_MONORAIL": {"name": "Chembur Eastern Freeway Access", "lat": 19.0622, "lon": 72.8988, "elevation_m": 11.0, "ward": "MH-BMC-ME", "type": "elevated_corridor"},
}

# Road segments (from_node, to_node, distance_km, base_transit_min, water_depth_m, is_closed)
ROAD_EDGES = [
    # South to Central
    {"u": "NODE_FORT_HQ", "v": "NODE_KEM_HOSPITAL", "dist_km": 8.5, "time_min": 18, "water_depth_m": 0.05, "is_closed": False, "corridor": "Dr. Ambedkar Road"},
    {"u": "NODE_KEM_HOSPITAL", "v": "NODE_HINDMATA", "dist_km": 1.2, "time_min": 4, "water_depth_m": 0.55, "is_closed": True, "corridor": "Hindmata Surface Road (Flooded)"},
    {"u": "NODE_KEM_HOSPITAL", "v": "NODE_DADAR_TT", "dist_km": 2.1, "time_min": 5, "water_depth_m": 0.10, "is_closed": False, "corridor": "Parel Flyover Bypass (Safe Elevated)"},
    {"u": "NODE_HINDMATA", "v": "NODE_DADAR_TT", "dist_km": 1.1, "time_min": 8, "water_depth_m": 0.60, "is_closed": True, "corridor": "Hindmata Underpass"},
    {"u": "NODE_DADAR_TT", "v": "NODE_SION_CIRCLE", "dist_km": 2.8, "time_min": 7, "water_depth_m": 0.35, "is_closed": False, "corridor": "Dr. Ambedkar Road North"},

    # Central to Suburban & Kurla
    {"u": "NODE_SION_CIRCLE", "v": "NODE_BKC_CONNECTOR", "dist_km": 2.5, "time_min": 6, "water_depth_m": 0.05, "is_closed": False, "corridor": "Sion-BKC Elevated Connector"},
    {"u": "NODE_SION_CIRCLE", "v": "NODE_KURLA_STATION", "dist_km": 3.4, "time_min": 14, "water_depth_m": 0.70, "is_closed": True, "corridor": "LBS Marg Kurla Surface (Flooded)"},
    {"u": "NODE_BKC_CONNECTOR", "v": "NODE_KURLA_STATION", "dist_km": 1.8, "time_min": 5, "water_depth_m": 0.20, "is_closed": False, "corridor": "BKC Elevated Spur to Kurla West"},
    {"u": "NODE_BKC_CONNECTOR", "v": "NODE_BANDRA_STATION", "dist_km": 3.2, "time_min": 8, "water_depth_m": 0.10, "is_closed": False, "corridor": "BKC Arterial Road"},

    # Bandra to Western Suburbs
    {"u": "NODE_BANDRA_STATION", "v": "NODE_MILAN_SUBWAY", "dist_km": 4.0, "time_min": 12, "water_depth_m": 0.85, "is_closed": True, "corridor": "SV Road through Milan Subway (Submerged)"},
    {"u": "NODE_BANDRA_STATION", "v": "NODE_WEH_SANTACRUZ", "dist_km": 3.5, "time_min": 7, "water_depth_m": 0.05, "is_closed": False, "corridor": "Western Express Highway Main Carriageway"},
    {"u": "NODE_WEH_SANTACRUZ", "v": "NODE_NANAVATI_HOSP", "dist_km": 2.2, "time_min": 5, "water_depth_m": 0.10, "is_closed": False, "corridor": "Vile Parle East Flyover to SV Road"},
    {"u": "NODE_MILAN_SUBWAY", "v": "NODE_NANAVATI_HOSP", "dist_km": 1.5, "time_min": 6, "water_depth_m": 0.40, "is_closed": True, "corridor": "SV Road Direct"},

    # Andheri Suburbs
    {"u": "NODE_NANAVATI_HOSP", "v": "NODE_ANDHERI_SUBWAY", "dist_km": 2.8, "time_min": 10, "water_depth_m": 0.90, "is_closed": True, "corridor": "Andheri Subway Low Crossing (Flooded)"},
    {"u": "NODE_NANAVATI_HOSP", "v": "NODE_ANDHERI_FLYOVER", "dist_km": 3.0, "time_min": 7, "water_depth_m": 0.05, "is_closed": False, "corridor": "Gokhale Elevated Bridge Route (Safe)"},
    {"u": "NODE_ANDHERI_SUBWAY", "v": "NODE_ANDHERI_FLYOVER", "dist_km": 1.0, "time_min": 4, "water_depth_m": 0.45, "is_closed": False, "corridor": "Station Link Road"},

    # Eastern Connectivity
    {"u": "NODE_KURLA_STATION", "v": "NODE_CHEMBUR_MONORAIL", "dist_km": 3.1, "time_min": 8, "water_depth_m": 0.15, "is_closed": False, "corridor": "SCLR Santa Cruz Chembur Link Road"},
    {"u": "NODE_SION_CIRCLE", "v": "NODE_CHEMBUR_MONORAIL", "dist_km": 4.5, "time_min": 9, "water_depth_m": 0.05, "is_closed": False, "corridor": "Eastern Express Highway to Chembur"},
]


@routing_router.get("/landmarks", summary="Get all emergency navigation nodes, hospitals, and command hubs")
async def get_routing_landmarks():
    """
    Lists all navigational waypoints and their current inundation risk state.
    """
    return {
        "count": len(MUMBAI_NODES),
        "landmarks": [
            {"id": k, **v} for k, v in MUMBAI_NODES.items()
        ]
    }


@routing_router.get("/blocked-roads", summary="Get list of currently flooded and closed road corridors")
async def get_blocked_roads():
    """
    Returns active traffic closures due to waterlogging and submerged subways.
    """
    blocked = [e for e in ROAD_EDGES if e["is_closed"] or e["water_depth_m"] >= 0.4]
    return {
        "total_blocked_segments": len(blocked),
        "segments": blocked
    }


@routing_router.post("/safe-path", summary="Compute flood-resilient safe route for emergency responders")
async def calculate_safe_path(req: RouteRequest):
    """
    Runs Dijkstra's algorithm with flood penalties:
    Impassable segments are avoided; waterlogged routes incur high travel time penalties.
    """
    if req.origin_id not in MUMBAI_NODES or req.destination_id not in MUMBAI_NODES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Origin or destination node ID not found in Mumbai emergency network."
        )

    # Max water depth clearance by vehicle type
    depth_clearance = {
        "light_vehicle": 0.15,
        "standard_ambulance": 0.30,
        "ndrf_high_axle_truck": 0.80,
        "rescue_boat": 9.99  # boats operate on flooded water
    }.get(req.vehicle_type, 0.30)

    # Build bidirectional adjacency graph
    adj: Dict[str, List[Dict[str, Any]]] = {n: [] for n in MUMBAI_NODES}
    for e in ROAD_EDGES:
        u, v = e["u"], e["v"]
        water_depth = e["water_depth_m"]
        is_closed = e["is_closed"]

        # Check vehicle passability
        if req.vehicle_type != "rescue_boat":
            if req.avoid_waterlogging and (is_closed or water_depth > depth_clearance):
                # Impassable edge for this vehicle
                continue

        # Effective weight calculation
        # Base transit time + penalty for water depth
        flood_penalty = 0.0
        if water_depth > 0.1:
            flood_penalty = water_depth * 15.0  # Slows speed substantially

        weight = e["time_min"] + flood_penalty
        adj[u].append({"to": v, "weight": weight, "edge": e})
        adj[v].append({"to": u, "weight": weight, "edge": e})

    # Dijkstra priority queue
    pq = [(0.0, req.origin_id, [])]
    visited = set()
    best_cost = {n: float("inf") for n in MUMBAI_NODES}
    best_cost[req.origin_id] = 0.0

    target_path = None
    target_cost = None

    while pq:
        cost, current, path = heapq.heappop(pq)

        if current in visited:
            continue
        visited.add(current)

        if current == req.destination_id:
            target_path = path + [current]
            target_cost = cost
            break

        for neighbor in adj[current]:
            nxt = neighbor["to"]
            new_cost = cost + neighbor["weight"]
            if new_cost < best_cost[nxt]:
                best_cost[nxt] = new_cost
                heapq.heappush(pq, (new_cost, nxt, path + [current]))

    if not target_path:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"No safe passage exists between {req.origin_id} and {req.destination_id} for vehicle type '{req.vehicle_type}'. All intermediate routes submerged."
        )

    # Reconstruct path details
    waypoint_details = []
    total_dist_km = 0.0
    max_encountered_depth = 0.0

    for i, node_id in enumerate(target_path):
        node_info = MUMBAI_NODES[node_id]
        waypoint_details.append({
            "step": i + 1,
            "node_id": node_id,
            "name": node_info["name"],
            "lat": node_info["lat"],
            "lon": node_info["lon"],
            "elevation_m": node_info["elevation_m"],
            "type": node_info["type"],
            "ward": node_info["ward"]
        })

    # Calculate distance and max depth along the chosen edges
    for i in range(len(target_path) - 1):
        u = target_path[i]
        v = target_path[i + 1]
        for e in ROAD_EDGES:
            if (e["u"] == u and e["v"] == v) or (e["u"] == v and e["v"] == u):
                total_dist_km += e["dist_km"]
                if e["water_depth_m"] > max_encountered_depth:
                    max_encountered_depth = e["water_depth_m"]
                break

    return {
        "status": "route_found",
        "origin": MUMBAI_NODES[req.origin_id]["name"],
        "destination": MUMBAI_NODES[req.destination_id]["name"],
        "vehicle_type": req.vehicle_type,
        "estimated_transit_time_min": round(target_cost, 1),
        "total_distance_km": round(total_dist_km, 1),
        "max_water_depth_on_route_m": max_encountered_depth,
        "is_safe_elevated_route": max_encountered_depth <= 0.15,
        "waypoints_count": len(waypoint_details),
        "waypoints": waypoint_details,
        "advisory": (
            "Route cleared via elevated flyover corridors. Exercise standard wet-weather caution."
            if max_encountered_depth <= 0.15
            else "Caution: Route passes through low-water section. Maintain high-clearance speeds."
        )
    }
