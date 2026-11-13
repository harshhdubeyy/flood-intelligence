'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ExternalLink, Radio, ShieldAlert, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { socialApi } from '../lib/social-api';

function displayTime(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleString() : 'Not available';
}

export function SocialIntelligence() {
  const queryClient = useQueryClient();
  const [keyword, setKeyword] = useState('');
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');
  const status = useQuery({
    queryKey: ['social', 'status'],
    queryFn: socialApi.status,
    staleTime: 0,
    gcTime: 0,
    refetchInterval: 10_000,
    refetchOnWindowFocus: true,
  });
  const summary = useQuery({
    queryKey: ['social', 'summary'],
    queryFn: socialApi.summary,
    staleTime: 0,
    gcTime: 0,
    refetchInterval: 10_000,
    refetchOnWindowFocus: true,
  });
  const dateFilters = {
    keyword: keyword.trim() || undefined,
    posted_from: fromDate ? `${fromDate}T00:00:00.000Z` : undefined,
    posted_to: toDate ? `${toDate}T23:59:59.999Z` : undefined,
  };
  const posts = useQuery({
    queryKey: ['social', 'posts', dateFilters],
    queryFn: () => socialApi.posts(dateFilters),
    staleTime: 0,
    gcTime: 0,
    refetchInterval: 10_000,
    refetchOnWindowFocus: true,
  });
  const takedown = useMutation({
    mutationFn: socialApi.takedown,
    onSuccess: async () => {
      queryClient.removeQueries({ queryKey: ['social'] });
      await queryClient.invalidateQueries({ queryKey: ['social'] });
    },
  });

  const providerList = status.data?.providers ?? [];
  const postList = posts.data?.posts ?? [];
  return (
    <div className="social-intelligence">
      <section className="social-source-panel" aria-label="Social source availability">
        <div>
          <div className="social-eyebrow">AUTHORIZED PUBLIC SOURCES</div>
          <h2>Collection status</h2>
        </div>
        <div className="social-providers">
          {providerList.map((provider) => (
            <article className="social-provider" key={provider.platform}>
              <span className={`social-state ${provider.state}`} />
              <div>
                <strong>{provider.platform === 'x' ? 'X API' : 'Reddit API'}</strong>
                <small>
                  {provider.state === 'not_configured'
                    ? 'Credentials not configured'
                    : provider.state === 'disabled'
                      ? 'Collection disabled by backend configuration'
                    : provider.state === 'error'
                      ? 'Last collection attempt failed'
                      : 'Configured · collection not continuously scheduled'}
                </small>
                <small>Last successful collection: {displayTime(provider.last_success_at)}</small>
                <small>
                  Retention controls: {provider.lifecycle_policy_ready ? 'Configured' : 'Not approved/configured'}
                </small>
              </div>
            </article>
          ))}
          {status.isLoading && <p>Loading provider status…</p>}
          {status.isError && <p className="social-error">Provider status is unavailable.</p>}
        </div>
        <p className="social-latest">
          Latest successful collection: {displayTime(status.data?.latest_success_at)}
        </p>
      </section>

      <div className="kpis social-kpis">
        <div className="metric"><label>COLLECTED POSTS</label><strong className="metric-value">{summary.data?.total_posts ?? '—'}</strong><small>Public API records only</small></div>
        <div className="metric"><label>LAST 24 HOURS</label><strong className="metric-value">{summary.data?.posts_last_24h ?? '—'}</strong><small>By collection time</small></div>
        <div className="metric"><label>REDDIT</label><strong className="metric-value">{summary.data?.platform_breakdown.reddit ?? '—'}</strong><small>Distinct sourced posts</small></div>
        <div className="metric"><label>X</label><strong className="metric-value">{summary.data?.platform_breakdown.x ?? '—'}</strong><small>Distinct sourced posts</small></div>
      </div>

      <section className="list-surface social-feed">
        <div className="social-feed-heading">
          <div><div className="social-eyebrow">SOURCE RECORDS</div><h2>Recent public posts</h2></div>
          {posts.data && <span>{posts.data.total} matching records</span>}
        </div>
        <div className="social-filters">
          <label>Keyword
            <input value={keyword} onChange={(event) => setKeyword(event.target.value)} maxLength={80} placeholder="Filter matched keyword" />
          </label>
          <label>From
            <input type="date" value={fromDate} onChange={(event) => setFromDate(event.target.value)} />
          </label>
          <label>To
            <input type="date" value={toDate} onChange={(event) => setToDate(event.target.value)} />
          </label>
        </div>
        {posts.isError && <p className="social-error">Posts could not be loaded. Check your operator session and retry.</p>}
        {takedown.isError && <p className="social-error">The removal request could not be confirmed. Refresh the feed before retrying.</p>}
        {posts.isLoading && <p className="social-muted">Loading collected source records…</p>}
        {!posts.isLoading && !posts.isError && postList.length === 0 && (
          <div className="social-empty"><Radio size={20} /><strong>No collected posts match these filters.</strong><span>No sample or synthetic posts are displayed.</span></div>
        )}
        <div className="social-post-list">
          {postList.map((post) => (
            <article className="social-post" key={post.id}>
              <div className="social-post-meta">
                <strong>{post.platform === 'x' ? 'X' : 'Reddit'}</strong>
                <span>{displayTime(post.posted_at)}</span>
                <span className="social-processing">{post.processing_status}</span>
                <span className={`social-processing source-${post.source_status}`}>
                  {post.source_status.replaceAll('_', ' ')}
                </span>
              </div>
              {post.source_status === 'current' && post.expires_at && new Date(post.expires_at).getTime() > Date.now() ? (
                <>
                  <p>{post.text_content || 'Source did not provide post text.'}</p>
                  <div className="social-post-details">
                    <span>Location: {post.location_text || 'Unresolved'}</span>
                    <span>Ward: {post.ward_id || 'Unassigned'}</span>
                    <span>Last verified: {displayTime(post.last_verified_at)}</span>
                    <span>Next source check: {displayTime(post.next_reconcile_at)}</span>
                    <span>Expires: {displayTime(post.expires_at)}</span>
                  </div>
                  {!!post.matched_keywords.length && (
                    <div className="social-keywords">{post.matched_keywords.map((item) => <span key={item}>{item}</span>)}</div>
                  )}
                  {post.original_url && (
                    <a href={post.original_url} target="_blank" rel="noreferrer">
                      View original post <ExternalLink size={13} />
                    </a>
                  )}
                </>
              ) : (
                <div className="social-post-details">
                  <ShieldAlert size={14} />
                  <span>
                    {post.source_status === 'deleted'
                      ? 'Deletion or takedown recorded; stored content has been erased.'
                      : post.source_status === 'unavailable'
                        ? 'Source is unavailable through the provider API; stored content has been erased without inferring why.'
                      : post.source_status === 'expired'
                        ? 'Retention deadline passed; stored content has been erased.'
                        : post.source_status === 'pending_compliance'
                          ? 'Compliance action pending; source content is hidden.'
                          : 'Source availability is unverified; content is hidden.'}
                  </span>
                </div>
              )}
              {!['deleted', 'expired', 'unavailable'].includes(post.source_status) && (
                <button
                  type="button"
                  disabled={takedown.isPending}
                  onClick={() => {
                    if (window.confirm('Remove this social source record and its derived data?')) {
                      takedown.mutate(post.id);
                    }
                  }}
                >
                  <Trash2 size={13} /> Request removal
                </button>
              )}
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
