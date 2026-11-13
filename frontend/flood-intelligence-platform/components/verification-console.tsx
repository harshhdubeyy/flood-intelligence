'use client';

import dynamic from 'next/dynamic';
import { AlertTriangle, Check, Clock3, FileText, LogOut, MapPin, ShieldCheck, Upload, X } from 'lucide-react';
import { type FormEvent, useCallback, useEffect, useMemo, useState } from 'react';
import { api, type Ward, type WaterDepth } from '../lib/api';
import {
  operatorApi,
  type OperatorHistoryEntry,
  type OperatorReport,
  type VerificationPayload,
} from '../lib/operator-api';
import type { SelectedWard } from './geo-map';

const GeoMap = dynamic(() => import('./geo-map').then((module) => module.GeoMap), { ssr: false });
const PAGE_SIZE = 50;

type StatusFilter = 'needs_review' | 'all' | OperatorReport['operator_verification_status'];
type TextFilter = 'all' | 'yes' | 'no';

function localImageUrl(url: string): string {
  if (/^https?:\/\//i.test(url)) return url;
  const base = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/v1').replace(/\/v1\/?$/, '');
  return new URL(url, base).toString();
}

function statusLabel(status: OperatorReport['operator_verification_status']): string {
  return status.replace('_', ' ');
}

function dateLabel(value: string | null | undefined): string {
  if (!value) return 'Not recorded';
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleString();
}

function Login({ onLogin }: { onLogin: (operatorId: string, token: string) => Promise<void> }) {
  const [operatorId, setOperatorId] = useState('');
  const [token, setToken] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      await onLogin(operatorId, token);
      setToken('');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Sign-in failed.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="operator-login">
      <form className="operator-login-card" onSubmit={submit}>
        <div className="operator-brand"><ShieldCheck size={22}/></div>
        <div className="ops-eyebrow">MUMBAI FLOOD INTELLIGENCE</div>
        <h1>Operator sign in</h1>
        <p>Authorized personnel only. Decisions are recorded in an append-only audit history.</p>
        <label>Operator ID<input autoComplete="username" value={operatorId} onChange={(event) => setOperatorId(event.target.value)} required/></label>
        <label>Bearer token<input type="password" autoComplete="current-password" value={token} onChange={(event) => setToken(event.target.value)} required/></label>
        {error && <div className="ops-error" role="alert">{error}</div>}
        <button className="ops-primary" type="submit" disabled={submitting}>{submitting ? 'Verifying…' : 'Sign in securely'}</button>
        <small>Credentials are sent to this server for verification and are not stored in browser storage.</small>
      </form>
    </main>
  );
}

export function VerificationConsole() {
  const [operatorId, setOperatorId] = useState('');
  const [sessionChecked, setSessionChecked] = useState(false);
  const [reports, setReports] = useState<OperatorReport[]>([]);
  const [boundaries, setBoundaries] = useState<GeoJSON.FeatureCollection | null>(null);
  const [totalPending, setTotalPending] = useState(0);
  const [offset, setOffset] = useState(0);
  const [wards, setWards] = useState<Ward[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [history, setHistory] = useState<OperatorHistoryEntry[]>([]);
  const [historyError, setHistoryError] = useState('');
  const [queueError, setQueueError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [filterStatus, setFilterStatus] = useState<StatusFilter>('needs_review');
  const [wardFilter, setWardFilter] = useState('all');
  const [dateFilter, setDateFilter] = useState('');
  const [depthFilter, setDepthFilter] = useState<WaterDepth | 'all'>('all');
  const [cvFilter, setCvFilter] = useState<TextFilter>('all');
  const [duplicateFilter, setDuplicateFilter] = useState<TextFilter>('all');
  const [reason, setReason] = useState('');
  const [incidentTimestamp, setIncidentTimestamp] = useState('');
  const [latitude, setLatitude] = useState('');
  const [longitude, setLongitude] = useState('');
  const [depth, setDepth] = useState<WaterDepth>('ankle');
  const [measuredDepth, setMeasuredDepth] = useState('');
  const [evidenceNote, setEvidenceNote] = useState('');
  const [evidenceFiles, setEvidenceFiles] = useState<File[]>([]);
  const [actionError, setActionError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const refreshQueue = useCallback(async () => {
    if (!operatorId) return;
    setQueueError('');
    try {
      const [pending, confirmed, rejected] = await Promise.all([
        operatorApi.pendingQueue(PAGE_SIZE, offset),
        operatorApi.queue('confirmed', 100),
        operatorApi.queue('rejected', 100),
      ]);
      const allReports = [...pending.reports, ...confirmed.reports, ...rejected.reports];
      setReports(allReports);
      setTotalPending(pending.total);
      setSelectedId((current) => current && allReports.some((report) => report.report_id === current)
        ? current
        : pending.reports[0]?.report_id ?? allReports[0]?.report_id ?? '');
    } catch (error) {
      setQueueError(error instanceof Error ? error.message : 'Could not load the operator queue.');
    }
  }, [operatorId, offset]);

  useEffect(() => {
    let active = true;
    fetch('/api/operator/session', { cache: 'no-store' })
      .then(async (response) => {
        if (!response.ok) return null;
        return response.json() as Promise<{ operator_id: string }>;
      })
      .then((session) => {
        if (active && session) setOperatorId(session.operator_id);
      })
      .catch(() => undefined)
      .finally(() => {
        if (active) setSessionChecked(true);
      });
    api.wards().then(setWards).catch(() => undefined);
    api.wardBoundaries().then(setBoundaries).catch(() => undefined);
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!operatorId) return;
    void refreshQueue();
    const timer = window.setInterval(() => void refreshQueue(), 30_000);
    return () => window.clearInterval(timer);
  }, [operatorId, refreshQueue]);

  useEffect(() => {
    const expireSession = () => {
      setOperatorId('');
      setReports([]);
      setHistory([]);
    };
    window.addEventListener('operator-session-expired', expireSession);
    return () => window.removeEventListener('operator-session-expired', expireSession);
  }, []);

  const reportById = useMemo(() => new Map(reports.map((report) => [report.report_id, report])), [reports]);
  const selected = reportById.get(selectedId) ?? null;

  useEffect(() => {
    setReason('');
    setIncidentTimestamp(selected?.submitted_at ?? '');
    setLatitude(selected ? String(selected.latitude) : '');
    setLongitude(selected ? String(selected.longitude) : '');
    setDepth(selected?.water_depth ?? 'ankle');
    setMeasuredDepth('');
    setHistory([]);
    setHistoryError('');
    if (!operatorId || !selected) return;
    let active = true;
    operatorApi.history(selected.report_id)
      .then((entries) => { if (active) setHistory(entries); })
      .catch((error: unknown) => {
        if (active) setHistoryError(error instanceof Error ? error.message : 'Could not load review history.');
      });
    return () => { active = false; };
  }, [operatorId, selected?.report_id, selected?.submitted_at, selected?.latitude, selected?.longitude, selected?.water_depth]);

  const filteredReports = useMemo(() => reports.filter((report) => {
    if (filterStatus === 'needs_review' && !['pending', 'review_required'].includes(report.operator_verification_status)) return false;
    if (filterStatus !== 'needs_review' && filterStatus !== 'all' && report.operator_verification_status !== filterStatus) return false;
    if (wardFilter !== 'all' && report.ward_id !== wardFilter) return false;
    if (dateFilter && !report.submitted_at.startsWith(dateFilter)) return false;
    if (depthFilter !== 'all' && report.water_depth !== depthFilter) return false;
    if (cvFilter !== 'all' && report.cv_verified !== (cvFilter === 'yes')) return false;
    if (duplicateFilter !== 'all' && report.is_duplicate !== (duplicateFilter === 'yes')) return false;
    return true;
  }), [reports, filterStatus, wardFilter, dateFilter, depthFilter, cvFilter, duplicateFilter]);

  const wardNames = useMemo(() => new Map(wards.map((ward) => [ward.id, ward.name])), [wards]);

  async function login(id: string, token: string) {
    const session = await operatorApi.login(id.trim(), token);
    setOffset(0);
    setOperatorId(session.operator_id);
  }

  async function logout() {
    try {
      await operatorApi.logout();
    } finally {
      setOperatorId('');
      setReports([]);
      setHistory([]);
    }
  }

  async function decide(action: VerificationPayload['action']) {
    if (!selected) return;
    setActionError('');
    if (action !== 'confirm' && !reason.trim()) {
      setActionError('A reason is required to reject or flag a report for review.');
      return;
    }
    if (!/(?:[zZ]|[+-]\d{2}:\d{2})$/.test(incidentTimestamp) || Number.isNaN(new Date(incidentTimestamp).valueOf())) {
      setActionError('Use an ISO timestamp that includes a timezone, such as 2026-07-14T12:30:00+05:30.');
      return;
    }
    const lat = Number(latitude);
    const lon = Number(longitude);
    if (!Number.isFinite(lat) || lat < -90 || lat > 90 || !Number.isFinite(lon) || lon < -180 || lon > 180) {
      setActionError('Enter valid latitude and longitude coordinates.');
      return;
    }
    const waterDepth = measuredDepth.trim() ? Number(measuredDepth) : undefined;
    if (waterDepth !== undefined && (!Number.isFinite(waterDepth) || waterDepth < 0)) {
      setActionError('Measured water depth must be a non-negative number of metres.');
      return;
    }

    setSubmitting(true);
    try {
      await operatorApi.decide(selected.report_id, {
        action,
        reason: reason.trim() || undefined,
        event_timestamp: incidentTimestamp,
        latitude: lat,
        longitude: lon,
        water_depth: depth,
        water_depth_m: waterDepth,
      });
      setNotice(`Report ${selected.report_id} marked ${action === 'confirm' ? 'confirmed' : action === 'reject' ? 'rejected' : 'for review'}. This is not an official BMC confirmation.`);
      await refreshQueue();
      setHistory(await operatorApi.history(selected.report_id));
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'The verification decision failed.');
    } finally {
      setSubmitting(false);
    }
  }

  async function addEvidence(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected || !evidenceFiles.length || !evidenceNote.trim()) {
      setActionError('Add a short evidence note and at least one photograph.');
      return;
    }
    const form = event.currentTarget;
    setActionError('');
    setSubmitting(true);
    try {
      await operatorApi.addEvidence(selected.report_id, evidenceNote, evidenceFiles);
      setEvidenceNote('');
      setEvidenceFiles([]);
      form.reset();
      setHistory(await operatorApi.history(selected.report_id));
      setNotice('Evidence added to the report audit history.');
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'Evidence upload failed.');
    } finally {
      setSubmitting(false);
    }
  }

  if (!sessionChecked) {
    return <main className="operator-loading">Checking operator session…</main>;
  }
  if (!operatorId) return <Login onLogin={login}/>;

  return (
    <main className="operator-page">
      <header className="ops-header">
        <div className="ops-logo"><ShieldCheck size={19}/></div>
        <div><div className="ops-eyebrow">MUMBAI FLOOD INTELLIGENCE · OPERATIONS</div><h1>Incident verification</h1></div>
        <div className="ops-header-right"><span className="ops-auth"><i/>Authenticated · {operatorId}</span><button className="ops-logout" onClick={() => void logout()}><LogOut size={15}/>Sign out</button></div>
      </header>

      <section className="ops-metrics" aria-label="Queue summary">
        <div><span>Awaiting review</span><strong>{totalPending}</strong></div>
        <div><span>Loaded on map</span><strong>{reports.length}</strong></div>
        <div><span>CV verified</span><strong>{reports.filter((report) => report.cv_verified).length}</strong></div>
        <div><span>Location warnings</span><strong>{reports.filter((report) => report.location_validation_status !== 'matched').length}</strong></div>
      </section>

      {notice && <div className="ops-notice" role="status"><Check size={16}/>{notice}<button onClick={() => setNotice('')} aria-label="Dismiss"><X size={15}/></button></div>}
      {queueError && <div className="ops-error" role="alert">{queueError}<button onClick={() => void refreshQueue()}>Retry</button></div>}

      <section className="ops-workspace">
        <aside className="ops-queue">
          <div className="ops-section-heading"><div><span className="ops-eyebrow">CITIZEN SUBMISSIONS</span><h2>Review queue</h2></div><button className="ops-icon-button" onClick={() => void refreshQueue()} aria-label="Refresh queue"><Clock3 size={16}/></button></div>
          <div className="ops-filter-grid">
            <label>Status<select value={filterStatus} onChange={(event) => setFilterStatus(event.target.value as StatusFilter)}><option value="needs_review">Needs review</option><option value="all">All loaded</option><option value="pending">Pending</option><option value="review_required">Flagged for review</option><option value="confirmed">Confirmed</option><option value="rejected">Rejected</option></select></label>
            <label>Ward<select value={wardFilter} onChange={(event) => setWardFilter(event.target.value)}><option value="all">All wards</option>{wards.map((ward) => <option key={ward.id} value={ward.id}>{ward.name}</option>)}</select></label>
            <label>Submitted on<input type="date" value={dateFilter} onChange={(event) => setDateFilter(event.target.value)}/></label>
            <label>Reported depth<select value={depthFilter} onChange={(event) => setDepthFilter(event.target.value as WaterDepth | 'all')}><option value="all">Any depth</option><option value="ankle">Ankle</option><option value="knee">Knee</option><option value="waist">Waist</option><option value="submerged">Submerged</option></select></label>
            <label>CV verification<select value={cvFilter} onChange={(event) => setCvFilter(event.target.value as TextFilter)}><option value="all">All</option><option value="yes">CV verified</option><option value="no">Not verified</option></select></label>
            <label>Duplicate<select value={duplicateFilter} onChange={(event) => setDuplicateFilter(event.target.value as TextFilter)}><option value="all">All</option><option value="yes">Duplicate</option><option value="no">Not duplicate</option></select></label>
          </div>
          <div className="ops-queue-count">{filteredReports.length} shown · {filterStatus === 'needs_review' ? `${totalPending} awaiting review` : `${reports.length} loaded`}</div>
          <div className="ops-report-list">
            {filteredReports.map((report) => (
              <button key={report.report_id} className={`ops-report-row ${selectedId === report.report_id ? 'selected' : ''}`} onClick={() => setSelectedId(report.report_id)}>
                <div className="ops-report-row-top"><strong>{wardNames.get(report.ward_id ?? '') ?? report.ward_id ?? 'Ward unresolved'}</strong><span className={`ops-status ${report.operator_verification_status}`}>{statusLabel(report.operator_verification_status)}</span></div>
                <div className="ops-report-row-meta"><span>{dateLabel(report.submitted_at)}</span><span>{report.water_depth} depth</span></div>
                <div className="ops-report-flags">{report.cv_verified && <span className="ops-flag cv">CV checked</span>}{report.is_duplicate && <span className="ops-flag duplicate">Duplicate</span>}{report.location_validation_status !== 'matched' && <span className="ops-flag warning">Location warning</span>}</div>
              </button>
            ))}
            {!filteredReports.length && <div className="ops-empty">No reports match these filters.</div>}
          </div>
          <div className="ops-pagination">
            <span>{Math.min(offset + 1, totalPending)}–{Math.min(offset + PAGE_SIZE, totalPending)} of {totalPending} awaiting review</span>
            <div><button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Previous</button><button disabled={offset + PAGE_SIZE >= totalPending} onClick={() => setOffset(offset + PAGE_SIZE)}>Next</button></div>
          </div>
        </aside>

        <section className="ops-detail">
          {!selected ? <div className="ops-empty ops-empty-large"><MapPin size={22}/><h2>Select a report</h2><p>Choose an item from the queue to review the submission and its evidence.</p></div> : (
            <>
              <div className="ops-detail-header">
                <div><span className="ops-eyebrow">REPORT {selected.report_id}</span><h2>{wardNames.get(selected.ward_id ?? '') ?? selected.ward_id ?? 'Ward not resolved'}</h2><p>Citizen-submitted · {dateLabel(selected.submitted_at)}</p></div>
                <span className={`ops-status ${selected.operator_verification_status}`}>{statusLabel(selected.operator_verification_status)}</span>
              </div>

              <div className="ops-source-banner"><AlertTriangle size={16}/><span>CV results are advisory only. Operator confirmation records a verified citizen report candidate, not an official BMC-confirmed incident.</span></div>

              <div className="ops-detail-grid">
                <section className="ops-card">
                  <h3>Original submission</h3>
                  <dl className="ops-facts">
                    <div><dt>Submitted</dt><dd>{dateLabel(selected.submitted_at)}</dd></div>
                    <div><dt>Citizen water depth</dt><dd>{selected.water_depth}</dd></div>
                    <div><dt>CV verification</dt><dd>{selected.cv_verified ? 'CV verified' : 'Not verified'}{selected.cv_confidence == null ? '' : ` · ${(selected.cv_confidence * 100).toFixed(0)}% confidence`}</dd></div>
                    <div><dt>CV depth estimate</dt><dd>{selected.cv_water_depth_m == null ? 'Not available' : `${selected.cv_water_depth_m.toFixed(2)} m`}</dd></div>
                    <div><dt>Duplicate</dt><dd>{selected.is_duplicate ? `Yes${selected.duplicate_of_id ? ` · ${selected.duplicate_of_id}` : ''}` : 'No'}</dd></div>
                    <div><dt>Location validation</dt><dd className={selected.location_validation_status === 'matched' ? 'good' : 'warning'}>{selected.location_validation_status.replace('_', ' ')}</dd></div>
                    {selected.nlp_analysis && (
                      <>
                        <div><dt>NLP classification</dt><dd className="ops-nlp-class">{selected.nlp_analysis.classification?.replace('_', ' ') ?? 'None'}{selected.nlp_analysis.confidence != null ? ` · ${(selected.nlp_analysis.confidence * 100).toFixed(0)}% conf` : ''}</dd></div>
                        <div><dt>NLP extracted depth</dt><dd>{selected.nlp_analysis.extracted_depth_m != null ? `${selected.nlp_analysis.extracted_depth_m.toFixed(2)} m` : 'No depth mentioned'}</dd></div>
                        <div><dt>NLP urgency</dt><dd className={selected.nlp_analysis.urgency_score && selected.nlp_analysis.urgency_score >= 0.7 ? 'warning' : 'good'}>{selected.nlp_analysis.urgency_score != null ? `${(selected.nlp_analysis.urgency_score * 100).toFixed(0)}% (${selected.nlp_analysis.classification ?? 'standard'})` : 'Low'}</dd></div>
                        <div><dt>NLP language & landmarks</dt><dd>{selected.nlp_analysis.detected_language?.toUpperCase() ?? 'EN'}{selected.nlp_analysis.extracted_landmarks && selected.nlp_analysis.extracted_landmarks.length > 0 ? ` · ${selected.nlp_analysis.extracted_landmarks.join(', ')}` : ''}</dd></div>
                        <div><dt>NLP provenance</dt><dd className="ops-muted-text"><small>{selected.nlp_analysis.model_version ?? 'heuristic-indic-lexical-v1'} · Heuristic keyword analysis, not an official BMC confirmation</small></dd></div>
                      </>
                    )}
                  </dl>
                  {selected.description && <p className="ops-description">{selected.description}</p>}
                  {selected.image_url && <img className="ops-original-image" src={localImageUrl(selected.image_url)} alt={`Original citizen photo for ${selected.report_id}`}/>}
                </section>

                <section className="ops-card ops-map-card">
                  <h3><MapPin size={15}/>Reported location</h3>
                  <div className="ops-map">
                    {boundaries ? <GeoMap
                        boundaries={boundaries}
                        reports={reports}
                        hotspots={[]}
                        wardIntelligence={[]}
                        predictions={[]}
                        visibleLayers={{ reports: true, hotspots: false, intelligence: false, risk: false, prediction: false }}
                        selectedWardCode={null}
                        selectedReportId={selected.report_id}
                        operatorMode
                        onWardClick={(_ward: SelectedWard) => undefined}
                        onReportClick={(report) => setSelectedId(report.report_id)}
                        onHotspotClick={() => undefined}
                      /> : <div className="ops-map-loading">Loading ward geometry…</div>}
                  </div>
                  <div className="ops-coordinates">{selected.latitude.toFixed(5)}, {selected.longitude.toFixed(5)} · {wardNames.get(selected.ward_id ?? '') ?? 'Ward unresolved'}</div>
                  <div className="ops-map-legend"><span><i className="pending"/>Pending</span><span><i className="confirmed"/>Confirmed</span><span><i className="rejected"/>Rejected</span><span><i className="review"/>Review required</span><span><i className="location-warning"/>Location warning</span></div>
                </section>
              </div>

              <section className="ops-card ops-correction-card">
                <div className="ops-section-heading"><div><span className="ops-eyebrow">OPERATOR ACTION</span><h3>Verify incident details</h3></div><span className="ops-readonly"><ShieldCheck size={14}/>Changes are audited</span></div>
                <div className="ops-correction-grid">
                  <label>Incident timestamp (ISO 8601 with timezone)<input value={incidentTimestamp} onChange={(event) => setIncidentTimestamp(event.target.value)} placeholder="2026-07-14T12:30:00+05:30"/></label>
                  <label>Latitude<input type="number" step="any" value={latitude} onChange={(event) => setLatitude(event.target.value)}/></label>
                  <label>Longitude<input type="number" step="any" value={longitude} onChange={(event) => setLongitude(event.target.value)}/></label>
                  <label>Water depth category<select value={depth} onChange={(event) => setDepth(event.target.value as WaterDepth)}><option value="ankle">Ankle</option><option value="knee">Knee</option><option value="waist">Waist</option><option value="submerged">Submerged</option></select></label>
                  <label>Measured depth in metres (optional)<input type="number" step="0.01" min="0" value={measuredDepth} onChange={(event) => setMeasuredDepth(event.target.value)} placeholder="Not recorded"/></label>
                </div>
                <label className="ops-reason">Reason <span>(required for reject or review)</span><textarea rows={2} value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Record the evidence and rationale for this decision."/></label>
                {actionError && <div className="ops-error" role="alert">{actionError}</div>}
                <div className="ops-actions">
                  <button disabled={submitting || selected.operator_verification_status === 'confirmed'} className="ops-primary" onClick={() => void decide('confirm')}><Check size={15}/>Confirm report</button>
                  <button disabled={submitting || selected.operator_verification_status === 'rejected'} className="ops-danger" onClick={() => void decide('reject')}><X size={15}/>Reject</button>
                  <button disabled={submitting} className="ops-secondary" onClick={() => void decide('review')}><AlertTriangle size={15}/>Flag for review</button>
                  {submitting && <span className="ops-saving">Saving decision…</span>}
                </div>
              </section>

              <div className="ops-detail-grid ops-bottom-grid">
                <section className="ops-card">
                  <div className="ops-section-heading"><div><span className="ops-eyebrow">APPEND-ONLY RECORD</span><h3>Verification history</h3></div></div>
                  {historyError && <div className="ops-error" role="alert">{historyError}</div>}
                  {history.length ? <ol className="ops-history">{history.map((entry) => (
                    <li key={entry.id}>
                      <div className="ops-history-head"><strong>{entry.action.replaceAll('_', ' ')}</strong><time>{dateLabel(entry.occurred_at)}</time></div>
                      <div className="ops-history-operator">Operator {entry.operator_id} · {entry.previous_status} → {entry.new_status}</div>
                      {entry.reason && <p>{entry.reason}</p>}
                      {(entry.event_timestamp || entry.latitude != null || entry.water_depth) && <div className="ops-history-values">{entry.event_timestamp && <span>Timestamp: {dateLabel(entry.event_timestamp)}</span>}{entry.latitude != null && entry.longitude != null && <span>Location: {entry.latitude.toFixed(5)}, {entry.longitude.toFixed(5)} · {entry.location_validation_status ?? 'not validated'}</span>}{entry.ward_id && <span>Ward ID: {entry.ward_id}</span>}{entry.water_depth && <span>Depth: {entry.water_depth}{entry.water_depth_m == null ? '' : ` · ${entry.water_depth_m} m`}</span>}</div>}
                      {!!entry.evidence_image_urls.length && <div className="ops-evidence-gallery">{entry.evidence_image_urls.map((url) => <a key={url} href={operatorApi.imagePath(url)} target="_blank" rel="noreferrer"><img src={operatorApi.imagePath(url)} alt="Private verification evidence"/></a>)}</div>}
                    </li>
                  ))}</ol> : !historyError && <p className="ops-muted">No review decisions have been recorded for this report.</p>}
                </section>
                <section className="ops-card">
                  <h3><Upload size={15}/>Add verification evidence</h3>
                  <p className="ops-muted">Evidence is private and accessible only to authenticated operators. Uploaded files become part of the audit history.</p>
                  <form className="ops-evidence-form" onSubmit={(event) => void addEvidence(event)}>
                    <label>Evidence note<textarea rows={2} value={evidenceNote} onChange={(event) => setEvidenceNote(event.target.value)} placeholder="Describe the field observation or evidence."/></label>
                    <label>Photographs<input type="file" accept="image/jpeg,image/png,image/webp" multiple onChange={(event) => setEvidenceFiles(Array.from(event.target.files ?? []))}/><small>Up to 5 images · backend limit 10 MiB total</small></label>
                    <button className="ops-secondary" type="submit" disabled={submitting || !evidenceFiles.length || !evidenceNote.trim()}><Upload size={14}/>Attach evidence</button>
                  </form>
                </section>
              </div>
            </>
          )}
        </section>
      </section>

      <section className="ops-bmc-card">
        <div className="ops-bmc-icon"><FileText size={18}/></div>
        <div><span className="ops-eyebrow">HISTORICAL DATA TRACKING</span><h2>MCGM / BMC records request</h2><p>Draft prepared · Not submitted. An authorized project signatory, contact details, and organization information are still required. Follow-up has not started because submission is pending. No records or permissions have been received.</p></div>
        <span className="ops-status review_required">Draft · unsubmitted</span>
      </section>
      <footer className="ops-footer">Citizen reports and operator decisions are not official BMC incident records. CV output is not an official verification.</footer>
    </main>
  );
}
