import React from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import {
  Activity,
  FileDiff,
  GitBranch,
  Mail,
  Network,
  Server,
  ShieldCheck,
} from 'lucide-react';

const NAV_ITEMS = [
  { to: '/', label: 'Change Tracking', icon: Activity, subtitle: 'Feature 1 · ServiceNow' },
  { to: '/adhoc-compare', label: 'Ad-hoc CSV Compare', icon: FileDiff, subtitle: 'Feature 1 · Upload' },
  { to: '/route-summary', label: 'Route Summary', icon: GitBranch, subtitle: 'Feature 2 · Collapse' },
  { to: '/important-routes', label: 'Important Routes', icon: ShieldCheck, subtitle: 'Critical Watchlist' },
  { to: '/simulator', label: 'ServiceNow & Devices', icon: Server, subtitle: 'Sandbox & Scheduler' },
];

export const Layout: React.FC = () => {
  return (
    <div className="h-screen overflow-hidden flex bg-slate-50">
      {/* Sidebar (pinned to viewport height; independent of right-hand content scroll) */}
      <aside className="w-64 h-full bg-slate-900 text-slate-100 flex flex-col shrink-0 overflow-hidden">
        <div className="shrink-0 px-5 py-5 border-b border-slate-800 flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-indigo-600 flex items-center justify-center shadow">
            <Network className="w-5 h-5 text-white" />
          </div>
          <div>
            <div className="font-bold text-sm tracking-tight">NetRoute Guardian</div>
            <div className="text-[11px] text-slate-400">Routing Table Intelligence</div>
          </div>
        </div>

        <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-1">
          {NAV_ITEMS.map(({ to, label, icon: Icon, subtitle }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors ${
                  isActive
                    ? 'bg-indigo-600 text-white shadow-sm'
                    : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                }`
              }
            >
              <Icon className="w-4 h-4 shrink-0" />
              <div className="leading-tight">
                <div className="text-sm font-medium">{label}</div>
                <div className="text-[10px] opacity-75">{subtitle}</div>
              </div>
            </NavLink>
          ))}
        </nav>

        <div className="shrink-0 p-4 border-t border-slate-800">
          <a
            href="http://localhost:8025"
            target="_blank"
            rel="noreferrer"
            className="flex items-center justify-center gap-2 w-full px-3 py-2 rounded-lg text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700"
          >
            <Mail className="w-3.5 h-3.5 text-emerald-400" />
            Open Mailpit Inbox (:8025)
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
