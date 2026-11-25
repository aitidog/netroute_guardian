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
import type { ComparisonReport, RiskLevel, RouteDiffEntry, RoutePath } from '../types';
import { RiskBadge } from './RiskBadge';

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
    'VRF',
    'Subnet/Mask',
    'Next Hop',
    'Interface',
    'Metric',
    'Protocol',
    'Admin_Distance',
    'Metric_Value',
    'Peer_Priority',
    'Prefix_Change_Type',
    'Entry_Action',
    'Is_Important',
    'Severity',
    'Matched_Rules',
    'Importance_Reasons',
    'Prefix_Entries_Before',
    'Prefix_Entries_After',
    'Prefix_Entry_Delta',
    'Affected_IPs',
    'Fallback_Status',
    'Fallback_Parent',
    'Explanation',
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
          item.vrf,
          item.prefix,
          path.next_hop,
          path.interface,
          formatMetricDisplay(path),
          path.protocol,
          path.admin_distance ?? '',
          path.metric ?? '',
          path.peer_priority ?? '',
          item.change_type.toUpperCase(),
          action,
          item.is_important ? 'YES' : 'NO',
          item.severity,
          item.matched_rules.join('; '),
          item.importance_reasons.join('; '),
          beforeCnt,
          afterCnt,
          deltaText,
          item.affected_ip_count,
          item.fallback_status ?? '',
          item.fallback_parent_prefix ?? '',
          item.explanation,
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

const CHANGE_BADGE: Record<RouteDiffEntry['change_type'], string> = {
  removed: 'bg-red-100 text-red-700 border-red-200',
  added: 'bg-emerald-100 text-emerald-700 border-emerald-200',
  changed: 'bg-amber-100 text-amber-800 border-amber-200',
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
  const [severityFilter, setSeverityFilter] = useState<'all' | RiskLevel>('all');
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
    severityFilter !== 'all' ||
    ruleFilter !== 'all' ||
    vrfFilter !== 'all' ||
    searchQuery.trim() !== '';

  const resetFilters = () => {
    setChangeTypeFilter('all');
    setSeverityFilter('all');
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
      if (severityFilter !== 'all' && entry.severity !== severityFilter) {
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
  }, [tabEntries, changeTypeFilter, severityFilter, ruleFilter, vrfFilter, searchQuery]);

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

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
      {/* Header Banner */}
      <div className="px-6 py-4 bg-slate-900 text-white flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h3 className="text-lg font-bold font-mono">{payload.device_label}</h3>
            <RiskBadge level={payload.risk_level} />
          </div>
          <p className="text-xs text-slate-300 mt-1">{payload.executive_summary}</p>
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
            -{stats.removed_prefix_entries_count ?? payload.all_entries.filter((e) => e.change_type === 'removed').reduce((acc, e) => acc + (e.removed_paths.length || e.before_paths.length), 0)} route entries
          </div>
        </div>
        <div className="bg-white p-3 rounded-lg border border-slate-200">
          <div className="text-xs font-medium text-slate-500 uppercase">Added</div>
          <div className="text-2xl font-bold text-emerald-600 mt-0.5">{stats.added_count}</div>
          <div className="text-[11px] text-emerald-700 font-mono">
            +{stats.added_prefix_entries_count ?? payload.all_entries.filter((e) => e.change_type === 'added').reduce((acc, e) => acc + (e.added_paths.length || e.after_paths.length), 0)} route entries
          </div>
        </div>
        <div className="bg-white p-3 rounded-lg border border-slate-200">
          <div className="text-xs font-medium text-slate-500 uppercase">Changed</div>
          <div className="text-2xl font-bold text-amber-600 mt-0.5">{stats.changed_count}</div>
          <div className="text-[11px] text-amber-700 font-mono">
            -{stats.changed_removed_entries_count ?? payload.all_entries.filter((e) => e.change_type === 'changed').reduce((acc, e) => acc + e.removed_paths.length, 0)} / +{stats.changed_added_entries_count ?? payload.all_entries.filter((e) => e.change_type === 'changed').reduce((acc, e) => acc + e.added_paths.length, 0)} entries
          </div>
        </div>
        <div className="bg-white p-3 rounded-lg border border-red-200 bg-red-50/40">
          <div className="text-xs font-medium text-red-700 uppercase">Important Alerts</div>
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
            {stats.after_raw_entries - stats.before_raw_entries >= 0 ? '+' : ''}
            {stats.after_raw_entries - stats.before_raw_entries})
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

      {/* Filter Tabs + Pipeline Trace Toggle */}
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
            aria-label="Filter by Severity"
            value={severityFilter}
            onChange={(e) => setSeverityFilter(e.target.value as 'all' | RiskLevel)}
            className="rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value="all">Severity: All</option>
            <option value="CRITICAL">Severity: CRITICAL</option>
            <option value="HIGH">Severity: HIGH</option>
            <option value="MEDIUM">Severity: MEDIUM</option>
            <option value="LOW">Severity: LOW</option>
            <option value="INFO">Severity: INFO</option>
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
                <th className="px-4 py-3 text-left font-semibold">Severity</th>
                <th className="px-4 py-3 text-left font-semibold">Network Analysis &amp; Explanation</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {entries.map((entry) => {
                const rowKey = `${entry.vrf}:${entry.prefix}:${entry.change_type}`;
                const isExpanded = expandedKey === rowKey;
                const remEntries =
                  entry.removed_paths.length || (entry.change_type === 'removed' ? entry.before_paths.length : 0);
                const addEntries =
                  entry.added_paths.length || (entry.change_type === 'added' ? entry.after_paths.length : 0);
                return (
                  <React.Fragment key={rowKey}>
                    <tr
                      onClick={() => setExpandedKey(isExpanded ? null : rowKey)}
                      className={`cursor-pointer transition-colors ${
                        entry.is_important ? 'bg-red-50/30 hover:bg-red-50/60' : 'hover:bg-slate-50'
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
                        <div className="font-mono font-semibold text-slate-900 flex items-center gap-1.5">
                          {entry.is_important && (
                            <AlertTriangle className="w-4 h-4 text-red-600 shrink-0" />
                          )}
                          {entry.prefix}
                        </div>
                        <div className="text-xs text-slate-500">
                          VRF: {entry.vrf} · {entry.affected_ip_count.toLocaleString()} IPs
                        </div>
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <span
                          className={`inline-flex px-2 py-0.5 text-xs font-bold rounded border uppercase ${CHANGE_BADGE[entry.change_type]}`}
                        >
                          {entry.change_type}
                        </span>
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap font-mono text-xs">
                        <div className="font-semibold text-slate-800">
                          {entry.before_paths.length} &rarr; {entry.after_paths.length}
                        </div>
                        <div className="text-[11px]">
                          {entry.change_type === 'removed' && (
                            <span className="text-red-700">-{remEntries} entries</span>
                          )}
                          {entry.change_type === 'added' && (
                            <span className="text-emerald-700">+{addEntries} entries</span>
                          )}
                          {entry.change_type === 'changed' && (
                            <span className="text-amber-700">
                              -{remEntries} / +{addEntries} entries
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <RiskBadge level={entry.severity} />
                      </td>
                      <td className="px-4 py-3">
                        {entry.importance_reasons.length > 0 && (
                          <div className="flex flex-wrap gap-1.5 mb-1.5">
                            {entry.importance_reasons.map((reason) => (
                              <span
                                key={reason}
                                className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium bg-red-100 text-red-800 border border-red-200"
                              >
                                {reason}
                              </span>
                            ))}
                          </div>
                        )}
                        <p className="text-slate-700 leading-relaxed">{entry.explanation}</p>
                      </td>
                    </tr>

                    {isExpanded && (
                      <tr className="bg-slate-50/90">
                        <td colSpan={6} className="px-6 py-4">
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                            <div className="bg-white rounded-lg border border-slate-200 p-3">
                              <div className="font-semibold text-slate-700 mb-2">
                                Before Change Paths ({entry.before_paths.length})
                              </div>
                              {entry.before_paths.length === 0 ? (
                                <p className="text-slate-400 italic">Not present before change</p>
                              ) : (
                                <ul className="space-y-1 font-mono">
                                  {entry.before_paths.map((p, idx) => (
                                    <li key={idx} className="text-slate-700">
                                      NH: {p.next_hop || '(overlay)'} | IF: {p.interface || '-'} |{' '}
                                      {p.raw_metric || `M:${p.metric} AD:${p.admin_distance}`}
                                    </li>
                                  ))}
                                </ul>
                              )}
                            </div>

                            <div className="bg-white rounded-lg border border-slate-200 p-3">
                              <div className="font-semibold text-slate-700 mb-2">
                                After Change Paths ({entry.after_paths.length})
                              </div>
                              {entry.after_paths.length === 0 ? (
                                <p className="text-red-500 italic">Removed in post-change table</p>
                              ) : (
                                <ul className="space-y-1 font-mono">
                                  {entry.after_paths.map((p, idx) => (
                                    <li key={idx} className="text-slate-700">
                                      NH: {p.next_hop || '(overlay)'} | IF: {p.interface || '-'} |{' '}
                                      {p.raw_metric || `M:${p.metric} AD:${p.admin_distance}`}
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
