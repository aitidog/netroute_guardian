import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {
  annotatePathDiffs,
  buildComparisonCsv,
  ReportViewer,
} from '../components/ReportViewer';
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
          {
            next_hop: '',
            interface: '',
            protocol: 'sdwan_overlay',
            admin_distance: 15,
            metric: 100,
            peer_priority: null,
            raw_metric: '100 (AD:15)',
          },
        ],
        after_paths: [],
        removed_paths: [
          {
            next_hop: '',
            interface: '',
            protocol: 'sdwan_overlay',
            admin_distance: 15,
            metric: 50,
            peer_priority: null,
            raw_metric: '50 (AD:15)',
          },
          {
            next_hop: '',
            interface: '',
            protocol: 'sdwan_overlay',
            admin_distance: 15,
            metric: 100,
            peer_priority: null,
            raw_metric: '100 (AD:15)',
          },
        ],
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

    // Expanding row reveals before/after path panels & entry delta
    expect(screen.getByText('-2 entries')).toBeInTheDocument();
    await user.click(screen.getByText('10.132.0.0/14'));
    expect(screen.getByText(/Before Change Paths \(2\)/)).toBeInTheDocument();
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

  it('filters comparison results by Change Type, Rule, and search query without Severity column', async () => {
    const user = userEvent.setup();
    render(<ReportViewer report={mockReport} />);

    // Severity filter & column are intentionally removed; Important badge is highlighted
    expect(screen.queryByLabelText(/Filter by Severity/i)).not.toBeInTheDocument();
    expect(screen.getByText('Important')).toBeInTheDocument();

    // Switch to All Differences (contains 1 removed important + 1 added normal)
    await user.click(screen.getByRole('button', { name: /All Differences/i }));
    expect(screen.getByText('10.132.0.0/14')).toBeInTheDocument();
    expect(screen.getByText('10.156.43.128/25')).toBeInTheDocument();

    // Filter by Change Type = added
    await user.selectOptions(screen.getByLabelText(/Filter by Change Type/i), 'added');
    expect(screen.queryByText('10.132.0.0/14')).not.toBeInTheDocument();
    expect(screen.getByText('10.156.43.128/25')).toBeInTheDocument();

    // Combine with Rule = large_prefix -> 0 results
    await user.selectOptions(screen.getByLabelText(/Filter by Matched Rule/i), 'large_prefix');
    expect(screen.getByText(/No entries match the current filter criteria/i)).toBeInTheDocument();

    // Reset filters restores both entries
    await user.click(screen.getByRole('button', { name: /Reset/i }));
    expect(screen.getByText('10.132.0.0/14')).toBeInTheDocument();
    expect(screen.getByText('10.156.43.128/25')).toBeInTheDocument();

    // Filter by Rule = large_prefix alone
    await user.selectOptions(screen.getByLabelText(/Filter by Matched Rule/i), 'large_prefix');
    expect(screen.getByText('10.132.0.0/14')).toBeInTheDocument();
    expect(screen.queryByText('10.156.43.128/25')).not.toBeInTheDocument();

    // Reset and search by prefix substring
    await user.click(screen.getByRole('button', { name: /Reset/i }));
    await user.type(screen.getByLabelText(/Search prefix or explanation/i), '10.156');
    expect(screen.queryByText('10.132.0.0/14')).not.toBeInTheDocument();
    expect(screen.getByText('10.156.43.128/25')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Export Filtered CSV \(1\)/i })).toBeInTheDocument();
  });

  it('generates row-per-entry CSV with VRF/Protocol last and excluded columns omitted', async () => {
    const csvText = buildComparisonCsv('uec-abc-prd01', mockReport.report_payload.all_entries);
    const lines = csvText.trim().split('\n');
    const headers = lines[0].replace(/^\ufeff/, '').split(',');
    expect(headers.slice(0, 5)).toEqual([
      'Appliance',
      'Subnet/Mask',
      'Next Hop',
      'Interface',
      'Metric',
    ]);
    expect(headers.slice(-2)).toEqual(['VRF', 'Protocol']);
    for (const excluded of ['Severity', 'Affected_IPs', 'Fallback_Status', 'Fallback_Parent']) {
      expect(headers).not.toContain(excluded);
    }
    // 1 header + 2 removed entries for 10.132.0.0/14 + 1 added entry for 10.156.43.128/25
    expect(lines).toHaveLength(4);
    expect(csvText).toContain('50 (AD:15)');
    expect(csvText).toContain('100 (AD:15)');
    expect(csvText).toContain('10.156.43.128/25');

    const origCreate = URL.createObjectURL;
    const origRevoke = URL.revokeObjectURL;
    const createObjectURLMock = vi.fn().mockReturnValue('blob:mock-csv');
    const revokeObjectURLMock = vi.fn();
    URL.createObjectURL = createObjectURLMock;
    URL.revokeObjectURL = revokeObjectURLMock;
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});

    try {
      const user = userEvent.setup();
      render(<ReportViewer report={mockReport} />);
      await user.click(screen.getByRole('button', { name: /^Export CSV$/i }));

      expect(createObjectURLMock).toHaveBeenCalledTimes(1);
      expect(clickSpy).toHaveBeenCalledTimes(1);
      expect(revokeObjectURLMock).toHaveBeenCalledWith('blob:mock-csv');
    } finally {
      URL.createObjectURL = origCreate;
      URL.revokeObjectURL = origRevoke;
      clickSpy.mockRestore();
    }
  });

  it('color-codes removed (red), added (green), and unchanged (muted) route entries in summary and expanded path details', async () => {
    const sharedPath = {
      next_hop: '10.1.0.1',
      interface: 'eth0',
      protocol: 'bgp',
      admin_distance: 20,
      metric: 100,
      peer_priority: null,
      raw_metric: '100 (AD:20)',
    };
    const removedPath = {
      next_hop: '10.1.0.2',
      interface: 'eth1',
      protocol: 'bgp',
      admin_distance: 20,
      metric: 200,
      peer_priority: null,
      raw_metric: '200 (AD:20)',
    };
    const addedPath = {
      next_hop: '10.1.0.3',
      interface: 'eth2',
      protocol: 'bgp',
      admin_distance: 20,
      metric: 50,
      peer_priority: null,
      raw_metric: '50 (AD:20)',
    };

    const changedEntry = {
      ...mockReport.report_payload.important_entries[0],
      prefix: '0.0.0.0/0',
      prefix_len: 0,
      change_type: 'changed' as const,
      before_paths: [sharedPath, removedPath],
      after_paths: [sharedPath, addedPath],
      removed_paths: [removedPath],
      added_paths: [addedPath],
      unchanged_path_count: 1,
      importance_reasons: ['Pre-specified critical route (0.0.0.0/0)'],
    };

    const diffCheck = annotatePathDiffs(changedEntry);
    expect(diffCheck.before.map((x) => x.status)).toEqual(['unchanged', 'removed']);
    expect(diffCheck.after.map((x) => x.status)).toEqual(['unchanged', 'added']);

    const reportWithChanged: ComparisonReport = {
      ...mockReport,
      report_payload: {
        ...mockReport.report_payload,
        important_entries: [mockReport.report_payload.important_entries[0], changedEntry],
        all_entries: [
          mockReport.report_payload.important_entries[0],
          changedEntry,
          ...mockReport.report_payload.normal_entries,
        ],
      },
    };

    const user = userEvent.setup();
    render(<ReportViewer report={reportWithChanged} />);

    // Prefix text carries semantic colors: removed -> red, changed -> amber
    expect(screen.getByText('10.132.0.0/14')).toHaveClass('text-red-700');
    expect(screen.getByText('0.0.0.0/0')).toHaveClass('text-amber-800');

    // Expand changed entry to inspect path-level colors
    await user.click(screen.getByText('0.0.0.0/0'));
    const removedItem = screen.getByText(/NH: 10\.1\.0\.2/).closest('li');
    const addedItem = screen.getByText(/NH: 10\.1\.0\.3/).closest('li');
    const unchangedItems = screen.getAllByText(/NH: 10\.1\.0\.1/).map((el) => el.closest('li'));

    expect(removedItem).toHaveAttribute('data-path-status', 'removed');
    expect(removedItem).toHaveClass('text-red-700');
    expect(addedItem).toHaveAttribute('data-path-status', 'added');
    expect(addedItem).toHaveClass('text-emerald-700');
    for (const item of unchangedItems) {
      expect(item).toHaveAttribute('data-path-status', 'unchanged');
      expect(item).toHaveClass('text-slate-500');
    }

    // Switch to Normal tab and verify added prefix + expanded added path are green
    await user.click(screen.getByRole('button', { name: /Normal Differences/i }));
    expect(screen.getByText('10.156.43.128/25')).toHaveClass('text-emerald-700');
    await user.click(screen.getByText('10.156.43.128/25'));
    const normalAddedItem = screen.getByText(/50 \(AD:15\)/).closest('li');
    expect(normalAddedItem).toHaveAttribute('data-path-status', 'added');
    expect(normalAddedItem).toHaveClass('text-emerald-700');
  });
});
