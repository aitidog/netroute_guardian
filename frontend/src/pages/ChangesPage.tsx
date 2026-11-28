import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Clock,
  ExternalLink,
  Mail,
  Play,
  RefreshCw,
  Server,
  ShieldAlert,
  Trash2,
} from 'lucide-react';
import { api } from '../api/client';
import { StatusBadge } from '../components/StatusBadge';
import type { ChangeRequest, SchedulerStatus } from '../types';

function formatRelativeCountdown(iso: string): string {
  const diffMs = new Date(iso).getTime() - Date.now();
  const absMin = Math.round(Math.abs(diffMs) / 60000);
  if (diffMs <= 0) {
    return absMin === 0 ? 'Due now' : `${absMin}m ago (due)`;
  }
  if (absMin < 60) return `in ${absMin}m`;
  const hrs = Math.floor(absMin / 60);
  const rem = absMin % 60;
  return `in ${hrs}h ${rem}m`;
}

export const ChangesPage: React.FC = () => {
  const [changes, setChanges] = useState<ChangeRequest[]>([]);
  const [scheduler, setScheduler] = useState<SchedulerStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [banner, setBanner] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ChangeRequest | null>(null);

  const loadData = async () => {
    try {
      const [chgList, sched] = await Promise.all([api.listChanges(), api.getSchedulerStatus()]);
      setChanges(chgList);
      setScheduler(sched);
    } catch (err) {
      setBanner({ type: 'err', text: (err as Error).message });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, []);

  const handleSyncAndDispatch = async () => {
    setBusyAction('sync');
    setBanner(null);
    try {
      const res = await api.dispatchSchedulerNow();
      setBanner({
        type: 'ok',
        text: `Synced ${res.synced_count} change(s) from ServiceNow and dispatched ${res.dispatched_change_ids.length} due T-1h pre-capture(s).`,
      });
      await loadData();
    } catch (err) {
      setBanner({ type: 'err', text: (err as Error).message });
    } finally {
      setBusyAction(null);
    }
  };

  const handleQuickPre = async (id: number, chgNumber: string) => {
    setBusyAction(`pre-${id}`);
    setBanner(null);
    try {
      const res = await api.triggerPreCapture(id);
      setBanner({
        type: 'ok',
        text: `Pre-change capture completed for ${chgNumber} (${res.succeeded_devices.join(', ')}).`,
      });
      await loadData();
    } catch (err) {
      setBanner({ type: 'err', text: (err as Error).message });
    } finally {
      setBusyAction(null);
    }
  };

  const handleQuickPost = async (id: number, chgNumber: string) => {
    setBusyAction(`post-${id}`);
    setBanner(null);
    try {
      const res = await api.triggerPostCapture(id);
      setBanner({
        type: 'ok',
        text: `Post-change comparison completed for ${chgNumber} (${res.succeeded_devices.join(', ')}). Email status: ${res.email_status}.`,
      });
      await loadData();
    } catch (err) {
      setBanner({ type: 'err', text: (err as Error).message });
    } finally {
      setBusyAction(null);
    }
  };

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return;
    const target = deleteTarget;
    setBusyAction(`delete-${target.id}`);
    setBanner(null);
    try {
      await api.deleteChange(target.id);
      setDeleteTarget(null);
      setBanner({
        type: 'ok',
        text: `Deleted completed change request ${target.chg_number} and its associated comparison reports.`,
      });
      await loadData();
    } catch (err) {
      setBanner({ type: 'err', text: (err as Error).message });
    } finally {
      setBusyAction(null);
    }
  };

  const completedCount = changes.filter((c) => c.status === 'completed').length;
  const preCapturedCount = changes.filter((c) => c.status === 'pre_captured').length;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">ServiceNow Change Tracking</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Automatically captures routing tables 1 hour before scheduled network changes, compares post-change state, and emails engineers.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={busyAction !== null}
            onClick={handleSyncAndDispatch}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold bg-indigo-600 hover:bg-indigo-700 text-white disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${busyAction === 'sync' ? 'animate-spin' : ''}`} />
            Sync ServiceNow &amp; Run Due T-1h Jobs
          </button>
        </div>
      </div>

      {banner && (
        <div
          className={`px-4 py-3 rounded-lg text-sm border ${
            banner.type === 'ok'
              ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
              : 'bg-red-50 text-red-800 border-red-200'
          }`}
        >
          {banner.text}
        </div>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
          <div className="text-xs font-semibold text-slate-500 uppercase">Tracked Changes</div>
          <div className="text-2xl font-bold text-slate-900 mt-1">{changes.length}</div>
          <div className="text-xs text-slate-500 mt-1">
            Mode: <span className="font-mono uppercase">{scheduler?.servicenow_mode ?? 'mock'}</span>
          </div>
        </div>
        <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
          <div className="text-xs font-semibold text-slate-500 uppercase">Ready for Post-Change</div>
          <div className="text-2xl font-bold text-blue-600 mt-1">{preCapturedCount}</div>
          <div className="text-xs text-slate-500 mt-1">Pre-change baseline captured</div>
        </div>
        <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
          <div className="text-xs font-semibold text-slate-500 uppercase">Completed Comparisons</div>
          <div className="text-2xl font-bold text-emerald-600 mt-1 flex items-center gap-1.5">
            {completedCount}
            {completedCount > 0 && <ShieldAlert className="w-5 h-5 text-emerald-500" />}
          </div>
          <div className="text-xs text-slate-500 mt-1">Reports analyzed &amp; emailed</div>
        </div>
        <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
          <div className="text-xs font-semibold text-slate-500 uppercase">Background Scheduler</div>
          <div className="text-lg font-bold text-emerald-600 mt-1">
            {scheduler?.running ? 'Active' : 'Standby'}
          </div>
          <div className="text-xs text-slate-500 mt-1">
            Pending T-1h jobs: {scheduler?.pending_pre_captures ?? 0}
          </div>
        </div>
      </div>

      {/* Changes Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-200 flex items-center justify-between">
          <h2 className="font-semibold text-slate-800">Scheduled Network Change Requests</h2>
          <Link to="/simulator" className="text-xs font-medium text-indigo-600 hover:underline">
            + Create simulated ServiceNow change
          </Link>
        </div>

        {loading ? (
          <div className="p-8 text-center text-sm text-slate-500">Loading change requests...</div>
        ) : changes.length === 0 ? (
          <div className="p-8 text-center text-sm text-slate-500">
            No change requests synced yet. Click &ldquo;Sync ServiceNow&rdquo; or create one in the Simulator.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-slate-50 text-xs uppercase text-slate-500">
                <tr>
                  <th className="px-5 py-3 text-left font-semibold">Change / Engineer</th>
                  <th className="px-4 py-3 text-left font-semibold">Associated CIs</th>
                  <th className="px-4 py-3 text-left font-semibold">Schedule (T-1h Capture)</th>
                  <th className="px-4 py-3 text-left font-semibold">Workflow Status</th>
                  <th className="px-5 py-3 text-right font-semibold">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200">
                {changes.map((chg) => (
                  <tr key={chg.id} className="hover:bg-slate-50">
                    <td className="px-5 py-3.5">
                      <Link
                        to={`/changes/${chg.id}`}
                        className="font-mono font-bold text-indigo-700 hover:underline"
                      >
                        {chg.chg_number}
                      </Link>
                      <div className="font-medium text-slate-900 mt-0.5">{chg.title}</div>
                      <div className="text-xs text-slate-500 flex items-center gap-1 mt-0.5">
                        <Mail className="w-3 h-3" />
                        {chg.engineer_name} ({chg.engineer_email})
                      </div>
                    </td>
                    <td className="px-4 py-3.5">
                      <div className="flex flex-wrap gap-1.5">
                        {chg.devices.map((dev) => (
                          <span
                            key={dev.id}
                            className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-slate-100 border border-slate-200 text-xs font-mono text-slate-700"
                          >
                            <Server className="w-3 h-3 text-slate-400" />
                            {dev.hostname}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="px-4 py-3.5 whitespace-nowrap text-xs">
                      <div className="text-slate-800 font-medium">
                        Start: {new Date(chg.scheduled_start).toLocaleString()}
                      </div>
                      <div className="text-slate-500 flex items-center gap-1 mt-1">
                        <Clock className="w-3 h-3" />
                        T-1h Capture: {formatRelativeCountdown(chg.capture_scheduled_at)}
                      </div>
                    </td>
                    <td className="px-4 py-3.5 whitespace-nowrap">
                      <StatusBadge status={chg.status} />
                      <div className="text-[11px] text-slate-500 mt-1">
                        Pre: {chg.pre_snapshot_count} · Post: {chg.post_snapshot_count} · Reports:{' '}
                        {chg.report_count}
                      </div>
                    </td>
                    <td className="px-5 py-3.5 whitespace-nowrap text-right space-x-2">
                      {chg.status === 'synced' && (
                        <button
                          type="button"
                          disabled={busyAction !== null}
                          onClick={() => handleQuickPre(chg.id, chg.chg_number)}
                          className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-white disabled:opacity-50"
                        >
                          <Play className="w-3 h-3" />
                          Pre-Capture
                        </button>
                      )}
                      {(chg.status === 'pre_captured' || chg.status === 'completed') && (
                        <button
                          type="button"
                          disabled={busyAction !== null}
                          onClick={() => handleQuickPost(chg.id, chg.chg_number)}
                          className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-700 text-white disabled:opacity-50"
                        >
                          <Play className="w-3 h-3" />
                          Post-Capture &amp; Compare
                        </button>
                      )}
                      <Link
                        to={`/changes/${chg.id}`}
                        className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-semibold border border-slate-300 text-slate-700 hover:bg-slate-100"
                      >
                        Details
                        <ExternalLink className="w-3 h-3" />
                      </Link>
                      {chg.status === 'completed' && (
                        <button
                          type="button"
                          aria-label={`Delete ${chg.chg_number}`}
                          disabled={busyAction !== null}
                          onClick={() => setDeleteTarget(chg)}
                          className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-semibold border border-red-200 text-red-700 hover:bg-red-50 disabled:opacity-50"
                        >
                          <Trash2 className="w-3 h-3" />
                          Delete
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Delete Confirmation Modal */}
      {deleteTarget && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-change-dialog-title"
          className="fixed inset-0 z-50 bg-slate-900/60 flex items-center justify-center p-4"
        >
          <div className="bg-white rounded-xl shadow-xl max-w-md w-full border border-slate-200 overflow-hidden">
            <div className="px-5 py-4 border-b border-slate-200 bg-red-50/60">
              <h3 id="delete-change-dialog-title" className="text-base font-bold text-slate-900">
                Delete Completed Change Request?
              </h3>
              <p className="text-xs text-slate-600 mt-0.5 font-mono">
                {deleteTarget.chg_number} · {deleteTarget.title}
              </p>
            </div>
            <div className="px-5 py-4 text-sm text-slate-600 space-y-2">
              <p>
                This will permanently remove{' '}
                <strong className="font-mono text-slate-900">{deleteTarget.chg_number}</strong> along
                with its {deleteTarget.pre_snapshot_count + deleteTarget.post_snapshot_count} route
                snapshot(s) and {deleteTarget.report_count} comparison report(s).
              </p>
              <p className="text-xs text-slate-500">This action cannot be undone.</p>
            </div>
            <div className="px-5 py-3.5 border-t border-slate-200 bg-slate-50 flex items-center justify-end gap-2">
              <button
                type="button"
                disabled={busyAction !== null}
                onClick={() => setDeleteTarget(null)}
                className="px-3.5 py-1.5 rounded-lg text-xs font-semibold border border-slate-300 text-slate-700 hover:bg-white disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={busyAction !== null}
                onClick={handleConfirmDelete}
                className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-red-600 hover:bg-red-700 text-white disabled:opacity-50"
              >
                <Trash2 className="w-3.5 h-3.5" />
                {busyAction === `delete-${deleteTarget.id}` ? 'Deleting...' : 'Confirm Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
