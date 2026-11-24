import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { api } from '../api/client';
import { ImportantRoutesPage } from '../pages/ImportantRoutesPage';

vi.mock('../api/client', () => ({
  api: {
    listImportantRoutes: vi.fn(),
    getSettings: vi.fn(),
    createImportantRoute: vi.fn(),
    updateImportantRoute: vi.fn(),
    deleteImportantRoute: vi.fn(),
    updateSettings: vi.fn(),
  },
}));

describe('ImportantRoutesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.listImportantRoutes).mockResolvedValue([
      {
        id: 1,
        prefix: '0.0.0.0/0',
        description: 'Default route',
        enabled: true,
        created_at: '2026-11-24T00:00:00Z',
        updated_at: '2026-11-24T00:00:00Z',
      },
      {
        id: 2,
        prefix: '10.76.12.0/23',
        description: 'Core subnet',
        enabled: true,
        created_at: '2026-11-24T00:00:00Z',
        updated_at: '2026-11-24T00:00:00Z',
      },
    ]);
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

  it('lists pre-specified important routes and submits a new critical route', async () => {
    vi.mocked(api.createImportantRoute).mockResolvedValueOnce({
      id: 3,
      prefix: '10.198.0.0/16',
      description: 'New DC',
      enabled: true,
      created_at: '2026-11-24T00:00:00Z',
      updated_at: '2026-11-24T00:00:00Z',
    });

    const user = userEvent.setup();
    render(<ImportantRoutesPage />);

    expect(await screen.findByText('10.76.12.0/23')).toBeInTheDocument();

    await user.type(screen.getByPlaceholderText(/10\.198\.0\.0\/16/i), '10.198.0.0/16');
    await user.type(screen.getByPlaceholderText(/Business service/i), 'New DC');
    await user.click(screen.getByRole('button', { name: /Add Route/i }));

    await waitFor(() => {
      expect(api.createImportantRoute).toHaveBeenCalledWith({
        prefix: '10.198.0.0/16',
        description: 'New DC',
        enabled: true,
      });
    });
  });
});
