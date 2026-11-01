import axios from 'axios';
export type Ward = { id:string; name:string; risk_score?:number; risk_class?:'low'|'medium'|'high'|'critical' };
export const http = axios.create({ baseURL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/v1', timeout: 10_000 });
export const api = { wards:()=>http.get<Ward[]>('/wards').then(r=>r.data), wardGeojson:()=>http.get<GeoJSON.FeatureCollection>('/wards/geojson').then(r=>r.data), ward:(id:string)=>http.get(`/wards/${id}`).then(r=>r.data), wardRisk:(id:string)=>http.get(`/wards/${id}/risk`).then(r=>r.data), reports:()=>http.get('/reports').then(r=>r.data), reportSummary:()=>http.get('/reports/summary').then(r=>r.data), alerts:()=>http.get('/alerts').then(r=>r.data), socialSignals:()=>http.get('/social/signals').then(r=>r.data) };
