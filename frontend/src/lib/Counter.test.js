import { render, screen, fireEvent } from '@testing-library/svelte';
import { describe, it, expect } from 'vitest';
import Counter from './Counter.svelte';

describe('Counter Component', () => {
  it('renders with initial count 0', () => {
    render(Counter);
    const button = screen.getByRole('button');
    expect(button.textContent).toBe('Count is 0');
  });

  it('increments when clicked', async () => {
    render(Counter);
    const button = screen.getByRole('button');
    expect(button.textContent).toBe('Count is 0');
    
    await fireEvent.click(button);
    expect(button.textContent).toBe('Count is 1');
    
    await fireEvent.click(button);
    expect(button.textContent).toBe('Count is 2');
  });
});
