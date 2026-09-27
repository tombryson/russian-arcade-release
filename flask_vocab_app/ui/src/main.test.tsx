import { expect, it } from 'vitest';
import { render } from 'preact';
import { screen, within } from '@testing-library/preact';

it('replaces the server loading fallback when the application mounts', async () => {
  const root = document.createElement('div');
  root.id = 'word-post';
  root.dataset.view = 'app';
  root.dataset.accountMode = 'preview';
  root.dataset.signInAvailable = 'true';
  root.dataset.sessionScope = 'preview';
  root.dataset.profile = JSON.stringify({id:'demo-preview',display_name:'Demo'});
  root.innerHTML = '<section><h1>Opening your activities…</h1><a href="/tools/anki/">Existing workspace</a></section>';
  document.body.append(root);
  try {
    await import('./main');
    expect(screen.queryByRole('heading', { name: 'Opening your activities…' })).toBeNull();
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    expect(within(screen.getByRole('main')).getByRole('link', { name: /^Comprehension/ })).toBeTruthy();
    const account=screen.getByRole('link',{name:'Sign in'});
    expect(account.getAttribute('href')).toBe('/trial/account');
    expect(account.textContent).toBe('Sign in');
    expect(account.getAttribute('data-profile-id')).toBe('demo-preview');
    expect(account.getAttribute('data-session-scope')).toBe('preview');
  } finally {
    render(null, root);
    root.remove();
  }
});
