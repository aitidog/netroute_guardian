import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ReportViewer } from '../components/ReportViewer';
import type { ComparisonReport } from '../types';

const mockReport: ComparisonReport = {
  id: 1,
  change_id: 10,
  device_id: 1,
  device_label: 'uec-abc-prd01',
  before_snapshot_id: 1,
  after_snapshot_id: 2,
  risk_level: 'CRITICAL',
  email_recipient: 'alex.rivera@netops.local',
  email_status: 'sent',
  email_error: null,
  email_sent_at: '2026-11-24T10:00:00Z',
  created_at: '2026-11-24T10:00:00Z',
  summary_stats: {
    device_label: 'uec-abc-prd01',
    before_raw_entries: 4442,
    after_raw_entries: 4411,
    before_unique_prefixes: 1775,
    after_unique_prefixes: 1766,
    removed_count: 10,
    added_count: 1,
    changed_count: 3,
    unchanged_count: 1762,
    total_differences: 14,
    important_count: 2,
    normal_count: 1,
    large_prefix_alert_count: 2,
    prespecified_alert_count: 1,
    large_prefix_threshold: 20,
    affected_ips_excluding_default: 360448,
    risk_level: 'CRITICAL',
  },
  report_payload: {
    device_label: 'uec-abc-prd01',
    risk_level: 'CRITICAL',
    executive_summary: 'Detected 14 prefix differences on uec-abc-prd01.',
    summary_stats: {
      device_label: 'uec-abc-prd01',
      before_raw_entries: 4442,
      after_raw_entries: 4411,
      before_unique_prefixes: 1775,
      after_unique_prefixes: 1766,
      removed_count: 10,
      added_count: 1,
      changed_count: 3,
      unchanged_count: 1762,
      total_differences: 14,
      important_count: 2,
      normal_count: 1,
      large_prefix_alert_count: 2,
      prespecified_alert_count: 1,
      large_prefix_threshold: 20,
      affected_ips_excluding_default: 360448,
      risk_level: 'CRITICAL',
    },
    important_entries: [
      {
        vrf: 'default',
        prefix: '10.132.0.0/14',
        prefix_len: 14,
        change_type: 'removed',
        before_paths: [
          {
            next_hop: '',
            interface: '',
            protocol: 'sdwan_overlay',
            admin_distance: 15,
            metric: 50,
            peer_priority: null,
            raw_metric: '50 (AD:15)',
          },
        ],
        after_paths: [],
        removed_paths: [],
        added_paths: [],
        unchanged_path_count: 0,
        is_important: true,
        matched_rules: ['large_prefix'],
        importance_reasons: ['Large subnet mask (/14 <= /20) is missing'],
        severity: 'CRITICAL',
        affected_ip_count: 262144,
        fallback_status: 'default_or_blackhole',
        fallback_parent_prefix: null,
        fallback_parent_egress: null,
        active_path_changed: null,
        backup_only_changed: null,
        best_before_summary: null,
        best_after_summary: null,
        next_hop_changes: [],
        findings: [],
        explanation: 'No covering non-default supernet remains in the post-change table.',
      },
    ],
    normal_entries: [
      {
        vrf: 'default',
        prefix: '10.156.43.128/25',
        prefix_len: 25,
        change_type: 'added',
        before_paths: [],
        after_paths: [
          {
            next_hop: '',
            interface: '',
            protocol: 'sdwan_overlay',
            admin_distance: 15,
            metric: 50,
            peer_priority: null,
            raw_metric: '50 (AD:15)',
          },
        ],
        removed_paths: [],
        added_paths: [],
        unchanged_path_count: 0,
        is_important: false,
        matched_rules: [],
        importance_reasons: [],
        severity: 'INFO',
        affected_ip_count: 128,
        fallback_status: null,
        fallback_parent_prefix: null,
        fallback_parent_egress: null,
        active_path_changed: null,
        backup_only_changed: null,
        best_before_summary: null,
        best_after_summary: null,
        next_hop_changes: [],
        findings: [],
        explanation: 'New prefix advertised (128 addresses).',
      },
    ],
    all_entries: [],
    pipeline_stages: [
      { name: 'normalize', description: 'Normalize routes', duration_ms: 1.2, details: {} },
      { name: 'diff', description: 'Diff prefixes', duration_ms: 0.8, details: {} },
    ],
  },
};
mockReport.report_payload.all_entries = [
  ...mockReport.report_payload.important_entries,
  ...mockReport.report_payload.normal_entries,
];

describe('ReportViewer', () => {
  it('emphasizes important entries, switches tabs, expands path details, and shows pipeline telemetry', async () => {
    const user = userEvent.setup();
    const onPreview = vi.fn();
    render(<ReportViewer report={mockReport} onPreviewEmail={onPreview} />);

    // Important tab is active by default
    expect(screen.getByText('10.132.0.0/14')).toBeInTheDocument();
    expect(screen.queryByText('10.156.43.128/25')).not.toBeInTheDocument();

    // Expanding row reveals before/after path panels
    await user.click(screen.getByText('10.132.0.0/14'));
    expect(screen.getByText(/Before Change Paths \(1\)/)).toBeInTheDocument();
    expect(screen.getByText(/Removed in post-change table/)).toBeInTheDocument();

    // Switch to Normal Differences tab
    await user.click(screen.getByRole('button', { name: /Normal Differences/i }));
    expect(screen.getByText('10.156.43.128/25')).toBeInTheDocument();

    // Toggle pipeline telemetry
    await user.click(screen.getByRole('button', { name: /Inspect Pipeline Stages/i }));
    expect(screen.getByText('1. normalize')).toBeInTheDocument();

    // Trigger email preview callback
    await user.click(screen.getByRole('button', { name: /Email Preview/i }));
    expect(onPreview).toHaveBeenCalledWith(1);
  });
});
