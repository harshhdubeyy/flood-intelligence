"use client";

import React, { useState, useEffect, useRef, useMemo } from "react";
import DeckGL from "@deck.gl/react";
import { GeoJsonLayer } from "@deck.gl/layers";
import mapboxgl from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";

import { WardGeoJSONCollection, WardGeoJSONFeature, WardProperties } from "../../lib/api";
import { MUMBAI_CENTER, getRiskColor, RISK_COLOR_HEX } from "../../lib/mapUtils";

interface WardRiskLayerProps {
  geoData: WardGeoJSONCollection | null;
  selectedWardId?: string | null;
  onSelectWard?: (ward: WardProperties | null) => void;
}

export default function WardRiskLayer({
  geoData,
  selectedWardId,
  onSelectWard,
}: WardRiskLayerProps) {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);

  const [viewState, setViewState] = useState(MUMBAI_CENTER);
  const [hoverInfo, setHoverInfo] = useState<{
    x: number;
    y: number;
    properties?: WardProperties;
  } | null>(null);

  // Initialize Mapbox background instance
  useEffect(() => {
    if (!mapContainerRef.current) return;

    const MAPBOX_TOKEN = process.env.NEXT_PUBLIC_MAPBOX_TOKEN || "";

    const map = new mapboxgl.Map({
      container: mapContainerRef.current,
      style: "mapbox://styles/mapbox/dark-v11",
      center: [MUMBAI_CENTER.longitude, MUMBAI_CENTER.latitude],
      zoom: MUMBAI_CENTER.zoom,
      pitch: MUMBAI_CENTER.pitch,
      bearing: MUMBAI_CENTER.bearing,
      interactive: false, // Deck.gl controls interaction
    });

    mapRef.current = map;

    return () => {
      map.remove();
    };
  }, []);

  // Synchronize Mapbox camera with Deck.gl viewState
  useEffect(() => {
    if (!mapRef.current) return;
    mapRef.current.jumpTo({
      center: [viewState.longitude, viewState.latitude],
      zoom: viewState.zoom,
      pitch: viewState.pitch,
      bearing: viewState.bearing,
    });
  }, [viewState]);

  // Deck.gl GeoJsonLayer
  const layers = useMemo(() => {
    if (!geoData || !geoData.features || geoData.features.length === 0) {
      return [];
    }

    return [
      new GeoJsonLayer({
        id: "mumbai-ward-polygons",
        data: geoData as any,
        pickable: true,
        stroked: true,
        filled: true,
        extruded: true,
        wireframe: true,
        getElevation: (d: any) => {
          const score = d.properties?.risk_score || 0.1;
          // Extrude higher-risk wards for 3D command center visualization
          return score * 1200;
        },
        getFillColor: (d: any) => {
          const wardId = d.properties?.ward_id;
          const isSelected = selectedWardId && wardId === selectedWardId;
          const base = getRiskColor(d.properties?.risk_class || "low");
          return isSelected ? [255, 255, 255, 240] : base;
        },
        getLineColor: (d: any) => {
          const wardId = d.properties?.ward_id;
          return wardId === selectedWardId ? [255, 255, 255, 255] : [15, 23, 42, 220];
        },
        getLineWidth: (d: any) => (d.properties?.ward_id === selectedWardId ? 4 : 1.5),
        lineWidthUnits: "pixels",
        updateTriggers: {
          getFillColor: [selectedWardId, geoData],
          getLineColor: [selectedWardId],
          getLineWidth: [selectedWardId],
        },
        onHover: (info: any) => {
          if (info.object) {
            setHoverInfo({
              x: info.x,
              y: info.y,
              properties: info.object.properties,
            });
          } else {
            setHoverInfo(null);
          }
        },
        onClick: (info: any) => {
          if (info.object && onSelectWard) {
            onSelectWard(info.object.properties);
          }
        },
      }),
    ];
  }, [geoData, selectedWardId, onSelectWard]);

  return (
    <div className="relative w-full h-full overflow-hidden select-none bg-slate-950">
      {/* Underlying Mapbox GL Canvas */}
      <div ref={mapContainerRef} className="absolute inset-0 w-full h-full" />

      {/* Deck.gl 3D Geospatial Overlay */}
      <DeckGL
        viewState={viewState}
        onViewStateChange={({ viewState }: any) => setViewState(viewState)}
        controller={true}
        layers={layers}
      />

      {/* Real-time Hover Tooltip */}
      {hoverInfo && hoverInfo.properties && (
        <div
          className="pointer-events-none absolute z-30 transform -translate-x-1/2 -translate-y-full mb-3 px-3.5 py-2.5 bg-slate-900/95 border border-slate-700/80 rounded-lg shadow-2xl backdrop-blur-md text-xs text-slate-100 min-w-[200px]"
          style={{ left: hoverInfo.x, top: hoverInfo.y }}
        >
          <div className="flex items-center justify-between gap-2 border-b border-slate-700/60 pb-1.5 mb-1.5">
            <span className="font-semibold text-slate-200">
              {hoverInfo.properties.ward_name}
            </span>
            <span
              className="px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider text-slate-950"
              style={{
                backgroundColor:
                  RISK_COLOR_HEX[hoverInfo.properties.risk_class] || "#94a3b8",
              }}
            >
              {hoverInfo.properties.risk_class}
            </span>
          </div>
          <div className="grid grid-cols-2 gap-y-1 text-[11px] text-slate-300">
            <span>Ward ID:</span>
            <span className="font-mono text-right text-slate-100 font-medium">
              {hoverInfo.properties.ward_id}
            </span>
            <span>Flood Risk:</span>
            <span className="text-right font-bold text-amber-400">
              {Math.round(hoverInfo.properties.risk_score * 100)}%
            </span>
            <span>Avg Elevation:</span>
            <span className="text-right font-mono">
              {hoverInfo.properties.avg_elevation_m?.toFixed(1) ?? "N/A"} m
            </span>
            <span>Drainage Index:</span>
            <span className="text-right font-mono">
              {hoverInfo.properties.drainage_index.toFixed(2)}
            </span>
            <span>Coastal Ward:</span>
            <span className="text-right">
              {hoverInfo.properties.is_coastal ? "Yes (Arabian Sea)" : "Inland"}
            </span>
          </div>
        </div>
      )}

      {/* Floating Map Legend */}
      <div className="absolute bottom-6 left-6 z-20 bg-slate-900/90 border border-slate-800 backdrop-blur-md rounded-xl p-3.5 text-xs text-slate-200 shadow-xl max-w-xs">
        <div className="font-semibold text-[11px] tracking-wider uppercase text-slate-400 mb-2">
          Ward Risk Severity
        </div>
        <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-sm bg-[#22c55e]" />
            <span>Low (Safe)</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-sm bg-[#eab308]" />
            <span>Medium (Watch)</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-sm bg-[#f97316]" />
            <span>High (Warning)</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-sm bg-[#ef4444]" />
            <span>Critical (Alert)</span>
          </div>
        </div>
        <div className="mt-2.5 pt-2 border-t border-slate-800 text-[10px] text-slate-400">
          Height extrusion indicates relative flood susceptibility.
        </div>
      </div>
    </div>
  );
}
