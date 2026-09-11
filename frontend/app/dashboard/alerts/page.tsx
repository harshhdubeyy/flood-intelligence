"use client";

import React, { useState, useEffect } from "react";
import {
  Bell,
  Send,
  Radio,
  FileCode,
  Globe2,
  CheckCircle2,
  AlertTriangle,
  Flame,
  ShieldAlert,
  Users,
  Clock,
  Plus,
  X,
  ExternalLink,
} from "lucide-react";
import {
  fetchAlerts,
  publishAlert,
  fetchWardsList,
  AlertItem,
  WardSummary,
} from "../../lib/api";

export default function AlertsDashboard() {
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [wards, setWards] = useState<WardSummary[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [isModalOpen, setIsModalOpen] = useState<boolean>(false);
  const [selectedAlertForCap, setSelectedAlertForCap] = useState<AlertItem | null>(null);

  // Form State
  const [targetWard, setTargetWard] = useState<string>("MH-BMC-GN");
  const [severity, setSeverity] = useState<"watch" | "warning" | "critical">("warning");
  const [channel, setChannel] = useState<"cap" | "whatsapp" | "push" | "all">("all");
  const [headline, setHeadline] = useState<string>("High Tide Storm Surge & Backwater Warning");
  const [instruction, setInstruction] = useState<string>("Evacuate ground floor basements and avoid coastal promenades.");
  const [isPublishing, setIsPublishing] = useState<boolean>(false);

  const loadData = async () => {
    try {
      const [alertList, wardList] = await Promise.all([
        fetchAlerts(),
        fetchWardsList(),
      ]);
      setAlerts(alertList);
      setWards(wardList);
    } catch (e) {
      console.error("Failed to load alerts:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 20000);
    return () => clearInterval(interval);
  }, []);

  const handlePublish = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsPublishing(true);
    try {
      await publishAlert({
        ward_id: targetWard,
        severity,
        channel,
        headline,
        instruction,
      });
      setIsModalOpen(false);
      await loadData();
    } catch (err) {
      console.error("Alert dispatch failed:", err);
      alert("Alert dispatch failed. Check backend connectivity.");
    } finally {
      setIsPublishing(false);
    }
  };

  const severityColor = (sev: string) => {
    switch (sev.toLowerCase()) {
      case "critical":
        return "bg-red-500/10 text-red-400 border-red-500/30";
      case "warning":
        return "bg-amber-500/10 text-amber-400 border-amber-500/30";
      default:
        return "bg-blue-500/10 text-blue-400 border-blue-500/30";
    }
  };

  return (
    <div className="h-full w-full bg-slate-950 text-slate-100 flex flex-col overflow-hidden p-6 gap-6">
      {/* Top Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
            <Radio className="w-5 h-5 text-amber-400 animate-pulse" />
            Emergency Warning Dispatch & OASIS CAP Syndication
          </h1>
          <p className="text-xs text-slate-400 mt-0.5">
            Disseminate multi-channel alerts (OASIS CAP v1.2 XML, WhatsApp Sandbox, Web Push) in English, Marathi, & Hindi.
          </p>
        </div>

        <button
          onClick={() => setIsModalOpen(true)}
          className="px-4 py-2 rounded-xl bg-amber-600 hover:bg-amber-500 text-white text-xs font-semibold flex items-center gap-2 shadow-lg shadow-amber-600/20 transition-all"
        >
          <Plus className="w-4 h-4" />
          Broadcast Emergency Alert
        </button>
      </div>

      {/* Protocol Compliance & Protocol Stats */}
      <div className="grid grid-cols-4 gap-4">
        <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl p-4">
          <div className="text-[11px] text-slate-400 uppercase tracking-wider font-semibold">
            Protocol Standard
          </div>
          <div className="text-sm font-bold text-white mt-1 flex items-center gap-1.5">
            <FileCode className="w-4 h-4 text-emerald-400" />
            OASIS CAP v1.2 / ITU-T X.1303
          </div>
          <div className="text-[10px] text-slate-500 mt-0.5">NDMA SACHET Compliant</div>
        </div>

        <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl p-4">
          <div className="text-[11px] text-slate-400 uppercase tracking-wider font-semibold">
            Active Bulletins
          </div>
          <div className="text-2xl font-bold font-mono text-amber-400 mt-1">
            {alerts.length}
          </div>
        </div>

        <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl p-4">
          <div className="text-[11px] text-slate-400 uppercase tracking-wider font-semibold">
            Estimated Citizens Reached
          </div>
          <div className="text-2xl font-bold font-mono text-emerald-400 mt-1 flex items-center gap-1.5">
            <Users className="w-5 h-5 text-emerald-400" />
            {alerts.reduce((acc, a) => acc + (a.recipients_count || 0), 0).toLocaleString()}
          </div>
        </div>

        <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl p-4">
          <div className="text-[11px] text-slate-400 uppercase tracking-wider font-semibold">
            Supported Languages
          </div>
          <div className="text-sm font-bold text-white mt-1 flex items-center gap-1.5">
            <Globe2 className="w-4 h-4 text-blue-400" />
            EN, MR (मराठी), HI (हिंदी)
          </div>
          <div className="text-[10px] text-slate-500 mt-0.5">Auto-translated localization</div>
        </div>
      </div>

      {/* Bulletins Feed */}
      <div className="flex-1 bg-slate-900/40 border border-slate-800/80 rounded-2xl overflow-hidden flex flex-col">
        <div className="p-4 border-b border-slate-800/80 flex items-center justify-between text-xs text-slate-400 font-semibold uppercase tracking-wider">
          <span>Dispatched Bulletins Stream ({alerts.length})</span>
          <span>Target Distribution: Twilio Sandbox + VAPID Web Push + CAP</span>
        </div>

        <div className="flex-1 overflow-y-auto divide-y divide-slate-800/60">
          {alerts.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-slate-500 text-xs py-16">
              <ShieldAlert className="w-8 h-8 mb-2 opacity-40" />
              No emergency alerts currently active. All wards operating normally.
            </div>
          ) : (
            alerts.map((alert) => (
              <div
                key={alert.alert_id}
                className="p-4 hover:bg-slate-800/30 transition-colors flex items-start justify-between gap-4 text-xs"
              >
                <div className="flex items-start gap-3.5 min-w-0">
                  <div
                    className={`w-10 h-10 rounded-xl flex items-center justify-center font-bold text-xs uppercase border flex-shrink-0 ${severityColor(
                      alert.severity
                    )}`}
                  >
                    <AlertTriangle className="w-5 h-5" />
                  </div>

                  <div className="min-w-0 space-y-1.5">
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-white text-sm">
                        {alert.headline}
                      </span>
                      <span
                        className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase border ${severityColor(
                          alert.severity
                        )}`}
                      >
                        {alert.severity}
                      </span>
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-slate-800 text-slate-400 border border-slate-700">
                        {alert.channel.toUpperCase()}
                      </span>
                    </div>

                    <p className="text-slate-300 text-xs">
                      {alert.message_text}
                    </p>

                    {/* Trilingual pills preview */}
                    {alert.language_translations && (
                      <div className="grid grid-cols-3 gap-2 mt-2 pt-2 border-t border-slate-800/60 text-[11px]">
                        <div className="bg-slate-950/60 p-2 rounded-lg border border-slate-800">
                          <span className="font-bold text-slate-400 uppercase text-[9px] block mb-0.5">EN</span>
                          <span className="text-slate-200 line-clamp-2">{alert.language_translations.en?.instruction}</span>
                        </div>
                        <div className="bg-slate-950/60 p-2 rounded-lg border border-slate-800">
                          <span className="font-bold text-slate-400 uppercase text-[9px] block mb-0.5">MR (मराठी)</span>
                          <span className="text-slate-200 line-clamp-2">{alert.language_translations.mr?.instruction}</span>
                        </div>
                        <div className="bg-slate-950/60 p-2 rounded-lg border border-slate-800">
                          <span className="font-bold text-slate-400 uppercase text-[9px] block mb-0.5">HI (हिंदी)</span>
                          <span className="text-slate-200 line-clamp-2">{alert.language_translations.hi?.instruction}</span>
                        </div>
                      </div>
                    )}

                    <div className="flex items-center gap-4 text-[11px] text-slate-500 font-mono mt-1">
                      <span>ID: {alert.alert_id}</span>
                      <span>Ward: {alert.ward_id || "All"}</span>
                      <span className="flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {new Date(alert.dispatched_at).toLocaleTimeString()} IST
                      </span>
                      <span className="text-emerald-400">
                        Reach: ~{alert.recipients_count} citizens
                      </span>
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2 flex-shrink-0">
                  <button
                    onClick={() => setSelectedAlertForCap(alert)}
                    className="px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 flex items-center gap-1.5"
                  >
                    <FileCode className="w-3.5 h-3.5 text-blue-400" />
                    CAP XML
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Broadcast Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-lg shadow-2xl p-6 text-slate-200 animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3 mb-4">
              <h3 className="font-bold text-sm text-white flex items-center gap-2">
                <Send className="w-4 h-4 text-amber-400" />
                Draft & Broadcast Emergency Flood Warning
              </h3>
              <button
                onClick={() => setIsModalOpen(false)}
                className="p-1 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handlePublish} className="space-y-4 text-xs">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-400 mb-1">Target Ward</label>
                  <select
                    value={targetWard}
                    onChange={(e) => setTargetWard(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white"
                  >
                    {wards.map((w) => (
                      <option key={w.ward_id} value={w.ward_id}>
                        {w.ward_id} - {w.ward_name}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-slate-400 mb-1">Severity Tier</label>
                  <select
                    value={severity}
                    onChange={(e) => setSeverity(e.target.value as any)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white"
                  >
                    <option value="watch">Watch (Moderate)</option>
                    <option value="warning">Warning (Severe)</option>
                    <option value="critical">Critical (Extreme)</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-slate-400 mb-1">Distribution Channels</label>
                <select
                  value={channel}
                  onChange={(e) => setChannel(e.target.value as any)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white"
                >
                  <option value="all">Omnichannel (CAP v1.2 + WhatsApp + Web Push)</option>
                  <option value="cap">OASIS CAP v1.2 XML Syndication Only</option>
                  <option value="whatsapp">WhatsApp Sandbox Broadcast Only</option>
                  <option value="push">Browser Web Push (VAPID) Only</option>
                </select>
              </div>

              <div>
                <label className="block text-slate-400 mb-1">Bulletin Headline</label>
                <input
                  type="text"
                  value={headline}
                  onChange={(e) => setHeadline(e.target.value)}
                  required
                  placeholder="e.g. Mithi River Level Breaching Danger Mark"
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white font-medium"
                />
              </div>

              <div>
                <label className="block text-slate-400 mb-1">Recommended Citizen Action (English)</label>
                <textarea
                  rows={2}
                  value={instruction}
                  onChange={(e) => setInstruction(e.target.value)}
                  placeholder="e.g. Evacuate low-lying structures and move to designated BMC relief camps."
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl p-3 text-white"
                />
                <span className="text-[10px] text-slate-500 mt-1 block">
                  * Marathi and Hindi localized equivalents will be automatically generated and appended to the CAP payload.
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
                  disabled={isPublishing}
                  className="px-5 py-2 rounded-xl bg-amber-600 hover:bg-amber-500 text-white font-semibold disabled:opacity-50 flex items-center gap-2 shadow-lg shadow-amber-600/20"
                >
                  {isPublishing && <div className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />}
                  Confirm & Broadcast
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* CAP XML Viewer Modal */}
      {selectedAlertForCap && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-2xl max-h-[85vh] shadow-2xl flex flex-col p-6 text-slate-200 animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3 mb-3">
              <div>
                <h3 className="font-bold text-sm text-white flex items-center gap-2">
                  <FileCode className="w-4 h-4 text-emerald-400" />
                  OASIS CAP v1.2 Document: {selectedAlertForCap.alert_id}
                </h3>
                <span className="text-[11px] text-slate-400">
                  Standard NDMA / SACHET XML payload representation
                </span>
              </div>
              <button
                onClick={() => setSelectedAlertForCap(null)}
                className="p-1 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto bg-slate-950 p-4 rounded-xl border border-slate-800/80 font-mono text-[11px] text-emerald-400/90 whitespace-pre-wrap selection:bg-emerald-900 selection:text-white">
              {selectedAlertForCap.cap_xml || "<!-- No CAP XML document associated -->"}
            </div>

            <div className="pt-3 border-t border-slate-800 flex justify-between items-center text-xs">
              <span className="text-slate-500 font-mono text-[11px]">
                Target: {selectedAlertForCap.ward_id} | Severity: {selectedAlertForCap.severity}
              </span>
              <button
                onClick={() => setSelectedAlertForCap(null)}
                className="px-4 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-white font-medium"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
