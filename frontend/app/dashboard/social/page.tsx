"use client";

import React, { useState, useEffect } from "react";
import {
  MessageSquare,
  Radio,
  Send,
  Sparkles,
  AlertTriangle,
  Flame,
  ShieldAlert,
  MapPin,
  Clock,
  Filter,
  Plus,
  X,
  PhoneCall,
  Share2,
  RefreshCw,
  Cpu,
  Layers,
  CheckCircle2,
} from "lucide-react";
import {
  fetchSocialSignals,
  fetchSocialSummary,
  ingestSocialSignal,
  simulateSocialFeed,
  fetchWardsList,
  SocialSignalItem,
  SocialSummary,
  WardSummary,
} from "../../lib/api";

export default function SocialIntelligencePage() {
  const [signals, setSignals] = useState<SocialSignalItem[]>([]);
  const [summary, setSummary] = useState<SocialSummary | null>(null);
  const [wards, setWards] = useState<WardSummary[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [isSimulating, setIsSimulating] = useState<boolean>(false);

  // Filters
  const [selectedWard, setSelectedWard] = useState<string>("all");
  const [selectedClassification, setSelectedClassification] = useState<string>("all");

  // Ingestion Modal
  const [isModalOpen, setIsModalOpen] = useState<boolean>(false);
  const [source, setSource] = useState<string>("twitter");
  const [authorHandle, setAuthorHandle] = useState<string>("@Mumbaikar_Alerts");
  const [contentText, setContentText] = useState<string>(
    "कुर्ला कमानी जवळ पाणी भरले आहे. नाला ओसंडून वाहत असल्याने घरात पाणी शिरले. मदत हवी!"
  );
  const [manualWard, setManualWard] = useState<string>("");
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  const loadData = async () => {
    try {
      const [sigData, sumData, wardData] = await Promise.all([
        fetchSocialSignals(
          selectedWard !== "all" ? selectedWard : undefined,
          selectedClassification !== "all" ? selectedClassification : undefined
        ),
        fetchSocialSummary(24),
        fetchWardsList(),
      ]);
      setSignals(sigData);
      setSummary(sumData);
      setWards(wardData);
    } catch (e) {
      console.error("Failed to load social signals:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 15000);
    return () => clearInterval(interval);
  }, [selectedWard, selectedClassification]);

  const handleSimulate = async () => {
    setIsSimulating(true);
    try {
      await simulateSocialFeed();
      await loadData();
    } catch (err) {
      console.error("Simulation failed:", err);
    } finally {
      setIsSimulating(false);
    }
  };

  const handleManualIngest = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      await ingestSocialSignal({
        source,
        author_handle: authorHandle,
        content_text: contentText,
        ward_id: manualWard || undefined,
      });
      setIsModalOpen(false);
      setContentText("");
      await loadData();
    } catch (err) {
      console.error("Ingestion failed:", err);
      alert("Failed to ingest signal.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const getClassificationBadge = (cls: string) => {
    switch (cls) {
      case "evacuation_needed":
        return "bg-red-500/10 text-red-400 border-red-500/30";
      case "urgent":
        return "bg-amber-500/10 text-amber-400 border-amber-500/30";
      case "waterlogging":
        return "bg-blue-500/10 text-blue-400 border-blue-500/30";
      default:
        return "bg-slate-800 text-slate-400 border-slate-700";
    }
  };

  const getSourceIcon = (src: string) => {
    switch (src) {
      case "twitter":
        return <Share2 className="w-3.5 h-3.5 text-sky-400" />;
      case "telegram":
        return <MessageSquare className="w-3.5 h-3.5 text-blue-400" />;
      case "helpline_1916":
        return <PhoneCall className="w-3.5 h-3.5 text-emerald-400" />;
      default:
        return <Radio className="w-3.5 h-3.5 text-purple-400" />;
    }
  };

  return (
    <div className="h-full w-full bg-slate-950 text-slate-100 flex flex-col overflow-hidden p-6 gap-6">
      {/* Top Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
            <Cpu className="w-5 h-5 text-indigo-400" />
            Social Media Intelligence & Multilingual NLP Triage (Engine C)
          </h1>
          <p className="text-xs text-slate-400 mt-0.5">
            Real-time ingestion from X/Twitter, Telegram, & BMC 1916 Helpline with IndicBERT distress urgency scoring.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleSimulate}
            disabled={isSimulating}
            className="px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold flex items-center gap-2 border border-slate-700 transition-all disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isSimulating ? "animate-spin text-amber-400" : "text-slate-400"}`} />
            Simulate Monsoon Stream
          </button>

          <button
            onClick={() => setIsModalOpen(true)}
            className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold flex items-center gap-2 shadow-lg shadow-indigo-600/20 transition-all"
          >
            <Plus className="w-4 h-4" />
            Ingest Signal
          </button>
        </div>
      </div>

      {/* Overview Analytics Bar */}
      <div className="grid grid-cols-4 gap-4">
        <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl p-4">
          <div className="text-[11px] text-slate-400 uppercase tracking-wider font-semibold">
            Signals Ingested (24h)
          </div>
          <div className="text-2xl font-bold font-mono text-white mt-1">
            {summary?.total_signals_24h || signals.length}
          </div>
          <div className="text-[10px] text-slate-500 mt-0.5">Twitter / Telegram / BMC 1916</div>
        </div>

        <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl p-4">
          <div className="text-[11px] text-slate-400 uppercase tracking-wider font-semibold">
            Critical Evacuation Distress
          </div>
          <div className="text-2xl font-bold font-mono text-red-400 mt-1 flex items-center gap-1.5">
            <Flame className="w-5 h-5 text-red-500" />
            {summary?.evacuation_mentions_count || 0}
          </div>
          <div className="text-[10px] text-red-400/80 mt-0.5">High-priority dispatch trigger</div>
        </div>

        <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl p-4">
          <div className="text-[11px] text-slate-400 uppercase tracking-wider font-semibold">
            NLP Triage Engine
          </div>
          <div className="text-sm font-bold text-indigo-400 mt-1 flex items-center gap-1.5">
            <Sparkles className="w-4 h-4" />
            IndicBERT Multilingual v1.0
          </div>
          <div className="text-[10px] text-slate-500 mt-0.5">English, Marathi (मराठी), Hindi</div>
        </div>

        <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl p-4">
          <div className="text-[11px] text-slate-400 uppercase tracking-wider font-semibold">
            Top Hotspot Landmark
          </div>
          <div className="text-sm font-bold text-amber-400 mt-1 truncate">
            {summary?.top_hotspots?.[0]?.landmark || "Monitoring..."}
          </div>
          <div className="text-[10px] text-slate-500 mt-0.5">
            {summary?.top_hotspots?.[0]
              ? `${summary.top_hotspots[0].count} reports • ${(summary.top_hotspots[0].avg_urgency * 100).toFixed(0)}% urgency`
              : "No active surge"}
          </div>
        </div>
      </div>

      {/* Filter Row */}
      <div className="flex items-center justify-between bg-slate-900/40 border border-slate-800/80 p-3 rounded-xl">
        <div className="flex items-center gap-2">
          <Filter className="w-3.5 h-3.5 text-slate-400" />
          <span className="text-xs text-slate-400 font-semibold uppercase tracking-wider mr-2">
            Filter Tiers:
          </span>

          {["all", "evacuation_needed", "urgent", "waterlogging", "noise"].map((t) => (
            <button
              key={t}
              onClick={() => setSelectedClassification(t)}
              className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
                selectedClassification === t
                  ? "bg-indigo-600 text-white"
                  : "bg-slate-800/60 text-slate-400 hover:text-slate-200"
              }`}
            >
              {t.replace("_", " ").toUpperCase()}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-3 text-xs">
          <span className="text-slate-400">Ward:</span>
          <select
            value={selectedWard}
            onChange={(e) => setSelectedWard(e.target.value)}
            className="bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1 text-white text-xs"
          >
            <option value="all">All Mumbai Wards</option>
            {wards.map((w) => (
              <option key={w.ward_id} value={w.ward_id}>
                {w.ward_id} - {w.ward_name}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Main Grid: Stream & Analytics */}
      <div className="flex-1 grid grid-cols-3 gap-6 overflow-hidden min-h-0">
        {/* Left 2 Cols: Live Stream */}
        <div className="col-span-2 bg-slate-900/40 border border-slate-800/80 rounded-2xl overflow-hidden flex flex-col">
          <div className="p-4 border-b border-slate-800/80 flex items-center justify-between text-xs text-slate-400 font-semibold uppercase tracking-wider">
            <span>Classified Intelligence Feed ({signals.length})</span>
            <span>Spatial Landmark Resolution & Score</span>
          </div>

          <div className="flex-1 overflow-y-auto divide-y divide-slate-800/60">
            {signals.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-slate-500 text-xs py-16">
                <ShieldAlert className="w-8 h-8 mb-2 opacity-40" />
                No signals matching selected criteria. Click "Simulate Monsoon Stream" to ingest demo data.
              </div>
            ) : (
              signals.map((sig) => (
                <div
                  key={sig.signal_id}
                  className="p-4 hover:bg-slate-800/30 transition-colors flex items-start justify-between gap-4 text-xs"
                >
                  <div className="space-y-2 flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="p-1.5 rounded-lg bg-slate-800 border border-slate-700">
                        {getSourceIcon(sig.source)}
                      </span>
                      <span className="font-bold text-white text-xs">
                        {sig.author_handle || "Anonymous"}
                      </span>
                      <span className="text-[10px] text-slate-500 font-mono">
                        via {sig.source.replace("_", " ").toUpperCase()}
                      </span>
                      <span
                        className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase border ml-auto ${getClassificationBadge(
                          sig.classification
                        )}`}
                      >
                        {sig.classification.replace("_", " ")}
                      </span>
                      <span className="px-1.5 py-0.5 rounded text-[9px] font-mono uppercase bg-slate-800 text-slate-400 border border-slate-700">
                        {sig.language}
                      </span>
                    </div>

                    <p className="text-slate-200 text-xs leading-relaxed">
                      {sig.content_text}
                    </p>

                    {/* Extracted spatial entities */}
                    <div className="flex flex-wrap items-center gap-2 pt-1">
                      {sig.location_name && (
                        <span className="flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-md bg-indigo-500/10 text-indigo-300 border border-indigo-500/30">
                          <MapPin className="w-3 h-3 text-indigo-400" />
                          {sig.location_name}
                        </span>
                      )}

                      {sig.ward_id && (
                        <span className="text-[11px] px-2 py-0.5 rounded-md bg-slate-800 text-slate-300 border border-slate-700">
                          Ward {sig.ward_id}
                        </span>
                      )}

                      <span className="text-[10px] text-slate-500 font-mono ml-auto flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {new Date(sig.posted_at).toLocaleTimeString()} IST
                      </span>
                    </div>
                  </div>

                  {/* Urgency Score Gauge */}
                  <div className="flex flex-col items-center justify-center p-2 rounded-xl bg-slate-950 border border-slate-800 w-20 flex-shrink-0">
                    <span className="text-[9px] uppercase font-bold text-slate-500">Urgency</span>
                    <span
                      className={`text-lg font-mono font-bold ${
                        sig.urgency_score >= 0.8
                          ? "text-red-400"
                          : sig.urgency_score >= 0.5
                          ? "text-amber-400"
                          : "text-blue-400"
                      }`}
                    >
                      {(sig.urgency_score * 100).toFixed(0)}%
                    </span>
                    <div className="w-full bg-slate-800 h-1 rounded-full mt-1 overflow-hidden">
                      <div
                        className={`h-full ${
                          sig.urgency_score >= 0.8
                            ? "bg-red-500"
                            : sig.urgency_score >= 0.5
                            ? "bg-amber-500"
                            : "bg-blue-500"
                        }`}
                        style={{ width: `${sig.urgency_score * 100}%` }}
                      />
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Right 1 Col: Hotspots & Classification Breakdown */}
        <div className="space-y-4 overflow-y-auto">
          {/* Top Hotspots */}
          <div className="bg-slate-900/40 border border-slate-800/80 rounded-2xl p-4">
            <h3 className="text-xs font-bold text-white uppercase tracking-wider mb-3 flex items-center gap-1.5">
              <MapPin className="w-4 h-4 text-indigo-400" />
              Identified Hotspot Clusters
            </h3>

            <div className="space-y-2 text-xs">
              {!summary?.top_hotspots || summary.top_hotspots.length === 0 ? (
                <div className="text-slate-500 text-xs py-4 text-center">
                  No clusters identified yet.
                </div>
              ) : (
                summary.top_hotspots.map((h, i) => (
                  <div
                    key={h.landmark + i}
                    className="p-2.5 rounded-xl bg-slate-950/60 border border-slate-800 flex items-center justify-between"
                  >
                    <div>
                      <div className="font-semibold text-slate-200">
                        {h.landmark}
                      </div>
                      <div className="text-[10px] text-slate-500">
                        {h.ward_id || "Unassigned"} • {h.count} mentions
                      </div>
                    </div>
                    <div className="text-right">
                      <span
                        className={`text-xs font-mono font-bold ${
                          h.avg_urgency >= 0.7
                            ? "text-red-400"
                            : h.avg_urgency >= 0.4
                            ? "text-amber-400"
                            : "text-blue-400"
                        }`}
                      >
                        {(h.avg_urgency * 100).toFixed(0)}%
                      </span>
                      <span className="block text-[9px] text-slate-500 uppercase">Avg Urgency</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Classification Breakdown */}
          <div className="bg-slate-900/40 border border-slate-800/80 rounded-2xl p-4">
            <h3 className="text-xs font-bold text-white uppercase tracking-wider mb-3 flex items-center gap-1.5">
              <Layers className="w-4 h-4 text-indigo-400" />
              Category Distribution
            </h3>

            <div className="space-y-3 text-xs">
              {[
                { key: "evacuation_needed", label: "Evacuation Needed", color: "bg-red-500" },
                { key: "urgent", label: "Urgent Distress", color: "bg-amber-500" },
                { key: "waterlogging", label: "Waterlogging Reports", color: "bg-blue-500" },
                { key: "noise", label: "General Noise", color: "bg-slate-600" },
              ].map((item) => {
                const count = summary?.classification_distribution?.[item.key] || 0;
                const total = summary?.total_signals_24h || 1;
                const pct = Math.round((count / (total || 1)) * 100);

                return (
                  <div key={item.key} className="space-y-1">
                    <div className="flex justify-between text-[11px]">
                      <span className="text-slate-400">{item.label}</span>
                      <span className="text-white font-mono">{count} ({pct}%)</span>
                    </div>
                    <div className="h-1.5 w-full bg-slate-950 rounded-full overflow-hidden">
                      <div
                        className={`h-full ${item.color}`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* Manual Ingest Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-lg shadow-2xl p-6 text-slate-200">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3 mb-4">
              <h3 className="font-bold text-sm text-white flex items-center gap-2">
                <Send className="w-4 h-4 text-indigo-400" />
                Ingest & Classify Social Post
              </h3>
              <button
                onClick={() => setIsModalOpen(false)}
                className="p-1 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleManualIngest} className="space-y-4 text-xs">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-400 mb-1">Source Platform</label>
                  <select
                    value={source}
                    onChange={(e) => setSource(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white"
                  >
                    <option value="twitter">X / Twitter</option>
                    <option value="telegram">Telegram Channel</option>
                    <option value="helpline_1916">BMC 1916 Helpline</option>
                    <option value="citizen_app">Citizen Mobile Feed</option>
                  </select>
                </div>

                <div>
                  <label className="block text-slate-400 mb-1">Author / Handle</label>
                  <input
                    type="text"
                    value={authorHandle}
                    onChange={(e) => setAuthorHandle(e.target.value)}
                    required
                    placeholder="@handle or Caller ID"
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white"
                  />
                </div>
              </div>

              <div>
                <label className="block text-slate-400 mb-1">Explicit Ward Override (Optional)</label>
                <select
                  value={manualWard}
                  onChange={(e) => setManualWard(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white"
                >
                  <option value="">Auto-Detect from Landmarks</option>
                  {wards.map((w) => (
                    <option key={w.ward_id} value={w.ward_id}>
                      {w.ward_id} - {w.ward_name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-slate-400 mb-1">Post / Message Text (English, Marathi, Hindi)</label>
                <textarea
                  rows={4}
                  value={contentText}
                  onChange={(e) => setContentText(e.target.value)}
                  required
                  placeholder="e.g. Hindmata cinema flooded, 3 feet water on road..."
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl p-3 text-white"
                />
                <span className="text-[10px] text-slate-500 mt-1 block">
                  * Engine C will automatically detect Marathi/Hindi Devanagari characters and extract known Mumbai flood landmarks.
                </span>
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
                  className="px-5 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold disabled:opacity-50 flex items-center gap-2 shadow-lg shadow-indigo-600/20"
                >
                  {isSubmitting && <div className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />}
                  Classify & Ingest
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
