import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it } from 'vitest';
import { Layout } from '../components/Layout';

describe('Layout', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it('pins the sidebar to viewport height so the Mailpit inbox button stays visible when main content overflows', () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<div style={{ height: '4000px' }}>Long report content</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    );

    const shell = container.firstElementChild as HTMLElement;
    const aside = container.querySelector('aside') as HTMLElement;
    const nav = container.querySelector('nav') as HTMLElement;
    const main = container.querySelector('main') as HTMLElement;
    const mailpitLink = screen.getByRole('link', { name: /Open Mailpit Inbox/i });

    expect(shell.className).toContain('h-screen');
    expect(shell.className).toContain('overflow-hidden');
    expect(aside.className).toContain('h-full');
    expect(aside.className).toContain('overflow-hidden');
    expect(nav.className).toContain('overflow-y-auto');
    expect(main.className).toContain('h-full');
    expect(main.className).toContain('overflow-y-auto');
    expect(mailpitLink.getAttribute('href')).toBe('http://localhost:8025');
  });

  it('collapses the sidebar to an icon-only rail and restores it on toggle', async () => {
    const user = userEvent.setup();
    const { container } = render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<div>Content</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    );

    const aside = container.querySelector('aside') as HTMLElement;
    expect(aside.className).toContain('w-64');
    expect(screen.getByText('NetRoute Guardian')).toBeInTheDocument();
    expect(screen.getByText('Change Tracking')).toBeInTheDocument();

    // Collapse to icon-only rail
    await user.click(screen.getByRole('button', { name: /Collapse sidebar/i }));
    expect(aside.className).toContain('w-16');
    expect(screen.queryByText('NetRoute Guardian')).not.toBeInTheDocument();
    expect(screen.queryByText('Change Tracking')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Change Tracking' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Open Mailpit Inbox/i })).toBeInTheDocument();
    expect(window.localStorage.getItem('netroute.sidebar.collapsed')).toBe('true');

    // Expand back to full sidebar
    await user.click(screen.getByRole('button', { name: /Expand sidebar/i }));
    expect(aside.className).toContain('w-64');
    expect(screen.getByText('NetRoute Guardian')).toBeInTheDocument();
    expect(window.localStorage.getItem('netroute.sidebar.collapsed')).toBe('false');
  });
});
