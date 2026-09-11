/**
 * Geospatial and styling utility functions for Mapbox and Deck.gl integration.
 */

export const MUMBAI_CENTER = {
  longitude: 72.8777,
  latitude: 19.0760,
  zoom: 10.8,
  pitch: 45,
  bearing: -15,
};

/**
 * Color mappings for risk tiers conforming to TRD Section 10.2:
 * low: Green, medium: Yellow, high: Orange, critical: Red
 */
export const RISK_COLOR_RGB: Record<string, [number, number, number, number]> = {
  low: [34, 197, 94, 180],       // #22c55e (Safe)
  medium: [234, 179, 8, 200],    // #eab308 (Watch)
  high: [249, 115, 22, 220],     // #f97316 (Warning)
  critical: [239, 68, 68, 230],  // #ef4444 (Critical / Evacuate)
};

export const RISK_COLOR_HEX: Record<string, string> = {
  low: "#22c55e",
  medium: "#eab308",
  high: "#f97316",
  critical: "#ef4444",
};

/**
 * Returns RGBA array tuple [r, g, b, a] for Deck.gl fill color evaluation.
 */
export function getRiskColor(riskClass: string): [number, number, number, number] {
  return RISK_COLOR_RGB[riskClass.toLowerCase()] || [148, 163, 184, 160];
}

/**
 * Format risk score float as percentage string.
 */
export function formatRiskScore(score: number): string {
  return `${Math.round(score * 100)}%`;
}
