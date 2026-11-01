
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


type BackendWard = {
  id: number;
  ward_id: string;
  ward_name: string;
  city: string;

  current_risk_score?: number;
  current_risk_class?: 'low' | 'medium' | 'high' | 'critical';

  area_sqkm?: number;
  population?: number;
  is_coastal?: boolean;
  avg_elevation_m?: number;
  drainage_index?: number;
};


export const http = axios.create({
  baseURL:
    process.env.NEXT_PUBLIC_API_URL ||
    'http://localhost:8000/v1',
  timeout: 10000,
});

export const api = {
  wards: async (): Promise<Ward[]> => {
    const { data } = await http.get<BackendWard[]>('/wards');

    return data.map((ward) => ({
      id: ward.ward_id,
      name: ward.ward_name,
      risk_score: ward.current_risk_score,
      risk_class: ward.current_risk_class,
      area_sqkm: ward.area_sqkm,
      population: ward.population,
      is_coastal: ward.is_coastal,
      avg_elevation_m: ward.avg_elevation_m,
      drainage_index: ward.drainage_index,
    }));
  },

  wardGeojson: () =>
    http
      .get<GeoJSON.FeatureCollection>('/wards/geojson')
      .then((res) => res.data),

  ward: (id: string) =>
    http.get(`/wards/${id}`).then((res) => res.data),

  wardRisk: (id: string) =>
    http.get(`/wards/${id}/risk`).then((res) => res.data),

  reports: () =>
    http.get('/reports').then((res) => res.data),

  reportSummary: () =>
    http.get('/reports/summary').then((res) => res.data),

  alerts: () =>
    http.get('/alerts').then((res) => res.data),

  socialSignals: () =>
    http.get('/social/signals').then((res) => res.data),
};
