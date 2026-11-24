import React, { useState } from 'react';
import {
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Layers,
  Mail,
  Send,
  ShieldAlert,
} from 'lucide-react';
import type { ComparisonReport, RouteDiffEntry } from '../types';
import { RiskBadge } from './RiskBadge';

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
  const [expandedKey, setExpandedKey] = useState<string | null>(null);
  const [showPipeline, setShowPipeline] = useState(false);

  const payload = report.report_payload;
  const stats = payload.summary_stats;

  const entries =
    activeTab === 'important'
      ? payload.important_entries
      : activeTab === 'normal'
        ? payload.normal_entries
        : payload.all_entries;

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
        <div className="flex items-center gap-2">
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

      {/* Prefix Summary Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 p-5 bg-slate-50 border-b border-slate-200">
        <div className="bg-white p-3 rounded-lg border border-slate-200">
          <div className="text-xs font-medium text-slate-500 uppercase">Removed</div>
          <div className="text-2xl font-bold text-red-600 mt-0.5">{stats.removed_count}</div>
        </div>
        <div className="bg-white p-3 rounded-lg border border-slate-200">
          <div className="text-xs font-medium text-slate-500 uppercase">Added</div>
          <div className="text-2xl font-bold text-emerald-600 mt-0.5">{stats.added_count}</div>
        </div>
        <div className="bg-white p-3 rounded-lg border border-slate-200">
          <div className="text-xs font-medium text-slate-500 uppercase">Changed</div>
          <div className="text-2xl font-bold text-amber-600 mt-0.5">{stats.changed_count}</div>
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
          <div className="text-xs font-medium text-slate-500 uppercase">Unique Prefixes</div>
          <div className="text-lg font-bold text-slate-800 mt-1 font-mono">
            {stats.before_unique_prefixes} &rarr; {stats.after_unique_prefixes}
          </div>
          <div className="text-[11px] text-slate-500">
            Raw: {stats.before_raw_entries} &rarr; {stats.after_raw_entries}
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

      {/* Detailed Differences Table */}
      <div className="overflow-x-auto">
        {entries.length === 0 ? (
          <div className="p-8 text-center text-sm text-slate-500">
            No entries in this category.
          </div>
        ) : (
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                <th className="w-8 px-3 py-3" />
                <th className="px-4 py-3 text-left font-semibold">Prefix / VRF</th>
                <th className="px-4 py-3 text-left font-semibold">Change</th>
                <th className="px-4 py-3 text-left font-semibold">Severity</th>
                <th className="px-4 py-3 text-left font-semibold">Network Analysis &amp; Explanation</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {entries.map((entry) => {
                const rowKey = `${entry.vrf}:${entry.prefix}:${entry.change_type}`;
                const isExpanded = expandedKey === rowKey;
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
                        <td colSpan={5} className="px-6 py-4">
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
