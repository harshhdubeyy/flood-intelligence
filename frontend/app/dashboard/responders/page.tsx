"use client";

import React, { useState, useEffect } from "react";
import {
  Navigation,
  Shield,
  Truck,
  AlertTriangle,
  MapPin,
  Clock,
  ArrowRight,
  Radio,
  CheckCircle2,
  Sliders,
  Compass,
  CornerDownRight,
  RefreshCw,
  Waves
} from "lucide-react";
import {
  fetchRoutingLandmarks,
  fetchBlockedRoads,
  calculateSafeRoute,
  RoutingLandmark,
  BlockedRoadSegment,
  SafeRouteResult
} from "@/lib/api";

export default function RespondersRoutePage() {
  const [landmarks, setLandmarks] = useState<RoutingLandmark[]>([]);
  const [blockedRoads, setBlockedRoads] = useState<BlockedRoadSegment[]>([]);
  const [loading, setLoading] = useState(true);
  const [calculating, setCalculating] = useState(false);

  const [originId, setOriginId] = useState("NODE_KURLA_STATION");
  const [destinationId, setDestinationId] = useState("NODE_KEM_HOSPITAL");
  const [vehicleType, setVehicleType] = useState("standard_ambulance");
  const [avoidWaterlogging, setAvoidWaterlogging] = useState(true);
  const [routeResult, setRouteResult] = useState<SafeRouteResult | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    loadNetworkData();
  }, []);

  async function loadNetworkData() {
    setLoading(true);
    try {
      const [lms, blk] = await Promise.all([
        fetchRoutingLandmarks().catch(() => [
          { id: "NODE_FORT_HQ", name: "BMC Disaster Control Room (Fort)", lat: 18.9322, lon: 72.8335, elevation_m: 12.0, ward: "MH-BMC-A", type: "command_hq" },
          { id: "NODE_KURLA_STATION", name: "Kurla West / Kamani", lat: 19.0688, lon: 72.8797, elevation_m: 4.2, ward: "MH-BMC-L", type: "waterlogged_hotspot" },
          { id: "NODE_KEM_HOSPITAL", name: "KEM Hospital Parel", lat: 19.0028, lon: 72.8423, elevation_m: 14.0, ward: "MH-BMC-FS", type: "hospital" },
          { id: "NODE_DADAR_TT", name: "Dadar TT Circle (Elevated Hub)", lat: 19.0178, lon: 72.8478, elevation_m: 11.5, ward: "MH-BMC-GN", type: "transit_hub" },
          { id: "NODE_MILAN_SUBWAY", name: "Milan Subway (Santacruz)", lat: 19.0833, lon: 72.8415, elevation_m: 3.8, ward: "MH-BMC-HW", type: "subway_bottleneck" },
          { id: "NODE_NANAVATI_HOSP", name: "Nanavati Max Hospital Vile Parle", lat: 19.0975, lon: 72.8420, elevation_m: 12.5, ward: "MH-BMC-KW", type: "hospital" }
        ]),
        fetchBlockedRoads().catch(() => [
          { u: "NODE_KURLA_STATION", v: "NODE_SION_CIRCLE", dist_km: 3.4, time_min: 14, water_depth_m: 0.70, is_closed: true, corridor: "LBS Marg Kurla Surface (Flooded)" },
          { u: "NODE_MILAN_SUBWAY", v: "NODE_BANDRA_STATION", dist_km: 4.0, time_min: 12, water_depth_m: 0.85, is_closed: true, corridor: "Milan Subway Low Crossing (Submerged)" }
        ])
      ]);
      setLandmarks(lms);
      setBlockedRoads(blk);

      // Auto calculate default route
      computeRoute("NODE_KURLA_STATION", "NODE_KEM_HOSPITAL", "standard_ambulance", true);
    } finally {
      setLoading(false);
    }
  }

  async function computeRoute(
    oId = originId,
    dId = destinationId,
    vType = vehicleType,
    avoid = avoidWaterlogging
  ) {
    setCalculating(true);
    setErrorMsg(null);
    try {
      const res = await calculateSafeRoute({
        origin_id: oId,
        destination_id: dId,
        vehicle_type: vType,
        avoid_waterlogging: avoid
      });
      setRouteResult(res);
    } catch (err: any) {
      const detail = err.response?.data?.detail || "Unable to compute safe corridor between selected nodes.";
      setErrorMsg(detail);
      setRouteResult(null);
    } finally {
      setCalculating(false);
    }
  }

  return (
    <div className="flex-1 flex flex-col h-full bg-slate-950 text-slate-100 overflow-y-auto">
      {/* Top Header */}
      <header className="px-8 py-5 border-b border-slate-800/80 bg-slate-900/40 backdrop-blur-md flex items-center justify-between">
        <div>
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
              <Navigation className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
                Emergency Responder Routing & Evacuation
              </h1>
              <p className="text-xs text-slate-400">
                Flood-aware Dijkstra routing for NDRF boats, ambulances, and high-clearance response units
              </p>
            </div>
          </div>
        </div>

        <button
          onClick={() => loadNetworkData()}
          disabled={loading || calculating}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-slate-700 bg-slate-800/80 hover:bg-slate-700 text-xs font-medium text-slate-200 transition-colors"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          Refresh Network State
        </button>
      </header>

      {/* Main Content Area */}
      <div className="p-8 max-w-7xl mx-auto w-full grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Route Planner Controls */}
        <div className="lg:col-span-4 space-y-6">
          <div className="p-5 rounded-xl border border-slate-800 bg-slate-900/60 backdrop-blur-md space-y-5">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-300 flex items-center gap-2">
              <Sliders className="w-4 h-4 text-emerald-400" />
              Route Configuration
            </h2>

            {/* Origin Selection */}
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1.5 flex items-center gap-1.5">
                <MapPin className="w-3.5 h-3.5 text-blue-400" />
                Origin / Incident Site
              </label>
              <select
                value={originId}
                onChange={(e) => {
                  setOriginId(e.target.value);
                  computeRoute(e.target.value, destinationId, vehicleType, avoidWaterlogging);
                }}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-emerald-500"
              >
                {landmarks.map((lm) => (
                  <option key={lm.id} value={lm.id}>
                    {lm.name} ({lm.elevation_m}m elv)
                  </option>
                ))}
              </select>
            </div>

            {/* Destination Selection */}
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1.5 flex items-center gap-1.5">
                <MapPin className="w-3.5 h-3.5 text-rose-400" />
                Destination / Relief Shelter / Hospital
              </label>
              <select
                value={destinationId}
                onChange={(e) => {
                  setDestinationId(e.target.value);
                  computeRoute(originId, e.target.value, vehicleType, avoidWaterlogging);
                }}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-emerald-500"
              >
                {landmarks.map((lm) => (
                  <option key={lm.id} value={lm.id}>
                    {lm.name} ({lm.elevation_m}m elv)
                  </option>
                ))}
              </select>
            </div>

            {/* Vehicle Type Selection */}
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1.5 flex items-center gap-1.5">
                <Truck className="w-3.5 h-3.5 text-amber-400" />
                Emergency Vehicle Profile
              </label>
              <select
                value={vehicleType}
                onChange={(e) => {
                  setVehicleType(e.target.value);
                  computeRoute(originId, destinationId, e.target.value, avoidWaterlogging);
                }}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-emerald-500"
              >
                <option value="standard_ambulance">Standard Ambulance (0.3m clearance)</option>
                <option value="ndrf_high_axle_truck">NDRF High-Axle 4x4 Truck (0.8m clearance)</option>
                <option value="rescue_boat">NDRF Inflatable Rescue Boat (Navigates water)</option>
                <option value="light_vehicle">Light Quick Response Car (0.15m clearance)</option>
              </select>
            </div>

            {/* Avoid Inundated Roads Toggle */}
            <div className="flex items-center justify-between p-3 rounded-lg bg-slate-950/60 border border-slate-800">
              <div className="text-xs">
                <div className="font-medium text-slate-200">Avoid Waterlogged Roads</div>
                <div className="text-[11px] text-slate-400">Strictly bypass closed subways</div>
              </div>
              <input
                type="checkbox"
                checked={avoidWaterlogging}
                onChange={(e) => {
                  setAvoidWaterlogging(e.target.checked);
                  computeRoute(originId, destinationId, vehicleType, e.target.checked);
                }}
                className="w-4 h-4 rounded text-emerald-500 bg-slate-900 border-slate-700"
              />
            </div>

            <button
              onClick={() => computeRoute()}
              disabled={calculating}
              className="w-full py-2.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-xs font-semibold tracking-wide transition-colors flex items-center justify-center gap-2 shadow-lg shadow-emerald-950/40"
            >
              <Compass className={`w-4 h-4 ${calculating ? "animate-spin" : ""}`} />
              {calculating ? "Solving Graph..." : "Recalculate Safe Corridor"}
            </button>
          </div>

          {/* Blocked Corridors Telemetry */}
          <div className="p-5 rounded-xl border border-rose-900/40 bg-rose-950/20 backdrop-blur-md space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-semibold text-rose-400 uppercase tracking-wider flex items-center gap-1.5">
                <AlertTriangle className="w-3.5 h-3.5" />
                Active Road Closures ({blockedRoads.length})
              </h3>
            </div>
            <div className="space-y-2 text-xs">
              {blockedRoads.map((b, i) => (
                <div key={i} className="p-2.5 rounded-lg bg-slate-950/80 border border-rose-900/30">
                  <div className="font-medium text-rose-300">{b.corridor}</div>
                  <div className="flex items-center justify-between mt-1 text-[11px] text-slate-400">
                    <span>Depth: {(b.water_depth_m * 100).toFixed(0)} cm</span>
                    <span className="text-rose-400 font-semibold uppercase">Closed by Traffic Police</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Right Column: Waypoint Route Navigation Steps */}
        <div className="lg:col-span-8 space-y-6">
          {errorMsg && (
            <div className="p-4 rounded-xl border border-rose-800/80 bg-rose-950/50 text-rose-300 text-xs flex items-center gap-3">
              <AlertTriangle className="w-5 h-5 flex-shrink-0" />
              <div>{errorMsg}</div>
            </div>
          )}

          {routeResult && (
            <div className="space-y-6">
              {/* Route Summary Metrics Banner */}
              <div className="p-6 rounded-xl border border-emerald-900/40 bg-gradient-to-br from-emerald-950/30 to-slate-900/80 backdrop-blur-md">
                <div className="flex flex-wrap items-center justify-between gap-4 pb-5 border-b border-slate-800">
                  <div>
                    <div className="text-xs uppercase font-mono tracking-wider text-emerald-400 flex items-center gap-1.5">
                      <CheckCircle2 className="w-4 h-4" />
                      Optimized Safe Transit Corridor
                    </div>
                    <h2 className="text-lg font-bold text-white mt-0.5">
                      {routeResult.origin} <span className="text-slate-500 font-normal">→</span> {routeResult.destination}
                    </h2>
                  </div>

                  <div className="flex items-center gap-3">
                    <div className="px-3 py-1.5 rounded-lg bg-slate-950/80 border border-slate-800 text-center">
                      <div className="text-[10px] text-slate-400 uppercase">Transit Time</div>
                      <div className="text-base font-bold text-emerald-400">{routeResult.estimated_transit_time_min} min</div>
                    </div>
                    <div className="px-3 py-1.5 rounded-lg bg-slate-950/80 border border-slate-800 text-center">
                      <div className="text-[10px] text-slate-400 uppercase">Distance</div>
                      <div className="text-base font-bold text-slate-200">{routeResult.total_distance_km} km</div>
                    </div>
                    <div className="px-3 py-1.5 rounded-lg bg-slate-950/80 border border-slate-800 text-center">
                      <div className="text-[10px] text-slate-400 uppercase">Max Inundation</div>
                      <div className="text-base font-bold text-blue-400">{(routeResult.max_water_depth_on_route_m * 100).toFixed(0)} cm</div>
                    </div>
                  </div>
                </div>

                <div className="mt-4 flex items-center gap-2 text-xs text-slate-300">
                  <Shield className="w-4 h-4 text-emerald-400 flex-shrink-0" />
                  <span>{routeResult.advisory}</span>
                </div>
              </div>

              {/* Step-by-Step Waypoints */}
              <div className="p-6 rounded-xl border border-slate-800 bg-slate-900/60 backdrop-blur-md">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-300 mb-4 flex items-center gap-2">
                  <CornerDownRight className="w-4 h-4 text-emerald-400" />
                  Step-by-Step Tactical Waypoints ({routeResult.waypoints.length})
                </h3>

                <div className="space-y-3">
                  {routeResult.waypoints.map((wp, idx) => {
                    const isStart = idx === 0;
                    const isEnd = idx === routeResult.waypoints.length - 1;

                    return (
                      <div
                        key={wp.node_id}
                        className="p-3.5 rounded-lg bg-slate-950 border border-slate-800/80 flex items-center justify-between"
                      >
                        <div className="flex items-center gap-3">
                          <div
                            className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold ${
                              isStart
                                ? "bg-blue-600 text-white"
                                : isEnd
                                ? "bg-emerald-600 text-white"
                                : "bg-slate-800 text-slate-300"
                            }`}
                          >
                            {wp.step}
                          </div>
                          <div>
                            <div className="text-sm font-semibold text-white flex items-center gap-2">
                              {wp.name}
                              <span className="text-[10px] px-2 py-0.5 rounded bg-slate-800 text-slate-400 uppercase font-mono">
                                Ward {wp.ward}
                              </span>
                            </div>
                            <div className="text-xs text-slate-400 mt-0.5">
                              Type: {wp.type.replace(/_/g, " ")} • Elevation: {wp.elevation_m}m above MSL
                            </div>
                          </div>
                        </div>

                        <div className="text-right">
                          <span
                            className={`text-[10px] px-2.5 py-1 rounded-full font-medium ${
                              wp.elevation_m >= 10
                                ? "bg-emerald-950 text-emerald-400 border border-emerald-800/60"
                                : "bg-amber-950 text-amber-400 border border-amber-800/60"
                            }`}
                          >
                            {wp.elevation_m >= 10 ? "Safe High Ground" : "Low Basin Sector"}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
