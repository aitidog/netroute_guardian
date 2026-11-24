import React, { useEffect, useState } from 'react';
import { Pencil, Plus, Save, ShieldCheck, Trash2, X } from 'lucide-react';
import { api } from '../api/client';
import type { AppSettings, ImportantRoute } from '../types';

export const ImportantRoutesPage: React.FC = () => {
  const [routes, setRoutes] = useState<ImportantRoute[]>([]);
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [thresholdInput, setThresholdInput] = useState(20);

  const [newPrefix, setNewPrefix] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editPrefix, setEditPrefix] = useState('');
  const [editDesc, setEditDesc] = useState('');

  const [feedback, setFeedback] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);

  const load = async () => {
    try {
      const [list, cfg] = await Promise.all([api.listImportantRoutes(), api.getSettings()]);
      setRoutes(list);
      setSettings(cfg);
      setThresholdInput(cfg.large_prefix_threshold);
    } catch (err) {
      setFeedback({ type: 'err', text: (err as Error).message });
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setFeedback(null);
    try {
      await api.createImportantRoute({
        prefix: newPrefix.trim(),
        description: newDesc.trim(),
        enabled: true,
      });
      setNewPrefix('');
      setNewDesc('');
      setFeedback({ type: 'ok', text: 'Pre-specified critical route added.' });
      await load();
    } catch (err) {
      setFeedback({ type: 'err', text: (err as Error).message });
    }
  };

  const handleToggle = async (route: ImportantRoute) => {
    try {
      await api.updateImportantRoute(route.id, { enabled: !route.enabled });
      await load();
    } catch (err) {
      setFeedback({ type: 'err', text: (err as Error).message });
    }
  };

  const handleSaveEdit = async (id: number) => {
    setFeedback(null);
    try {
      await api.updateImportantRoute(id, { prefix: editPrefix.trim(), description: editDesc.trim() });
      setEditingId(null);
      setFeedback({ type: 'ok', text: 'Critical route updated.' });
      await load();
    } catch (err) {
      setFeedback({ type: 'err', text: (err as Error).message });
    }
  };

  const handleDelete = async (id: number) => {
    setFeedback(null);
    try {
      await api.deleteImportantRoute(id);
      setFeedback({ type: 'ok', text: 'Critical route deleted.' });
      await load();
    } catch (err) {
      setFeedback({ type: 'err', text: (err as Error).message });
    }
  };

  const handleSaveThreshold = async (e: React.FormEvent) => {
    e.preventDefault();
    setFeedback(null);
    try {
      const updated = await api.updateSettings({ large_prefix_threshold: thresholdInput });
      setSettings(updated);
      setFeedback({
        type: 'ok',
        text: `Large prefix alert threshold updated to <= /${updated.large_prefix_threshold}.`,
      });
    } catch (err) {
      setFeedback({ type: 'err', text: (err as Error).message });
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Important Routing Rules</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Manage pre-specified critical prefixes (exact CIDR match) and the broad subnet mask threshold emphasized in comparison reports.
        </p>
      </div>

      {feedback && (
        <div
          className={`px-4 py-3 rounded-lg text-sm border ${
            feedback.type === 'ok'
              ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
              : 'bg-red-50 text-red-800 border-red-200'
          }`}
        >
          {feedback.text}
        </div>
      )}

      {/* Rule 1: Large Prefix Threshold */}
      <form
        onSubmit={handleSaveThreshold}
        className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm flex flex-wrap items-center justify-between gap-4"
      >
        <div>
          <div className="text-sm font-bold text-slate-900">
            Rule 1: Broad Subnet Mask Threshold
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            Any subnet with prefix length less than or equal to <span className="font-mono font-semibold">/{settings?.large_prefix_threshold ?? 20}</span> that is removed or changed will be emphasized.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm font-mono text-slate-600">&lt;= /</span>
          <input
            type="number"
            min={1}
            max={32}
            value={thresholdInput}
            onChange={(e) => setThresholdInput(Number(e.target.value))}
            className="w-20 rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-mono"
          />
          <button
            type="submit"
            className="px-3.5 py-1.5 rounded-lg text-sm font-semibold bg-slate-900 hover:bg-slate-800 text-white"
          >
            Save Threshold
          </button>
        </div>
      </form>

      {/* Rule 2: Add Pre-Specified Route */}
      <form
        onSubmit={handleCreate}
        className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm grid grid-cols-1 md:grid-cols-12 gap-3 items-end"
      >
        <div className="md:col-span-4">
          <label className="block text-xs font-semibold text-slate-600 uppercase mb-1">
            CIDR Prefix (Exact Match)
          </label>
          <input
            type="text"
            required
            value={newPrefix}
            onChange={(e) => setNewPrefix(e.target.value)}
            placeholder="e.g. 10.198.0.0/16"
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm font-mono"
          />
        </div>
        <div className="md:col-span-6">
          <label className="block text-xs font-semibold text-slate-600 uppercase mb-1">
            Description
          </label>
          <input
            type="text"
            value={newDesc}
            onChange={(e) => setNewDesc(e.target.value)}
            placeholder="Business service or DC transit purpose"
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
        </div>
        <div className="md:col-span-2">
          <button
            type="submit"
            className="w-full inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold bg-indigo-600 hover:bg-indigo-700 text-white"
          >
            <Plus className="w-4 h-4" />
            Add Route
          </button>
        </div>
      </form>

      {/* Watchlist Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="px-5 py-3.5 border-b border-slate-200 flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-indigo-600" />
          <h2 className="font-semibold text-slate-800">
            Pre-Specified Important Routing Entries ({routes.length})
          </h2>
        </div>

        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-slate-500">
            <tr>
              <th className="px-5 py-3 text-left font-semibold">Prefix</th>
              <th className="px-4 py-3 text-left font-semibold">Description</th>
              <th className="px-4 py-3 text-left font-semibold">Status</th>
              <th className="px-5 py-3 text-right font-semibold">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200">
            {routes.map((route) => {
              const isEditing = editingId === route.id;
              return (
                <tr key={route.id} className="hover:bg-slate-50">
                  <td className="px-5 py-3 font-mono font-semibold text-slate-900">
                    {isEditing ? (
                      <input
                        type="text"
                        value={editPrefix}
                        onChange={(e) => setEditPrefix(e.target.value)}
                        className="rounded border border-slate-300 px-2 py-1 text-sm font-mono w-44"
                      />
                    ) : (
                      route.prefix
                    )}
                  </td>
                  <td className="px-4 py-3 text-slate-600">
                    {isEditing ? (
                      <input
                        type="text"
                        value={editDesc}
                        onChange={(e) => setEditDesc(e.target.value)}
                        className="rounded border border-slate-300 px-2 py-1 text-sm w-full"
                      />
                    ) : (
                      route.description || <span className="text-slate-400 italic">No description</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <button
                      type="button"
                      onClick={() => handleToggle(route)}
                      className={`px-2.5 py-0.5 rounded-full text-xs font-semibold border ${
                        route.enabled
                          ? 'bg-emerald-100 text-emerald-800 border-emerald-200'
                          : 'bg-slate-100 text-slate-500 border-slate-200'
                      }`}
                    >
                      {route.enabled ? 'Enabled' : 'Disabled'}
                    </button>
                  </td>
                  <td className="px-5 py-3 text-right space-x-2">
                    {isEditing ? (
                      <>
                        <button
                          type="button"
                          onClick={() => handleSaveEdit(route.id)}
                          className="inline-flex items-center gap-1 px-2.5 py-1 rounded text-xs font-semibold bg-emerald-600 text-white"
                        >
                          <Save className="w-3.5 h-3.5" />
                          Save
                        </button>
                        <button
                          type="button"
                          onClick={() => setEditingId(null)}
                          className="inline-flex items-center gap-1 px-2.5 py-1 rounded text-xs font-semibold border border-slate-300 text-slate-600"
                        >
                          <X className="w-3.5 h-3.5" />
                          Cancel
                        </button>
                      </>
                    ) : (
                      <>
                        <button
                          type="button"
                          aria-label={`Edit ${route.prefix}`}
                          onClick={() => {
                            setEditingId(route.id);
                            setEditPrefix(route.prefix);
                            setEditDesc(route.description);
                          }}
                          className="inline-flex items-center gap-1 px-2.5 py-1 rounded text-xs font-semibold border border-slate-300 text-slate-700 hover:bg-slate-100"
                        >
                          <Pencil className="w-3.5 h-3.5" />
                          Edit
                        </button>
                        <button
                          type="button"
                          aria-label={`Delete ${route.prefix}`}
                          onClick={() => handleDelete(route.id)}
                          className="inline-flex items-center gap-1 px-2.5 py-1 rounded text-xs font-semibold border border-red-200 text-red-700 hover:bg-red-50"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                          Delete
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
