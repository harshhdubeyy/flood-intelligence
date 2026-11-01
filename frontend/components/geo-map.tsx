'use client';

import { useEffect, useMemo, useState } from 'react';
import 'mapbox-gl/dist/mapbox-gl.css';
import MapboxMap from 'react-map-gl';
import DeckGL from '@deck.gl/react';
import { GeoJsonLayer } from '@deck.gl/layers';
import type { Ward } from '../lib/api';

type Props = {
  wards: Ward[];
  onWardClick: (id: string) => void;
  onUnmonitoredWardClick: (name: string) => void;
};

type WardFeatureCollection = GeoJSON.FeatureCollection<
  GeoJSON.Geometry,
  {
    NAME2?: string;
    OBJECTID?: number;
    [key: string]: unknown;
  }
>;

const INITIAL_VIEW_STATE = {
  longitude: 72.8777,
  latitude: 19.076,
  zoom: 9.2,
  pitch: 0,
  bearing: 0,
};

const WARD_CODE_TO_ID: Record<string, string> = {
  A: 'BMC-A',
  'G/N': 'BMC-GN',
  'H/W': 'BMC-HW',
  L: 'BMC-L',
  'M/W': 'BMC-MW',
};

const RISK_COLORS: Record<
  string,
  [number, number, number, number]
> = {
  low: [34, 160, 110, 65],
  medium: [232, 174, 45, 90],
  high: [235, 112, 48, 105],
  critical: [220, 55, 65, 120],
  unknown: [110, 125, 145, 35],
};

function normalizeWardCode(value: unknown): string {
  return String(value ?? '')
    .replace(/\s+/g, '')
    .toUpperCase();
}

export function GeoMap({
  wards,
  onWardClick,
  onUnmonitoredWardClick,
}: Props) {
  const token = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;

  const [boundaries, setBoundaries] =
    useState<WardFeatureCollection | null>(null);
  const [boundaryError, setBoundaryError] = useState(false);

  useEffect(() => {
    let cancelled = false;

    fetch('/data/mumbai-wards.geojson')
      .then((response) => {
        if (!response.ok) {
          throw new Error('Unable to load Mumbai ward boundaries');
        }
        return response.json();
      })
      .then((data: WardFeatureCollection) => {
        if (!cancelled) {
          setBoundaries(data);
          setBoundaryError(false);
        }
      })
      .catch(() => {
        if (!cancelled) setBoundaryError(true);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const wardById = useMemo(
    () => new Map(wards.map((ward) => [ward.id, ward])),
    [wards]
  );

  const mapData = useMemo<WardFeatureCollection | null>(() => {
    if (!boundaries) return null;

    return {
      ...boundaries,
      features: boundaries.features.map((feature) => {
        const code = normalizeWardCode(feature.properties?.NAME2);
        const backendId = WARD_CODE_TO_ID[code];
        const ward = backendId ? wardById.get(backendId) : undefined;

        return {
          ...feature,
          properties: {
            ...feature.properties,
            normalized_code: code,
            backend_id: backendId ?? null,
            ward_name: ward?.name ?? `BMC ${code}`,
            monitored: Boolean(ward),
            risk_class: ward?.risk_class ?? 'unknown',
            risk_score: ward?.risk_score ?? null,
          },
        };
      }),
    };
  }, [boundaries, wardById]);

  const layers = useMemo(() => {
    if (!mapData) return [];

    return [
      new GeoJsonLayer({
  id: 'mumbai-ward-boundaries',
  data: mapData,
  pickable: true,
  filled: true,
  stroked: true,
  autoHighlight: true,
  highlightColor: [255, 190, 40, 110],

  // Visible ward fills
  getFillColor: (feature: any) => {
    const riskClass = String(
      feature.properties?.risk_class ?? 'unknown'
    ).toLowerCase();

    if (riskClass === 'low') return [34, 160, 110, 75];
    if (riskClass === 'medium') return [232, 174, 45, 95];
    if (riskClass === 'high') return [235, 112, 48, 110];
    if (riskClass === 'critical') return [220, 55, 65, 125];

    // Boundary-only wards
    return [100, 125, 155, 45];
  },

  // Stronger outlines for all 24 wards
  getLineColor: [25, 65, 110, 235],
  getLineWidth: 2,

  lineWidthUnits: 'pixels',
  lineWidthMinPixels: 2,
  lineWidthMaxPixels: 4,

  onClick: (info: any) => {
    const properties = info.object?.properties;
    if (!properties) return;

    const backendId = properties.backend_id;

    if (backendId) {
      onWardClick(String(backendId));
    } else {
      onUnmonitoredWardClick(
        String(properties.ward_name ?? 'Unmonitored ward')
      );
    }
  },
})
    ];
  }, [mapData, onWardClick, onUnmonitoredWardClick]);

  if (!token) {
    return (
      <div className="flex h-full w-full items-center justify-center">
        Mapbox token unavailable. Check NEXT_PUBLIC_MAPBOX_TOKEN.
      </div>
    );
  }

  if (boundaryError) {
    return (
      <div className="flex h-full w-full items-center justify-center">
        Unable to load the 24 Mumbai ward boundaries.
      </div>
    );
  }

  if (!mapData) {
    return (
      <div className="flex h-full w-full items-center justify-center">
        Loading Mumbai administrative boundaries...
      </div>
    );
  }

  return (
    <DeckGL
      initialViewState={INITIAL_VIEW_STATE}
      controller
      layers={layers}
      style={{ width: '100%', height: '100%' }}
    >
      <MapboxMap
        mapboxAccessToken={token}
        mapStyle="mapbox://styles/mapbox/light-v11"
      />
    </DeckGL>
  );
}