import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { api } from '../api/client';
import { RouteSummaryPage } from '../pages/RouteSummaryPage';
import type { RouteSummaryResponse } from '../types';

vi.mock('../api/client', () => ({
  api: {
    summarizeDevice: vi.fn(),
    summarizeText: vi.fn(),
    summarizeFile: vi.fn(),
    summarizeDemoCsv: vi.fn(),
  },
}));

const mockSummary: RouteSummaryResponse = {
  source_label: 'uec-abc-prd01',
  device_type: 'edgeconnect',
  device_ip: '10.162.183.10',
  total_raw_entries: 8,
  total_unique_prefixes: 7,
  ignored_default_routes: 1,
  output_route_count: 4,
  summary_route_count: 2,
  remaining_route_count: 2,
  covered_route_count: 3,
  compression_ratio_pct: 42.86,
  vrf_groups: [],
  summary_routes: [
    {
      vrf: 'default',
      prefix: '10.1.0.0/16',
      prefix_len: 16,
      is_summary: true,
      covered_count: 2,
      covered_routes: ['10.1.1.0/24', '10.1.5.0/25'],
    },
    {
      vrf: 'default',
      prefix: '172.16.2.0/24',
      prefix_len: 24,
      is_summary: true,
      covered_count: 1,
      covered_routes: ['172.16.2.128/26'],
    },
  ],
  remaining_routes: [
    {
      vrf: 'default',
      prefix: '10.2.2.0/26',
      prefix_len: 26,
      is_summary: false,
      covered_count: 0,
      covered_routes: [],
    },
    {
      vrf: 'default',
      prefix: '192.168.8.0/26',
      prefix_len: 26,
      is_summary: false,
      covered_count: 0,
      covered_routes: [],
    },
  ],
  all_output_routes: [
    {
      vrf: 'default',
      prefix: '10.1.0.0/16',
      prefix_len: 16,
      is_summary: true,
      covered_count: 2,
      covered_routes: ['10.1.1.0/24', '10.1.5.0/25'],
    },
    {
      vrf: 'default',
      prefix: '10.2.2.0/26',
      prefix_len: 26,
      is_summary: false,
      covered_count: 0,
      covered_routes: [],
    },
    {
      vrf: 'default',
      prefix: '172.16.2.0/24',
      prefix_len: 24,
      is_summary: true,
      covered_count: 1,
      covered_routes: ['172.16.2.128/26'],
    },
    {
      vrf: 'default',
      prefix: '192.168.8.0/26',
      prefix_len: 26,
      is_summary: false,
      covered_count: 0,
      covered_routes: [],
    },
  ],
  supernet_suggestions: null,
  pipeline_stages: [],
};

describe('RouteSummaryPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('queries device routes by hostname/IP and expands covered sub-routes', async () => {
    vi.mocked(api.summarizeDevice).mockResolvedValueOnce(mockSummary);
    const user = userEvent.setup();

    render(<RouteSummaryPage />);
    await user.click(screen.getByRole('button', { name: /Fetch & Summarize/i }));

    await waitFor(() => {
      expect(api.summarizeDevice).toHaveBeenCalledWith('uec-abc-prd01', false);
    });

    expect(screen.getByText('10.1.0.0/16')).toBeInTheDocument();
    expect(screen.getByText('10.2.2.0/26')).toBeInTheDocument();
    expect(screen.getByText('42.86%')).toBeInTheDocument();

    // Expand summary route to inspect covered sub-routes
    await user.click(screen.getByText('10.1.0.0/16'));
    expect(screen.getByText('10.1.1.0/24')).toBeInTheDocument();
    expect(screen.getByText('10.1.5.0/25')).toBeInTheDocument();
  });
});
