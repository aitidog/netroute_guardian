import React, { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, CheckCircle2, Mail, Play, Server, X } from 'lucide-react';
import { api } from '../api/client';
import { ReportViewer } from '../components/ReportViewer';
import { StatusBadge } from '../components/StatusBadge';
import type { ChangeRequestDetail } from '../types';

export const ChangeDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const changeId = Number(id);
  const [detail, setDetail] = useState<ChangeRequestDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);
  const [emailModal, setEmailModal] = useState<{ subject: string; html: string } | null>(null);

  const load = async () => {
    try {
      const data = await api.getChange(changeId);
      setDetail(data);
    } catch (err) {
      setMessage({ type: 'err', text: (err as Error).message });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!Number.isNaN(changeId)) {
      void load();
    }
  }, [changeId]);

  const handlePreCapture = async () => {
    setBusy('pre');
    setMessage(null);
    try {
      const res = await api.triggerPreCapture(changeId);
      setMessage({
        type: 'ok',
        text: `Captured pre-change routing tables concurrently for: ${res.succeeded_devices.join(', ')}.`,
      });
      await load();
    } catch (err) {
      setMessage({ type: 'err', text: (err as Error).message });
    } finally {
      setBusy(null);
    }
  };

  const handlePostCapture = async () => {
    setBusy('post');
    setMessage(null);
    try {
      const res = await api.triggerPostCapture(changeId);
      setMessage({
        type: 'ok',
        text: `Post-change collection & parallel comparison finished for ${res.succeeded_devices.join(', ')}. Email delivery: ${res.email_status}.`,
      });
      await load();
    } catch (err) {
      setMessage({ type: 'err', text: (err as Error).message });
    } finally {
      setBusy(null);
    }
  };

  const handlePreviewEmail = async (reportId: number) => {
    try {
      const preview = await api.getReportEmailPreview(reportId);
      setEmailModal(preview);
    } catch (err) {
      setMessage({ type: 'err', text: (err as Error).message });
    }
  };

  const handleResendEmail = async (reportId: number) => {
    setBusy(`email-${reportId}`);
    setMessage(null);
    try {
      const res = await api.resendReportEmail(reportId);
      setMessage({
        type: res.status === 'sent' ? 'ok' : 'err',
        text:
          res.status === 'sent'
            ? `Report email sent to ${res.recipient_email}. Check Mailpit (:8025).`
            : `Email status: ${res.status}${res.error ? ` (${res.error})` : ''}`,
      });
      await load();
    } catch (err) {
      setMessage({ type: 'err', text: (err as Error).message });
    } finally {
      setBusy(null);
    }
  };

  if (loading) {
    return <div className="p-8 text-sm text-slate-500">Loading change details...</div>;
  }
  if (!detail) {
    return <div className="p-8 text-sm text-red-600">Change request not found.</div>;
  }

  const steps = [
    { label: '1. ServiceNow Synced', done: true },
    { label: '2. Pre-Change Capture (T-1h)', done: detail.pre_snapshot_count > 0 },
    { label: '3. Post-Change Capture & Diff', done: detail.reports.length > 0 },
    {
      label: '4. Email Sent to Engineer',
      done: detail.reports.some((r) => r.email_status === 'sent'),
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <Link to="/" className="inline-flex items-center gap-1 text-xs font-medium text-indigo-600 hover:underline mb-1">
            <ArrowLeft className="w-3.5 h-3.5" />
            Back to Change Tracking
          </Link>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold font-mono text-slate-900">{detail.chg_number}</h1>
            <StatusBadge status={detail.status} />
          </div>
          <p className="text-sm text-slate-600 mt-1">{detail.title}</p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            disabled={busy !== null}
            onClick={handlePreCapture}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold bg-slate-800 hover:bg-slate-700 text-white disabled:opacity-50"
          >
            <Play className="w-4 h-4" />
            {busy === 'pre' ? 'Capturing...' : 'Capture Pre-Change Routes'}
          </button>
          <button
            type="button"
            disabled={busy !== null || detail.pre_snapshot_count === 0}
            onClick={handlePostCapture}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold bg-emerald-600 hover:bg-emerald-700 text-white disabled:opacity-50"
          >
            <Play className="w-4 h-4" />
            {busy === 'post' ? 'Comparing...' : 'Trigger Post-Change & Send Report'}
          </button>
        </div>
      </div>

      {message && (
        <div
          className={`px-4 py-3 rounded-lg text-sm border ${
            message.type === 'ok'
              ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
              : 'bg-red-50 text-red-800 border-red-200'
          }`}
        >
          {message.text}
        </div>
      )}

      {/* Workflow Stepper */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {steps.map((s) => (
          <div
            key={s.label}
            className={`rounded-xl border p-3.5 flex items-center gap-2.5 ${
              s.done
                ? 'bg-emerald-50/60 border-emerald-200 text-emerald-900'
                : 'bg-white border-slate-200 text-slate-500'
            }`}
          >
            <CheckCircle2
              className={`w-5 h-5 shrink-0 ${s.done ? 'text-emerald-600' : 'text-slate-300'}`}
            />
            <span className="text-xs font-semibold">{s.label}</span>
          </div>
        ))}
      </div>

      {/* Metadata & CIs */}
      <div className="bg-white rounded-xl border border-slate-200 p-5 grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
        <div>
          <div className="text-xs font-semibold text-slate-500 uppercase">Engineer Mailbox</div>
          <div className="mt-1 font-medium text-slate-900 flex items-center gap-1.5">
            <Mail className="w-4 h-4 text-slate-400" />
            {detail.engineer_name} ({detail.engineer_email})
          </div>
        </div>
        <div>
          <div className="text-xs font-semibold text-slate-500 uppercase">Scheduled Window</div>
          <div className="mt-1 text-slate-800">
            Start: {new Date(detail.scheduled_start).toLocaleString()}
          </div>
          <div className="text-xs text-slate-500">
            T-1h Auto Capture: {new Date(detail.capture_scheduled_at).toLocaleString()}
          </div>
        </div>
        <div>
          <div className="text-xs font-semibold text-slate-500 uppercase">Associated Network CIs</div>
          <div className="flex flex-wrap gap-1.5 mt-1">
            {detail.devices.map((dev) => (
              <span
                key={dev.id}
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-slate-100 border border-slate-200 text-xs font-mono"
              >
                <Server className="w-3 h-3 text-slate-400" />
                {dev.hostname} ({dev.ip_address})
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Comparison Reports */}
      <div className="space-y-5">
        <h2 className="text-lg font-bold text-slate-900">
          Device Comparison Reports ({detail.reports.length})
        </h2>
        {detail.reports.length === 0 ? (
          <div className="bg-white rounded-xl border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
            No comparison reports generated yet. Once the change completes, click{' '}
            <strong>Trigger Post-Change &amp; Send Report</strong> above.
          </div>
        ) : (
          detail.reports.map((report) => (
            <ReportViewer
              key={report.id}
              report={report}
              onPreviewEmail={handlePreviewEmail}
              onResendEmail={handleResendEmail}
            />
          ))
        )}
      </div>

      {/* Email Preview Modal */}
      {emailModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-4xl w-full max-h-[85vh] flex flex-col overflow-hidden">
            <div className="px-5 py-3.5 border-b border-slate-200 flex items-center justify-between bg-slate-50">
              <div>
                <div className="text-xs uppercase font-semibold text-slate-500">HTML Email Preview</div>
                <div className="text-sm font-bold text-slate-900">{emailModal.subject}</div>
              </div>
              <button
                type="button"
                onClick={() => setEmailModal(null)}
                className="p-1.5 rounded-lg hover:bg-slate-200 text-slate-600"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <iframe
              title="Email report preview"
              srcDoc={emailModal.html}
              className="w-full flex-1 min-h-[520px] border-0"
            />
          </div>
        </div>
      )}
    </div>
  );
};
