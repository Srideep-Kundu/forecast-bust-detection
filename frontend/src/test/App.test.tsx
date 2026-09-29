import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from '../App';
import { installMockApi } from './mockApi';
import { renderWithQuery } from './render';

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe('forecast dashboard', () => {
  it('renders the full historical-replay evidence flow from canonical API contracts', async () => {
    const fetchMock = installMockApi();
    renderWithQuery(<App />);

    expect(screen.getByText('Historical Replay')).toBeInTheDocument();
    expect(await screen.findByRole('heading', { name: 'Lakshadweep' })).toBeInTheDocument();
    await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThan(7));
    expect(await screen.findByRole('img', { name: /36 IMD meteorological subdivisions/i }, { timeout: 5000 })).toBeInTheDocument();
    expect(await screen.findByRole('img', { name: /Day 1 selected/i }, { timeout: 5000 })).toBeInTheDocument();
    expect(await screen.findByRole('heading', { name: 'Why the model shifted this risk' }, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Increases predicted bust risk' })).toHaveTextContent('500–850 hPa Thickness');
    expect(screen.getByRole('region', { name: 'Decreases predicted bust risk' })).toHaveTextContent('24-hour Precipitation');
    expect(screen.getByRole('heading', { name: 'Similar historical forecast states' })).toBeInTheDocument();
    expect(screen.getByText('Historical bust')).toBeInTheDocument();

    await userEvent.click(screen.getByText('Model and held-out evaluation'));
    expect(screen.getByText('0.7541')).toBeInTheDocument();
    expect(screen.getByText('mean-only-mvp-v2')).toBeInTheDocument();
  });

  it('switches lead day, updates the risk query, and highlights the selected lead', async () => {
    const fetchMock = installMockApi();
    renderWithQuery(<App />);
    await screen.findByRole('heading', { name: 'Lakshadweep' });

    await userEvent.selectOptions(screen.getByLabelText('Lead day'), '2');

    expect(await screen.findByRole('img', { name: /Day 2 selected/i }, { timeout: 5000 })).toBeInTheDocument();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('lead_day=2'),
      expect.anything(),
    ));
    expect(screen.getByText(/Day 2 · valid/)).toBeInTheDocument();
  });

  it('updates region summary, curve, and prediction evidence from keyboard selection', async () => {
    const fetchMock = installMockApi();
    renderWithQuery(<App />);
    await screen.findByRole('heading', { name: 'Lakshadweep' });

    await userEvent.selectOptions(screen.getByLabelText('Keyboard region selection'), 'imd-02');

    expect(await screen.findByRole('heading', { name: 'Test Region 2' })).toBeInTheDocument();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/v1/regions/imd-02/lead-curve'),
      expect.anything(),
    ));
    expect(await screen.findByText(/__imd-02__d01/)).toBeInTheDocument();
  });

  it('shows layout-matched loading and isolated secondary failure states', async () => {
    installMockApi({ delayExplanation: true });
    const { unmount } = renderWithQuery(<App />);
    expect(screen.getByRole('region', { name: 'Forecast controls' })).toHaveAttribute('aria-busy', 'true');
    expect(await screen.findByRole('img', { name: /Day 1 selected/i }, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getByLabelText('Loading deterministic explanation')).toHaveAttribute('aria-busy', 'true');
    unmount();

    installMockApi({ failExplanation: true });
    renderWithQuery(<App />);
    expect(await screen.findByText('Explanation unavailable', {}, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getByRole('img', { name: /Day 1 selected/i })).toBeInTheDocument();
  });

  it('renders actionable empty and independent risk-map error states', async () => {
    installMockApi({ emptyRuns: true });
    const { unmount } = renderWithQuery(<App />);
    expect(await screen.findByText('No replay runs')).toBeInTheDocument();
    unmount();

    installMockApi({ failRisk: true });
    renderWithQuery(<App />);
    const error = await screen.findByText('Risk map unavailable', {}, { timeout: 5000 });
    expect(error).toBeInTheDocument();
    expect(within(error.closest('.cds--inline-notification') ?? document.body).getByText(/Other panels remain available/)).toBeInTheDocument();
  });
});
