/** Typed REST API client for the NetRoute Guardian backend. */

import type {
  AppSettings,
  ChangeRequest,
  ChangeRequestDetail,
  ComparisonReport,
  Device,
  ImportantRoute,
  MockServiceNowChange,
  RouteSummaryResponse,
  SchedulerStatus,
} from '../types';

const API_BASE = '/api/v1';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body.detail === 'string') {
        detail = body.detail;
      } else if (Array.isArray(body.detail) && body.detail[0]?.msg) {
        detail = body.detail[0].msg;
      }
    } catch {
      // Fallback to status message when body is non-JSON.
    }
    throw new Error(detail);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return (await res.json()) as T;
}

export const api = {
  // Feature 1: Changes & Workflow
  listChanges: () => request<ChangeRequest[]>('/changes'),
  getChange: (id: number) => request<ChangeRequestDetail>(`/changes/${id}`),
  syncChanges: () => request<{ synced_count: number; chg_numbers: string[] }>('/changes/sync', { method: 'POST' }),
  triggerPreCapture: (id: number) =>
    request<{ succeeded_devices: string[]; failed_devices: Array<{ hostname: string; error: string }> }>(
      `/changes/${id}/trigger-pre-capture`,
      { method: 'POST' }
    ),
  triggerPostCapture: (id: number) =>
    request<{
      succeeded_devices: string[];
      failed_devices: Array<{ hostname: string; error: string }>;
      email_status: string | null;
    }>(`/changes/${id}/trigger-post-capture`, { method: 'POST' }),

  // Reports & Ad-hoc Comparison
  getReportEmailPreview: (reportId: number) =>
    request<{ subject: string; html: string }>(`/reports/${reportId}/email-preview`),
  resendReportEmail: (reportId: number, recipientEmail?: string) => {
    const qs = recipientEmail ? `?recipient_email=${encodeURIComponent(recipientEmail)}` : '';
    return request<{ status: string; recipient_email: string; error: string | null }>(
      `/reports/${reportId}/resend-email${qs}`,
      { method: 'POST' }
    );
  },
  runDemoCsvComparison: () =>
    request<ComparisonReport>('/comparisons/demo-csv', { method: 'POST' }),
  runAdhocComparison: (beforeFile: File, afterFile: File, deviceLabel: string) => {
    const fd = new FormData();
    fd.append('before_file', beforeFile);
    fd.append('after_file', afterFile);
    fd.append('device_label', deviceLabel);
    return request<ComparisonReport>('/comparisons/adhoc', { method: 'POST', body: fd });
  },

  // Feature 1: Pre-specified Important Routes
  listImportantRoutes: () => request<ImportantRoute[]>('/important-routes'),
  createImportantRoute: (payload: { prefix: string; description: string; enabled: boolean }) =>
    request<ImportantRoute>('/important-routes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  updateImportantRoute: (
    id: number,
    payload: { prefix?: string; description?: string; enabled?: boolean }
  ) =>
    request<ImportantRoute>(`/important-routes/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  deleteImportantRoute: (id: number) =>
    request<void>(`/important-routes/${id}`, { method: 'DELETE' }),

  // Feature 2: Route Summary
  summarizeDevice: (query: string, includeSupernetSuggestions: boolean) =>
    request<RouteSummaryResponse>('/route-summary/device', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query,
        include_supernet_suggestions: includeSupernetSuggestions,
      }),
    }),
  summarizeText: (rawText: string, sourceLabel: string, includeSupernetSuggestions: boolean) =>
    request<RouteSummaryResponse>('/route-summary/text', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        raw_text: rawText,
        source_label: sourceLabel,
        include_supernet_suggestions: includeSupernetSuggestions,
      }),
    }),
  summarizeFile: (file: File, includeSupernetSuggestions: boolean) => {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('include_supernet_suggestions', String(includeSupernetSuggestions));
    return request<RouteSummaryResponse>('/route-summary/upload', { method: 'POST', body: fd });
  },
  summarizeDemoCsv: (includeSupernetSuggestions: boolean) =>
    request<RouteSummaryResponse>(
      `/route-summary/demo-csv?include_supernet_suggestions=${includeSupernetSuggestions}`,
      { method: 'POST' }
    ),

  // Devices & ServiceNow Simulator & Settings
  listDevices: () => request<Device[]>('/devices'),
  listMockSnowChanges: () => request<MockServiceNowChange[]>('/mock-servicenow/changes'),
  createMockSnowChange: (payload: {
    chg_number?: string;
    title: string;
    description: string;
    scheduled_start: string;
    engineer_name: string;
    engineer_email: string;
    ci_device_ids: number[];
  }) =>
    request<MockServiceNowChange>('/mock-servicenow/changes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  updateMockSnowChange: (
    id: number,
    payload: Partial<{
      title: string;
      scheduled_start: string;
      state: 'scheduled' | 'implement' | 'closed' | 'cancelled';
      engineer_email: string;
    }>
  ) =>
    request<MockServiceNowChange>(`/mock-servicenow/changes/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  getSettings: () => request<AppSettings>('/settings'),
  updateSettings: (payload: Partial<AppSettings>) =>
    request<AppSettings>('/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  getSchedulerStatus: () => request<SchedulerStatus>('/scheduler/status'),
  dispatchSchedulerNow: () =>
    request<{ synced_count: number; dispatched_change_ids: number[] }>('/scheduler/dispatch-now', {
      method: 'POST',
    }),
};
