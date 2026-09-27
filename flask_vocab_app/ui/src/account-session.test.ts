import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it, vi } from 'vitest';

const source = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), '../../static/js/user_sessions.js'), 'utf8');

function watcher(scope: string | undefined, response: object) {
  const reload = vi.fn();
  const listeners: Record<string, (event: unknown) => Promise<void>> = {};
  let check: () => Promise<void> = async () => {};
  const window = {
    addEventListener: (name: string, callback: typeof listeners[string]) => { listeners[name] = callback; },
    location: { pathname: '/', reload, assign: vi.fn() },
    history: { replaceState: vi.fn() },
  };
  const document = {
    visibilityState: 'visible',
    querySelector: () => ({ dataset: { profileId: 'personal-learning', sessionScope: scope } }),
    addEventListener: vi.fn(),
  };
  new Function('window', 'document', 'fetch', 'localStorage', 'setInterval', source)(
    window, document, async () => ({ ok: true, json: async () => response }),
    { setItem: vi.fn() }, (callback: typeof check) => { check = callback; },
  );
  return { check, reload, window };
}

describe('Account changes in another tab', () => {
  it('reloads when two hosted accounts have the same local profile ID', async () => {
    const state = watcher('hosted:first', { mode: 'personal', profile: { id: 'personal-learning' }, session_scope: 'hosted:second' });
    await state.check();
    expect(state.window.history.replaceState).toHaveBeenCalledWith(null, '', '/#home');
    expect(state.reload).toHaveBeenCalledOnce();
  });

  it('keeps the page when both account and profile are unchanged', async () => {
    const state = watcher('hosted:first', { mode: 'personal', profile: { id: 'personal-learning' }, session_scope: 'hosted:first' });
    await state.check();
    expect(state.reload).not.toHaveBeenCalled();
  });

  it('still notices local profile switches without a scope marker', async () => {
    const state = watcher(undefined, { mode: 'personal', profile: { id: 'another-profile' } });
    await state.check();
    expect(state.reload).toHaveBeenCalledOnce();
  });
});
