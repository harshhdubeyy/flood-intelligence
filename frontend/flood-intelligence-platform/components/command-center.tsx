'use client';

import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { useQuery } from '@tanstack/react-query';
import { Activity, AlertTriangle, Bell, ChevronRight, CircleDot, Compass, Database, Flag, Layers3, MapPinned, MessageSquareWarning, Radio, Route, Send, Settings, ShieldAlert, Users, Waves, X } from 'lucide-react';
import { usePathname, useRouter } from 'next/navigation';
import { api, CitizenReport, FloodHotspot, ForecastHorizon, Ward, WardIntelligenceItem, WardPrediction, WaterDepth } from '../lib/api';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { GeoMap, SelectedWard } from './geo-map';
import { SocialIntelligence } from './social-intelligence';

export type Section = 'map'|'reports'|'alerts'|'social'|'responders';
const sections:{id:Section;label:string;path:string;icon:typeof MapPinned}[] = [
  {id:'map',label:'GIS',path:'/dashboard',icon:MapPinned}, {id:'reports',label:'Reports',path:'/dashboard/reports',icon:MessageSquareWarning}, {id:'alerts',label:'Alerts',path:'/dashboard/alerts',icon:Bell}, {id:'social',label:'Intel',path:'/dashboard/social',icon:Radio}, {id:'responders',label:'Routes',path:'/dashboard/responders',icon:Route}
];
const pageMeta:Record<Section,[string,string,string]> = { map:['GIS Command Map','MUMBAI · OPERATIONAL OVERVIEW','Geospatial intelligence for flood assessment and coordinated response.'], reports:['Citizen Reports','FIELD VERIFICATION','Crowdsourced flood observations and verification.'], alerts:['CAP Alert Dispatch','EMERGENCY COMMUNICATION','Create precise, multilingual alerts for affected communities.'], social:['Social Intelligence','AUTHORIZED PUBLIC SOURCES','Public API posts are collected as unverified signals, not confirmed flood incidents.'], responders:['Responder Routes','FIELD OPERATIONS','Coordinate available response capacity and route intelligence.'] };
const ease = [0.22,1,0.36,1] as const;
const pageMotion = { initial:{opacity:0,y:8}, animate:{opacity:1,y:0}, exit:{opacity:0,y:-6}, transition:{duration:.21,ease} };

function Empty({title,copy,icon:Icon=CircleDot}:{title:string;copy:string;icon?:typeof CircleDot}){ return <motion.div initial={{opacity:0,y:5}} animate={{opacity:1,y:0}} transition={{duration:.2}} className="empty"><div><div className="empty-icon"><Icon size={20}/></div><h2>{title}</h2><p>{copy}</p></div></motion.div> }
function Skeleton(){ return <div className="skeleton-wrap" aria-label="Loading data"><i/><i/><i/></div> }
function Metric({label,value}:{label:string;value?:string|number}){ return <div className="metric"><label>{label}</label><strong className="metric-value">{value??'—'}</strong><small>{value==null?'Awaiting data':''}</small></div> }
function StatusDot({kind='online'}:{kind?:'online'|'degraded'|'offline'}){return <i className={`status-dot ${kind}`}/>}
function Toast({message,onClose}:{message:string;onClose:()=>void}){ return <motion.div initial={{opacity:0,y:-10,x:8}} animate={{opacity:1,y:0,x:0}} exit={{opacity:0,y:-8,x:8}} transition={{duration:.2,ease}} className="toast"><Activity size={15}/><span>{message}</span><button onClick={onClose}><X size={14}/></button></motion.div> }

export function CommandCenter({section}:{section:Section}){
  const router=useRouter(), pathname=usePathname(), reduced=useReducedMotion(), [toast,setToast]=useState<string|undefined>();
  const [selectedWard,setSelectedWard]=useState<SelectedWard|null>(null);
  const {data:boundaries,isLoading:boundariesLoading,isError:boundariesError,refetch:refetchBoundaries}=useQuery({queryKey:['ward-boundaries'],queryFn:api.wardBoundaries,enabled:section==='map',staleTime:Infinity});
  const {data:riskGeoJSON}=useQuery({queryKey:['wards','geojson'],queryFn:api.wardGeojson,enabled:section==='map',refetchInterval:60000});
  const {data:mapReports,isLoading:mapReportsLoading,isError:mapReportsError,refetch:refetchMapReports}=useQuery({queryKey:['reports','map'],queryFn:api.reportsForMap,enabled:section==='map',refetchInterval:30000});
  const {data:hotspots,isLoading:hotspotsLoading,isError:hotspotsError,refetch:refetchHotspots}=useQuery({queryKey:['reports','intelligence','hotspots'],queryFn:()=>api.hotspots(),enabled:section==='map',refetchInterval:60000});
  const {data:wardIntelligence,isLoading:intelligenceLoading,isError:intelligenceError,refetch:refetchIntelligence}=useQuery({queryKey:['reports','intelligence','wards'],queryFn:()=>api.wardIntelligence(),enabled:section==='map',refetchInterval:60000});
  const [forecastHorizon,setForecastHorizon]=useState<ForecastHorizon>('6h');
  const {data:predictionData,isLoading:predictionsLoading,isError:predictionsError,refetch:refetchPredictions}=useQuery({queryKey:['predictions','wards',forecastHorizon],queryFn:()=>api.wardPredictions(forecastHorizon),enabled:section==='map',refetchInterval:60000});
  const supportedHorizons=predictionData?.supported_horizons??[];
  useEffect(()=>{
    if(supportedHorizons.length&&!supportedHorizons.includes(forecastHorizon))setForecastHorizon(supportedHorizons[0]);
  },[forecastHorizon,supportedHorizons]);
  const {data:reports,isLoading:reportsLoading,isError:reportsError,refetch:refetchReports}=useQuery({queryKey:['reports'],queryFn:()=>api.reports().then(r=>r.reports),enabled:section==='reports'});
  const meta=pageMeta[section]; const go=(path:string)=> { if(path!==pathname) router.push(path) };
  const notify=(m:string)=>{setToast(m);window.setTimeout(()=>setToast(undefined),3600)};
  return <div className="app-shell"><aside className="rail"><div className="brand"><Waves size={22}/></div><div className="rail-line"/><nav>{sections.map(({id,label,path,icon:Icon})=><motion.button key={id} whileHover={reduced?undefined:{x:2}} whileTap={reduced?undefined:{scale:.98}} onClick={()=>go(path)} className={section===id?'nav-item active':'nav-item'} aria-label={label}><Icon size={20}/><span>{label}</span></motion.button>)}</nav><div className="rail-bottom"><StatusDot/><button className="nav-item"><Settings size={19}/></button></div></aside>
  <main className="main"><header className="topbar"><strong>{meta[0]}</strong><div className="top-actions"><div className="status-chip"><StatusDot kind="degraded"/>Monsoon watch</div><button onClick={()=>notify('System status details are unavailable until services are connected.')} className="status-chip"><StatusDot/>System status</button><div className="avatar">OP</div></div></header>
  <div className="canvas"><AnimatePresence mode="wait"><motion.div key={section} {...(reduced?{}:pageMotion)}><section className="page-heading"><div><div className="eyebrow">{meta[1]}</div><h1>{meta[0]}</h1><p>{meta[2]}</p></div><button className="outline-button" onClick={()=>section==='map'?document.getElementById('map-layer-controls')?.focus():notify('This control will become available with the connected service.')}>{section==='map'?'Layer settings':'Refresh'}</button></section>
  {section==='map'?<MapScreen boundaries={boundaries} boundariesLoading={boundariesLoading} boundariesError={boundariesError} refetchBoundaries={refetchBoundaries} riskGeoJSON={riskGeoJSON} reports={mapReports??[]} reportsLoading={mapReportsLoading} reportsError={mapReportsError} refetchReports={refetchMapReports} hotspots={hotspots??[]} hotspotsLoading={hotspotsLoading} hotspotsError={hotspotsError} refetchHotspots={refetchHotspots} wardIntelligence={wardIntelligence??[]} intelligenceLoading={intelligenceLoading} intelligenceError={intelligenceError} refetchIntelligence={refetchIntelligence} predictions={predictionData?.wards??[]} predictionsLoading={predictionsLoading} predictionsError={predictionsError} refetchPredictions={refetchPredictions} supportedHorizons={supportedHorizons} forecastHorizon={forecastHorizon} onForecastHorizonChange={setForecastHorizon} selected={selectedWard} onSelect={setSelectedWard}/>:section==='alerts'?<Alerts notify={notify}/>:section==='responders'?<Responders/>:<ListScreen section={section} reports={reports} reportsLoading={reportsLoading} reportsError={reportsError} refetchReports={refetchReports} notify={notify}/>}</motion.div></AnimatePresence></div></main><AnimatePresence>{toast&&<Toast message={toast} onClose={()=>setToast(undefined)}/>}</AnimatePresence></div>
}

type MapFilters = {
  waterDepth: WaterDepth | 'all';
  verification: 'all' | 'verified' | 'unverified';
  recency: 'all' | '1' | '3' | '24';
  wardCode: string;
};

type MapSelection =
  | { kind: 'ward'; ward: SelectedWard }
  | { kind: 'report'; report: CitizenReport }
  | { kind: 'hotspot'; hotspot: FloodHotspot }
  | null;

const initialLayerVisibility = {
  reports: true,
  hotspots: true,
  intelligence: true,
  risk: true,
  prediction: false,
};

function normalizedWardKey(value: string | null | undefined): string {
  return String(value ?? '')
    .trim()
    .toUpperCase()
    .replace(/^(?:MH[-_]*)?BMC[-_]*/, '')
    .replace(/[^A-Z0-9]/g, '');
}

function MapScreen({
  boundaries,
  boundariesLoading,
  boundariesError,
  refetchBoundaries,
  riskGeoJSON,
  reports,
  reportsLoading,
  reportsError,
  refetchReports,
  hotspots,
  hotspotsLoading,
  hotspotsError,
  refetchHotspots,
  wardIntelligence,
  intelligenceLoading,
  intelligenceError,
  refetchIntelligence,
  predictions,
  predictionsLoading,
  predictionsError,
  refetchPredictions,
  supportedHorizons,
  forecastHorizon,
  onForecastHorizonChange,
  selected,
  onSelect,
}: {
  boundaries?: GeoJSON.FeatureCollection;
  boundariesLoading: boolean;
  boundariesError: boolean;
  refetchBoundaries: () => void;
  riskGeoJSON?: GeoJSON.FeatureCollection;
  reports: CitizenReport[];
  reportsLoading: boolean;
  reportsError: boolean;
  refetchReports: () => void;
  hotspots: FloodHotspot[];
  hotspotsLoading: boolean;
  hotspotsError: boolean;
  refetchHotspots: () => void;
  wardIntelligence: WardIntelligenceItem[];
  intelligenceLoading: boolean;
  intelligenceError: boolean;
  refetchIntelligence: () => void;
  predictions: WardPrediction[];
  predictionsLoading: boolean;
  predictionsError: boolean;
  refetchPredictions: () => void;
  supportedHorizons: ForecastHorizon[];
  forecastHorizon: ForecastHorizon;
  onForecastHorizonChange: (horizon: ForecastHorizon) => void;
  selected: SelectedWard | null;
  onSelect: (ward: SelectedWard | null) => void;
}) {
  const [visibleLayers, setVisibleLayers] = useState(initialLayerVisibility);
  const [filters, setFilters] = useState<MapFilters>({
    waterDepth: 'all',
    verification: 'all',
    recency: 'all',
    wardCode: 'all',
  });
  const [selection, setSelection] = useState<MapSelection>(null);

  const wardOptions = useMemo(() => {
    const names = new Map(
      wardIntelligence.map((item) => [
        normalizedWardKey(item.analytics.ward_id),
        item.analytics.ward_name,
      ]),
    );
    return (boundaries?.features ?? []).map((feature) => {
      const properties = feature.properties as Record<string, unknown> | null;
      const code = normalizedWardKey(String(properties?.NAME2 ?? properties?.Name ?? ''));
      return {
        code,
        label: names.get(code) ?? String(properties?.NAME2 ?? properties?.Name ?? code).trim(),
      };
    }).filter((ward) => ward.code);
  }, [boundaries, wardIntelligence]);

  const filteredReports = useMemo(() => {
    const minimumTime = filters.recency === 'all'
      ? null
      : Date.now() - Number(filters.recency) * 60 * 60 * 1000;
    return reports.filter((report) => {
      if (filters.waterDepth !== 'all' && report.water_depth !== filters.waterDepth) return false;
      if (filters.verification === 'verified' && !report.cv_verified) return false;
      if (filters.verification === 'unverified' && report.cv_verified) return false;
      if (filters.wardCode !== 'all' && normalizedWardKey(report.ward_id) !== filters.wardCode) return false;
      if (minimumTime !== null) {
        const submittedAt = Date.parse(report.submitted_at);
        if (!Number.isFinite(submittedAt) || submittedAt < minimumTime) return false;
      }
      return true;
    });
  }, [filters, reports]);

  const handleWardClick = useCallback((ward: SelectedWard) => {
    onSelect(ward);
    setSelection({ kind: 'ward', ward });
    setFilters((current) => ({ ...current, wardCode: ward.code }));
  }, [onSelect]);
  const handleReportClick = useCallback((report: CitizenReport) => {
    setSelection({ kind: 'report', report });
  }, []);
  const handleHotspotClick = useCallback((hotspot: FloodHotspot) => {
    setSelection({ kind: 'hotspot', hotspot });
  }, []);

  const wardNameById = useMemo(() => {
    const names = new Map<string, string>();
    for (const ward of wardOptions) names.set(ward.code, ward.label);
    for (const item of wardIntelligence) {
      names.set(normalizedWardKey(item.analytics.ward_id), item.analytics.ward_name);
    }
    return names;
  }, [wardIntelligence, wardOptions]);

  const reportImage = (imageUrl: string) => {
    if (/^https?:\/\//i.test(imageUrl)) return imageUrl;
    const apiBase = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/v1')
      .replace(/\/v1\/?$/, '');
    return new URL(imageUrl, apiBase).toString();
  };
  const refreshFailures = [
    boundariesError && ['Ward boundaries', refetchBoundaries],
    reportsError && ['Citizen reports', refetchReports],
    hotspotsError && ['Flood hotspots', refetchHotspots],
    intelligenceError && ['Ward intelligence', refetchIntelligence],
    predictionsError && ['Predictive outlook', refetchPredictions],
  ].filter((value): value is [string, () => void] => Boolean(value));
  const scoredPredictions = predictions.filter((prediction) => prediction.predicted_risk_score !== null);
  const highRiskWards = scoredPredictions.filter((prediction) => prediction.risk_category === 'high').length;
  const criticalRiskWards = scoredPredictions.filter((prediction) => prediction.risk_category === 'critical').length;
  const insufficientPredictionCount = predictions.filter((prediction) => prediction.status === 'unavailable').length;

  return (
    <>
      <div className="kpis">
        <Metric label="MUMBAI WARDS" value={boundaries?.features.length ?? '—'}/>
        <Metric label="CITIZEN REPORTS" value={reportsLoading && !reports.length ? '…' : reports.length}/>
        <Metric label="CV VERIFIED" value={reports.filter((report) => report.cv_verified).length}/>
        <Metric label="ACTIVE HOTSPOTS" value={hotspots.length}/>
      </div>
      <section className="prediction-summary" aria-label="Predictive outlook summary">
        <div><strong>HEURISTIC SCENARIO OUTLOOK</strong><span>Not a validated probability</span></div>
        <div><strong>{predictionsError ? '—' : predictionsLoading && !predictions.length ? '…' : highRiskWards}</strong><span>High-risk wards</span></div>
        <div><strong>{predictionsError ? '—' : predictionsLoading && !predictions.length ? '…' : criticalRiskWards}</strong><span>Critical wards</span></div>
        <div><strong>{predictionsError ? '—' : predictionsLoading && !predictions.length ? '…' : insufficientPredictionCount}</strong><span>Insufficient forecast data</span></div>
        <div><strong>—</strong><span>Trend needs stored history</span></div>
      </section>
      <section className="map-workspace">
        <div className="map-surface">
          <div className="map-water"/><div className="map-land"/>
          {boundaries && (
            <div className="live-map">
              <GeoMap
                boundaries={boundaries}
                riskGeoJSON={riskGeoJSON}
                reports={filteredReports}
                hotspots={hotspots}
                wardIntelligence={wardIntelligence}
                predictions={predictions}
                visibleLayers={visibleLayers}
                selectedWardCode={selected?.code ?? null}
                onWardClick={handleWardClick}
                onReportClick={handleReportClick}
                onHotspotClick={handleHotspotClick}
              />
            </div>
          )}
          <div className="map-toolbar">
            <div className="map-tabs"><span className="active"><Layers3 size={15}/>Mumbai flood layers</span></div>
          </div>
          <div id="map-layer-controls" className="map-layer-controls" aria-label="Map layers" tabIndex={-1}>
            {([
              ['reports', 'Citizen reports'],
              ['hotspots', 'Flood hotspots'],
              ['intelligence', 'Ward intelligence'],
              ['risk', 'Flood risk'],
              ['prediction', 'Prediction outlook'],
            ] as const).map(([layer, label]) => (
              <button
                type="button"
                key={layer}
                className={visibleLayers[layer] ? 'layer-toggle active' : 'layer-toggle'}
                aria-pressed={visibleLayers[layer]}
                onClick={() => setVisibleLayers((current) => ({ ...current, [layer]: !current[layer] }))}
              >
                <i className={`layer-swatch ${layer}`}/>{label}
              </button>
            ))}
          </div>
          <div className="map-filters" aria-label="Map filters">
            <label>Depth
              <select value={filters.waterDepth} onChange={(event) => setFilters((current) => ({ ...current, waterDepth: event.target.value as MapFilters['waterDepth'] }))}>
                <option value="all">All depths</option><option value="ankle">Ankle</option><option value="knee">Knee</option><option value="waist">Waist</option><option value="submerged">Submerged</option>
              </select>
            </label>
            <label>Verification
              <select value={filters.verification} onChange={(event) => setFilters((current) => ({ ...current, verification: event.target.value as MapFilters['verification'] }))}>
                <option value="all">All reports</option><option value="verified">CV verified</option><option value="unverified">Unverified</option>
              </select>
            </label>
            <label>Submitted
              <select value={filters.recency} onChange={(event) => setFilters((current) => ({ ...current, recency: event.target.value as MapFilters['recency'] }))}>
                <option value="all">Any time</option><option value="1">Last hour</option><option value="3">Last 3 hours</option><option value="24">Last 24 hours</option>
              </select>
            </label>
            <label>Ward
              <select value={filters.wardCode} onChange={(event) => setFilters((current) => ({ ...current, wardCode: event.target.value }))}>
                <option value="all">All wards</option>
                {wardOptions.map((ward) => <option key={ward.code} value={ward.code}>{ward.label}</option>)}
              </select>
            </label>
            <label>Forecast
              <select
                value={supportedHorizons.includes(forecastHorizon) ? forecastHorizon : ''}
                disabled={!supportedHorizons.length}
                onChange={(event) => onForecastHorizonChange(event.target.value as ForecastHorizon)}
                aria-label="Forecast horizon"
              >
                {supportedHorizons.length
                  ? supportedHorizons.map((horizon) => <option key={horizon} value={horizon}>Next {horizon}</option>)
                  : <option value="">No fresh forecast</option>}
              </select>
            </label>
          </div>
          {boundariesLoading && !boundaries ? <div className="map-loading"><Skeleton/><span>Loading all 24 ward boundaries</span></div> : null}
          {boundariesError && !boundaries ? <div className="map-empty"><Compass size={20}/><h3>Ward geometry is unavailable</h3><p>The local Mumbai ward boundary data could not be loaded.</p><button className="outline-button" onClick={() => refetchBoundaries()}>Retry</button></div> : null}
          {boundaries && !boundaries.features.length ? <div className="map-empty"><Compass size={20}/><h3>No valid ward geometry</h3><p>The boundary file did not contain renderable polygons.</p></div> : null}
          {refreshFailures.length ? (
            <div className="map-data-warning" role="status">
              {refreshFailures.map(([name, retry]) => <button key={name} onClick={() => retry()}>{name} unavailable · Retry</button>)}
            </div>
          ) : null}
          <div className="coordinates"><StatusDot kind={boundariesError || reportsError ? 'offline' : 'online'}/>MUMBAI · {reports.length} reports · refreshed automatically</div>
          {!process.env.NEXT_PUBLIC_MAPBOX_TOKEN && <div className="map-basemap-warning">Mapbox token is not configured; ward and incident overlays remain interactive.</div>}
          <div className="map-bottom">
            <div className="legend map-legend">
              {visibleLayers.intelligence && <div><b>WARD INTELLIGENCE</b><span><i className="intel-low"/>Low · &lt;0.35</span><span><i className="intel-moderate"/>Moderate · 0.35–0.54</span><span><i className="intel-high"/>High · 0.55–0.74</span><span><i className="intel-critical"/>Critical · ≥0.75</span></div>}
              {visibleLayers.reports && <div><b>REPORT DEPTH</b><span><i className="depth-ankle"/>Ankle</span><span><i className="depth-knee"/>Knee</span><span><i className="depth-waist"/>Waist</span><span><i className="depth-submerged"/>Submerged</span><span><i className="verified-key"/>Verified</span><span><i className="duplicate-key"/>Duplicate</span></div>}
              {visibleLayers.hotspots && <div><b>HOTSPOTS</b><span><i className="hotspot-key"/>Cluster size and intensity reflect report count and confidence</span></div>}
              {visibleLayers.risk && <div><b>FLOOD RISK</b><span><i className="risk-key"/>Existing ward risk engine</span></div>}
              {visibleLayers.prediction && <div><b>OUTLOOK · {forecastHorizon}</b><span><i className="prediction-low"/>Low</span><span><i className="prediction-moderate"/>Moderate</span><span><i className="prediction-high"/>High</span><span><i className="prediction-critical"/>Critical</span><span><i className="prediction-unavailable"/>Unavailable</span><span>Scenario index only; not a calibrated probability.</span></div>}
            </div>
            <div className="map-controls"><button type="button" aria-label="Zoom in">+</button><button type="button" aria-label="Zoom out">−</button><button type="button" aria-label="Reset map"><Compass size={16}/></button></div>
          </div>
        </div>
        <MapDetails
          selection={selection}
          onClose={() => {
            setSelection(null);
            onSelect(null);
            setFilters((current) => ({ ...current, wardCode: 'all' }));
          }}
          wardNameById={wardNameById}
          reportImage={reportImage}
          predictions={predictions}
          forecastHorizon={forecastHorizon}
        />
      </section>
      <div className="gateway"><StatusDot kind={refreshFailures.length ? 'degraded' : 'online'}/><b>LIVE DATA</b><span>Reports refresh every 30s · intelligence and outlook every 60s</span></div>
      {reportsLoading && !reports.length ? <span className="map-sr-status">Loading citizen reports</span> : null}
      {hotspotsLoading && !hotspots.length ? <span className="map-sr-status">Loading hotspots</span> : null}
      {intelligenceLoading && !wardIntelligence.length ? <span className="map-sr-status">Loading ward intelligence</span> : null}
    </>
  );
}

function MapDetails({
  selection,
  onClose,
  wardNameById,
  reportImage,
  predictions,
  forecastHorizon,
}: {
  selection: MapSelection;
  onClose: () => void;
  wardNameById: Map<string, string>;
  reportImage: (url: string) => string;
  predictions: WardPrediction[];
  forecastHorizon: ForecastHorizon;
}) {
  const ward = selection?.kind === 'ward' ? selection.ward : null;
  const report = selection?.kind === 'report' ? selection.report : null;
  const hotspot = selection?.kind === 'hotspot' ? selection.hotspot : null;
  const wardPrediction = ward
    ? predictions.find((prediction) => normalizedWardKey(prediction.ward_code) === normalizedWardKey(ward.code))
    : undefined;
  const forecastRain = wardPrediction?.feature_vector[`forecast_rainfall_${forecastHorizon}_mm`];

  return (
    <aside className={selection ? 'inspector' : 'inspector idle'}>
      {selection && <button type="button" onClick={onClose} className="close" aria-label="Close details"><X size={17}/></button>}
      {ward ? (
        <>
          <div className="tag">WARD SELECTED</div><h2>{ward.wardName}</h2>
          {ward.intelligence?.intelligence ? (
            <p>Citizen intelligence score <strong>{ward.intelligence.intelligence.intelligence_score.toFixed(2)}</strong> · {ward.intelligence.intelligence.intelligence_class}</p>
          ) : (
            <p>No citizen reports are available for this ward; no intelligence score is assigned.</p>
          )}
          <div className="inspector-section"><h3>FLOOD OUTLOOK · {forecastHorizon}</h3>
            <Detail label="Current risk engine score" value={wardPrediction?.current_risk_score == null ? '—' : `${wardPrediction.current_risk_score.toFixed(2)} · ${wardPrediction.current_risk_category ?? 'unclassified'}`}/>
            {wardPrediction?.current_risk_model_version && <Detail label="Current risk model version" value={wardPrediction.current_risk_model_version}/>}
            <Detail label="Heuristic scenario index" value={wardPrediction?.predicted_risk_score == null ? 'Unavailable' : `${wardPrediction.predicted_risk_score.toFixed(2)} · ${wardPrediction.risk_category}`}/>
            <Detail label="Flood probability" value="Not calibrated"/>
            <Detail label="Outlook data status" value={wardPrediction?.status.replace('_', ' ') ?? 'Unavailable'}/>
            <Detail label="Forecast rain" value={typeof forecastRain === 'number' ? `${forecastRain.toFixed(1)} mm` : 'Unavailable'}/>
            <Detail label="Data completeness" value={wardPrediction ? `${Math.round(wardPrediction.data_completeness * 100)}%` : '—'}/>
            {wardPrediction?.unavailable_reason && <p>{wardPrediction.unavailable_reason}</p>}
            {wardPrediction?.contributing_factors.map((factor) => <p className="map-detail-description" key={factor}>{factor}</p>)}
          </div>
          <div className="inspector-section"><h3>CITIZEN REPORT ANALYTICS</h3>
            <Detail label="Total reports" value={ward.intelligence?.analytics.total_reports ?? 0}/>
            <Detail label="Last 1 hour" value={ward.intelligence?.analytics.reports_last_1h ?? 0}/>
            <Detail label="Last 3 hours" value={ward.intelligence?.analytics.reports_last_3h ?? 0}/>
            <Detail label="Last 24 hours" value={ward.intelligence?.analytics.reports_last_24h ?? 0}/>
            <Detail label="CV verified" value={ward.intelligence?.analytics.cv_verified_count ?? 0}/>
            <Detail label="Severe reports" value={ward.intelligence?.analytics.severe_count ?? 0}/>
            <Detail label="Duplicates" value={ward.intelligence?.analytics.duplicate_count ?? 0}/>
            <Detail label="Average severity" value={ward.intelligence ? ward.intelligence.analytics.avg_severity.toFixed(2) : '—'}/>
          </div>
        </>
      ) : report ? (
        <>
          <div className="tag">CITIZEN REPORT</div><h2>{report.water_depth} water</h2>
          <Detail label="Report ID" value={report.report_id}/>
          <Detail label="Ward" value={report.ward_id ? wardNameById.get(normalizedWardKey(report.ward_id)) ?? report.ward_id : 'Unassigned'}/>
          <Detail label="Depth category" value={report.water_depth}/>
          <Detail label="Submitted" value={new Date(report.submitted_at).toLocaleString()}/>
          <Detail label="CV status" value={report.cv_verified ? 'Verified' : 'Unverified'}/>
          <Detail label="CV confidence" value={report.cv_confidence == null ? '—' : `${(report.cv_confidence * 100).toFixed(1)}%`}/>
          <Detail label="CV estimated depth" value={report.cv_water_depth_m == null ? '—' : `${report.cv_water_depth_m.toFixed(2)} m`}/>
          <Detail label="Duplicate" value={report.is_duplicate ? `Yes${report.duplicate_of_id ? ` · ${report.duplicate_of_id}` : ''}` : 'No'}/>
          {report.description && <p className="map-detail-description">{report.description}</p>}
          {report.image_url && <img className="report-photo" src={reportImage(report.image_url)} alt={`Flood report ${report.report_id}`}/>}
        </>
      ) : hotspot ? (
        <>
          <div className="tag">FLOOD HOTSPOT</div><h2>Active report cluster</h2>
          <Detail label="Hotspot ID" value={hotspot.hotspot_id}/>
          <Detail label="Reports" value={hotspot.report_count}/>
          <Detail label="Average severity" value={hotspot.avg_severity.toFixed(2)}/>
          <Detail label="Confidence" value={`${(hotspot.confidence * 100).toFixed(1)}%`}/>
          <Detail label="CV verified reports" value={hotspot.cv_verified_count}/>
          <Detail label="Latest incident" value={hotspot.latest_incident ? new Date(hotspot.latest_incident).toLocaleString() : '—'}/>
          <Detail label="Wards" value={hotspot.ward_ids.map((id) => wardNameById.get(normalizedWardKey(id)) ?? id).join(', ') || 'Unassigned'}/>
          <Detail label="Center" value={`${hotspot.center_latitude.toFixed(5)}, ${hotspot.center_longitude.toFixed(5)}`}/>
        </>
      ) : (
        <>
          <div className="tag">MAP INSPECTOR</div><h2>Flood intelligence</h2>
          <p>Select a ward polygon, citizen report marker, or hotspot circle to inspect its live details.</p>
          <div className="inspector-section"><h3>MAP DATA</h3>
            <Detail label="Ward boundaries" value="24 Mumbai wards"/>
            <Detail label="Visible reports" value="Filtered by current selections"/>
            <Detail label="Refresh" value="Reports 30s · layers 60s"/>
          </div>
        </>
      )}
    </aside>
  );
}

function Detail({label,value}:{label:string;value:string|number}) {
  return <div className="map-detail-row"><span>{label}</span><strong>{value}</strong></div>;
}
function ListScreen({section,reports,reportsLoading,reportsError,refetchReports,notify}:{section:'reports'|'social';reports?:CitizenReport[];reportsLoading:boolean;reportsError:boolean;refetchReports:()=>void;notify:(message:string)=>void}){
  const [submitReportOpen,setSubmitReportOpen]=useState(false);
  const [submitting,setSubmitting]=useState(false);
  const [reportForm,setReportForm]=useState({latitude:19.076,longitude:72.8777,water_depth:'knee' as WaterDepth,description:'',image:null as File|null});
  if(section==='social'){
    return <SocialIntelligence/>;
  }
  const repList=reports??[];
  const total=repList.length;
  const verified=repList.filter(r=>r.cv_verified).length;
  const duplicates=repList.filter(r=>r.is_duplicate).length;
  const severe=repList.filter(r=>r.water_depth==='waist'||r.water_depth==='submerged').length;
  const handleSubmit=async(e:React.FormEvent)=>{
    e.preventDefault();
    setSubmitting(true);
    try{
      const data=await api.submitReport({
        latitude:reportForm.latitude,
        longitude:reportForm.longitude,
        water_depth:reportForm.water_depth,
        description:reportForm.description||undefined,
        ...(reportForm.image?{image:reportForm.image}:{}),
      });
      notify(`Report submitted: ${data.report_id}`);
      setSubmitReportOpen(false);
      refetchReports();
    }catch(err:unknown){notify(err instanceof Error?err.message:'Submission failed');}
    finally{setSubmitting(false);}
  };
  return <><div className="kpis">{['TOTAL REPORTS','VERIFIED','DUPLICATES','SEVERE'].map((x,i)=>(
    <Metric key={i} label={x} value={i===0?total:i===1?verified:i===2?duplicates:severe}/>
  ))}</div>
  <section className="list-surface">
    <div className="filters">
      <button className="outline-button" onClick={()=>setSubmitReportOpen(true)}>+ Submit Report</button>
      {['Ward · All','Severity · All','Verification · All','Time · Latest'].map(x=>(<motion.button whileTap={{scale:.98}} key={x}>{x}</motion.button>))}
    </div>
    {submitReportOpen?<div className="report-form"><form onSubmit={handleSubmit} className="form-grid">
      <label>Latitude<input type="number" step="any" defaultValue={reportForm.latitude} onChange={e=>setReportForm({...reportForm,latitude:parseFloat(e.target.value)})}/></label>
      <label>Longitude<input type="number" step="any" defaultValue={reportForm.longitude} onChange={e=>setReportForm({...reportForm,longitude:parseFloat(e.target.value)})}/></label>
      <label>Water Depth<select value={reportForm.water_depth} onChange={e=>setReportForm({...reportForm,water_depth:e.target.value as WaterDepth})}>
        <option value="ankle">Ankle</option><option value="knee">Knee</option><option value="waist">Waist</option><option value="submerged">Submerged</option>
      </select></label>
      <label>Description<textarea defaultValue={reportForm.description} onChange={e=>setReportForm({...reportForm,description:e.target.value})}/></label>
      <label>Photo<input type="file" accept="image/jpeg,image/jpg,image/png,image/webp" onChange={e=>setReportForm({...reportForm,image:e.target.files?e.target.files[0]:null})}/></label>
      <button type="submit" className="primary-button" disabled={submitting}>{submitting?'Submitting…':'Submit Report'}</button>
    </form></div>:reportsLoading?<div className="map-loading"><Skeleton/><span>Loading citizen reports</span></div>:reportsError?<div className="map-empty"><Flag size={20}/><h3>Citizen reports are unavailable</h3><p>Could not retrieve reports from the service.</p><button className="outline-button" onClick={()=>refetchReports()}>Retry connection</button></div>:repList.length?<div className="report-list">{repList.map(r=>(<div key={r.report_id} className="report-card" onClick={()=>{if(r.image_url)notify(`Report ${r.report_id} · ${r.water_depth} · CV ${r.cv_verified?'VERIFIED':'UNVERIFIED'}`)}}>
      <div className="report-header"><span className={`depth-badge ${r.water_depth}`}>{r.water_depth}</span><span className={r.is_duplicate?'duplicate-tag':'verified-tag'}>{r.is_duplicate?'DUPLICATE':r.cv_verified?'CV VERIFIED':r.operator_verification_status === 'resolved'?'RESOLVED':r.operator_verification_status === 'expired'?'EXPIRED':r.operator_verification_status === 'confirmed'?'CONFIRMED':'PENDING'}</span></div>
      <div className="report-body"><strong>Ward:</strong>{r.ward_id||'—'}<br/><strong>Location:</strong>{r.latitude.toFixed(4)},{r.longitude.toFixed(4)}<br/><strong>Reported:</strong>{new Date(r.submitted_at).toLocaleString()}<br/>{r.description?<span className="report-desc">{r.description}</span>:null}{r.cv_water_depth_m!=null?<span className="report-cv">CV depth: {r.cv_water_depth_m}m (conf: {(r.cv_confidence??0).toFixed(2)})</span>:null}{r.nlp_analysis?<span className="report-cv"><br/>NLP: {r.nlp_analysis.classification?.replace('_', ' ')} (conf: {(r.nlp_analysis.confidence??0).toFixed(2)}){r.nlp_analysis.extracted_depth_m!=null?` · text depth: ${r.nlp_analysis.extracted_depth_m}m`:''}</span>:null}</div>
    </div>))}</div> : <Empty title="No citizen reports available" copy="Submit your first flood report or wait for field observations to arrive." icon={Flag}/>}
  </section></>;
}
function Alerts({notify}:{notify:(s:string)=>void}){return <><div className="kpis">{['ACTIVE ALERTS','CRITICAL','SCHEDULED','DELIVERED'].map(x=><Metric key={x} label={x}/>)}</div><section className="alert-layout"><div className="history"><h2>Alert history</h2><p>Recent emergency communications.</p><div className="unavailable"><b>No alerts available</b>When returned by the dispatch service, alert history will appear here.</div></div><div className="composer"><h2>Compose alert</h2><p>All fields are reviewed before dispatch.</p>{['Alert title','Affected area','Message'].map((x,i)=><label key={x}>{x.toUpperCase()}<div className={i===2?'field textarea':'field'}>{i===2?'Compose public guidance and required action':'Select or enter '+x.toLowerCase()}</div></label>)}<label>DELIVERY</label><div className="delivery"><span>CAP</span><span>SMS</span><span>WhatsApp</span><span>Push</span></div><div className="button-row"><button className="outline-button">Preview</button><motion.button whileHover={{y:-1}} whileTap={{scale:.98}} className="primary-button" onClick={()=>notify('CAP generation is unavailable until alert dispatch is configured.')}>Generate CAP</motion.button></div></div></section></>}
function Responders(){return <><div className="kpis">{['RESPONDER UNITS','INCIDENTS','BLOCKED ROADS','SUGGESTED ROUTES'].map(x=><Metric key={x} label={x}/>)}</div><section className="route-surface"><Empty title="Responder routing is being integrated" copy="Unit locations, traffic constraints, incidents and recommended routes will be shown when the routing engine is connected." icon={Route}/></section></>}
