import React, { useState } from 'react';
import { Download, FileDiff, Sparkles, Upload } from 'lucide-react';
import { api } from '../api/client';
import { ReportViewer } from '../components/ReportViewer';
import type { ComparisonReport } from '../types';

export const AdhocComparePage: React.FC = () => {
  const [beforeFile, setBeforeFile] = useState<File | null>(null);
  const [afterFile, setAfterFile] = useState<File | null>(null);
  const [deviceLabel, setDeviceLabel] = useState('custom-device-01');
  const [report, setReport] = useState<ComparisonReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleDemoCompare = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.runDemoCsvComparison();
      setReport(res);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const handleUploadCompare = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!beforeFile || !afterFile) {
      setError('Please select both a before-change file and an after-change file.');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await api.runAdhocComparison(beforeFile, afterFile, deviceLabel);
      setReport(res);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Ad-hoc Routing Table Compare</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Upload any two routing tables (EdgeConnect CSV, Cisco NX-OS, or IOS-XE) or run the built-in requirement sample files.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <a
            href="/api/v1/sample-data/before"
            download="subnetsExample_beforeChange.csv"
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold border border-slate-300 bg-white hover:bg-slate-50 text-slate-700"
          >
            <Download className="w-3.5 h-3.5" />
            Download Before CSV
          </a>
          <a
            href="/api/v1/sample-data/after"
            download="subnetsExample_afterChange.csv"
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold border border-slate-300 bg-white hover:bg-slate-50 text-slate-700"
          >
            <Download className="w-3.5 h-3.5" />
            Download After CSV
          </a>
          <button
            type="button"
            disabled={loading}
            onClick={handleDemoCompare}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold bg-indigo-600 hover:bg-indigo-700 text-white disabled:opacity-50"
          >
            <Sparkles className="w-4 h-4" />
            {loading ? 'Analyzing...' : 'Run Sample CSV Demo (before vs after)'}
          </button>
        </div>
      </div>

      {error && (
        <div className="px-4 py-3 rounded-lg text-sm bg-red-50 text-red-800 border border-red-200">
          {error}
        </div>
      )}

      <form
        onSubmit={handleUploadCompare}
        className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm grid grid-cols-1 md:grid-cols-4 gap-4 items-end"
      >
        <div>
          <label className="block text-xs font-semibold text-slate-600 uppercase mb-1">
            Device Label
          </label>
          <input
            type="text"
            value={deviceLabel}
            onChange={(e) => setDeviceLabel(e.target.value)}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            placeholder="uec-abc-prd01"
          />
        </div>
        <div>
          <label className="block text-xs font-semibold text-slate-600 uppercase mb-1">
            Before Change File
          </label>
          <input
            type="file"
            accept=".csv,.txt,.log"
            onChange={(e) => setBeforeFile(e.target.files?.[0] ?? null)}
            className="w-full text-xs text-slate-600 file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:bg-slate-100 file:font-semibold"
          />
        </div>
        <div>
          <label className="block text-xs font-semibold text-slate-600 uppercase mb-1">
            After Change File
          </label>
          <input
            type="file"
            accept=".csv,.txt,.log"
            onChange={(e) => setAfterFile(e.target.files?.[0] ?? null)}
            className="w-full text-xs text-slate-600 file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:bg-slate-100 file:font-semibold"
          />
        </div>
        <button
          type="submit"
          disabled={loading}
          className="inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold bg-slate-900 hover:bg-slate-800 text-white disabled:opacity-50"
        >
          <Upload className="w-4 h-4" />
          Compare Uploaded Files
        </button>
      </form>

      {report ? (
        <ReportViewer report={report} />
      ) : (
        <div className="bg-white rounded-xl border border-dashed border-slate-300 p-12 text-center">
          <FileDiff className="w-10 h-10 text-slate-300 mx-auto mb-3" />
          <div className="text-sm font-medium text-slate-600">
            Click <strong>Run Sample CSV Demo</strong> or upload two routing table files to inspect the comparison pipeline output.
          </div>
        </div>
      )}
    </div>
  );
};
