import React, { useState } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import {
  Activity,
  FileDiff,
  GitBranch,
  Mail,
  Network,
  PanelLeftClose,
  PanelLeftOpen,
  Server,
  ShieldCheck,
} from 'lucide-react';

const SIDEBAR_STORAGE_KEY = 'netroute.sidebar.collapsed';

const NAV_ITEMS = [
  { to: '/', label: 'Change Tracking', icon: Activity, subtitle: 'Feature 1 · ServiceNow' },
  { to: '/adhoc-compare', label: 'Ad-hoc CSV Compare', icon: FileDiff, subtitle: 'Feature 1 · Upload' },
  { to: '/route-summary', label: 'Route Summary', icon: GitBranch, subtitle: 'Feature 2 · Collapse' },
  { to: '/important-routes', label: 'Important Routes', icon: ShieldCheck, subtitle: 'Critical Watchlist' },
  { to: '/simulator', label: 'ServiceNow & Devices', icon: Server, subtitle: 'Sandbox & Scheduler' },
];

function readInitialCollapsed(): boolean {
  try {
    return typeof window !== 'undefined' && window.localStorage.getItem(SIDEBAR_STORAGE_KEY) === 'true';
  } catch {
    return false;
  }
}

function resolveMailpitUrl(): { href: string; label: string } {
  const configured = import.meta.env.VITE_MAILPIT_URL as string | undefined;
  if (configured && configured.trim()) {
    const trimmed = configured.trim();
    return {
      href: trimmed,
      label: trimmed.includes(':8025') ? 'Open Mailpit Inbox (:8025)' : 'Open Mailpit Inbox',
    };
  }
  if (
    typeof window !== 'undefined' &&
    window.location.hostname !== 'localhost' &&
    window.location.hostname !== '127.0.0.1'
  ) {
    return { href: '/mailpit/', label: 'Open Mailpit Inbox' };
  }
  return { href: 'http://localhost:8025', label: 'Open Mailpit Inbox (:8025)' };
}

export const Layout: React.FC = () => {
  const [collapsed, setCollapsed] = useState<boolean>(readInitialCollapsed);
  const mailpit = resolveMailpitUrl();

  const handleToggleSidebar = () => {
    setCollapsed((prev) => {
      const next = !prev;
      try {
        window.localStorage.setItem(SIDEBAR_STORAGE_KEY, String(next));
      } catch {
        // Ignore storage write errors in restricted browser contexts.
      }
      return next;
    });
  };

  return (
    <div className="h-screen overflow-hidden flex bg-slate-50">
      {/* Sidebar (pinned to viewport height; collapsible to icon-only rail) */}
      <aside
        className={`${
          collapsed ? 'w-16' : 'w-64'
        } h-full bg-slate-900 text-slate-100 flex flex-col shrink-0 overflow-hidden transition-all duration-200`}
      >
        <div
          className={`shrink-0 border-b border-slate-800 flex ${
            collapsed
              ? 'flex-col items-center gap-2.5 px-2 py-4'
              : 'items-center justify-between px-4 py-5'
          }`}
        >
          <div className="flex items-center gap-3 min-w-0">
            <div
              className="w-9 h-9 rounded-lg bg-indigo-600 flex items-center justify-center shadow shrink-0"
              title="NetRoute Guardian"
            >
              <Network className="w-5 h-5 text-white" />
            </div>
            {!collapsed && (
              <div className="min-w-0">
                <div className="font-bold text-sm tracking-tight truncate">NetRoute Guardian</div>
                <div className="text-[11px] text-slate-400 truncate">Routing Table Intelligence</div>
              </div>
            )}
          </div>
          <button
            type="button"
            onClick={handleToggleSidebar}
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            aria-expanded={!collapsed}
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors shrink-0"
          >
            {collapsed ? (
              <PanelLeftOpen className="w-4 h-4" />
            ) : (
              <PanelLeftClose className="w-4 h-4" />
            )}
          </button>
        </div>

        <nav className={`flex-1 overflow-y-auto py-4 space-y-1 ${collapsed ? 'px-2' : 'px-3'}`}>
          {NAV_ITEMS.map(({ to, label, icon: Icon, subtitle }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              aria-label={label}
              title={collapsed ? `${label} · ${subtitle}` : undefined}
              className={({ isActive }) =>
                `flex items-center rounded-lg transition-colors ${
                  collapsed ? 'justify-center px-0 py-2.5' : 'gap-3 px-3 py-2.5'
                } ${
                  isActive
                    ? 'bg-indigo-600 text-white shadow-sm'
                    : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                }`
              }
            >
              <Icon className="w-4 h-4 shrink-0" />
              {!collapsed && (
                <div className="leading-tight min-w-0">
                  <div className="text-sm font-medium truncate">{label}</div>
                  <div className="text-[10px] opacity-75 truncate">{subtitle}</div>
                </div>
              )}
            </NavLink>
          ))}
        </nav>

        <div className={`shrink-0 border-t border-slate-800 ${collapsed ? 'p-2' : 'p-4'}`}>
          <a
            href={mailpit.href}
            target="_blank"
            rel="noreferrer"
            aria-label={mailpit.label}
            title={collapsed ? mailpit.label : undefined}
            className={`flex items-center justify-center w-full rounded-lg text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 ${
              collapsed ? 'p-2.5' : 'gap-2 px-3 py-2'
            }`}
          >
            <Mail className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
            {!collapsed && <span className="truncate">{mailpit.label}</span>}
          </a>
        </div>
      </aside>

      {/* Main Content (scrolls independently within viewport) */}
      <main className="flex-1 min-w-0 h-full overflow-y-auto">
        <div className="max-w-7xl mx-auto px-6 py-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
};
