import React, { useState } from 'react';
import {
  ChevronDown,
  ChevronRight,
  Download,
  GitBranch,
  Search,
  Sparkles,
  Upload,
} from 'lucide-react';
import { api } from '../api/client';
import type { RouteSummaryResponse } from '../types';

const MINI_EXAMPLE_TEXT = `0.0.0.0/0
10.1.0.0/16
10.1.1.0/24
10.1.5.0/25
10.2.2.0/26
172.16.2.0/24
172.16.2.128/26
192.168.8.0/26`;

export const RouteSummaryPage: React.FC = () => {
  const [mode, setMode] = useState<'device' | 'text' | 'upload'>('device');
  const [query, setQuery] = useState('uec-abc-prd01');
  const [rawText, setRawText] = useState(MINI_EXAMPLE_TEXT);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [includeSupernets, setIncludeSupernets] = useState(false);

  const [result, setResult] = useState<RouteSummaryResponse | null>(null);
  const [activeTab, setActiveTab] = useState<'all' | 'summary' | 'remaining'>('all');
  const [searchFilter, setSearchFilter] = useState('');
  const [expandedPrefix, setExpandedPrefix] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleRunDevice = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await api.summarizeDevice(query, includeSupernets);
      setResult(res);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const handleRunText = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await api.summarizeText(rawText, 'Manual CIDR Input', includeSupernets);
      setResult(res);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const handleRunUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!uploadFile) {
      setError('Please select a CSV or CLI routing table file.');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await api.summarizeFile(uploadFile, includeSupernets);
      setResult(res);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const handleDemoCsv = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.summarizeDemoCsv(includeSupernets);
      setResult(res);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const handleExportCsv = () => {
    if (!result) return;
    const lines = ['VRF,Prefix,Category,CoveredCount,CoveredRoutes'];
    for (const r of result.all_output_routes) {
      lines.push(
        `${r.vrf},${r.prefix},${r.is_summary ? 'SUMMARY' : 'REMAINING'},${r.covered_count},"${r.covered_routes.join(' ')}"`
      );
    }
    const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `route-summary-${result.source_label.replace(/[^a-zA-Z0-9._-]/g, '_')}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const displayedRoutes = result
    ? (activeTab === 'summary'
        ? result.summary_routes
        : activeTab === 'remaining'
          ? result.remaining_routes
          : result.all_output_routes
      ).filter((r) =>
        searchFilter.trim()
          ? r.prefix.includes(searchFilter.trim()) ||
            r.covered_routes.some((c) => c.includes(searchFilter.trim()))
          : true
      )
    : [];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Route Summarization (Feature 2)</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Identify existing summary routes that cover more-specific prefixes and list remaining unsummarizable routes (ignoring 0.0.0.0/0).
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <a
            href="/api/v1/sample-data/after"
            download="subnetsExample_afterChange.csv"
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold border border-slate-300 bg-white hover:bg-slate-50 text-slate-700"
          >
            <Download className="w-3.5 h-3.5" />
            Download Sample CSV
          </a>
          <button
            type="button"
            disabled={loading}
            onClick={handleDemoCsv}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold bg-indigo-600 hover:bg-indigo-700 text-white disabled:opacity-50"
          >
            <Sparkles className="w-4 h-4" />
            Run Demo (afterChange.csv)
          </button>
        </div>
      </div>

      {/* Mode Switcher + Input Form */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="px-5 pt-3 border-b border-slate-200 flex flex-wrap items-center justify-between gap-3">
          <div className="flex gap-2">
            {(
              [
                ['device', 'Query Device (IP / Hostname)'],
                ['text', 'Paste Prefixes / CLI'],
                ['upload', 'Upload CSV File'],
              ] as const
            ).map(([m, label]) => (
              <button
                key={m}
                type="button"
                onClick={() => setMode(m)}
                className={`px-3 py-2 text-sm font-semibold border-b-2 transition-colors ${
                  mode === m
                    ? 'border-indigo-600 text-indigo-700'
                    : 'border-transparent text-slate-500 hover:text-slate-700'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          <label className="mb-2 inline-flex items-center gap-2 text-xs text-slate-600 cursor-pointer">
            <input
              type="checkbox"
              checked={includeSupernets}
              onChange={(e) => setIncludeSupernets(e.target.checked)}
              className="rounded border-slate-300"
            />
            Include optional adjacent CIDR supernet suggestions
          </label>
        </div>

        <div className="p-5">
          {mode === 'device' && (
            <form onSubmit={handleRunDevice} className="space-y-3">
              <div className="flex flex-wrap gap-3">
                <input
                  type="text"
                  aria-label="Device IP or Hostname"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Enter hostname or IP (e.g. uec-abc-prd01 or 10.0.1.11)"
                  className="flex-1 min-w-[260px] rounded-lg border border-slate-300 px-3.5 py-2 text-sm font-mono"
                />
                <button
                  type="submit"
                  disabled={loading}
                  className="inline-flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-semibold bg-slate-900 hover:bg-slate-800 text-white disabled:opacity-50"
                >
                  <GitBranch className="w-4 h-4" />
                  {loading ? 'Summarizing...' : 'Fetch & Summarize'}
                </button>
              </div>
              <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
                <span>Quick select demo devices:</span>
                {[
                  ['uec-abc-prd01', 'EdgeConnect (CSV)'],
                  ['10.0.1.11', 'Cisco Nexus (nx-dc1-core01)'],
                  ['10.0.1.21', 'Cisco Router (rtr-hq-wan01)'],
                ].map(([val, lbl]) => (
                  <button
                    key={val}
                    type="button"
                    onClick={() => setQuery(val)}
                    className="px-2 py-0.5 rounded bg-slate-100 hover:bg-slate-200 font-mono text-slate-700"
                  >
                    {val} · {lbl}
                  </button>
                ))}
              </div>
            </form>
          )}

          {mode === 'text' && (
            <form onSubmit={handleRunText} className="space-y-3">
              <textarea
                rows={6}
                aria-label="Routing Table Prefixes"
                value={rawText}
                onChange={(e) => setRawText(e.target.value)}
                className="w-full rounded-lg border border-slate-300 p-3 text-sm font-mono"
              />
              <div className="flex items-center justify-between">
                <button
                  type="button"
                  onClick={() => setRawText(MINI_EXAMPLE_TEXT)}
                  className="text-xs text-indigo-600 hover:underline"
                >
                  Reset to requirement mini-example (7 routes)
                </button>
                <button
                  type="submit"
                  disabled={loading}
                  className="inline-flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-semibold bg-slate-900 hover:bg-slate-800 text-white disabled:opacity-50"
                >
                  <GitBranch className="w-4 h-4" />
                  Summarize Text
                </button>
              </div>
            </form>
          )}

          {mode === 'upload' && (
            <form onSubmit={handleRunUpload} className="flex flex-wrap items-center gap-4">
              <input
                type="file"
                accept=".csv,.txt,.log"
                onChange={(e) => setUploadFile(e.target.files?.[0] ?? null)}
                className="text-sm text-slate-600 file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-slate-100 file:font-semibold"
              />
              <button
                type="submit"
                disabled={loading}
                className="inline-flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-semibold bg-slate-900 hover:bg-slate-800 text-white disabled:opacity-50"
              >
                <Upload className="w-4 h-4" />
                Upload &amp; Summarize
              </button>
            </form>
          )}
        </div>
      </div>

      {error && (
        <div className="px-4 py-3 rounded-lg text-sm bg-red-50 text-red-800 border border-red-200">
          {error}
        </div>
      )}

      {/* Results Panel */}
      {result && (
        <div className="space-y-5">
          {/* Compression Stats */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            <div className="bg-white rounded-xl border border-slate-200 p-4">
              <div className="text-xs font-semibold text-slate-500 uppercase">Unique Prefixes</div>
              <div className="text-2xl font-bold text-slate-900 mt-0.5">
                {result.total_unique_prefixes.toLocaleString()}
              </div>
              <div className="text-[11px] text-slate-500">
                Ignored 0.0.0.0/0: {result.ignored_default_routes}
              </div>
            </div>
            <div className="bg-white rounded-xl border border-indigo-200 bg-indigo-50/40 p-4">
              <div className="text-xs font-semibold text-indigo-700 uppercase">Output Routes</div>
              <div className="text-2xl font-bold text-indigo-700 mt-0.5">
                {result.output_route_count.toLocaleString()}
              </div>
              <div className="text-[11px] text-indigo-600">Summary + Remaining</div>
            </div>
            <div className="bg-white rounded-xl border border-emerald-200 bg-emerald-50/40 p-4">
              <div className="text-xs font-semibold text-emerald-700 uppercase">Summary Routes</div>
              <div className="text-2xl font-bold text-emerald-700 mt-0.5">
                {result.summary_route_count}
              </div>
              <div className="text-[11px] text-emerald-600">Cover specific subnets</div>
            </div>
            <div className="bg-white rounded-xl border border-slate-200 p-4">
              <div className="text-xs font-semibold text-slate-500 uppercase">Remaining Routes</div>
              <div className="text-2xl font-bold text-slate-800 mt-0.5">
                {result.remaining_route_count}
              </div>
              <div className="text-[11px] text-slate-500">Cannot be summarized</div>
            </div>
            <div className="bg-white rounded-xl border border-slate-200 p-4">
              <div className="text-xs font-semibold text-slate-500 uppercase">Covered / Folded</div>
              <div className="text-2xl font-bold text-slate-800 mt-0.5">
                {result.covered_route_count.toLocaleString()}
              </div>
              <div className="text-[11px] text-slate-500">More-specific routes</div>
            </div>
            <div className="bg-white rounded-xl border border-slate-200 p-4">
              <div className="text-xs font-semibold text-slate-500 uppercase">Reduction Ratio</div>
              <div className="text-2xl font-bold text-indigo-600 mt-0.5">
                {result.compression_ratio_pct}%
              </div>
              <div className="text-[11px] text-slate-500 truncate">{result.source_label}</div>
            </div>
          </div>

          {/* Optional Supernet Suggestions */}
          {result.supernet_suggestions && result.supernet_suggestions.length > 0 && (
            <div className="bg-amber-50/70 rounded-xl border border-amber-200 p-4">
              <div className="text-sm font-bold text-amber-900 mb-2">
                Optional Adjacent CIDR Supernet Suggestions ({result.supernet_suggestions.length})
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
                {result.supernet_suggestions.slice(0, 12).map((s) => (
                  <div
                    key={`${s.vrf}:${s.suggested_supernet}`}
                    className="bg-white rounded-lg border border-amber-200 p-2.5 text-xs"
                  >
                    <div className="font-mono font-bold text-amber-900">{s.suggested_supernet}</div>
                    <div className="text-slate-600 mt-0.5">
                      Combines {s.member_count} adjacent routes: {s.member_prefixes.slice(0, 4).join(', ')}
                      {s.member_prefixes.length > 4 ? '...' : ''}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Route Table */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
            <div className="px-5 py-3.5 border-b border-slate-200 flex flex-wrap items-center justify-between gap-3">
              <div className="flex gap-1">
                {(
                  [
                    ['all', `All Output (${result.output_route_count})`],
                    ['summary', `Summary Routes (${result.summary_route_count})`],
                    ['remaining', `Remaining (${result.remaining_route_count})`],
                  ] as const
                ).map(([tab, label]) => (
                  <button
                    key={tab}
                    type="button"
                    onClick={() => setActiveTab(tab)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-semibold ${
                      activeTab === tab
                        ? 'bg-indigo-600 text-white'
                        : 'text-slate-600 hover:bg-slate-100'
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>

              <div className="flex items-center gap-2">
                <div className="relative">
                  <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2.5" />
                  <input
                    type="text"
                    value={searchFilter}
                    onChange={(e) => setSearchFilter(e.target.value)}
                    placeholder="Filter prefix..."
                    className="pl-8 pr-3 py-1.5 rounded-lg border border-slate-300 text-xs font-mono"
                  />
                </div>
                <button
                  type="button"
                  onClick={handleExportCsv}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-300 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                >
                  <Download className="w-3.5 h-3.5" />
                  Export CSV
                </button>
              </div>
            </div>

            <div className="overflow-x-auto max-h-[540px] overflow-y-auto">
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <thead className="bg-slate-50 text-xs uppercase text-slate-500 sticky top-0">
                  <tr>
                    <th className="w-8 px-3 py-3" />
                    <th className="px-4 py-3 text-left font-semibold">Output Prefix</th>
                    <th className="px-4 py-3 text-left font-semibold">VRF</th>
                    <th className="px-4 py-3 text-left font-semibold">Category</th>
                    <th className="px-4 py-3 text-left font-semibold">Covered Specific Routes</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200">
                  {displayedRoutes.map((item) => {
                    const key = `${item.vrf}:${item.prefix}`;
                    const isOpen = expandedPrefix === key;
                    return (
                      <React.Fragment key={key}>
                        <tr
                          onClick={() =>
                            item.is_summary && setExpandedPrefix(isOpen ? null : key)
                          }
                          className={item.is_summary ? 'cursor-pointer hover:bg-emerald-50/40' : 'hover:bg-slate-50'}
                        >
                          <td className="px-3 py-2.5 text-slate-400">
                            {item.is_summary &&
                              (isOpen ? (
                                <ChevronDown className="w-4 h-4" />
                              ) : (
                                <ChevronRight className="w-4 h-4" />
                              ))}
                          </td>
                          <td className="px-4 py-2.5 font-mono font-semibold text-slate-900">
                            {item.prefix}
                          </td>
                          <td className="px-4 py-2.5 text-xs text-slate-600">{item.vrf}</td>
                          <td className="px-4 py-2.5">
                            {item.is_summary ? (
                              <span className="inline-flex px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800 border border-emerald-200">
                                SUMMARY
                              </span>
                            ) : (
                              <span className="inline-flex px-2 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-600 border border-slate-200">
                                REMAINING
                              </span>
                            )}
                          </td>
                          <td className="px-4 py-2.5 text-xs text-slate-600">
                            {item.is_summary ? (
                              <span>
                                Covers <strong>{item.covered_count}</strong> more-specific route(s)
                                (click to expand)
                              </span>
                            ) : (
                              <span className="text-slate-400">—</span>
                            )}
                          </td>
                        </tr>
                        {isOpen && item.is_summary && (
                          <tr className="bg-slate-50">
                            <td colSpan={5} className="px-8 py-3">
                              <div className="text-xs font-semibold text-slate-700 mb-2">
                                Routes covered by {item.prefix} ({item.covered_count}):
                              </div>
                              <div className="flex flex-wrap gap-1.5 max-h-48 overflow-y-auto">
                                {item.covered_routes.map((sub) => (
                                  <span
                                    key={sub}
                                    className="px-2 py-0.5 rounded bg-white border border-slate-200 font-mono text-xs text-slate-700"
                                  >
                                    {sub}
                                  </span>
                                ))}
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
