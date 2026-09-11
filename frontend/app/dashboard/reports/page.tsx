"use client";

import React, { useState, useEffect, useMemo } from "react";
import {
  Camera,
  CheckCircle2,
  AlertTriangle,
  Copy,
  MapPin,
  Clock,
  ShieldCheck,
  Filter,
  Plus,
  X,
  Upload,
  Layers,
  ChevronRight,
} from "lucide-react";
import {
  fetchCitizenReports,
  fetchReportSummary,
  submitCitizenReport,
  CitizenReportItem,
  ReportSummary,
} from "../../lib/api";

export default function ReportsDashboard() {
  const [reports, setReports] = useState<CitizenReportItem[]>([]);
  const [summary, setSummary] = useState<ReportSummary | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [verifiedFilter, setVerifiedFilter] = useState<boolean>(false);
  const [isModalOpen, setIsModalOpen] = useState<boolean>(false);

  // Intake Form State
  const [lat, setLat] = useState<string>("19.0434");
  const [lon, setLon] = useState<string>("72.8576");
  const [waterDepth, setWaterDepth] = useState<"ankle" | "knee" | "waist" | "submerged">("knee");
  const [description, setDescription] = useState<string>("");
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  const loadData = async () => {
    try {
      const [reps, sum] = await Promise.all([
        fetchCitizenReports(undefined, verifiedFilter),
        fetchReportSummary(),
      ]);
      setReports(reps);
      setSummary(sum);
    } catch (e) {
      console.error("Failed to load reports:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 20000);
    return () => clearInterval(interval);
  }, [verifiedFilter]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      const formData = new FormData();
      formData.append("latitude", lat);
      formData.append("longitude", lon);
      formData.append("water_depth", waterDepth);
      if (description) formData.append("description", description);
      if (imageFile) formData.append("image", imageFile);

      await submitCitizenReport(formData);
      setIsModalOpen(false);
      setDescription("");
      setImageFile(null);
      await loadData();
    } catch (err) {
      console.error("Failed to submit report:", err);
      alert("Submission failed. Ensure backend is reachable.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const depthColorBadge = (depth: string) => {
    switch (depth) {
      case "submerged":
        return "bg-red-500/10 text-red-400 border-red-500/30";
      case "waist":
        return "bg-amber-500/10 text-amber-400 border-amber-500/30";
      case "knee":
        return "bg-yellow-500/10 text-yellow-400 border-yellow-500/30";
      default:
        return "bg-blue-500/10 text-blue-400 border-blue-500/30";
    }
  };

  return (
    <div className="h-full w-full bg-slate-950 text-slate-100 flex flex-col overflow-hidden p-6 gap-6">
      {/* Top Banner KPI summary */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
            <Camera className="w-5 h-5 text-blue-400" />
            Citizen Ground-Truth Reports
          </h1>
          <p className="text-xs text-slate-400 mt-0.5">
            Crowdsourced water depth observations validated by YOLOv8 Computer Vision (Engine B).
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => setVerifiedFilter(!verifiedFilter)}
            className={`px-3 py-2 rounded-xl text-xs font-medium border flex items-center gap-2 transition-all ${
              verifiedFilter
                ? "bg-emerald-600/20 text-emerald-300 border-emerald-500/40"
                : "bg-slate-900 border-slate-800 text-slate-400 hover:text-white"
            }`}
          >
            <ShieldCheck className="w-4 h-4" />
            {verifiedFilter ? "Verified Only" : "All Incidents"}
          </button>

          <button
            onClick={() => setIsModalOpen(true)}
            className="px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold flex items-center gap-2 shadow-lg shadow-blue-600/20 transition-all"
          >
            <Plus className="w-4 h-4" />
            Submit Ground Report
          </button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-4 gap-4">
        <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl p-4">
          <div className="text-[11px] text-slate-400 uppercase tracking-wider font-semibold">
            24H Reports Received
          </div>
          <div className="text-2xl font-bold font-mono text-white mt-1">
            {summary?.total_reports_24h ?? 0}
          </div>
        </div>

        <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl p-4">
          <div className="text-[11px] text-slate-400 uppercase tracking-wider font-semibold">
            CV Verified Photos
          </div>
          <div className="text-2xl font-bold font-mono text-emerald-400 mt-1 flex items-center gap-2">
            <CheckCircle2 className="w-5 h-5" />
            {summary?.cv_verified_count ?? 0}
          </div>
        </div>

        <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl p-4">
          <div className="text-[11px] text-slate-400 uppercase tracking-wider font-semibold">
            Duplicates Deduplicated
          </div>
          <div className="text-2xl font-bold font-mono text-slate-400 mt-1 flex items-center gap-2">
            <Copy className="w-5 h-5 text-slate-500" />
            {summary?.flagged_duplicates ?? 0}
          </div>
        </div>

        <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl p-4">
          <div className="text-[11px] text-slate-400 uppercase tracking-wider font-semibold">
            Severe Inundations (Waist+)
          </div>
          <div className="text-2xl font-bold font-mono text-red-400 mt-1 flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-red-400" />
            {summary?.severe_reports ?? 0}
          </div>
        </div>
      </div>

      {/* Reports Feed Table */}
      <div className="flex-1 bg-slate-900/40 border border-slate-800/80 rounded-2xl overflow-hidden flex flex-col">
        <div className="p-4 border-b border-slate-800/80 flex items-center justify-between text-xs text-slate-400 font-semibold uppercase tracking-wider">
          <span>Incident Stream ({reports.length})</span>
          <span>Engine B Model: YOLOv8-WaterSeg</span>
        </div>

        <div className="flex-1 overflow-y-auto divide-y divide-slate-800/60">
          {reports.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-slate-500 text-xs py-16">
              <Camera className="w-8 h-8 mb-2 opacity-40" />
              No citizen flood reports match the current filter.
            </div>
          ) : (
            reports.map((rep) => (
              <div
                key={rep.report_id}
                className="p-4 hover:bg-slate-800/30 transition-colors flex items-center justify-between gap-4 text-xs"
              >
                <div className="flex items-start gap-3.5 min-w-0">
                  <div
                    className={`w-10 h-10 rounded-xl flex items-center justify-center font-bold text-xs uppercase border flex-shrink-0 ${depthColorBadge(
                      rep.water_depth
                    )}`}
                  >
                    {rep.water_depth.slice(0, 2)}
                  </div>

                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-white truncate">
                        {rep.ward_id ? `Ward ${rep.ward_id}` : "Mumbai Unclassified"}
                      </span>
                      {rep.cv_verified && (
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 flex items-center gap-1">
                          <CheckCircle2 className="w-3 h-3" />
                          CV Verified ({Math.round((rep.cv_confidence || 0) * 100)}%)
                        </span>
                      )}
                      {rep.is_duplicate && (
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-slate-800 text-slate-400 border border-slate-700">
                          Duplicate (&lt;50m)
                        </span>
                      )}
                    </div>

                    <p className="text-slate-300 mt-1 truncate">
                      {rep.description || "Citizen reported standing water accumulation."}
                    </p>

                    <div className="flex items-center gap-3 text-[11px] text-slate-500 mt-1.5 font-mono">
                      <span className="flex items-center gap-1">
                        <MapPin className="w-3 h-3" />
                        {rep.latitude.toFixed(4)}, {rep.longitude.toFixed(4)}
                      </span>
                      <span className="flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {new Date(rep.submitted_at).toLocaleTimeString()} IST
                      </span>
                      {rep.cv_water_depth_m !== undefined && (
                        <span className="text-amber-400 font-semibold">
                          Estimated: {rep.cv_water_depth_m?.toFixed(2)}m
                        </span>
                      )}
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-3 flex-shrink-0">
                  <span
                    className={`px-2.5 py-1 rounded-lg font-bold uppercase tracking-wider text-[10px] border ${depthColorBadge(
                      rep.water_depth
                    )}`}
                  >
                    {rep.water_depth} Level
                  </span>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Submission Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-md shadow-2xl p-6 text-slate-200 animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3 mb-4">
              <h3 className="font-bold text-sm text-white flex items-center gap-2">
                <Camera className="w-4 h-4 text-blue-400" />
                Submit Citizen Incident Report
              </h3>
              <button
                onClick={() => setIsModalOpen(false)}
                className="p-1 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4 text-xs">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-400 mb-1">Latitude</label>
                  <input
                    type="text"
                    value={lat}
                    onChange={(e) => setLat(e.target.value)}
                    required
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white font-mono"
                  />
                </div>
                <div>
                  <label className="block text-slate-400 mb-1">Longitude</label>
                  <input
                    type="text"
                    value={lon}
                    onChange={(e) => setLon(e.target.value)}
                    required
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white font-mono"
                  />
                </div>
              </div>

              <div>
                <label className="block text-slate-400 mb-1">Water Depth Category</label>
                <select
                  value={waterDepth}
                  onChange={(e) => setWaterDepth(e.target.value as any)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white"
                >
                  <option value="ankle">Ankle Deep (~0.15m)</option>
                  <option value="knee">Knee Deep (~0.50m)</option>
                  <option value="waist">Waist Deep (~1.00m)</option>
                  <option value="submerged">Fully Submerged (&gt;1.80m)</option>
                </select>
              </div>

              <div>
                <label className="block text-slate-400 mb-1">Incident Notes / Landmarks</label>
                <textarea
                  rows={2}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="e.g. Hindmata flyover underpass, cars stalled"
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl p-3 text-white"
                />
              </div>

              <div>
                <label className="block text-slate-400 mb-1">Incident Photo (for CV Verification)</label>
                <input
                  type="file"
                  accept="image/*"
                  onChange={(e) => setImageFile(e.target.files?.[0] || null)}
                  className="w-full text-slate-400 file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-blue-600/20 file:text-blue-400 hover:file:bg-blue-600/30"
                />
              </div>

              <div className="pt-3 border-t border-slate-800 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-white font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="px-5 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-semibold disabled:opacity-50 flex items-center gap-2"
                >
                  {isSubmitting && <div className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />}
                  Submit Report
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
