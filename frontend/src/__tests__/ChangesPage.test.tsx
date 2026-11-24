import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { api } from '../api/client';
import { ChangesPage } from '../pages/ChangesPage';

vi.mock('../api/client', () => ({
  api: {
    listChanges: vi.fn(),
    getSchedulerStatus: vi.fn(),
    dispatchSchedulerNow: vi.fn(),
    triggerPreCapture: vi.fn(),
    triggerPostCapture: vi.fn(),
  },
}));

describe('ChangesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.listChanges).mockResolvedValue([
      {
        id: 1,
        chg_number: 'CHG0042108',
        title: 'SD-WAN Hub & Core BGP Cutover',
        description: 'Planned cutover',
        scheduled_start: new Date(Date.now() + 3600_000).toISOString(),
        scheduled_end: null,
        capture_scheduled_at: new Date().toISOString(),
        engineer_name: 'Alex Rivera',
        engineer_email: 'alex.rivera@netops.local',
        status: 'pre_captured',
        sync_source: 'mock',
        retry_count: 0,
        last_error: null,
        synced_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        devices: [
          {
            id: 1,
            hostname: 'uec-abc-prd01',
            ip_address: '10.162.183.10',
            device_type: 'edgeconnect',
            connection_mode: 'mock',
            location: 'DC1',
            description: '',
            config_json: {},
            created_at: new Date().toISOString(),
          },
        ],
        pre_snapshot_count: 1,
        post_snapshot_count: 0,
        report_count: 0,
        highest_risk_level: null,
      },
    ]);
    vi.mocked(api.getSchedulerStatus).mockResolvedValue({
      running: true,
      servicenow_mode: 'mock',
      last_sync_at: new Date().toISOString(),
      last_dispatch_at: new Date().toISOString(),
      synced_changes_count: 1,
      pending_pre_captures: 0,
      next_due_capture_at: null,
      jobs: [],
    });
  });

  it('renders synced ServiceNow changes and triggers post-change comparison', async () => {
    vi.mocked(api.triggerPostCapture).mockResolvedValueOnce({
      succeeded_devices: ['uec-abc-prd01'],
      failed_devices: [],
      email_status: 'sent',
    });

    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <ChangesPage />
      </MemoryRouter>
    );

    expect(await screen.findByText('CHG0042108')).toBeInTheDocument();
    expect(screen.getByText('uec-abc-prd01')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /Post-Capture & Compare/i }));
    await waitFor(() => {
      expect(api.triggerPostCapture).toHaveBeenCalledWith(1);
    });
    expect(await screen.findByText(/Email status: sent/i)).toBeInTheDocument();
  });
});
