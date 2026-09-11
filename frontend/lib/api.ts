/**
 * API client configuration and typed request helpers for Flood Intelligence Platform.
 */

import axios from "axios";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/v1";

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15000,
  headers: {
    "Content-Type": "application/json",
  },
});

export interface WardProperties {
  ward_id: string;
  ward_name: string;
  city: string;
  area_sqkm?: number;
  population?: number;
  is_coastal: boolean;
  avg_elevation_m?: number;
  drainage_index: number;
  risk_score: number;
  risk_class: "low" | "medium" | "high" | "critical";
  computed_at?: string;
}

export interface WardGeoJSONFeature {
  type: "Feature";
  id?: string;
  geometry: {
    type: "MultiPolygon" | "Polygon";
    coordinates: any[];
  };
  properties: WardProperties;
}

export interface WardGeoJSONCollection {
  type: "FeatureCollection";
  features: WardGeoJSONFeature[];
}

export interface WardSummary {
  id: number;
  ward_id: string;
  ward_name: string;
  city: string;
  area_sqkm?: number;
  population?: number;
  is_coastal: boolean;
  avg_elevation_m?: number;
  drainage_index: number;
  current_risk_score: number;
  current_risk_class: "low" | "medium" | "high" | "critical";
}

export interface CitizenReportItem {
  report_id: string;
  ward_id?: string;
  latitude: number;
  longitude: number;
  water_depth: "ankle" | "knee" | "waist" | "submerged";
  image_url?: string;
  cv_verified: boolean;
  cv_water_depth_m?: number;
  cv_confidence?: number;
  description?: string;
  is_duplicate: boolean;
  duplicate_of_id?: string;
  submitted_at: string;
}

export interface ReportSummary {
  total_reports_24h: number;
  cv_verified_count: number;
  flagged_duplicates: number;
  severe_reports: number;
}

/**
 * Fetch ward boundaries and active risk features in RFC 7946 GeoJSON format.
 */
export async function fetchWardsGeoJSON(): Promise<WardGeoJSONCollection> {
  const response = await apiClient.get<WardGeoJSONCollection>("/wards/geojson");
  return response.data;
}

/**
 * List all wards and their summary risk scores.
 */
export async function fetchWardsList(): Promise<WardSummary[]> {
  const response = await apiClient.get<WardSummary[]>("/wards");
  return response.data;
}

/**
 * Fetch detailed 24-hour risk progression for a specific ward.
 */
export async function fetchWardRiskHistory(wardId: string) {
  const response = await apiClient.get(`/wards/${encodeURIComponent(wardId)}/risk`);
  return response.data;
}

/**
 * List citizen incident reports.
 */
export async function fetchCitizenReports(wardId?: string, verifiedOnly: boolean = false): Promise<CitizenReportItem[]> {
  const params: Record<string, any> = {};
  if (wardId) params.ward_id = wardId;
  if (verifiedOnly) params.verified_only = true;

  const response = await apiClient.get<{ total: number; reports: CitizenReportItem[] }>("/reports", { params });
  return response.data.reports;
}

/**
 * Fetch 24-hour report verification metrics.
 */
export async function fetchReportSummary(): Promise<ReportSummary> {
  const response = await apiClient.get<ReportSummary>("/reports/summary");
  return response.data;
}

/**
 * Submit crowdsourced citizen flood report with optional photo.
 */
export interface AlertItem {
  alert_id: string;
  ward_id?: string;
  severity: "watch" | "warning" | "critical";
  channel: "cap" | "whatsapp" | "push" | "all";
  headline: string;
  message_text: string;
  cap_xml?: string;
  recipients_count: number;
  language_translations?: {
    en?: { headline: string; description: string; instruction: string };
    mr?: { headline: string; description: string; instruction: string };
    hi?: { headline: string; description: string; instruction: string };
  };
  dispatched_at: string;
}

export interface PublishAlertPayload {
  ward_id: string;
  severity: "watch" | "warning" | "critical";
  channel: "cap" | "whatsapp" | "push" | "all";
  headline: string;
  instruction?: string;
}

/**
 * List dispatched emergency flood bulletins.
 */
export async function fetchAlerts(wardId?: string): Promise<AlertItem[]> {
  const params: Record<string, any> = {};
  if (wardId) params.ward_id = wardId;
  const response = await apiClient.get<{ total: number; alerts: AlertItem[] }>("/alerts", { params });
  return response.data.alerts;
}

/**
 * Publish an emergency bulletin across CAP v1.2, WhatsApp, and Web Push.
 */
export async function publishAlert(payload: PublishAlertPayload): Promise<AlertItem> {
  const response = await apiClient.post<AlertItem>("/alerts", payload);
  return response.data;
}

export interface SocialSignalItem {
  signal_id: string;
  source: "twitter" | "telegram" | "helpline_1916" | "citizen_app";
  author_handle?: string;
  content_text: string;
  language: "en" | "mr" | "hi";
  ward_id?: string;
  location_name?: string;
  classification: "evacuation_needed" | "urgent" | "waterlogging" | "noise";
  urgency_score: number;
  confidence: number;
  extracted_landmarks?: string[];
  posted_at: string;
  ingested_at: string;
}

export interface HotspotKeyword {
  landmark: string;
  ward_id?: string;
  count: number;
  avg_urgency: number;
}

export interface SocialSummary {
  total_signals_24h: number;
  urgent_signals_count: number;
  evacuation_mentions_count: number;
  top_hotspots: HotspotKeyword[];
  classification_distribution: Record<string, number>;
}

/**
 * Fetch classified social media and helpline distress signals.
 */
export async function fetchSocialSignals(
  wardId?: string,
  classification?: string,
  urgencyMin?: number
): Promise<SocialSignalItem[]> {
  const params: Record<string, any> = {};
  if (wardId) params.ward_id = wardId;
  if (classification && classification !== "all") params.classification = classification;
  if (urgencyMin !== undefined) params.urgency_min = urgencyMin;
  
  const response = await apiClient.get<{ total: number; signals: SocialSignalItem[] }>(
    "/social/signals",
    { params }
  );
  return response.data.signals;
}

/**
 * Fetch 24-hour social situational summary and hot spots.
 */
export async function fetchSocialSummary(hours = 24): Promise<SocialSummary> {
  const response = await apiClient.get<SocialSummary>("/social/summary", {
    params: { hours },
  });
  return response.data;
}

/**
 * Submit / ingest a social post or helpline entry for NLP processing.
 */
export async function ingestSocialSignal(payload: {
  source: string;
  content_text: string;
  author_handle?: string;
  ward_id?: string;
  location_name?: string;
}): Promise<SocialSignalItem> {
  const response = await apiClient.post<SocialSignalItem>("/social/signals", payload);
  return response.data;
}

/**
 * Trigger simulation batch of Mumbai monsoon tweets and helpline signals.
 */
export async function simulateSocialFeed(): Promise<SocialSignalItem[]> {
  const response = await apiClient.post<SocialSignalItem[]>("/social/simulate");
  return response.data;
}

// -------------------------------------------------------------
// IoT Telemetry & Signals API
// -------------------------------------------------------------

export interface SensorItem {
  sensor_id: string;
  name: string;
  sensor_type: string;
  ward_id?: string;
  location_name: string;
  latitude: number;
  longitude: number;
  value: number;
  unit: string;
  danger_mark: number;
  warning_mark: number;
  status: "normal" | "warning" | "critical" | "offline";
  battery_pct: number;
  last_updated: string;
}

export interface TidePoint {
  timestamp: string;
  time_str: string;
  height_m: number;
  stage: "high" | "low";
  sluice_gates_status: "open" | "closed";
}

export interface TideTelemetry {
  current_tide_m: number;
  tidal_stage: "spring_tide" | "high_tide" | "normal";
  sluice_gates_locked: boolean;
  tide_datum: string;
  curve_24h: TidePoint[];
}

export interface RadarCell {
  cell_id: string;
  lat: number;
  lon: number;
  dbz: number;
  intensity: string;
  area: string;
}

export interface RadarSummary {
  radar_station: string;
  timestamp: string;
  peak_reflectivity_dbz: number;
  rain_rate_equivalent_mmh: number;
  storm_motion_direction: string;
  storm_speed_kmh: number;
  convective_cells: RadarCell[];
}

export async function fetchLiveSensors(): Promise<SensorItem[]> {
  const response = await apiClient.get<{ count: number; sensors: SensorItem[] }>("/signals/live");
  return response.data.sensors;
}

export async function fetchTides(): Promise<TideTelemetry> {
  const response = await apiClient.get<TideTelemetry>("/signals/tides");
  return response.data;
}

export async function fetchRadarSummary(): Promise<RadarSummary> {
  const response = await apiClient.get<RadarSummary>("/signals/radar");
  return response.data;
}

// -------------------------------------------------------------
// Safe Evacuation & Responder Routing API
// -------------------------------------------------------------

export interface RoutingLandmark {
  id: string;
  name: string;
  lat: number;
  lon: number;
  elevation_m: number;
  ward: string;
  type: string;
}

export interface BlockedRoadSegment {
  u: string;
  v: string;
  dist_km: number;
  time_min: number;
  water_depth_m: number;
  is_closed: boolean;
  corridor: string;
}

export interface SafeRouteResult {
  status: string;
  origin: string;
  destination: string;
  vehicle_type: string;
  estimated_transit_time_min: number;
  total_distance_km: number;
  max_water_depth_on_route_m: number;
  is_safe_elevated_route: boolean;
  waypoints_count: number;
  waypoints: Array<{
    step: number;
    node_id: string;
    name: string;
    lat: number;
    lon: number;
    elevation_m: number;
    type: string;
    ward: string;
  }>;
  advisory: string;
}

export async function fetchRoutingLandmarks(): Promise<RoutingLandmark[]> {
  const response = await apiClient.get<{ count: number; landmarks: RoutingLandmark[] }>("/routing/landmarks");
  return response.data.landmarks;
}

export async function fetchBlockedRoads(): Promise<BlockedRoadSegment[]> {
  const response = await apiClient.get<{ total_blocked_segments: number; segments: BlockedRoadSegment[] }>("/routing/blocked-roads");
  return response.data.segments;
}

export async function calculateSafeRoute(params: {
  origin_id: string;
  destination_id: string;
  vehicle_type?: string;
  avoid_waterlogging?: boolean;
}): Promise<SafeRouteResult> {
  const response = await apiClient.post<SafeRouteResult>("/routing/safe-path", {
    origin_id: params.origin_id,
    destination_id: params.destination_id,
    vehicle_type: params.vehicle_type || "standard_ambulance",
    avoid_waterlogging: params.avoid_waterlogging !== false,
  });
  return response.data;
}
