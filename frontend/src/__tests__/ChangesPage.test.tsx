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
    deleteChange: vi.fn(),
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

  it('shows delete action only for completed changes and confirms deletion', async () => {
    const baseDevice = {
      id: 1,
      hostname: 'uec-abc-prd01',
      ip_address: '10.162.183.10',
      device_type: 'edgeconnect' as const,
      connection_mode: 'mock' as const,
      location: 'DC1',
      description: '',
      config_json: {},
      created_at: new Date().toISOString(),
    };
    const nowIso = new Date().toISOString();

    vi.mocked(api.listChanges).mockResolvedValueOnce([
      {
        id: 1,
        chg_number: 'CHG0042108',
        title: 'Active Pre-Captured Change',
        description: '',
        scheduled_start: nowIso,
        scheduled_end: null,
        capture_scheduled_at: nowIso,
        engineer_name: 'Alex Rivera',
        engineer_email: 'alex.rivera@netops.local',
        status: 'pre_captured',
        sync_source: 'mock',
        retry_count: 0,
        last_error: null,
        synced_at: nowIso,
        updated_at: nowIso,
        devices: [baseDevice],
        pre_snapshot_count: 1,
        post_snapshot_count: 0,
        report_count: 0,
        highest_risk_level: null,
      },
      {
        id: 2,
        chg_number: 'CHG0042199',
        title: 'Finished Core Cutover',
        description: '',
        scheduled_start: nowIso,
        scheduled_end: null,
        capture_scheduled_at: nowIso,
        engineer_name: 'Alex Rivera',
        engineer_email: 'alex.rivera@netops.local',
        status: 'completed',
        sync_source: 'mock',
        retry_count: 0,
        last_error: null,
        synced_at: nowIso,
        updated_at: nowIso,
        devices: [baseDevice],
        pre_snapshot_count: 1,
        post_snapshot_count: 1,
        report_count: 1,
        highest_risk_level: 'HIGH',
      },
    ]);
    vi.mocked(api.deleteChange).mockResolvedValueOnce(undefined);

    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <ChangesPage />
      </MemoryRouter>
    );

    expect(await screen.findByText('CHG0042199')).toBeInTheDocument();
    // Active (pre_captured) change must NOT offer Delete
    expect(screen.queryByRole('button', { name: 'Delete CHG0042108' })).not.toBeInTheDocument();
    // Completed change MUST offer Delete
    const deleteBtn = screen.getByRole('button', { name: 'Delete CHG0042199' });
    await user.click(deleteBtn);

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText(/Delete Completed Change Request\?/i)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /Confirm Delete/i }));
    await waitFor(() => {
      expect(api.deleteChange).toHaveBeenCalledWith(2);
    });
    expect(await screen.findByText(/Deleted completed change request CHG0042199/i)).toBeInTheDocument();
  });
});
