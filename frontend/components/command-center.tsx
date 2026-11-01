
'use client';

import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { useQuery } from '@tanstack/react-query';
import {
  Activity,
  Bell,
  ChevronRight,
  CircleDot,
  Compass,
  Flag,
  Layers3,
  MapPinned,
  MessageSquareWarning,
  Radio,
  Route,
  Settings,
  Waves,
  X,
} from 'lucide-react';
import { usePathname, useRouter } from 'next/navigation';
import { useState } from 'react';

import { api, Ward } from '../lib/api';
import { GeoMap } from './geo-map';

export type Section =
  | 'map'
  | 'reports'
  | 'alerts'
  | 'social'
  | 'responders';

const sections: {
  id: Section;
  label: string;
  path: string;
  icon: typeof MapPinned;
}[] = [
  { id: 'map', label: 'GIS', path: '/dashboard', icon: MapPinned },
  { id: 'reports', label: 'Reports', path: '/dashboard/reports', icon: MessageSquareWarning },
  { id: 'alerts', label: 'Alerts', path: '/dashboard/alerts', icon: Bell },
  { id: 'social', label: 'Intel', path: '/dashboard/social', icon: Radio },
  { id: 'responders', label: 'Routes', path: '/dashboard/responders', icon: Route },
];

const pageMeta: Record<Section, [string, string, string]> = {
  map: [
    'GIS Command Map',
    'MUMBAI · OPERATIONAL OVERVIEW',
    'Geospatial intelligence for flood assessment and coordinated response.',
  ],
  reports: [
    'Citizen Reports',
    'FIELD VERIFICATION',
    'Crowdsourced flood observations and verification.',
  ],
  alerts: [
    'CAP Alert Dispatch',
    'EMERGENCY COMMUNICATION',
    'Create precise, multilingual alerts for affected communities.',
  ],
  social: [
    'Social Intelligence',
    'SIGNAL ASSESSMENT',
    'Signals evaluated for operational relevance and urgency.',
  ],
  responders: [
    'Responder Routes',
    'FIELD OPERATIONS',
    'Coordinate available response capacity and route intelligence.',
  ],
};

const ease = [0.22, 1, 0.36, 1] as const;

const pageMotion = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -6 },
  transition: { duration: 0.21, ease },
};

// --------------------------------------------------
// SHARED COMPONENTS
// --------------------------------------------------

function Empty({
  title,
  copy,
  icon: Icon = CircleDot,
}: {
  title: string;
  copy: string;
  icon?: typeof CircleDot;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 5 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className="empty"
    >
      <div>
        <div className="empty-icon">
          <Icon size={20} />
        </div>
        <h2>{title}</h2>
        <p>{copy}</p>
      </div>
    </motion.div>
  );
}

function Skeleton() {
  return (
    <div className="skeleton-wrap" aria-label="Loading data">
      <i />
      <i />
      <i />
    </div>
  );
}

function Metric({
  label,
  value = '—',
  detail = 'Awaiting data',
}: {
  label: string;
  value?: string | number;
  detail?: string;
}) {
  return (
    <div className="metric">
      <label>{label}</label>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}

function StatusDot({
  kind = 'online',
}: {
  kind?: 'online' | 'degraded' | 'offline';
}) {
  return <i className={`status-dot ${kind}`} />;
}

function Toast({
  message,
  onClose,
}: {
  message: string;
  onClose: () => void;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: -10, x: 8 }}
      animate={{ opacity: 1, y: 0, x: 0 }}
      exit={{ opacity: 0, y: -8, x: 8 }}
      transition={{ duration: 0.2, ease }}
      className="toast"
    >
      <Activity size={15} />
      <span>{message}</span>
      <button onClick={onClose}>
        <X size={14} />
      </button>
    </motion.div>
  );
}

// --------------------------------------------------
// MAIN COMMAND CENTER
// --------------------------------------------------

export function CommandCenter({
  section,
}: {
  section: Section;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const reduced = useReducedMotion();

  const [toast, setToast] = useState<string | undefined>();
  const [selectedWard, setSelectedWard] = useState<Ward | null>(null);

  // Fetch ward information
  const {
    data: wards,
    isLoading: wardsLoading,
    isError: wardsError,
    refetch: refetchWards,
  } = useQuery({
    queryKey: ['wards'],
    queryFn: api.wards,
    enabled: section === 'map',
  });

  const meta = pageMeta[section];

  const go = (path: string) => {
    if (path !== pathname) {
      router.push(path);
    }
  };

  const notify = (message: string) => {
    setToast(message);
    window.setTimeout(() => setToast(undefined), 3600);
  };

  return (
    <div className="app-shell">

      {/* LEFT NAVIGATION */}
      <aside className="rail">

        <div className="brand">
          <Waves size={22} />
        </div>

        <div className="rail-line" />

        <nav>
          {sections.map(({ id, label, path, icon: Icon }) => (
            <motion.button
              key={id}
              whileHover={reduced ? undefined : { x: 2 }}
              whileTap={reduced ? undefined : { scale: 0.98 }}
              onClick={() => go(path)}
              className={section === id ? 'nav-item active' : 'nav-item'}
              aria-label={label}
            >
              <Icon size={20} />
              <span>{label}</span>
            </motion.button>
          ))}
        </nav>

        <div className="rail-bottom">
          <StatusDot />
          <button className="nav-item">
            <Settings size={19} />
          </button>
        </div>

      </aside>

      {/* MAIN CONTENT */}
      <main className="main">

        {/* TOP HEADER */}
        <header className="topbar">
          <strong>{meta[0]}</strong>

          <div className="top-actions">

            <div className="status-chip">
              <StatusDot kind="degraded" />
              Monsoon watch
            </div>

            <button
              onClick={() =>
                notify('System status details are unavailable until services are connected.')
              }
              className="status-chip"
            >
              <StatusDot />
              System status
            </button>

            <div className="avatar">OP</div>

          </div>
        </header>

        {/* PAGE CONTENT */}
        <div className="canvas">

          <AnimatePresence mode="wait">

            <motion.div
              key={section}
              {...(reduced ? {} : pageMotion)}
            >

              <section className="page-heading">

                <div>
                  <div className="eyebrow">{meta[1]}</div>
                  <h1>{meta[0]}</h1>
                  <p>{meta[2]}</p>
                </div>

                <button
                  className="outline-button"
                  onClick={() =>
                    section === 'map'
                      ? refetchWards()
                      : notify('This control will become available with the connected service.')
                  }
                >
                  {section === 'map' ? 'Refresh data' : 'Refresh'}
                </button>

              </section>

              {section === 'map' ? (
                <MapScreen
                  wards={wards}
                  loading={wardsLoading}
                  error={wardsError}
                  refetch={refetchWards}
                  selected={selectedWard}
                  onSelect={setSelectedWard}
                  notify={notify}
                />

              ) : section === 'alerts' ? (
                <Alerts notify={notify} />
              ) : section === 'responders' ? (
                <Responders />
              ) : (
                <ListScreen section={section} />
              )}

            </motion.div>

          </AnimatePresence>

        </div>

      </main>

      <AnimatePresence>
        {toast && (
          <Toast
            message={toast}
            onClose={() => setToast(undefined)}
          />
        )}
      </AnimatePresence>

    </div>
  );
}

// --------------------------------------------------
// GIS MAP SCREEN
// --------------------------------------------------

function MapScreen({
  wards,
  loading,
  error,
  refetch,
  selected,
  onSelect,
  notify,
}: {
  wards?: Ward[];
  loading: boolean;
  error: boolean;
  refetch: () => void;
  selected: Ward | null;
  onSelect: (ward: Ward | null) => void;
  notify: (message: string) => void;
}) {

  // Calculate actual ward metrics
  const coastalCount =
    wards?.filter((ward) => ward.is_coastal).length ?? 0;

  const scores =
    wards
      ?.map((ward) => ward.risk_score)
      .filter(
        (score): score is number =>
          typeof score === 'number' && Number.isFinite(score)
      ) ?? [];

  const averageRisk =
    scores.length > 0
      ? scores.reduce((sum, score) => sum + score, 0) /
        scores.length
      : null;

  const criticalCount =
    wards?.filter(
      (ward) => ward.risk_class === 'critical'
    ).length ?? 0;

  const selectById = (id: string) => {
    const ward = wards?.find((item) => item.id === id);

    if (ward) {
      onSelect(ward);
    }
  };

  const gatewayError = error;

  return (
    <>

      {/* KPI CARDS */}
      <div className="kpis">

        <Metric
          label="MONITORED WARDS"
          value={loading ? '—' : error ? '—' : wards?.length ?? 0}
          detail={loading ? 'Loading...' : 'Connected wards'}
        />

        <Metric
          label="CRITICAL ALERTS"
          value={loading ? '—' : criticalCount}
          detail="Critical ward risk classifications"
        />

        <Metric
          label="COASTAL EXPOSURE"
          value={loading ? '—' : `${coastalCount} wards`}
          detail="Coastal wards monitored"
        />

        <Metric
          label="CITYWIDE RISK"
          value={
            averageRisk !== null
              ? `${(averageRisk * 100).toFixed(1)}/100`
              : '—'
          }
          detail={
            averageRisk !== null
              ? 'Average ward risk score'
              : 'Risk data unavailable'
          }
        />

      </div>

      {/* MAP WORKSPACE */}
      <section className="map-workspace">

        <div className="map-surface">

          <div className="map-water" />
          <div className="map-land" />

          {/* MAPBOX + DECK.GL */}
          <div className="live-map">
            <GeoMap
              wards={wards ?? []}
              onWardClick={selectById}
              onUnmonitoredWardClick={(name) =>
                notify(`${name}: no live risk data available.`)
              }
            />
          </div>

          {/* MAP TOOLBAR */}
          <div className="map-toolbar">

            <div className="map-tabs">

              <button className="active">
                <Layers3 size={15} />
                Ward polygons
              </button>

              <button
                onClick={() =>
                  notify('Weather layer is not yet connected.')
                }
              >
                Weather
              </button>

              <button
                onClick={() =>
                  notify('Report layer is not yet connected.')
                }
              >
                Reports
              </button>

            </div>

          </div>

          {/* CONNECTION STATUS */}
          <div className="coordinates">

            <StatusDot
              kind={
                gatewayError
                  ? 'offline'
                  : loading
                    ? 'degraded'
                    : 'online'
              }
            />

            MUMBAI GEO-ENGINE · {
              gatewayError
                ? 'CONNECTION ERROR'
                : loading
                  ? 'CONNECTING'
                  : 'CONNECTED'
            }

          </div>

          {/* LOADING / ERROR STATES */}
          {loading ? (

            <div className="map-loading">
              <Skeleton />
              <span>Loading ward geometry</span>
            </div>

          ) : gatewayError ? (

            <div className="map-empty">
              <Compass size={20} />

              <h3>Ward geometry is unavailable</h3>

              <p>
                The ward service could not return the required
                geographic information.
              </p>

              <button
                className="outline-button"
                onClick={() => refetch()}
              >
                Retry connection
              </button>
            </div>

          ) : wards?.length ? (

            <WardList
              wards={wards}
              onSelect={onSelect}
            />

          ) : (

            <div className="map-empty">
              <Compass size={20} />
              <h3>No ward geometry available</h3>
              <p>
                The connected service returned no ward boundaries.
              </p>
            </div>

          )}

          {/* MAP LEGEND AND CONTROLS */}
          <div className="map-bottom">

            <div className="legend">
              <b>INUNDATION RISK</b>

              <span><i className="low" />Low</span>
              <span><i className="medium" />Medium</span>
              <span><i className="high" />High</span>
              <span><i className="critical" />Critical</span>
            </div>

            <div className="map-controls">
              <button>+</button>
              <button>−</button>
              <button>
                <Compass size={16} />
              </button>
            </div>

          </div>

        </div>

        {/* WARD INSPECTOR */}
        <WardInspector
          ward={selected}
          close={() => onSelect(null)}
          notify={notify}
        />

      </section>

      {/* DATA ATTRIBUTION — OUTSIDE THE GRID */}
      <div className="px-3 py-2 text-[10px] text-slate-500">
        Administrative boundaries: Mumbai 24-ward GeoJSON · OpenCity /
        Bharatlas · ODbL-1.0
      </div>

      {/* DATA GATEWAY */}
      <div className="gateway">

        <StatusDot
          kind={
            gatewayError
              ? 'offline'
              : loading
                ? 'degraded'
                : 'online'
          }
        />

        <b>DATA GATEWAY</b>

        <span>
          {gatewayError
            ? 'API connection error'
            : loading
              ? 'Connecting to API'
              : 'API connected'}
        </span>

        <code>
          {process.env.NEXT_PUBLIC_API_URL ||
            'http://localhost:8000/v1'}
        </code>

      </div>

    </>
  );
}

// --------------------------------------------------
// WARD LIST
// --------------------------------------------------

function WardList({
  wards,
  onSelect,
}: {
  wards: Ward[];
  onSelect: (ward: Ward) => void;
}) {
  return (
    <div className="ward-list">

      {wards.slice(0, 5).map((ward) => (

        <motion.button
          key={ward.id}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          whileHover={{ scale: 1.01 }}
          onClick={() => onSelect(ward)}
        >
          {ward.name}

          <ChevronRight size={14} />
        </motion.button>

      ))}

    </div>
  );
}

// --------------------------------------------------
// WARD INSPECTOR
// --------------------------------------------------

function WardInspector({
  ward,
  close,
  notify,
}: {
  ward: Ward | null;
  close: () => void;
  notify: (message: string) => void;
}) {

  return (
    <AnimatePresence>

      {ward ? (

        <motion.aside
          initial={{ opacity: 0, x: 22 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: 22 }}
          transition={{ duration: 0.25, ease }}
          className="inspector"
        >

          <button
            onClick={close}
            className="close"
            aria-label="Close ward inspector"
          >
            <X size={17} />
          </button>

          <div className="tag">WARD SELECTED</div>

          <h2>{ward.name}</h2>

          <p>{ward.id} · Mumbai</p>

          <div className="inspector-sections">

            {/* RISK */}
            <div className="inspector-section">

              <h3>RISK & EXPOSURE</h3>

              <div className="unavailable">
                <b>
                  {ward.risk_class?.toUpperCase() ?? 'N/A'} RISK
                </b>

                Risk score: {
                  ward.risk_score !== undefined
                    ? `${(ward.risk_score * 100).toFixed(1)}/100`
                    : 'N/A'
                }
              </div>

            </div>

            {/* GEOGRAPHY */}
            <div className="inspector-section">

              <h3>GEOGRAPHY</h3>

              <div className="unavailable">

                <b>
                  {ward.area_sqkm ?? 'N/A'} km²
                </b>

                Area

                <br />

                Population: {
                  ward.population?.toLocaleString() ?? 'N/A'
                }

                <br />

                Elevation: {
                  ward.avg_elevation_m ?? 'N/A'
                } m

              </div>

            </div>

            {/* DRAINAGE */}
            <div className="inspector-section">

              <h3>DRAINAGE & COASTAL EXPOSURE</h3>

              <div className="unavailable">

                <b>
                  {ward.is_coastal === undefined
                    ? 'Unknown coastal status'
                    : ward.is_coastal
                      ? 'Coastal ward'
                      : 'Non-coastal ward'}
                </b>

                Drainage index: {
                  ward.drainage_index ?? 'N/A'
                }

              </div>

            </div>

            {/* WEATHER AND SOCIAL */}
            <div className="inspector-section">

              <h3>WEATHER & SOCIAL INTELLIGENCE</h3>

              <div className="unavailable">
                <b>Live telemetry unavailable</b>
                Weather and social intelligence services
                are not yet connected.
              </div>

            </div>

          </div>

          <button
            className="primary-button"
            onClick={() =>
              notify('Alert dispatch service is not yet connected.')
            }
          >
            Create alert
          </button>

        </motion.aside>

      ) : (

        <aside className="inspector idle">

          <div className="tag">NO WARD SELECTED</div>

          <h2>Ward inspector</h2>

          <p>
            Select a ward polygon to review flood intelligence,
            evidence, and response actions.
          </p>

          <div className="inspector-section">

            <h3>WARD INTELLIGENCE</h3>

            <div className="unavailable">

              <b>Awaiting ward selection</b>

              Risk, geography and drainage data
              will appear here.

            </div>

          </div>

        </aside>

      )}

    </AnimatePresence>
  );
}

// --------------------------------------------------
// REPORTS AND SOCIAL INTELLIGENCE
// --------------------------------------------------

function ListScreen({
  section,
}: {
  section: 'reports' | 'social';
}) {

  const label =
    section === 'reports'
      ? 'No citizen reports available'
      : 'No social signals available';

  const metric =
    section === 'reports'
      ? ['TOTAL REPORTS', 'PENDING', 'VERIFIED', 'CRITICAL']
      : ['TOTAL SIGNALS', 'HIGH URGENCY', 'ACTIVE WARDS', 'VERIFIED'];

  return (
    <>

      <div className="kpis">

        {metric.map((item) => (
          <Metric
            key={item}
            label={item}
          />
        ))}

      </div>

      <section className="list-surface">

        <div className="filters">

          {[
            'Ward · All',
            section === 'reports'
              ? 'Severity · All'
              : 'Classification · All',
            section === 'reports'
              ? 'Verification · All'
              : 'Urgency · All',
            'Time · Latest',
          ].map((item) => (

            <motion.button
              whileTap={{ scale: 0.98 }}
              key={item}
            >
              {item}
            </motion.button>

          ))}

        </div>

        <Empty
          title={label}
          copy="The service has not returned any records. This workspace will populate automatically when verified data becomes available."
          icon={section === 'reports' ? Flag : Radio}
        />

      </section>

    </>
  );
}

// --------------------------------------------------
// ALERTS
// --------------------------------------------------

function Alerts({
  notify,
}: {
  notify: (message: string) => void;
}) {

  return (
    <>

      <div className="kpis">

        {[
          'ACTIVE ALERTS',
          'CRITICAL',
          'SCHEDULED',
          'DELIVERED',
        ].map((item) => (

          <Metric
            key={item}
            label={item}
          />

        ))}

      </div>

      <section className="alert-layout">

        <div className="history">

          <h2>Alert history</h2>

          <p>Recent emergency communications.</p>

          <div className="unavailable">
            <b>No alerts available</b>
            When returned by the dispatch service,
            alert history will appear here.
          </div>

        </div>

        <div className="composer">

          <h2>Compose alert</h2>

          <p>All fields are reviewed before dispatch.</p>

          {[
            'Alert title',
            'Affected area',
            'Message',
          ].map((item, index) => (

            <label key={item}>

              {item.toUpperCase()}

              <div className={index === 2 ? 'field textarea' : 'field'}>

                {index === 2
                  ? 'Compose public guidance and required action'
                  : `Select or enter ${item.toLowerCase()}`}

              </div>

            </label>

          ))}

          <label>DELIVERY</label>

          <div className="delivery">
            <span>CAP</span>
            <span>SMS</span>
            <span>WhatsApp</span>
            <span>Push</span>
          </div>

          <div className="button-row">

            <button className="outline-button">
              Preview
            </button>

            <motion.button
              whileHover={{ y: -1 }}
              whileTap={{ scale: 0.98 }}
              className="primary-button"
              onClick={() =>
                notify('CAP generation is unavailable until alert dispatch is configured.')
              }
            >
              Generate CAP
            </motion.button>

          </div>

        </div>

      </section>

    </>
  );
}

// --------------------------------------------------
// RESPONDER ROUTES
// --------------------------------------------------

function Responders() {

  return (
    <>

      <div className="kpis">

        {[
          'RESPONDER UNITS',
          'INCIDENTS',
          'BLOCKED ROADS',
          'SUGGESTED ROUTES',
        ].map((item) => (

          <Metric
            key={item}
            label={item}
          />

        ))}

      </div>

      <section className="route-surface">

        <Empty
          title="Responder routing is being integrated"
          copy="Unit locations, traffic constraints, incidents and recommended routes will be shown when the routing engine is connected."
          icon={Route}
        />

      </section>

    </>

  );
}
