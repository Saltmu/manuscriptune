import { describe, it, expect } from 'vitest';
import { parseLineNumber } from './utils.js';

describe('parseLineNumber', () => {
  it('should return correct line number for L123', () => {
    expect(parseLineNumber('L123')).toBe(123);
  });

  it('should return null for invalid format', () => {
    expect(parseLineNumber('no-digits')).toBeNull();
  });

  it('should return null for empty input', () => {
    expect(parseLineNumber('')).toBeNull();
    expect(parseLineNumber(null)).toBeNull();
  });
});
