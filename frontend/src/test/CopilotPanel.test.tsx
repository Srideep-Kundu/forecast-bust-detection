import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from '../App';
import { installMockApi } from './mockApi';
import { renderWithQuery } from './render';

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe('AI Copilot panel', () => {
  it('renders as a secondary grounded panel with disclaimer and disabled submit', async () => {
    installMockApi();
    renderWithQuery(<App />);
    expect(await screen.findByRole('heading', { name: 'AI Copilot' }, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getByText(/does not independently predict weather or replace meteorological analysis/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Ask Copilot' })).toBeDisabled();
  });

  it('supports quick prompts, keyboard input, mode selection, and a grounded response', async () => {
    const fetchMock = installMockApi();
    const user = userEvent.setup();
    renderWithQuery(<App />);
    await screen.findByRole('heading', { name: 'AI Copilot' }, { timeout: 5000 });

    await user.click(screen.getByRole('button', { name: 'Which factor matters most?' }));
    expect(screen.getByLabelText('Question about this prediction')).toHaveValue('Which factor matters most?');
    await user.selectOptions(screen.getByLabelText('Explanation mode'), 'meteorological');
    await user.tab();
    await user.click(screen.getByRole('button', { name: 'Ask Copilot' }));

    expect(await screen.findByText(/500–850 hPa Thickness increased/i)).toBeInTheDocument();
    expect(screen.getByLabelText('Evidence grounding sources')).toHaveTextContent('Bust Probability');
    expect(screen.getByLabelText('Evidence grounding sources')).toHaveTextContent('Historical Analogs');
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/v1/copilot/query'),
      expect.objectContaining({ method: 'POST', body: expect.stringContaining('meteorological') }),
    ));
  });

  it('shows an accessible loading state while the request is pending', async () => {
    installMockApi({ delayCopilot: true });
    const user = userEvent.setup();
    renderWithQuery(<App />);
    await screen.findByRole('heading', { name: 'AI Copilot' }, { timeout: 5000 });
    await user.type(screen.getByLabelText('Question about this prediction'), 'Explain the evidence');
    await user.click(screen.getByRole('button', { name: 'Ask Copilot' }));
    expect(screen.getByText('Generating…')).toBeDisabled();
    expect(document.querySelector('.copilot-answer')).toHaveAttribute('aria-busy', 'true');
  });

  it('renders deterministic fallback and isolates provider errors', async () => {
    installMockApi({ degradedCopilot: true });
    const user = userEvent.setup();
    const { unmount } = renderWithQuery(<App />);
    await screen.findByRole('heading', { name: 'AI Copilot' }, { timeout: 5000 });
    await user.click(screen.getByRole('button', { name: 'Why is this forecast risky?' }));
    await user.click(screen.getByRole('button', { name: 'Ask Copilot' }));
    expect(await screen.findByText('Deterministic evidence summary')).toBeInTheDocument();
    expect(screen.getByText(/AI explanation temporarily unavailable/i)).toBeInTheDocument();
    unmount();

    installMockApi({ failCopilot: true });
    renderWithQuery(<App />);
    await screen.findByRole('heading', { name: 'AI Copilot' }, { timeout: 5000 });
    await user.click(screen.getByRole('button', { name: 'Why is this forecast risky?' }));
    await user.click(screen.getByRole('button', { name: 'Ask Copilot' }));
    expect(await screen.findByText(/Deterministic model evidence remains available above/i)).toBeInTheDocument();
    expect(screen.getByRole('img', { name: /Day 1 selected/i })).toBeInTheDocument();
  });

  it('resets the answer when the selected prediction changes', async () => {
    installMockApi();
    const user = userEvent.setup();
    renderWithQuery(<App />);
    await screen.findByRole('heading', { name: 'AI Copilot' }, { timeout: 5000 });
    await user.click(screen.getByRole('button', { name: 'Why is this forecast risky?' }));
    await user.click(screen.getByRole('button', { name: 'Ask Copilot' }));
    expect(await screen.findByRole('heading', { name: 'Grounded explanation' })).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText('Lead day'), '2');
    await screen.findByText(/Day 2 · valid/);
    await waitFor(() => expect(screen.queryByRole('heading', { name: 'Grounded explanation' })).not.toBeInTheDocument());
    expect(screen.getByLabelText('Question about this prediction')).toHaveValue('');
  });
});
