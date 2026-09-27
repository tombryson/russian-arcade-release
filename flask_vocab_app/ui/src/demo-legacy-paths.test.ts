import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterEach, expect, it, vi } from 'vitest';

// These classic scripts need a separate browser realm, including event listeners.
const { JSDOM } = createRequire(import.meta.url)('jsdom');
const source = (name: string) => readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), `../../static/js/${name}.js`), 'utf8');
const browsers: { close: () => void }[] = [];
function browser(base = '/demo', path = '/demo/') {
  const dom = new JSDOM(`<html><head><meta name="app-base-path" content="${base}">
    <meta name="csrf-token" content="demo-csrf"><meta name="learning-profile" content="personal-learning">
    <meta name="learning-account" content="hosted:demo-identity"></head><body></body></html>`,
  { url: `https://arcade.test${path}`, runScripts: 'outside-only', pretendToBeVisual: true });
  const w = dom.window;
  browsers.push(w);
  w.Request = Request;
  w.Headers = Headers;
  const transport = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => new Response('{}'));
  w.fetch = transport;
  w.eval(source('app_paths'));
  return { w, transport };
}
afterEach(() => { browsers.splice(0).forEach(w => w.close()); });

it('keeps demo activities and private media mounted while sharing packaged assets and sign-in', () => {
  const { w } = browser();
  for (const [input, expected] of [
    ['/', '/demo/'], ['/#flashcards', '/demo/#flashcards'],
    ['/writing/load/id?revision=1#answer', '/demo/writing/load/id?revision=1#answer'],
    ['/api/v1/user-session', '/demo/api/v1/user-session'],
    ['/trial/account', '/demo/trial/account'],
    ['/static/media/recording.mp3', '/demo/static/media/recording.mp3'],
    ['/static/uploads/page.png', '/demo/static/uploads/page.png'],
    ['https://arcade.test/lessons?view=cards', 'https://arcade.test/demo/lessons?view=cards'],
  ]) expect(w.arcadeUrl(input)).toBe(expected);
  for (const value of ['/demo/', '/demo/api/v1/user-session', '/static/css/style.css', '/post/assets/main.js',
    '/trial/sign-in/google?next=%2F', '/trial/callback', '/trial/callback/google', '/trial/connect/github', '/trial/sign-out',
    '#journey', './chunk.js', 'blob:https://arcade.test/recording', 'https://dictionary.test/word', '//cdn.test/file.js']) {
    expect(w.arcadeUrl(value)).toBe(value);
  }
  expect(w.arcadePath('/demo/comprehension/answer')).toBe('/comprehension/answer');
  expect(w.arcadePath('/demonstration')).toBe('/demonstration');
});

it('leaves the unmounted main application and its fetch inputs untouched', async () => {
  const { w, transport } = browser('', '/');
  const request = new Request('https://arcade.test/api/v1/user-session');
  expect(w.arcadeUrl('/api/v1/user-session')).toBe('/api/v1/user-session');
  expect(w.fetch).toBe(transport);
  await w.fetch(request);
  expect(transport.mock.calls[0][0]).toBe(request);
});

it('mounts Request fetches without losing their body, headers, cancellation or explicit options', async () => {
  const { w, transport } = browser();
  const controller = new AbortController();
  const request = new Request('https://arcade.test/writing/save', {
    method: 'POST', body: 'answer=Здравствуйте', headers: { 'X-Existing': 'kept' },
    credentials: 'same-origin', signal: controller.signal, cache: 'no-store',
  });
  const options: RequestInit = { redirect: 'error' };
  await w.fetch(request, options);
  const forwarded = transport.mock.calls[0][0] as Request;
  expect(forwarded.url).toBe('https://arcade.test/demo/writing/save');
  expect(forwarded.method).toBe('POST');
  expect(forwarded.headers.get('X-Existing')).toBe('kept');
  expect(forwarded.credentials).toBe('same-origin');
  expect(forwarded.cache).toBe('no-store');
  expect(await forwarded.text()).toBe('answer=Здравствуйте');
  controller.abort();
  expect(forwarded.signal.aborted).toBe(true);
  expect(transport.mock.calls[0][1]).toBe(options);
  const external = new Request('https://external.test/api');
  await w.fetch(external);
  expect(transport.mock.calls[1][0]).toBe(external);
});

it('mounts legacy HTMX and fetch requests while retaining account protection and the unbound session probe', async () => {
  const { w, transport } = browser();
  w.eval(source('household_security'));
  const detail = { path: '/comprehension/answer', headers: {} };
  w.document.dispatchEvent(new w.CustomEvent('htmx:configRequest', { detail }));
  expect(detail.path).toBe('/demo/comprehension/answer');
  expect(detail.headers).toMatchObject({ 'X-CSRF-Token': 'demo-csrf', 'X-Account-Scope': 'hosted:demo-identity' });
  await w.fetch('/writing/save', { method: 'POST', body: 'answer' });
  expect(transport.mock.calls[0][0]).toBe('/demo/writing/save');
  expect(new Headers(transport.mock.calls[0][1]?.headers).get('X-Account-Scope')).toBe('hosted:demo-identity');
  await w.fetch('/demo/api/v1/user-session');
  expect(transport.mock.calls[1][0]).toBe('/demo/api/v1/user-session');
  expect(new Headers(transport.mock.calls[1][1]?.headers).has('X-Account-Scope')).toBe(false);
});

it('preserves a keepalive Request body when mounting an unload write', async () => {
  const { w, transport } = browser();
  await w.fetch(new Request('https://arcade.test/api/v1/conversations/session/finish', {
    method: 'POST', body: '{}', keepalive: true,
  }));
  const forwarded = transport.mock.calls[0][0] as Request;
  expect(forwarded.url).toBe('https://arcade.test/demo/api/v1/conversations/session/finish');
  expect(forwarded.keepalive).toBe(true);
  expect(await forwarded.text()).toBe('{}');
});

it('checks the demo identity in a native page without the legacy security script', async () => {
  const { w, transport } = browser();
  w.document.body.innerHTML = '<span data-user-session data-profile-id="personal-learning" data-session-scope="hosted:demo-identity"></span>';
  transport.mockResolvedValue(new Response(JSON.stringify({
    mode: 'personal', profile: { id: 'personal-learning' }, session_scope: 'hosted:demo-identity',
  })));
  w.eval(source('user_sessions'));
  w.dispatchEvent(new w.StorageEvent('storage', { key: 'russian-arcade-session', newValue: 'personal account changed' }));
  await vi.waitFor(() => expect(transport).toHaveBeenCalledOnce());
  expect(transport.mock.calls[0][0]).toBe('/demo/api/v1/user-session');
  expect(w.location.pathname).toBe('/demo/');
});

it('keeps a legacy generation progress stream in the demo after an HTMX request', () => {
  const { w } = browser('/demo', '/demo/tools/anki/');
  w.document.body.innerHTML = '<main id="mainContent" data-page="flashcards"></main><form id="generate" hx-post="/demo/generate"></form><div id="result" data-session-id="task-123"></div><span id="progress"></span>';
  const streams: string[] = [];
  w.EventSource = class { constructor(url: string) { streams.push(url); } close() {} };
  w.requestAnimationFrame = vi.fn();
  w.eval(source('app_shell'));
  w.document.body.dispatchEvent(new w.CustomEvent('htmx:afterRequest', { detail: {
    elt: w.document.querySelector('#generate'), successful: true, xhr: { response: '' },
  } }));
  expect(streams).toEqual(['/demo/progress/task-123']);
});
