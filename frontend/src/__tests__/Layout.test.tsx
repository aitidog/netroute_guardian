import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { Layout } from '../components/Layout';

describe('Layout', () => {
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
});
