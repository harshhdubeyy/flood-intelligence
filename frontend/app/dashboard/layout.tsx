"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  ShieldAlert,
  MapPin,
  Camera,
  Radio,
  Navigation,
  Activity,
  Waves,
  MessageSquare,
} from "lucide-react";


interface DashboardLayoutProps {
  children: React.ReactNode;
}

export default function DashboardLayout({ children }: DashboardLayoutProps) {
  const pathname = usePathname();

  const navItems = [
    { label: "GIS Command Map", href: "/dashboard", icon: MapPin },
    { label: "Citizen Reports", href: "/dashboard/reports", icon: Camera },
    { label: "CAP Alert Dispatch", href: "/dashboard/alerts", icon: Radio },
    { label: "Social Intelligence", href: "/dashboard/social", icon: MessageSquare },
    { label: "Responder Routes", href: "/dashboard/responders", icon: Navigation },
  ];

  return (
    <div className="flex h-screen w-screen bg-slate-950 text-slate-100 overflow-hidden font-sans">
      {/* Sidebar */}
      <aside className="w-64 border-r border-slate-800/80 bg-slate-900/60 backdrop-blur-xl flex flex-col justify-between flex-shrink-0 z-30">
        <div>
          {/* Platform Identity */}
          <div className="h-16 px-5 flex items-center gap-3 border-b border-slate-800/80">
            <div className="p-2 rounded-lg bg-blue-500/10 border border-blue-500/20 text-blue-400">
              <Waves className="w-5 h-5" />
            </div>
            <div>
              <div className="font-bold text-sm tracking-tight text-white flex items-center gap-1.5">
                Flood Intelligence
              </div>
              <div className="text-[10px] text-slate-400 font-mono">
                MUMBAI BMC / NDMA
              </div>
            </div>
          </div>

          {/* Navigation Links */}
          <nav className="p-3 space-y-1.5 mt-2">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`flex items-center gap-3 px-3.5 py-2.5 rounded-lg text-xs font-medium transition-all ${
                    isActive
                      ? "bg-blue-600/20 text-blue-400 border border-blue-500/30 shadow-sm"
                      : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50"
                  }`}
                >
                  <Icon className={`w-4 h-4 ${isActive ? "text-blue-400" : "text-slate-400"}`} />
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </div>

        {/* Live Operational Heartbeat */}
        <div className="p-4 border-t border-slate-800/80 bg-slate-900/40">
          <div className="flex items-center justify-between text-[11px] mb-2">
            <span className="flex items-center gap-1.5 text-slate-400">
              <Activity className="w-3.5 h-3.5 text-emerald-400 animate-pulse" />
              Engine A (ML)
            </span>
            <span className="font-mono text-emerald-400 font-semibold">ONLINE</span>
          </div>
          <div className="text-[10px] text-slate-500 leading-tight">
            15-min XGBoost cycle active. Monitored wards: 24
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Top Header Bar */}
        <header className="h-16 border-b border-slate-800/80 bg-slate-900/40 backdrop-blur-md px-6 flex items-center justify-between flex-shrink-0 z-20">
          <div className="flex items-center gap-3">
            <span className="relative flex h-2.5 w-2.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-amber-500"></span>
            </span>
            <span className="text-xs font-medium text-slate-300">
              Monsoon Watch Mode: <strong className="text-amber-400">Moderate Surge Risk</strong>
            </span>
          </div>

          <div className="flex items-center gap-4 text-xs">
            <div className="px-2.5 py-1 rounded-full bg-slate-800 border border-slate-700 font-mono text-[11px] text-slate-300">
              High Tide: 4.1m @ 14:45 IST
            </div>
            <div className="flex items-center gap-2 px-3 py-1 rounded-md bg-red-500/10 border border-red-500/30 text-red-400 font-medium">
              <ShieldAlert className="w-3.5 h-3.5" />
              Emergency Ops: 112 / 1916
            </div>
          </div>
        </header>

        {/* Dynamic Route Content */}
        <main className="flex-1 relative overflow-hidden">{children}</main>
      </div>
    </div>
  );
}
