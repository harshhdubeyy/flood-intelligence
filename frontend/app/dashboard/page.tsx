"use client";

import React, { useState, useMemo } from "react";
import WardRiskLayer from "../../components/Map/WardRiskLayer";
import { useWardRisk } from "../../hooks/useWardRisk";
import { WardProperties } from "../../lib/api";
import { RISK_COLOR_HEX } from "../../lib/mapUtils";
import {
  AlertTriangle,
  Waves,
  Shield,
  Layers,
  ArrowRight,
  X,
  Radio,
} from "lucide-react";

export default function DashboardPage() {
  const { geoData, wardsList, isLoading, error } = useWardRisk(30000);
  const [selectedWard, setSelectedWard] = useState<WardProperties | null>(null);

  // Derive citywide analytics
  const stats = useMemo(() => {
    if (!wardsList.length) {
      return { total: 0, critical: 0, high: 0, coastalCount: 0, avgRisk: 0 };
    }

    const critical = wardsList.filter((w) => w.current_risk_class === "critical").length;
    const high = wardsList.filter((w) => w.current_risk_class === "high").length;
    const coastalCount = wardsList.filter((w) => w.is_coastal).length;
    const totalScore = wardsList.reduce((acc, w) => acc + (w.current_risk_score || 0), 0);

    return {
      total: wardsList.length,
      critical,
      high,
      coastalCount,
      avgRisk: Math.round((totalScore / wardsList.length) * 100),
    };
  }, [wardsList]);

  return (
    <div className="relative w-full h-full">
      {/* 3D GIS Map Surface */}
      <WardRiskLayer
        geoData={geoData}
        selectedWardId={selectedWard?.ward_id}
        onSelectWard={(ward) => setSelectedWard(ward)}
      />

      {/* Floating Header KPI Overlay */}
      <div className="absolute top-5 left-5 z-20 flex items-center gap-3">
        <div className="bg-slate-900/90 border border-slate-800 backdrop-blur-md rounded-xl p-3 shadow-2xl flex items-center gap-4 text-xs">
          <div>
            <div className="text-[10px] uppercase text-slate-400 font-semibold tracking-wider">
              Monitored Wards
            </div>
            <div className="text-lg font-bold font-mono text-white">
              {stats.total} <span className="text-xs font-normal text-slate-400">BMC</span>
            </div>
          </div>

          <div className="h-7 w-px bg-slate-800" />

          <div>
            <div className="text-[10px] uppercase text-slate-400 font-semibold tracking-wider">
              Critical Alerts
            </div>
            <div className="text-lg font-bold font-mono text-red-400 flex items-center gap-1">
              <AlertTriangle className="w-4 h-4 text-red-400" />
              {stats.critical}
            </div>
          </div>

          <div className="h-7 w-px bg-slate-800" />

          <div>
            <div className="text-[10px] uppercase text-slate-400 font-semibold tracking-wider">
              Coastal Exposure
            </div>
            <div className="text-lg font-bold font-mono text-blue-400 flex items-center gap-1">
              <Waves className="w-4 h-4 text-blue-400" />
              {stats.coastalCount} Wards
            </div>
          </div>

          <div className="h-7 w-px bg-slate-800" />

          <div>
            <div className="text-[10px] uppercase text-slate-400 font-semibold tracking-wider">
              Citywide Index
            </div>
            <div className="text-lg font-bold font-mono text-amber-400">
              {stats.avgRisk}%
            </div>
          </div>
        </div>
      </div>

      {/* Ward Detail Inspector Panel (Drawer) */}
      {selectedWard && (
        <div className="absolute top-5 right-5 bottom-5 w-96 bg-slate-900/95 border border-slate-800 backdrop-blur-xl rounded-2xl shadow-2xl z-30 p-5 flex flex-col justify-between text-slate-200 animate-in fade-in slide-in-from-right-5 duration-200">
          <div>
            {/* Header */}
            <div className="flex items-start justify-between border-b border-slate-800 pb-3">
              <div>
                <span
                  className="px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider text-slate-950 inline-block mb-1.5"
                  style={{
                    backgroundColor:
                      RISK_COLOR_HEX[selectedWard.risk_class] || "#94a3b8",
                  }}
                >
                  {selectedWard.risk_class} Risk Tier
                </span>
                <h2 className="text-base font-bold text-white leading-tight">
                  {selectedWard.ward_name}
                </h2>
                <div className="text-xs text-slate-400 font-mono mt-0.5">
                  Identifier: {selectedWard.ward_id}
                </div>
              </div>

              <button
                onClick={() => setSelectedWard(null)}
                className="p-1 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Risk Gauge Bar */}
            <div className="mt-4 p-3.5 bg-slate-950/60 rounded-xl border border-slate-800/80">
              <div className="flex justify-between items-center text-xs mb-1.5">
                <span className="text-slate-400 font-medium">Inundation Risk Score</span>
                <span className="font-mono font-bold text-sm text-white">
                  {Math.round(selectedWard.risk_score * 100)} / 100
                </span>
              </div>
              <div className="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-500"
                  style={{
                    width: `${Math.max(5, selectedWard.risk_score * 100)}%`,
                    backgroundColor:
                      RISK_COLOR_HEX[selectedWard.risk_class] || "#3b82f6",
                  }}
                />
              </div>
            </div>

            {/* Physical & Topological Properties */}
            <div className="mt-4 space-y-2.5 text-xs">
              <div className="flex justify-between py-1.5 border-b border-slate-800/60">
                <span className="text-slate-400">SRTM Avg Elevation</span>
                <span className="font-mono font-medium text-white">
                  {selectedWard.avg_elevation_m?.toFixed(1) ?? "N/A"} meters
                </span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-slate-800/60">
                <span className="text-slate-400">Drainage Capacity Index</span>
                <span className="font-mono font-medium text-white">
                  {selectedWard.drainage_index.toFixed(2)} (0=Poor, 1=Optimum)
                </span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-slate-800/60">
                <span className="text-slate-400">Geographic Area</span>
                <span className="font-mono font-medium text-white">
                  {selectedWard.area_sqkm ?? "N/A"} km²
                </span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-slate-800/60">
                <span className="text-slate-400">Coastal Storm Surge</span>
                <span className="font-medium text-white">
                  {selectedWard.is_coastal ? "High Vulnerability (Tidal)" : "Low (Inland)"}
                </span>
              </div>
            </div>
          </div>

          {/* Quick Action Trigger */}
          <div className="pt-4 border-t border-slate-800 space-y-2">
            <button className="w-full py-2.5 px-3 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-medium text-xs flex items-center justify-center gap-2 transition-all shadow-lg shadow-blue-600/20">
              <Radio className="w-3.5 h-3.5" />
              Dispatch Micro-Targeted Alert
            </button>
          </div>
        </div>
      )}

      {/* Loading Overlay */}
      {isLoading && (
        <div className="absolute inset-0 bg-slate-950/70 backdrop-blur-sm z-40 flex items-center justify-center">
          <div className="bg-slate-900 border border-slate-800 p-5 rounded-xl shadow-2xl flex items-center gap-3 text-xs text-slate-300">
            <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
            Loading Mumbai Ward Polygons & Risk telemetry...
          </div>
        </div>
      )}

      {/* Error Banner */}
      {error && !isLoading && (
        <div className="absolute bottom-6 right-6 z-30 bg-red-950/90 border border-red-800/80 text-red-200 text-xs px-4 py-3 rounded-xl shadow-2xl flex items-center gap-2 max-w-md">
          <AlertTriangle className="w-4 h-4 text-red-400 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}
    </div>
  );
}
