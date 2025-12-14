import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, test } from 'vitest';

import App from './App';

test('renders MAIS shell and disables start when topic is empty', async () => {
  render(<App />);
  expect(screen.getByText('MAIS')).toBeInTheDocument();

  const topic = screen.getByLabelText(/global topic/i);
  await userEvent.clear(topic);

  const start = screen.getByRole('button', { name: /start simulation/i });
  expect(start).toBeDisabled();
});

test('custom mode enables editing stage text', async () => {
  render(<App />);
  // In some React setups, multiple matches can exist; pick the first matching mode button.
  await userEvent.click(screen.getAllByRole('button', { name: /custom/i })[0]!);
  const stages = screen.getAllByLabelText(/stage \(prepended to system prompt\)/i);
  expect(stages.some((el) => !el.hasAttribute('readonly'))).toBe(true);
});


