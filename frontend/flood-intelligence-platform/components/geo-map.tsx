'use client';

import { memo, useMemo } from 'react';
import DeckGL from '@deck.gl/react';
import type { Layer } from '@deck.gl/core';
import { GeoJsonLayer, ScatterplotLayer } from '@deck.gl/layers';
import MapboxMap from 'react-map-gl';
import 'mapbox-gl/dist/mapbox-gl.css';
import type {
  CitizenReport,
  FloodHotspot,
  WardPrediction,
  WardIntelligenceItem,
  WaterDepth,
} from '../lib/api';

type LayerVisibility = {
  reports: boolean;
  hotspots: boolean;
  intelligence: boolean;
  risk: boolean;
  prediction: boolean;
};

export type SelectedWard = {
  code: string;
  wardName: string;
  wardId: string | null;
  intelligence: WardIntelligenceItem | null;
};

type Props = {
  boundaries: GeoJSON.FeatureCollection;
  riskGeoJSON?: GeoJSON.FeatureCollection;
  reports: CitizenReport[];
  hotspots: FloodHotspot[];
  wardIntelligence: WardIntelligenceItem[];
  predictions: WardPrediction[];
  visibleLayers: LayerVisibility;
  selectedWardCode: string | null;
  selectedReportId?: string | null;
  operatorMode?: boolean;
  onWardClick: (ward: SelectedWard) => void;
  onReportClick: (report: CitizenReport) => void;
  onHotspotClick: (hotspot: FloodHotspot) => void;
};

type WardProperties = Record<string, unknown> & {
  ward_code: string;
  ward_id: string | null;
  ward_name: string;
  intelligence_score: number | null;
  risk_score: number | null;
  risk_class: string | null;
  prediction_score: number | null;
  prediction_category: string | null;
  prediction_status: WardPrediction['status'] | null;
};

type WardFeature = GeoJSON.Feature<GeoJSON.Geometry, WardProperties>;

const depthColors: Record<WaterDepth, [number, number, number, number]> = {
  ankle: [35, 155, 94, 225],
  knee: [226, 183, 35, 235],
  waist: [230, 111, 34, 240],
  submerged: [205, 54, 64, 245],
};

const depthRadii: Record<WaterDepth, number> = {
  ankle: 5,
  knee: 7,
  waist: 9,
  submerged: 11,
};

const riskColors: Record<string, [number, number, number, number]> = {
  low: [38, 155, 104, 42],
  medium: [216, 173, 49, 48],
  high: [225, 119, 43, 52],
  critical: [197, 57, 69, 56],
};

function wardKey(value: unknown): string {
  return String(value ?? '')
    .trim()
    .toUpperCase()
    .replace(/^(?:MH[-_]*)?BMC[-_]*/, '')
    .replace(/[^A-Z0-9]/g, '');
}

function normalizePosition(position: unknown): number[] | null {
  if (
    !Array.isArray(position) ||
    position.length < 2 ||
    typeof position[0] !== 'number' ||
    typeof position[1] !== 'number'
  ) {
    return null;
  }

  const [latitude, longitude, ...extra] = position;
  if (
    !Number.isFinite(latitude) ||
    !Number.isFinite(longitude) ||
    latitude < -90 ||
    latitude > 90 ||
    longitude < -180 ||
    longitude > 180
  ) {
    return null;
  }

  return [longitude, latitude, ...extra.filter((value): value is number => typeof value === 'number')];
}

function normalizeCoordinates(value: unknown): unknown {
  if (!Array.isArray(value)) return null;
  if (typeof value[0] === 'number') return normalizePosition(value);

  const children = value.map(normalizeCoordinates);
  return children.every((child) => child !== null) ? children : null;
}

function validLineCoordinates(value: unknown): value is GeoJSON.Position[] {
  return (
    Array.isArray(value) &&
    value.length >= 4 &&
    value.every(
      (position) =>
        Array.isArray(position) &&
        position.length >= 2 &&
        typeof position[0] === 'number' &&
        typeof position[1] === 'number' &&
        Number.isFinite(position[0]) &&
        Number.isFinite(position[1]) &&
        Math.abs(position[0]) <= 180 &&
        Math.abs(position[1]) <= 90,
    )
  );
}

function validPolygonCoordinates(value: unknown): value is GeoJSON.Polygon['coordinates'] {
  return (
    Array.isArray(value) &&
    value.length > 0 &&
    value.every(validLineCoordinates)
  );
}

function validMultiPolygonCoordinates(value: unknown): value is GeoJSON.MultiPolygon['coordinates'] {
  return Array.isArray(value) && value.length > 0 && value.every(validPolygonCoordinates);
}

function normalizeBoundaries(
  input: GeoJSON.FeatureCollection,
): GeoJSON.FeatureCollection<GeoJSON.Geometry, Record<string, unknown>> {
  const features = input.features.flatMap((feature) => {
    const sourceGeometry = feature.geometry;
    if (!sourceGeometry) return [];
    let geometry: GeoJSON.Polygon | GeoJSON.MultiPolygon;
    if (sourceGeometry.type === 'Polygon') {
      const coordinates = normalizeCoordinates(sourceGeometry.coordinates);
      if (!validPolygonCoordinates(coordinates)) return [];
      geometry = { type: 'Polygon', coordinates };
    } else if (sourceGeometry.type === 'MultiPolygon') {
      const coordinates = normalizeCoordinates(sourceGeometry.coordinates);
      if (!validMultiPolygonCoordinates(coordinates)) return [];
      geometry = { type: 'MultiPolygon', coordinates };
    } else {
      return [];
    }

    const normalizedFeature: GeoJSON.Feature<GeoJSON.Geometry, Record<string, unknown>> = {
      type: 'Feature',
      ...(feature.id === undefined ? {} : { id: feature.id }),
      geometry,
      properties: feature.properties ?? {},
    };
    return [normalizedFeature];
  });

  return { type: 'FeatureCollection', features };
}

const normalizedBoundariesCache = new WeakMap<object, GeoJSON.FeatureCollection>();

function normalizedBoundaries(data: GeoJSON.FeatureCollection): GeoJSON.FeatureCollection {
  const cached = normalizedBoundariesCache.get(data);
  if (cached) return cached;

  const normalized = normalizeBoundaries(data);
  normalizedBoundariesCache.set(data, normalized);
  return normalized;
}

function intelligenceColor(score: number): [number, number, number, number] {
  if (score >= 0.75) return [202, 58, 67, 145];
  if (score >= 0.55) return [231, 125, 45, 135];
  if (score >= 0.35) return [226, 191, 55, 125];
  return [48, 155, 102, 120];
}

function reportTooltip(report: CitizenReport): string {
  const verification = report.cv_verified ? 'CV verified' : 'Unverified';
  const operatorStatus = report.operator_verification_status
    ? ` · Operator ${report.operator_verification_status.replace('_', ' ')}`
    : '';
  const locationStatus = report.location_validation_status && report.location_validation_status !== 'matched'
    ? ` · Location ${report.location_validation_status.replace('_', ' ')}`
    : '';
  return `${report.water_depth} · ${verification}${operatorStatus}${locationStatus}${report.is_duplicate ? ' · Duplicate' : ''}`;
}

function hotspotTooltip(hotspot: FloodHotspot): string {
  return `${hotspot.report_count} reports · ${Math.round(hotspot.confidence * 100)}% confidence`;
}

function GeoMapComponent({
  boundaries,
  riskGeoJSON,
  reports,
  hotspots,
  wardIntelligence,
  predictions,
  visibleLayers,
  selectedWardCode,
  selectedReportId,
  operatorMode = false,
  onWardClick,
  onReportClick,
  onHotspotClick,
}: Props) {
  const token = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;
  const localBoundaries = useMemo(() => normalizedBoundaries(boundaries), [boundaries]);
  const intelligenceByWard = useMemo(
    () => new Map(wardIntelligence.map((item) => [wardKey(item.analytics.ward_id), item])),
    [wardIntelligence],
  );
  const predictionByWard = useMemo(
    () => new Map(predictions.map((item) => [wardKey(item.ward_code), item])),
    [predictions],
  );
  const riskByWard = useMemo(() => {
    const result = new Map<string, Record<string, unknown>>();
    for (const feature of riskGeoJSON?.features ?? []) {
      const properties = feature.properties;
      const key = wardKey(properties?.ward_id ?? properties?.ward_code ?? properties?.ward_name);
      if (key) result.set(key, properties ?? {});
    }
    return result;
  }, [riskGeoJSON]);

  const wardData = useMemo<GeoJSON.FeatureCollection<GeoJSON.Geometry, WardProperties>>(() => ({
    type: 'FeatureCollection',
    features: localBoundaries.features.map((feature) => {
      const properties = (feature.properties ?? {}) as Record<string, unknown>;
      const sourceCode = String(properties.NAME2 ?? properties.Name ?? '').trim();
      const code = wardKey(sourceCode);
      const intelligence = intelligenceByWard.get(code) ?? null;
      const prediction = predictionByWard.get(code);
      const risk = riskByWard.get(code);
      const wardId = intelligence?.analytics.ward_id
        ?? (typeof properties.ward_id === 'string' ? properties.ward_id : null);

      return {
        ...feature,
        properties: {
          ...properties,
          ward_code: code,
          ward_id: wardId,
          ward_name: intelligence?.analytics.ward_name ?? sourceCode,
          intelligence_score: intelligence?.intelligence?.intelligence_score ?? null,
          risk_score: typeof risk?.risk_score === 'number' ? risk.risk_score : null,
          risk_class: typeof risk?.risk_class === 'string' ? risk.risk_class : null,
          prediction_score: prediction?.predicted_risk_score ?? null,
          prediction_category: prediction?.risk_category ?? null,
          prediction_status: prediction?.status ?? null,
        },
      } as WardFeature;
    }),
  }), [intelligenceByWard, localBoundaries, predictionByWard, riskByWard]);

  const mapReports = useMemo(
    () => reports.filter((report) =>
      Number.isFinite(report.latitude) &&
      Number.isFinite(report.longitude) &&
      Math.abs(report.latitude) <= 90 &&
      Math.abs(report.longitude) <= 180,
    ),
    [reports],
  );
  const mapHotspots = useMemo(
    () => hotspots.filter((hotspot) =>
      Number.isFinite(hotspot.center_latitude) &&
      Number.isFinite(hotspot.center_longitude) &&
      Math.abs(hotspot.center_latitude) <= 90 &&
      Math.abs(hotspot.center_longitude) <= 180,
    ),
    [hotspots],
  );

  const layers = useMemo(() => {
    const output: Layer[] = [
      new GeoJsonLayer({
        id: 'mumbai-ward-boundaries',
        data: wardData,
        pickable: true,
        stroked: true,
        filled: true,
        getFillColor: [30, 75, 110, 0],
        getLineColor: (feature) =>
          wardKey(feature.properties.ward_code) === wardKey(selectedWardCode)
            ? [24, 91, 174, 245]
            : [79, 104, 126, 150],
        getLineWidth: (feature) =>
          wardKey(feature.properties.ward_code) === wardKey(selectedWardCode) ? 3 : 1,
        lineWidthMinPixels: 1,
        onClick: (info) => {
          const feature = info.object as WardFeature | undefined;
          if (!feature) return;
          onWardClick({
            code: feature.properties.ward_code,
            wardName: feature.properties.ward_name,
            wardId: feature.properties.ward_id,
            intelligence: intelligenceByWard.get(wardKey(feature.properties.ward_code)) ?? null,
          });
        },
      }),
    ];

    if (visibleLayers.intelligence) {
      output.push(new GeoJsonLayer({
        id: 'mumbai-ward-intelligence',
        data: wardData,
        pickable: false,
        stroked: false,
        filled: true,
        getFillColor: (feature) =>
          feature.properties.intelligence_score === null
            ? [0, 0, 0, 0]
            : intelligenceColor(feature.properties.intelligence_score),
      }));
    }

    if (visibleLayers.risk) {
      output.push(new GeoJsonLayer({
        id: 'mumbai-ward-flood-risk',
        data: wardData,
        pickable: false,
        stroked: false,
        filled: true,
        getFillColor: (feature) =>
          feature.properties.risk_class
            ? riskColors[feature.properties.risk_class] ?? [0, 0, 0, 0]
            : [0, 0, 0, 0],
      }));
    }

    if (visibleLayers.prediction) {
      const predictionColors: Record<string, [number, number, number, number]> = {
        low: [44, 153, 101, 82],
        moderate: [220, 184, 48, 96],
        high: [225, 119, 43, 112],
        critical: [197, 57, 69, 128],
      };
      output.push(new GeoJsonLayer({
        id: 'mumbai-predictive-outlook',
        data: wardData,
        pickable: false,
        stroked: true,
        filled: true,
        getFillColor: (feature) => {
          if (feature.properties.prediction_status === 'unavailable') return [126, 137, 151, 42];
          const category = feature.properties.prediction_category;
          return category ? predictionColors[category] ?? [0, 0, 0, 0] : [0, 0, 0, 0];
        },
        getLineColor: (feature) =>
          feature.properties.prediction_status === 'low_confidence'
            ? [93, 102, 117, 200]
            : [0, 0, 0, 0],
        lineWidthMinPixels: 1,
      }));
    }

    if (visibleLayers.hotspots) {
      output.push(new ScatterplotLayer<FloodHotspot>({
        id: 'flood-hotspots',
        data: mapHotspots,
        pickable: true,
        stroked: true,
        filled: true,
        getPosition: (hotspot) => [hotspot.center_longitude, hotspot.center_latitude],
        getRadius: (hotspot) => Math.max(hotspot.radius_meters, 1),
        radiusUnits: 'meters',
        radiusMinPixels: 7,
        radiusMaxPixels: 85,
        getFillColor: (hotspot) => [207, 48, 55, 35 + Math.round(100 * hotspot.confidence)],
        getLineColor: [174, 38, 46, 220],
        lineWidthMinPixels: 2,
        onClick: (info) => {
          if (info.object) onHotspotClick(info.object);
        },
      }));
    }

    if (visibleLayers.reports) {
      output.push(new ScatterplotLayer<CitizenReport>({
        id: 'citizen-flood-reports',
        data: mapReports,
        pickable: true,
        stroked: true,
        filled: true,
        getPosition: (report) => [report.longitude, report.latitude],
        getRadius: (report) => depthRadii[report.water_depth],
        radiusUnits: 'pixels',
        radiusMinPixels: 5,
        radiusMaxPixels: 15,
        getFillColor: (report) => {
          if (operatorMode) {
            if (report.operator_verification_status === 'confirmed') return [20, 112, 74, 235];
            if (report.operator_verification_status === 'rejected') return [100, 110, 125, 195];
            if (report.operator_verification_status === 'review_required') return [226, 151, 34, 235];
            return [226, 173, 35, 235];
          }
          if (report.operator_verification_status === 'confirmed') return [20, 112, 74, 235];
          if (report.operator_verification_status === 'rejected') return [100, 110, 125, 195];
          if (report.operator_verification_status === 'review_required') return [226, 151, 34, 235];
          const [red, green, blue, alpha] = depthColors[report.water_depth];
          return [red, green, blue, report.cv_verified ? alpha : Math.round(alpha * 0.58)];
        },
        getLineColor: (report) => {
          if (report.report_id === selectedReportId) return [31, 51, 82, 255];
          if (operatorMode && report.location_validation_status !== 'matched') return [200, 55, 59, 255];
          if (report.operator_verification_status === 'confirmed') return [12, 72, 49, 255];
          if (report.operator_verification_status === 'rejected') return [75, 82, 94, 255];
          if (report.operator_verification_status === 'review_required') return [145, 91, 12, 255];
          return report.is_duplicate
            ? [160, 42, 168, 255]
            : report.cv_verified ? [20, 86, 54, 255] : [255, 255, 255, 235];
        },
        lineWidthMinPixels: 2,
        onClick: (info) => {
          if (info.object) onReportClick(info.object);
        },
      }));
    }

    return output;
  }, [
    intelligenceByWard,
    mapHotspots,
    mapReports,
    onHotspotClick,
    onReportClick,
    onWardClick,
    selectedWardCode,
    selectedReportId,
    operatorMode,
    visibleLayers.hotspots,
    visibleLayers.intelligence,
    visibleLayers.prediction,
    visibleLayers.reports,
    visibleLayers.risk,
    wardData,
  ]);

  return (
    <DeckGL
      initialViewState={{
        longitude: 72.8777,
        latitude: 19.076,
        zoom: 9,
        pitch: 0,
        bearing: 0,
      }}
      controller
      layers={layers}
      getTooltip={({ object }) => {
        if (!object) return null;
        if ('report_id' in object) return { text: reportTooltip(object as CitizenReport) };
        if ('hotspot_id' in object) return { text: hotspotTooltip(object as FloodHotspot) };
        if ('prediction_status' in object) {
          return { text: object.prediction_status === 'unavailable' ? 'Forecast unavailable' : `Forecast ${object.prediction_category ?? 'outlook'}` };
        }
        if ('ward_name' in object) return { text: String(object.ward_name) };
        return null;
      }}
      style={{ position: 'absolute', inset: '0' }}
    >
      {token ? (
        <MapboxMap
          mapboxAccessToken={token}
          initialViewState={{
            longitude: 72.8777,
            latitude: 19.076,
            zoom: 9,
          }}
          mapStyle="mapbox://styles/mapbox/light-v11"
          reuseMaps
        />
      ) : null}
    </DeckGL>
  );
}

export const GeoMap = memo(GeoMapComponent);
