import React, { useMemo, useState } from 'react';
import {
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Download,
  Filter,
  Layers,
  Mail,
  RotateCcw,
  Search,
  Send,
  ShieldAlert,
} from 'lucide-react';
import type { ComparisonReport, RouteDiffEntry, RoutePath } from '../types';

function escapeCsvCell(value: string | number | null | undefined): string {
  const str = String(value ?? '');
  if (str.includes(',') || str.includes('"') || str.includes('\n') || str.includes('\r')) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

function formatMetricDisplay(path: RoutePath): string {
  if (path.raw_metric && path.raw_metric.trim()) {
    return path.raw_metric.trim();
  }
  if (path.metric === null && path.admin_distance === null) {
    return '';
  }
  const meta: string[] = [];
  if (path.admin_distance !== null) meta.push(`AD:${path.admin_distance}`);
  if (path.peer_priority !== null) meta.push(`PP:${path.peer_priority}`);
  return meta.length > 0 ? `${path.metric ?? ''} (${meta.join(', ')})` : String(path.metric ?? '');
}

function expandEntryRows(item: RouteDiffEntry): Array<{ action: 'REMOVED' | 'ADDED'; path: RoutePath }> {
  const expanded: Array<{ action: 'REMOVED' | 'ADDED'; path: RoutePath }> = [];
  for (const p of item.removed_paths) {
    expanded.push({ action: 'REMOVED', path: p });
  }
  for (const p of item.added_paths) {
    expanded.push({ action: 'ADDED', path: p });
  }
  if (expanded.length === 0) {
    if (item.change_type === 'removed') {
      for (const p of item.before_paths) {
        expanded.push({ action: 'REMOVED', path: p });
      }
    } else if (item.change_type === 'added') {
      for (const p of item.after_paths) {
        expanded.push({ action: 'ADDED', path: p });
      }
    }
  }
  return expanded;
}

export function buildComparisonCsv(deviceLabel: string, rows: RouteDiffEntry[]): string {
  const headers = [
    'Appliance',
    'Subnet/Mask',
    'Next Hop',
    'Interface',
    'Metric',
    'Admin_Distance',
    'Metric_Value',
    'Peer_Priority',
    'Prefix_Change_Type',
    'Entry_Action',
    'Is_Important',
    'Matched_Rules',
    'Importance_Reasons',
    'Prefix_Entries_Before',
    'Prefix_Entries_After',
    'Prefix_Entry_Delta',
    'Explanation',
    'VRF',
    'Protocol',
  ];
  const lines = [headers.join(',')];
  for (const item of rows) {
    const beforeCnt = item.before_paths.length;
    const afterCnt = item.after_paths.length;
    const delta = afterCnt - beforeCnt;
    const deltaText = delta > 0 ? `+${delta}` : String(delta);

    for (const { action, path } of expandEntryRows(item)) {
      lines.push(
        [
          deviceLabel,
          item.prefix,
          path.next_hop,
          path.interface,
          formatMetricDisplay(path),
          path.admin_distance ?? '',
          path.metric ?? '',
          path.peer_priority ?? '',
          item.change_type.toUpperCase(),
          action,
          item.is_important ? 'YES' : 'NO',
          item.matched_rules.join('; '),
          item.importance_reasons.join('; '),
          beforeCnt,
          afterCnt,
          deltaText,
          item.explanation,
          item.vrf,
          path.protocol,
        ]
          .map(escapeCsvCell)
          .join(',')
      );
    }
  }
  return `\ufeff${lines.join('\n')}\n`;
}

interface ReportViewerProps {
  report: ComparisonReport;
  onPreviewEmail?: (reportId: number) => void;
  onResendEmail?: (reportId: number) => void;
}

function pathSignature(path: RoutePath): string {
  return JSON.stringify([
    path.next_hop ?? '',
    path.interface ?? '',
    path.protocol ?? 'unknown',
    path.admin_distance ?? null,
    path.metric ?? null,
    path.peer_priority ?? null,
    path.raw_metric ?? '',
  ]);
}

export function annotatePathDiffs(entry: RouteDiffEntry): {
  before: Array<{ path: RoutePath; status: 'removed' | 'unchanged' }>;
  after: Array<{ path: RoutePath; status: 'added' | 'unchanged' }>;
} {
  const removedCounts = new Map<string, number>();
  const removedSource =
    entry.removed_paths.length > 0
      ? entry.removed_paths
      : entry.change_type === 'removed'
        ? entry.before_paths
        : [];
  for (const p of removedSource) {
    const sig = pathSignature(p);
    removedCounts.set(sig, (removedCounts.get(sig) ?? 0) + 1);
  }

  const addedCounts = new Map<string, number>();
  const addedSource =
    entry.added_paths.length > 0
      ? entry.added_paths
      : entry.change_type === 'added'
        ? entry.after_paths
        : [];
  for (const p of addedSource) {
    const sig = pathSignature(p);
    addedCounts.set(sig, (addedCounts.get(sig) ?? 0) + 1);
  }

  const before = entry.before_paths.map((path) => {
    const sig = pathSignature(path);
    const remaining = removedCounts.get(sig) ?? 0;
    if (remaining > 0) {
      removedCounts.set(sig, remaining - 1);
      return { path, status: 'removed' as const };
    }
    return { path, status: 'unchanged' as const };
  });

  const after = entry.after_paths.map((path) => {
    const sig = pathSignature(path);
    const remaining = addedCounts.get(sig) ?? 0;
    if (remaining > 0) {
      addedCounts.set(sig, remaining - 1);
      return { path, status: 'added' as const };
    }
    return { path, status: 'unchanged' as const };
  });

  return { before, after };
}

const CHANGE_BADGE: Record<RouteDiffEntry['change_type'], string> = {
  removed: 'bg-red-100 text-red-700 border-red-200',
  added: 'bg-emerald-100 text-emerald-700 border-emerald-200',
  changed: 'bg-amber-100 text-amber-800 border-amber-200',
};

const CHANGE_PREFIX_TEXT: Record<RouteDiffEntry['change_type'], string> = {
  removed: 'text-red-700',
  added: 'text-emerald-700',
  changed: 'text-amber-800',
};

export const ReportViewer: React.FC<ReportViewerProps> = ({
  report,
  onPreviewEmail,
  onResendEmail,
}) => {
  const [activeTab, setActiveTab] = useState<'important' | 'all' | 'normal'>('important');
  const [changeTypeFilter, setChangeTypeFilter] = useState<'all' | RouteDiffEntry['change_type']>(
    'all'
  );
  const [ruleFilter, setRuleFilter] = useState<'all' | 'large_prefix' | 'pre_specified_route'>(
    'all'
  );
  const [vrfFilter, setVrfFilter] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedKey, setExpandedKey] = useState<string | null>(null);
  const [showPipeline, setShowPipeline] = useState(false);

  const payload = report.report_payload;
  const stats = payload.summary_stats;

  const tabEntries =
    activeTab === 'important'
      ? payload.important_entries
      : activeTab === 'normal'
        ? payload.normal_entries
        : payload.all_entries;

  const availableVrfs = useMemo(() => {
    const vrfs = new Set(payload.all_entries.map((e) => e.vrf));
    return Array.from(vrfs).sort();
  }, [payload.all_entries]);

  const hasActiveFilters =
    changeTypeFilter !== 'all' ||
    ruleFilter !== 'all' ||
    vrfFilter !== 'all' ||
    searchQuery.trim() !== '';

  const resetFilters = () => {
    setChangeTypeFilter('all');
    setRuleFilter('all');
    setVrfFilter('all');
    setSearchQuery('');
  };

  const entries = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return tabEntries.filter((entry) => {
      if (changeTypeFilter !== 'all' && entry.change_type !== changeTypeFilter) {
        return false;
      }
      if (ruleFilter !== 'all' && !entry.matched_rules.includes(ruleFilter)) {
        return false;
      }
      if (vrfFilter !== 'all' && entry.vrf !== vrfFilter) {
        return false;
      }
      if (q) {
        const matchesPrefix = entry.prefix.toLowerCase().includes(q);
        const matchesVrf = entry.vrf.toLowerCase().includes(q);
        const matchesExplanation = entry.explanation.toLowerCase().includes(q);
        if (!matchesPrefix && !matchesVrf && !matchesExplanation) {
          return false;
        }
      }
      return true;
    });
  }, [tabEntries, changeTypeFilter, ruleFilter, vrfFilter, searchQuery]);

  const handleExportCsv = (exportScope: 'all' | 'filtered') => {
    const targetRows = exportScope === 'filtered' ? entries : payload.all_entries;
    const csvContent = buildComparisonCsv(payload.device_label, targetRows);
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const safeDevice = payload.device_label.replace(/[^a-zA-Z0-9._-]+/g, '_');
    const suffix = exportScope === 'filtered' ? 'filtered' : 'full';
    const link = document.createElement('a');
    link.href = url;
    link.download = `route-comparison-${safeDevice}-${suffix}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const removedPrefixEntries =
    stats.removed_prefix_entries_count ??
    payload.all_entries
      .filter((e) => e.change_type === 'removed')
      .reduce((acc, e) => acc + (e.removed_paths.length || e.before_paths.length), 0);
  const addedPrefixEntries =
    stats.added_prefix_entries_count ??
    payload.all_entries
      .filter((e) => e.change_type === 'added')
      .reduce((acc, e) => acc + (e.added_paths.length || e.after_paths.length), 0);
  const changedRemovedEntries =
    stats.changed_removed_entries_count ??
    payload.all_entries
      .filter((e) => e.change_type === 'changed')
      .reduce((acc, e) => acc + e.removed_paths.length, 0);
  const changedAddedEntries =
    stats.changed_added_entries_count ??
    payload.all_entries
      .filter((e) => e.change_type === 'changed')
      .reduce((acc, e) => acc + e.added_paths.length, 0);

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
      {/* Header Banner */}
      <div className="px-6 py-4 bg-slate-900 text-white flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h3 className="text-lg font-bold font-mono">{payload.device_label}</h3>
            {stats.important_count > 0 ? (
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-bold bg-red-500/20 text-red-200 border border-red-400/50">
                <ShieldAlert className="w-3.5 h-3.5" />
                {stats.important_count} IMPORTANT ALERT{stats.important_count > 1 ? 'S' : ''}
              </span>
            ) : (
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold bg-emerald-500/20 text-emerald-200 border border-emerald-400/40">
                NO IMPORTANT ALERTS
              </span>
            )}
          </div>
          <p className="text-xs text-slate-300 mt-1">
            {stats.total_differences === 0
              ? `No routing table differences detected (${stats.after_unique_prefixes} unique prefixes verified).`
              : `${stats.total_differences} prefix difference(s): ${stats.removed_count} removed (-${removedPrefixEntries} entries), ${stats.added_count} added (+${addedPrefixEntries} entries), ${stats.changed_count} changed (-${changedRemovedEntries}/+${changedAddedEntries} entries).`}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => handleExportCsv('all')}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-emerald-600 hover:bg-emerald-500 text-white"
          >
            <Download className="w-3.5 h-3.5" />
            Export CSV
          </button>
          {onPreviewEmail && (
            <button
              type="button"
              onClick={() => onPreviewEmail(report.id)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-100 border border-slate-700"
            >
              <Mail className="w-3.5 h-3.5" />
              Email Preview
            </button>
          )}
          {onResendEmail && (
            <button
              type="button"
              onClick={() => onResendEmail(report.id)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-indigo-600 hover:bg-indigo-500 text-white"
            >
              <Send className="w-3.5 h-3.5" />
              Resend Email
            </button>
          )}
        </div>
      </div>

      {/* Prefix & Route Entry Summary Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 p-5 bg-slate-50 border-b border-slate-200">
        <div className="bg-white p-3 rounded-lg border border-slate-200">
          <div className="text-xs font-medium text-slate-500 uppercase">Removed</div>
          <div className="text-2xl font-bold text-red-600 mt-0.5">{stats.removed_count}</div>
          <div className="text-[11px] text-red-700 font-mono">
            -{removedPrefixEntries} route entries
          </div>
        </div>
        <div className="bg-white p-3 rounded-lg border border-slate-200">
          <div className="text-xs font-medium text-slate-500 uppercase">Added</div>
          <div className="text-2xl font-bold text-emerald-600 mt-0.5">{stats.added_count}</div>
          <div className="text-[11px] text-emerald-700 font-mono">
            +{addedPrefixEntries} route entries
          </div>
        </div>
        <div className="bg-white p-3 rounded-lg border border-slate-200">
          <div className="text-xs font-medium text-slate-500 uppercase">Changed</div>
          <div className="text-2xl font-bold text-amber-600 mt-0.5">{stats.changed_count}</div>
          <div className="text-[11px] font-mono">
            <span className="text-red-700 font-semibold">-{changedRemovedEntries}</span>
            <span className="text-slate-400"> / </span>
            <span className="text-emerald-700 font-semibold">+{changedAddedEntries}</span>
            <span className="text-slate-500"> entries</span>
          </div>
        </div>
        <div className="bg-red-50/70 p-3 rounded-lg border border-red-300">
          <div className="text-xs font-semibold text-red-700 uppercase">Important Alerts</div>
          <div className="text-2xl font-bold text-red-700 mt-0.5">{stats.important_count}</div>
          <div className="text-[11px] text-red-600">
            &lt;=/{stats.large_prefix_threshold}: {stats.large_prefix_alert_count} · Rules:{' '}
            {stats.prespecified_alert_count}
          </div>
        </div>
        <div className="bg-white p-3 rounded-lg border border-slate-200">
          <div className="text-xs font-medium text-slate-500 uppercase">Prefixes &amp; Entries</div>
          <div className="text-base font-bold text-slate-800 mt-1 font-mono">
            {stats.before_unique_prefixes} &rarr; {stats.after_unique_prefixes}
          </div>
          <div className="text-[11px] text-slate-600 font-mono">
            Entries: {stats.before_raw_entries} &rarr; {stats.after_raw_entries} (
            <span
              className={
                stats.after_raw_entries - stats.before_raw_entries < 0
                  ? 'text-red-700 font-semibold'
                  : stats.after_raw_entries - stats.before_raw_entries > 0
                    ? 'text-emerald-700 font-semibold'
                    : 'text-slate-600'
              }
            >
              {stats.after_raw_entries - stats.before_raw_entries > 0 ? '+' : ''}
              {stats.after_raw_entries - stats.before_raw_entries}
            </span>
            )
          </div>
        </div>
        <div className="bg-white p-3 rounded-lg border border-slate-200">
          <div className="text-xs font-medium text-slate-500 uppercase">Email Delivery</div>
          <div className="text-sm font-semibold text-slate-800 mt-1.5 uppercase">
            {report.email_status}
          </div>
          <div className="text-[11px] text-slate-500 truncate" title={report.email_recipient ?? ''}>
            {report.email_recipient || 'No recipient'}
          </div>
        </div>
      </div>

      {/* Category Tabs + Pipeline Trace Toggle */}
      <div className="px-5 pt-4 flex flex-wrap items-center justify-between gap-3 border-b border-slate-200">
        <div className="flex gap-1">
          <button
            type="button"
            onClick={() => setActiveTab('important')}
            className={`px-4 py-2 text-sm font-semibold border-b-2 transition-colors ${
              activeTab === 'important'
                ? 'border-red-600 text-red-700'
                : 'border-transparent text-slate-500 hover:text-slate-700'
            }`}
          >
            <span className="inline-flex items-center gap-1.5">
              <ShieldAlert className="w-4 h-4" />
              Important Entries ({payload.important_entries.length})
            </span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('normal')}
            className={`px-4 py-2 text-sm font-semibold border-b-2 transition-colors ${
              activeTab === 'normal'
                ? 'border-indigo-600 text-indigo-700'
                : 'border-transparent text-slate-500 hover:text-slate-700'
            }`}
          >
            Normal Differences ({payload.normal_entries.length})
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('all')}
            className={`px-4 py-2 text-sm font-semibold border-b-2 transition-colors ${
              activeTab === 'all'
                ? 'border-indigo-600 text-indigo-700'
                : 'border-transparent text-slate-500 hover:text-slate-700'
            }`}
          >
            All Differences ({payload.all_entries.length})
          </button>
        </div>

        {payload.pipeline_stages && payload.pipeline_stages.length > 0 && (
          <button
            type="button"
            onClick={() => setShowPipeline((v) => !v)}
            className="mb-2 inline-flex items-center gap-1.5 text-xs font-medium text-slate-600 hover:text-indigo-600"
          >
            <Layers className="w-3.5 h-3.5" />
            {showPipeline ? 'Hide Pipeline Telemetry' : 'Inspect Pipeline Stages'}
          </button>
        )}
      </div>

      {/* Optional Pipeline Stage Telemetry */}
      {showPipeline && payload.pipeline_stages && (
        <div className="px-5 py-3 bg-indigo-50/50 border-b border-indigo-100">
          <div className="text-xs font-semibold text-indigo-900 mb-2">
            Single-Responsibility Pipeline Execution Trace
          </div>
          <div className="grid grid-cols-1 md:grid-cols-5 gap-2">
            {payload.pipeline_stages.map((st, idx) => (
              <div key={st.name} className="bg-white rounded-lg p-2.5 border border-indigo-100 text-xs">
                <div className="font-semibold text-indigo-700">
                  {idx + 1}. {st.name}
                </div>
                <div className="text-[11px] text-slate-500 mt-0.5">{st.description}</div>
                <div className="text-[11px] font-mono text-slate-700 mt-1">{st.duration_ms} ms</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Multi-Criteria Filter Bar */}
      <div className="px-5 py-3 bg-slate-50/80 border-b border-slate-200 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2.5">
          <span className="inline-flex items-center gap-1 text-xs font-semibold text-slate-500 uppercase">
            <Filter className="w-3.5 h-3.5" />
            Filters
          </span>

          <div className="relative">
            <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2" />
            <input
              type="text"
              aria-label="Search prefix or explanation"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search prefix or analysis..."
              className="pl-8 pr-3 py-1.5 rounded-lg border border-slate-300 bg-white text-xs font-mono w-52 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>

          <select
            aria-label="Filter by Change Type"
            value={changeTypeFilter}
            onChange={(e) =>
              setChangeTypeFilter(e.target.value as 'all' | RouteDiffEntry['change_type'])
            }
            className="rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value="all">Change: All</option>
            <option value="removed">Change: Removed</option>
            <option value="added">Change: Added</option>
            <option value="changed">Change: Changed</option>
          </select>

          <select
            aria-label="Filter by Matched Rule"
            value={ruleFilter}
            onChange={(e) =>
              setRuleFilter(e.target.value as 'all' | 'large_prefix' | 'pre_specified_route')
            }
            className="rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value="all">Rule: All</option>
            <option value="large_prefix">Rule: Mask &lt;= /{stats.large_prefix_threshold}</option>
            <option value="pre_specified_route">Rule: Pre-Specified Route</option>
          </select>

          {availableVrfs.length > 1 && (
            <select
              aria-label="Filter by VRF"
              value={vrfFilter}
              onChange={(e) => setVrfFilter(e.target.value)}
              className="rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <option value="all">VRF: All</option>
              {availableVrfs.map((vrf) => (
                <option key={vrf} value={vrf}>
                  VRF: {vrf}
                </option>
              ))}
            </select>
          )}

          {hasActiveFilters && (
            <button
              type="button"
              onClick={resetFilters}
              className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-semibold text-indigo-700 bg-indigo-50 hover:bg-indigo-100 border border-indigo-200"
            >
              <RotateCcw className="w-3 h-3" />
              Reset
            </button>
          )}
        </div>

        <div className="flex items-center gap-3">
          {hasActiveFilters && entries.length > 0 && (
            <button
              type="button"
              onClick={() => handleExportCsv('filtered')}
              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold text-emerald-800 bg-emerald-50 hover:bg-emerald-100 border border-emerald-200"
            >
              <Download className="w-3 h-3" />
              Export Filtered CSV ({entries.length})
            </button>
          )}
          <div className="text-xs text-slate-500 font-medium">
            Showing <span className="font-semibold text-slate-800">{entries.length}</span> of{' '}
            <span className="font-semibold text-slate-800">{tabEntries.length}</span> entries
          </div>
        </div>
      </div>

      {/* Detailed Differences Table */}
      <div className="overflow-x-auto">
        {entries.length === 0 ? (
          <div className="p-8 text-center text-sm text-slate-500">
            {hasActiveFilters
              ? 'No entries match the current filter criteria.'
              : 'No entries in this category.'}
          </div>
        ) : (
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                <th className="w-8 px-3 py-3" />
                <th className="px-4 py-3 text-left font-semibold">Prefix / VRF</th>
                <th className="px-4 py-3 text-left font-semibold">Change</th>
                <th className="px-4 py-3 text-left font-semibold">Route Entries</th>
                <th className="px-4 py-3 text-left font-semibold">Analysis &amp; Explanation</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {entries.map((entry) => {
                const rowKey = `${entry.vrf}:${entry.prefix}:${entry.change_type}`;
                const isExpanded = expandedKey === rowKey;
                const remEntries =
                  entry.removed_paths.length ||
                  (entry.change_type === 'removed' ? entry.before_paths.length : 0);
                const addEntries =
                  entry.added_paths.length ||
                  (entry.change_type === 'added' ? entry.after_paths.length : 0);
                const annotatedPaths = isExpanded ? annotatePathDiffs(entry) : null;
                const afterCountColor =
                  entry.after_paths.length < entry.before_paths.length
                    ? 'text-red-700'
                    : entry.after_paths.length > entry.before_paths.length
                      ? 'text-emerald-700'
                      : 'text-amber-700';
                return (
                  <React.Fragment key={rowKey}>
                    <tr
                      onClick={() => setExpandedKey(isExpanded ? null : rowKey)}
                      className={`cursor-pointer transition-colors ${
                        entry.is_important
                          ? 'bg-red-50/75 hover:bg-red-100/70 border-l-4 border-l-red-600'
                          : 'hover:bg-slate-50'
                      }`}
                    >
                      <td className="px-3 py-3 text-slate-400">
                        {isExpanded ? (
                          <ChevronDown className="w-4 h-4" />
                        ) : (
                          <ChevronRight className="w-4 h-4" />
                        )}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <div className="font-mono font-semibold flex items-center gap-1.5">
                          {entry.is_important && (
                            <AlertTriangle className="w-4 h-4 text-red-600 shrink-0" />
                          )}
                          <span className={CHANGE_PREFIX_TEXT[entry.change_type]}>
                            {entry.prefix}
                          </span>
                          {entry.is_important && (
                            <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wide bg-red-600 text-white">
                              Important
                            </span>
                          )}
                        </div>
                        <div className="text-xs text-slate-500">VRF: {entry.vrf}</div>
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <span
                          className={`inline-flex px-2 py-0.5 text-xs font-bold rounded border uppercase ${CHANGE_BADGE[entry.change_type]}`}
                        >
                          {entry.change_type}
                        </span>
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap font-mono text-xs">
                        <div className="font-semibold text-slate-700">
                          {entry.before_paths.length} &rarr;{' '}
                          <span className={afterCountColor}>{entry.after_paths.length}</span>
                        </div>
                        <div className="text-[11px]">
                          {entry.change_type === 'removed' && (
                            <span className="text-red-700 font-semibold">-{remEntries} entries</span>
                          )}
                          {entry.change_type === 'added' && (
                            <span className="text-emerald-700 font-semibold">
                              +{addEntries} entries
                            </span>
                          )}
                          {entry.change_type === 'changed' && (
                            <span className="inline-flex items-center gap-1">
                              {remEntries > 0 && (
                                <span className="text-red-700 font-semibold">-{remEntries}</span>
                              )}
                              {remEntries > 0 && addEntries > 0 && (
                                <span className="text-slate-400">/</span>
                              )}
                              {addEntries > 0 && (
                                <span className="text-emerald-700 font-semibold">+{addEntries}</span>
                              )}
                              <span className="text-slate-500">entries</span>
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        {entry.importance_reasons.length > 0 && (
                          <div className="flex flex-wrap gap-1.5 mb-1.5">
                            {entry.importance_reasons.map((reason) => (
                              <span
                                key={reason}
                                className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold bg-red-100 text-red-800 border border-red-300"
                              >
                                {reason}
                              </span>
                            ))}
                          </div>
                        )}
                        <p className="text-slate-700 leading-relaxed">{entry.explanation}</p>
                      </td>
                    </tr>

                    {isExpanded && annotatedPaths && (
                      <tr className="bg-slate-50/90">
                        <td colSpan={5} className="px-6 py-4">
                          <div className="flex flex-wrap items-center gap-4 text-[11px] mb-2.5 text-slate-500">
                            <span className="font-semibold uppercase tracking-wide text-slate-600">
                              Path Entry Legend:
                            </span>
                            <span className="inline-flex items-center gap-1.5 text-red-700 font-medium">
                              <span className="inline-block w-2 h-2 rounded-full bg-red-500" />
                              [-] Removed
                            </span>
                            <span className="inline-flex items-center gap-1.5 text-emerald-700 font-medium">
                              <span className="inline-block w-2 h-2 rounded-full bg-emerald-500" />
                              [+] Added
                            </span>
                            <span className="inline-flex items-center gap-1.5 text-slate-500">
                              <span className="inline-block w-2 h-2 rounded-full bg-slate-300" />
                              [=] Unchanged
                            </span>
                          </div>
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                            <div className="bg-white rounded-lg border border-slate-200 p-3">
                              <div className="flex items-center justify-between gap-2 mb-2">
                                <span className="font-semibold text-slate-700">
                                  Before Change Paths ({entry.before_paths.length})
                                </span>
                                {remEntries > 0 && (
                                  <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-red-100 text-red-700">
                                    -{remEntries} removed
                                  </span>
                                )}
                              </div>
                              {annotatedPaths.before.length === 0 ? (
                                <p className="text-slate-400 italic">Not present before change</p>
                              ) : (
                                <ul className="space-y-1 font-mono">
                                  {annotatedPaths.before.map(({ path: p, status }, idx) => (
                                    <li
                                      key={idx}
                                      data-path-status={status}
                                      className={
                                        status === 'removed'
                                          ? 'flex items-start gap-2 px-2 py-1 rounded bg-red-50/90 text-red-700 border-l-2 border-red-500 font-medium'
                                          : 'flex items-start gap-2 px-2 py-1 rounded text-slate-500'
                                      }
                                    >
                                      <span className="font-bold select-none shrink-0">
                                        {status === 'removed' ? '[-]' : '[=]'}
                                      </span>
                                      <span>
                                        NH: {p.next_hop || '(overlay)'} | IF: {p.interface || '-'}{' '}
                                        | {p.raw_metric || `M:${p.metric} AD:${p.admin_distance}`}
                                      </span>
                                    </li>
                                  ))}
                                </ul>
                              )}
                            </div>

                            <div className="bg-white rounded-lg border border-slate-200 p-3">
                              <div className="flex items-center justify-between gap-2 mb-2">
                                <span className="font-semibold text-slate-700">
                                  After Change Paths ({entry.after_paths.length})
                                </span>
                                {addEntries > 0 && (
                                  <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-emerald-100 text-emerald-700">
                                    +{addEntries} added
                                  </span>
                                )}
                              </div>
                              {annotatedPaths.after.length === 0 ? (
                                <p className="text-red-600 italic font-medium">
                                  Removed in post-change table
                                </p>
                              ) : (
                                <ul className="space-y-1 font-mono">
                                  {annotatedPaths.after.map(({ path: p, status }, idx) => (
                                    <li
                                      key={idx}
                                      data-path-status={status}
                                      className={
                                        status === 'added'
                                          ? 'flex items-start gap-2 px-2 py-1 rounded bg-emerald-50/90 text-emerald-700 border-l-2 border-emerald-500 font-medium'
                                          : 'flex items-start gap-2 px-2 py-1 rounded text-slate-500'
                                      }
                                    >
                                      <span className="font-bold select-none shrink-0">
                                        {status === 'added' ? '[+]' : '[=]'}
                                      </span>
                                      <span>
                                        NH: {p.next_hop || '(overlay)'} | IF: {p.interface || '-'}{' '}
                                        | {p.raw_metric || `M:${p.metric} AD:${p.admin_distance}`}
                                      </span>
                                    </li>
                                  ))}
                                </ul>
                              )}
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};
