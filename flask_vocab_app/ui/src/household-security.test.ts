import { afterAll, afterEach, beforeAll, expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const source = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), '../../static/js/household_security.js'), 'utf8');

const transport = vi.fn<typeof window.fetch>(async () => new Response('{}'));
let originalFetch: typeof window.fetch;
const metadata: HTMLMetaElement[] = [];

beforeAll(() => {
  for (const [name, content] of [['csrf-token', 'fixture-token'], ['learning-profile', 'fixture-profile'], ['learning-account', 'hosted:fixture-account']]) {
    const meta = document.createElement('meta');
    meta.name = name;
    meta.content = content;
    document.head.append(meta);
    metadata.push(meta);
  }
  originalFetch = window.fetch;
  window.fetch = transport;
  // Execute the actual classic script once, as the legacy document does.
  Function(source)();
});

afterEach(() => { document.body.innerHTML = ''; });
afterAll(() => {
  window.fetch = originalFetch;
  metadata.forEach(meta => meta.remove());
});

function form(method?: string) {
  const element = document.createElement('form');
  element.action = '/sentences/saved';
  if (method) element.method = method;
  element.innerHTML = '<input name="q" value="семья"><button type="submit">Submit</button>';
  document.body.append(element);
  return element;
}

function submit(element: HTMLFormElement, submitter: HTMLElement | null = null) {
  element.dispatchEvent(new SubmitEvent('submit', { bubbles: true, cancelable: true, submitter }));
}

function formData(element: HTMLFormElement) {
  const data = new FormData(element);
  // jsdom does not emit formdata when FormData is constructed.
  const event = new Event('formdata', { bubbles: true });
  Object.defineProperty(event, 'formData', { value: data });
  element.dispatchEvent(event);
  return data;
}

it('preserves bodies and existing headers while adding CSRF and profile headers to local fetches', async () => {
  await window.fetch('/sync', { method: 'POST', body: 'fixture' });
  const init = transport.mock.calls[0][1] as RequestInit;
  expect(new Headers(init.headers).get('X-CSRF-Token')).toBe('fixture-token');
  expect(new Headers(init.headers).get('X-Profile-ID')).toBe('fixture-profile');
  expect(new Headers(init.headers).get('X-Account-Scope')).toBe('hosted:fixture-account');
  expect(init.body).toBe('fixture');

  const request = new Request(`${window.location.origin}/writing/save`, {
    method: 'POST', headers: { 'X-Existing': 'kept' }, body: 'answer',
  });
  await window.fetch(request);
  const requestHeaders = new Headers((transport.mock.calls[1][1] as RequestInit).headers);
  expect(requestHeaders.get('X-Existing')).toBe('kept');
  expect(requestHeaders.get('X-CSRF-Token')).toBe('fixture-token');
  expect(requestHeaders.get('X-Profile-ID')).toBe('fixture-profile');
  expect(transport.mock.calls[1][0]).toBe(request);
});

it('does not add household headers to external fetches', async () => {
  await window.fetch('https://external.invalid/upload', { method: 'POST', body: 'fixture' });
  const headers = new Headers((transport.mock.calls[0][1] as RequestInit).headers);
  expect(headers.has('X-CSRF-Token')).toBe(false);
  expect(headers.has('X-Profile-ID')).toBe(false);
  expect(headers.has('X-Account-Scope')).toBe(false);
});

it('leaves the current-session probe unbound so the watcher can detect an account change', async () => {
  await window.fetch('/api/v1/user-session');
  const headers = new Headers((transport.mock.calls[0][1] as RequestInit).headers);
  expect(headers.has('X-Account-Scope')).toBe(false);
});

it('keeps CSRF and profile headers on local HTMX requests only', () => {
  const local = { path: '/sync_vocab', headers: { 'X-Existing': 'kept' } as Record<string, string> };
  document.dispatchEvent(new CustomEvent('htmx:configRequest', { detail: local }));
  expect(local.headers).toEqual({
    'X-Existing': 'kept', 'X-CSRF-Token': 'fixture-token', 'X-Profile-ID': 'fixture-profile',
    'X-Account-Scope': 'hosted:fixture-account',
  });
  const external = { path: 'https://external.invalid/upload', headers: {} };
  document.dispatchEvent(new CustomEvent('htmx:configRequest', { detail: external }));
  expect(external.headers).toEqual({});
});

it('adds one current token to POST forms and replaces stale duplicate values', () => {
  const element = form('post');
  element.insertAdjacentHTML('beforeend', '<input type="hidden" name="csrf_token" value="old"><input type="hidden" name="csrf_token" value="older">');
  submit(element);
  submit(element);

  expect(new FormData(element).getAll('csrf_token')).toEqual(['fixture-token']);
  expect(formData(element).getAll('csrf_token')).toEqual(['fixture-token']);
  expect(formData(element).get('q')).toBe('семья');
});

it.each([undefined, 'get'])('omits tokens from search submissions with method %s, including stale hidden fields', method => {
  const element = form(method);
  element.id = 'sentence-search';
  element.insertAdjacentHTML('beforeend', '<input type="hidden" name="csrf_token" value="stale-token">');
  document.body.insertAdjacentHTML('beforeend', '<input form="sentence-search" type="hidden" name="csrf_token" value="outside-token">');
  submit(element);

  expect(new FormData(element).has('csrf_token')).toBe(false);
  const data = formData(element);
  expect(data.has('csrf_token')).toBe(false);
  expect(data.get('q')).toBe('семья');
});

it('removes a stale token from GET formdata constructed without a submit event', () => {
  const element = form('get');
  element.insertAdjacentHTML('beforeend', '<input type="hidden" name="csrf_token" value="stale-token">');

  const data = formData(element);

  expect(data.has('csrf_token')).toBe(false);
  expect(data.get('q')).toBe('семья');
});

it('adds CSRF to POST formdata constructed without a submit event', () => {
  expect(formData(form('post')).get('csrf_token')).toBe('fixture-token');
});

it('honors a GET submitter on a POST form without leaking its existing token', () => {
  const element = form('post');
  element.insertAdjacentHTML('beforeend', '<input type="hidden" name="csrf_token" value="fixture-token">');
  const button = element.querySelector('button')!;
  button.setAttribute('formmethod', 'get');
  submit(element, button);

  expect(new FormData(element).has('csrf_token')).toBe(false);
  expect(formData(element).has('csrf_token')).toBe(false);
});

it('protects a POST submitter on a GET form without changing later GET formdata', async () => {
  const element = form('get');
  const button = element.querySelector('button')!;
  button.setAttribute('formmethod', 'post');
  submit(element, button);

  expect(new FormData(element).get('csrf_token')).toBe('fixture-token');
  expect(formData(element).get('csrf_token')).toBe('fixture-token');
  await new Promise(resolve => setTimeout(resolve, 0));
  expect(formData(element).has('csrf_token')).toBe(false);
  submit(element);
  expect(new FormData(element).has('csrf_token')).toBe(false);
});

it('does not send a form token to a submitter that overrides the action to another origin', () => {
  const element = form('post');
  const button = element.querySelector('button')!;
  button.setAttribute('formaction', 'https://external.invalid/upload');
  element.insertAdjacentHTML('beforeend', '<input type="hidden" name="csrf_token" value="fixture-token">');
  submit(element, button);

  expect(new FormData(element).has('csrf_token')).toBe(false);
  expect(formData(element).has('csrf_token')).toBe(false);
});
