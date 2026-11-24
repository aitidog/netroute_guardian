import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { api } from '../api/client';
import { SimulatorPage } from '../pages/SimulatorPage';

vi.mock('../api/client', () => ({
  api: {
    listDevices: vi.fn(),
    listMockSnowChanges: vi.fn(),
    getSchedulerStatus: vi.fn(),
    getSettings: vi.fn(),
    createMockSnowChange: vi.fn(),
    updateMockSnowChange: vi.fn(),
    dispatchSchedulerNow: vi.fn(),
  },
}));

describe('SimulatorPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.listDevices).mockResolvedValue([
      {
        id: 1,
        hostname: 'uec-abc-prd01',
        ip_address: '10.162.183.10',
        device_type: 'edgeconnect',
        connection_mode: 'mock',
        location: 'DC1',
        description: 'EdgeConnect CSV fixture',
        config_json: {},
        created_at: new Date().toISOString(),
      },
    ]);
    vi.mocked(api.listMockSnowChanges).mockResolvedValue([]);
    vi.mocked(api.getSchedulerStatus).mockResolvedValue({
      running: true,
      servicenow_mode: 'mock',
      last_sync_at: null,
      last_dispatch_at: null,
      synced_changes_count: 0,
      pending_pre_captures: 0,
      next_due_capture_at: null,
      jobs: [],
    });
    vi.mocked(api.getSettings).mockResolvedValue({
      servicenow_mode: 'mock',
      servicenow_window_hours: 24,
      pre_capture_lead_minutes: 60,
      large_prefix_threshold: 20,
      max_concurrent_device_collections: 10,
      pipeline_executor_mode: 'process',
      pipeline_max_workers: 4,
      mailpit_web_url: 'http://localhost:8025',
    });
  });

  it('displays concurrency settings and creates a simulated ServiceNow change', async () => {
    vi.mocked(api.createMockSnowChange).mockResolvedValueOnce({
      id: 99,
      chg_number: 'CHG0099001',
      title: 'Emergency WAN Failover & Core Route Update',
      description: '',
      scheduled_start: new Date().toISOString(),
      scheduled_end: null,
      engineer_name: 'Morgan Taylor',
      engineer_email: 'morgan.taylor@netops.local',
      state: 'scheduled',
      ci_device_ids: [1],
      updated_at: new Date().toISOString(),
    });

    const user = userEvent.setup();
    render(<SimulatorPage />);

    expect(await screen.findByText(/PROCESS \(4 workers\)/i)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Schedule Change in Mock ServiceNow/i }));

    await waitFor(() => {
      expect(api.createMockSnowChange).toHaveBeenCalledTimes(1);
    });
    expect(await screen.findByText(/CHG0099001/)).toBeInTheDocument();
  });
});
