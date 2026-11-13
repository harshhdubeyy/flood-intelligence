import type { CitizenReport, WaterDepth } from './api';

export type OperatorReport = CitizenReport & {
  operator_verification_status: 'pending' | 'confirmed' | 'rejected' | 'review_required' | 'resolved' | 'expired';
  location_validation_status: 'matched' | 'outside_wards' | 'ambiguous_boundary';
};

export type OperatorHistoryEntry = {
  id: number;
  report_id: string;
  event_id: string | null;
  operator_id: string;
  action: string;
  previous_status: string;
  new_status: string;
  reason: string | null;
  event_timestamp: string | null;
  latitude: number | null;
  longitude: number | null;
  location_validation_status: string | null;
  ward_id: string | null;
  water_depth: WaterDepth | null;
  water_depth_m: number | null;
  is_duplicate: boolean;
  duplicate_of_report_id: string | null;
  evidence_image_urls: string[];
  occurred_at: string;
};

export type QueueResponse = { total: number; reports: OperatorReport[] };

export type VerificationPayload = {
  action: 'confirm' | 'reject' | 'review';
  reason?: string;
  event_timestamp?: string;
  latitude?: number;
  longitude?: number;
  water_depth?: WaterDepth;
  water_depth_m?: number;
};

export type AlertRecord = {
  id: string;
  ward_id: string | null;
  headline: string;
  instruction: string | null;
  severity: 'minor' | 'moderate' | 'severe' | 'extreme';
  channel: string;
  status:
    | 'draft'
    | 'pending_approval'
    | 'approved'
    | 'queued'
    | 'dispatching'
    | 'completed'
    | 'partially_failed'
    | 'failed'
    | 'cancelled'
    | 'expired';
  requires_approval: boolean;
  center_lat: number | null;
  center_lon: number | null;
  radius_km: number | null;
  expires_at: string | null;
  approved_at: string | null;
  approved_by: string | null;
  dispatched_at: string | null;
  cancelled_at: string | null;
  cancellation_reason: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
};

export type AlertRecipientPreview = {
  alert_id?: string | null;
  ward_id?: string | null;
  center_lat?: number | null;
  center_lon?: number | null;
  radius_km: number;
  min_severity?: string | null;
  eligible_subscriptions_count: number;
  breakdown_by_platform: Record<string, number>;
  breakdown_by_language: Record<string, number>;
  targeting_criteria: Record<string, any>;
};

export type DeliveryStatus = {
  id: string;
  alert_id: string;
  subscription_id: string;
  channel: string;
  status: string;
  attempt_count: number;
  error_message: string | null;
  sent_at: string | null;
  delivered_at: string | null;
  created_at: string;
};

export type DeliveryAnalytics = {
  alert_id: string;
  total_recipients: number;
  attempted: number;
  successful: number;
  failed: number;
  pending: number;
  success_rate: number;
  breakdown_by_provider: Record<string, { attempted: number; successful: number; failed: number }>;
  common_errors: Array<{ error_type: string; count: number; sample_message: string | null }>;
  dispatch_duration_ms: number | null;
};

export type AlertConfig = {
  dispatch_enabled: boolean;
  default_radius_km: number;
  location_freshness_hours: number;
  vapid_public_key: string | null;
  vapid_configured: boolean;
  fcm_configured: boolean;
  max_retry_attempts: number;
};

export type CreateAlertPayload = {
  ward_id?: string;
  center_lat?: number;
  center_lon?: number;
  radius_km?: number;
  headline: string;
  instruction?: string;
  severity: 'minor' | 'moderate' | 'severe' | 'extreme';
  channel?: string;
  requires_approval?: boolean;
  expires_in_hours?: number;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/operator/${path}`, {
    ...init,
    cache: 'no-store',
  });
  if (!response.ok) {
    if (response.status === 401 && typeof window !== 'undefined') {
      window.dispatchEvent(new Event('operator-session-expired'));
    }
    let detail = `Request failed (${response.status}).`;
    try {
      const body = await response.json() as { detail?: string };
      detail = body.detail ?? detail;
    } catch {
      // Keep the HTTP status when the server does not return a JSON error.
    }
    throw new Error(detail);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const operatorApi = {
  login: (operatorId: string, token: string) =>
    request<{ operator_id: string; expires_at: string }>('session', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ operator_id: operatorId, token }),
    }),

  logout: () => request<void>('session', { method: 'DELETE' }),

  queue: (status: OperatorReport['operator_verification_status'], limit = 100) => {
    const query = new URLSearchParams({ verification_status: status, limit: String(limit) });
    return request<QueueResponse>(`reports/operator/queue?${query}`);
  },

  pendingQueue: (limit = 100, offset = 0) => {
    const query = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    return request<QueueResponse>(`reports/operator/queue?${query}`);
  },

  history: (reportId: string) =>
    request<OperatorHistoryEntry[]>(`reports/${encodeURIComponent(reportId)}/verification-history`),

  decide: (reportId: string, payload: VerificationPayload) =>
    request<{ report_id: string; operator_verification_status: string; official_confirmation: boolean }>(
      `reports/${encodeURIComponent(reportId)}/verification`,
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) },
    ),

  addEvidence: async (reportId: string, note: string, photos: File[]) => {
    const form = new FormData();
    if (note.trim()) form.append('note', note.trim());
    photos.forEach((photo) => form.append('photos', photo));
    const response = await fetch(
      `/api/operator/reports/${encodeURIComponent(reportId)}/verification-evidence`,
      { method: 'POST', body: form, cache: 'no-store' },
    );
    if (!response.ok) {
      if (response.status === 401) {
        window.dispatchEvent(new Event('operator-session-expired'));
      }
      let detail = `Evidence upload failed (${response.status}).`;
      try {
        const body = await response.json() as { detail?: string };
        detail = body.detail ?? detail;
      } catch {
        // Keep the HTTP status when the server does not return a JSON error.
      }
      throw new Error(detail);
    }
    return response.json() as Promise<{ evidence_image_urls: string[] }>;
  },

  imagePath: (url: string) => {
    const prefix = '/v1/reports/';
    const marker = '/verification-evidence/';
    const reportIndex = url.indexOf(prefix);
    const evidenceIndex = url.indexOf(marker);
    if (reportIndex >= 0 && evidenceIndex > reportIndex) {
      const suffix = url.slice(evidenceIndex + marker.length).split(/[?#]/, 1)[0];
      const reportId = url.slice(reportIndex + prefix.length, evidenceIndex);
      if (reportId && suffix && !reportId.includes('/')) {
        return `/api/operator/reports/${encodeURIComponent(reportId)}/verification-evidence/${encodeURIComponent(suffix)}`;
      }
    }
    return url;
  },

  getAlerts: () => request<AlertRecord[]>('alerts'),

  getAlert: (alertId: string) => request<AlertRecord>(`alerts/${encodeURIComponent(alertId)}`),

  getAlertConfig: () => request<AlertConfig>('alerts/config'),

  createAlert: (payload: CreateAlertPayload) =>
    request<AlertRecord>('alerts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),

  previewRecipients: (alertId: string) =>
    request<AlertRecipientPreview>(`alerts/${encodeURIComponent(alertId)}/recipients`),

  approveAlert: (alertId: string, notes?: string) =>
    request<AlertRecord>(`alerts/${encodeURIComponent(alertId)}/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ notes }),
    }),

  dispatchAlert: (alertId: string, force = false) =>
    request<{ alert_id: string; status: string; total_recipients: number; successful: number; failed: number }>(
      `alerts/${encodeURIComponent(alertId)}/dispatch`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ force }),
      },
    ),

  cancelAlert: (alertId: string, reason: string) =>
    request<AlertRecord>(`alerts/${encodeURIComponent(alertId)}/cancel`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason }),
    }),

  getDeliveries: (alertId: string) =>
    request<DeliveryStatus[]>(`alerts/${encodeURIComponent(alertId)}/deliveries`),

  getAnalytics: (alertId: string) =>
    request<DeliveryAnalytics>(`alerts/${encodeURIComponent(alertId)}/analytics`),
};
