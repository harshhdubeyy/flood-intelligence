import axios from 'axios';

export type Ward = {
  id: string;
  name: string;
  risk_score?: number;
  risk_class?: 'low' | 'medium' | 'high' | 'critical';
  area_sqkm?: number;
  population?: number;
  is_coastal?: boolean;
  avg_elevation_m?: number;
  drainage_index?: number;
};

export type WaterDepth = 'ankle' | 'knee' | 'waist' | 'submerged';

export type CitizenReport = {
  report_id: string;
  ward_id: string | null;
  latitude: number;
  longitude: number;
  water_depth: WaterDepth;
  image_url: string | null;
  cv_verified: boolean;
  cv_water_depth_m: number | null;
  cv_confidence: number | null;
  cv_detected_objects: any[] | null;
  cv_water_detected: boolean | null;
  cv_reason: string | null;
  description: string | null;
  is_duplicate: boolean;
  duplicate_of_id: string | null;
  operator_verification_status?: 'pending' | 'confirmed' | 'rejected' | 'review_required' | 'resolved' | 'expired';
  location_validation_status?: 'matched' | 'outside_wards' | 'ambiguous_boundary' | null;
  submitted_at: string;
  nlp_analysis?: {
    classification?: string;
    confidence?: number;
    urgency_score?: number;
    is_flood_related?: boolean;
    is_waterlogging?: boolean;
    is_spam?: boolean;
    detected_language?: string;
    extracted_depth_m?: number | null;
    extracted_landmarks?: string[];
    matched_keywords?: string[];
    model_version?: string;
    provenance?: Record<string, any>;
    processed_at?: string;
  } | null;
};

export type ReportSummary = {
  total_reports: number;
  total_reports_24h: number;
  cv_verified_count: number;
  flagged_duplicates: number;
  severe_reports: number;
  ward_wise_counts: Record<string, number>;
  water_depth_distribution: Record<string, number>;
};

export type WardAnalytics = {
  ward_id: string;
  ward_name: string;
  total_reports: number;
  reports_last_1h: number;
  reports_last_3h: number;
  reports_last_24h: number;
  cv_verified_count: number;
  unverified_count: number;
  duplicate_count: number;
  severe_count: number;
  avg_severity: number;
  latest_incident: string | null;
};

export type WardIntelligenceScore = {
  ward_id: string;
  ward_name: string;
  intelligence_score: number;
  intelligence_class: 'minimal' | 'low' | 'moderate' | 'elevated' | 'critical';
  severity_factor: number;
  recency_factor: number;
  verification_factor: number;
  clustering_factor: number;
  volume_factor: number;
  report_count: number;
  cv_verified_count: number;
  duplicate_count: number;
  latest_incident: string | null;
  model_version: string;
  avg_reliability: number;
};

export type WardIntelligenceItem = {
  analytics: WardAnalytics;
  intelligence: WardIntelligenceScore | null;
  reliability_summary: {
    avg_reliability: number;
    total_scored: number;
    high_reliability: number;
    low_reliability: number;
  };
};

export type WardIntelligenceResponse = WardIntelligenceItem[];

export type ForecastHorizon = '1h' | '3h' | '6h' | '12h' | '24h';

export type WardPrediction = {
  ward_id: string | null;
  ward_code: string;
  ward_name: string;
  status: 'available' | 'low_confidence' | 'unavailable';
  current_risk_score: number | null;
  current_risk_category: string | null;
  current_risk_computed_at: string | null;
  current_risk_model_version: string | null;
  predicted_risk_score: number | null;
  predicted_probability: null;
  risk_category: 'low' | 'moderate' | 'high' | 'critical' | null;
  horizon: ForecastHorizon;
  prediction_timestamp: string;
  model_version: string;
  data_completeness: number;
  contributing_factors: string[];
  unavailable_reason: string | null;
  feature_vector: Record<string, unknown>;
  data_availability: Record<string, boolean>;
  feature_provenance: Record<string, unknown>;
};

export type WardPredictionsResponse = {
  horizon: ForecastHorizon;
  prediction_timestamp: string;
  model_version: string;
  outlook_type: 'heuristic_scenario_index';
  validated_probability_model: false;
  supported_horizons: ForecastHorizon[];
  wards: WardPrediction[];
};

export type ReportReliability = {
  report_id: string;
  reliability_score: number;
  cv_verified: boolean;
  cv_confidence: number | null;
  is_duplicate: boolean;
  has_image: boolean;
  has_description: boolean;
  score_breakdown: Record<string, number>;
};

export type FloodHotspot = {
  hotspot_id: string;
  center_latitude: number;
  center_longitude: number;
  radius_meters: number;
  report_count: number;
  cv_verified_count: number;
  severe_count: number;
  avg_severity: number;
  confidence: number;
  latest_incident: string | null;
  ward_ids: string[];
};

export type IntelligenceSummary = {
  total_reports: number;
  reports_last_24h: number;
  cv_verified_count: number;
  duplicate_count: number;
  severe_count: number;
  avg_intelligence_score: number;
  critical_wards: string[];
  hotspot_count: number;
  wards_with_reports: number;
  model_version: string;
};

export type SubmitReportPayload = {
  latitude: number;
  longitude: number;
  water_depth: WaterDepth;
  description?: string;
  image?: File;
};

export const http = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/v1',
  timeout: 30_000,
});

export type CitizenSubscriptionPayload = {
  device_token: string;
  platform: 'web_push' | 'fcm' | 'ios' | 'android';
  web_push_subscription?: {
    endpoint: string;
    keys: { p256dh: string; auth: string };
  };
  notification_consent: boolean;
  location_consent: boolean;
  preferred_language?: 'en' | 'hi' | 'mr';
  min_severity?: 'minor' | 'moderate' | 'severe' | 'extreme';
  latitude?: number | null;
  longitude?: number | null;
  ward_id?: string | null;
};

export type CitizenSubscription = {
  id: string;
  device_token: string;
  platform: string;
  is_active: boolean;
  notification_consent: boolean;
  location_consent: boolean;
  consent_timestamp: string | null;
  preferred_language: string;
  min_severity: string;
  has_location: boolean;
  ward_id: string | null;
  location_updated_at: string | null;
  created_at: string;
  updated_at: string;
};

export const api = {
  wards: () => http.get<Ward[]>('/wards').then((r) => r.data),

  wardBoundaries: async () => {
    const response = await fetch('/api/ward-boundaries');
    if (!response.ok) {
      throw new Error(`Could not load ward boundaries: ${response.status}`);
    }
    return response.json() as Promise<GeoJSON.FeatureCollection>;
  },

  wardGeojson: () =>
    http
      .get<GeoJSON.FeatureCollection>('/wards/geojson')
      .then((r) => r.data),

  ward: (id: string) => http.get(`/wards/${id}`).then((r) => r.data),

  wardRisk: (id: string) => http.get(`/wards/${id}/risk`).then((r) => r.data),

  reports: (params?: {
    ward_id?: string;
    verified_only?: boolean;
    water_depth?: WaterDepth;
    limit?: number;
    offset?: number;
  }) =>
    http
      .get<{ total: number; reports: CitizenReport[] }>('/reports', { params })
      .then((r) => r.data),

  reportsForMap: async () => {
    const pageSize = 100;
    const firstPage = await api.reports({ limit: pageSize, offset: 0 });
    const reports = [...firstPage.reports];

    for (let offset = pageSize; offset < firstPage.total; offset += pageSize * 5) {
      const offsets = Array.from(
        { length: Math.min(5, Math.ceil((firstPage.total - offset) / pageSize)) },
        (_, index) => offset + index * pageSize,
      );
      const pages = await Promise.all(
        offsets.map((pageOffset) => api.reports({ limit: pageSize, offset: pageOffset })),
      );
      pages.forEach((page) => reports.push(...page.reports));
    }

    return reports;
  },

  report: (id: string) => http.get<CitizenReport>(`/reports/${id}`).then((r) => r.data),

  reportSummary: () => http.get<ReportSummary>('/reports/summary').then((r) => r.data),

  wardIntelligence: (params?: { ward_id?: string }) =>
    http
      .get<WardIntelligenceResponse>('/reports/intelligence/wards', { params })
      .then((r) => r.data),

  wardIntelligenceDetail: (wardId: string) =>
    http.get(`/reports/intelligence/wards/${wardId}`).then((r) => r.data),

  wardPredictions: (horizon: ForecastHorizon) =>
    http
      .get<WardPredictionsResponse>('/predictions/wards', { params: { horizon } })
      .then((r) => r.data),

  reportReliability: (reportId: string) =>
    http.get(`/reports/intelligence/reliability/${reportId}`).then((r) => r.data),

  hotspots: (params?: {
    cluster_distance_m?: number;
    min_reports?: number;
    recency_hours?: number;
  }) =>
    http
      .get<FloodHotspot[]>('/reports/intelligence/hotspots', { params })
      .then((r) => r.data),

  intelligenceSummary: () =>
    http.get<IntelligenceSummary>('/reports/intelligence/summary').then((r) => r.data),

  submitReport: async (payload: SubmitReportPayload) => {
    const form = new FormData();
    form.append('latitude', String(payload.latitude));
    form.append('longitude', String(payload.longitude));
    form.append('water_depth', payload.water_depth);
    if (payload.description) form.append('description', payload.description);
    if (payload.image) form.append('image', payload.image);
    const { data } = await http.post('/reports', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data;
  },

  alerts: () => http.get('/alerts').then((r) => r.data),

  registerSubscription: (payload: CitizenSubscriptionPayload) =>
    http.post<CitizenSubscription>('/subscriptions', payload).then((r) => r.data),

  getSubscription: (id: string) =>
    http.get<CitizenSubscription>(`/subscriptions/${id}`).then((r) => r.data),

  updateSubscription: (id: string, payload: Partial<CitizenSubscriptionPayload>) =>
    http.put<CitizenSubscription>(`/subscriptions/${id}`, payload).then((r) => r.data),

  revokeSubscription: (id: string, reason?: string) =>
    http.post<CitizenSubscription>(`/subscriptions/${id}/revoke`, { reason }).then((r) => r.data),

  getVapidPublicKey: () =>
    http.get<{ public_key: string | null; enabled: boolean }>('/subscriptions/vapid-public-key').then((r) => r.data),
};
