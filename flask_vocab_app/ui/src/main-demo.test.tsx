import { expect, it, vi } from 'vitest';
import { render } from 'preact';
import { screen, within } from '@testing-library/preact';

it('mounts the native demo with scoped activity navigation, account entry, and form return paths', async () => {
  history.replaceState(null, '', '/demo/');
  vi.stubGlobal('fetch', vi.fn(async () => ({ok:true,json:async()=>({profile_id:'guest',balance:0,skill:{status:'not_calibrated',skills:[]}})})));
  const root = document.createElement('div');
  root.id = 'word-post';
  root.dataset.view = 'app';
  root.dataset.accountMode = 'demo';
  root.dataset.signInAvailable = 'true';
  root.dataset.demoAvailable = 'true';
  root.dataset.sessionScope = 'demo:guest';
  root.dataset.profile = JSON.stringify({id:'guest',display_name:'Demo'});
  document.body.append(root);
  try {
    await import('./main');
    expect(screen.getByRole('link', {name:'Demo account'}).getAttribute('href')).toBe('/demo/trial/account');
    expect(screen.queryByRole('link', {name:'Try demo'})).toBeNull();
    expect(within(screen.getByRole('main')).getByRole('link', {name:/^Comprehension/}).getAttribute('href')).toBe('/demo/comprehension');
    const language = root.querySelector('form[action="/demo/ui-language"]');
    expect(language).toBeTruthy();
    expect(language?.querySelector<HTMLInputElement>('input[name="next"]')?.value).toBe('/demo/');
    expect(root.querySelector('form[action="/demo/ui-navigation"]')).toBeTruthy();
  } finally {
    render(null, root);
    root.remove();
    vi.unstubAllGlobals();
  }
});
