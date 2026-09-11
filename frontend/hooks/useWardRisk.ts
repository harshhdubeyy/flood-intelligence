/**
 * Custom React hook for fetching and managing real-time ward risk states and GeoJSON.
 */

import { useState, useEffect, useCallback } from "react";
import { fetchWardsGeoJSON, fetchWardsList, WardGeoJSONCollection, WardSummary } from "../lib/api";

export function useWardRisk(pollIntervalMs: number = 60000) {
  const [geoData, setGeoData] = useState<WardGeoJSONCollection | null>(null);
  const [wardsList, setWardsList] = useState<WardSummary[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      setError(null);
      const [geo, list] = await Promise.all([
        fetchWardsGeoJSON(),
        fetchWardsList(),
      ]);
      setGeoData(geo);
      setWardsList(list);
    } catch (err: any) {
      console.error("Failed to load ward risk datasets:", err);
      setError(err?.message || "Failed to connect to Flood Intelligence API");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, pollIntervalMs);
    return () => clearInterval(interval);
  }, [loadData, pollIntervalMs]);

  return {
    geoData,
    wardsList,
    isLoading,
    error,
    refetch: loadData,
  };
}
