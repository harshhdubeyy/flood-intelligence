export type SocialProviderStatus = {
  platform: string;
  state: 'configured' | 'not_configured' | 'disabled' | 'error';
  configured: boolean;
  last_success_at: string | null;
  lifecycle_policy_ready: boolean;
};

export type SocialStatus = {
  providers: SocialProviderStatus[];
  latest_success_at: string | null;
};

export type SocialPost = {
  id: number;
  platform: string;
  external_post_id: string | null;
  original_url: string | null;
  text_content: string | null;
  posted_at: string | null;
  collected_at: string;
  location_text: string | null;
  latitude: number | null;
  longitude: number | null;
  ward_id: string | null;
  geolocation_confidence: number | null;
  ward_assignment_provenance: string | null;
  matched_keywords: string[];
  media_references: { url: string; type: string }[];
  processing_status: string;
  source_provenance: Record<string, unknown>;
  source_status: 'unverified' | 'current' | 'pending_compliance' | 'unavailable' | 'expired' | 'deleted';
  expires_at: string | null;
  last_verified_at: string | null;
  next_reconcile_at: string | null;
};

export type SocialPostsPage = {
  total: number;
  limit: number;
  offset: number;
  posts: SocialPost[];
};

export type SocialSummary = {
  total_posts: number;
  posts_last_24h: number;
  platform_breakdown: Record<string, number>;
  latest_collected_at: string | null;
};

async function request<T>(path: string): Promise<T> {
  const response = await fetch(`/api/operator/social/${path}`, { cache: 'no-store' });
  if (!response.ok) {
    if (response.status === 401 && typeof window !== 'undefined') {
      window.dispatchEvent(new Event('operator-session-expired'));
    }
    let detail = `Social intelligence request failed (${response.status}).`;
    try {
      const body = await response.json() as { detail?: string };
      detail = body.detail ?? detail;
    } catch {
      // Preserve the HTTP status when the proxy returns a non-JSON error.
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

async function mutate<T>(path: string, payload: unknown): Promise<T> {
  const response = await fetch(`/api/operator/social/${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    cache: 'no-store',
  });
  if (!response.ok) {
    if (response.status === 401 && typeof window !== 'undefined') {
      window.dispatchEvent(new Event('operator-session-expired'));
    }
    throw new Error(`Social compliance request failed (${response.status}).`);
  }
  return response.json() as Promise<T>;
}

export const socialApi = {
  status: () => request<SocialStatus>('status'),
  summary: () => request<SocialSummary>('summary'),
  posts: (filters: { keyword?: string; posted_from?: string; posted_to?: string }) => {
    const query = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value) query.set(key, value);
    });
    const encoded = query.toString();
    const suffix = encoded ? `?${encoded}` : '';
    return request<SocialPostsPage>(`posts${suffix}`);
  },
  takedown: (postId: number) =>
    mutate<{ status: string; outcome: string }>('compliance/takedowns', { post_id: postId }),
};
