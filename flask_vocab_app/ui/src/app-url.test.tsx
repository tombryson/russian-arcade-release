import { afterEach, describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/preact';
import { appUrl } from './app-url';
import { installAppUrlVnodes } from './app-url-vnodes';

let uninstall: (() => void) | undefined;
afterEach(() => {
  uninstall?.();
  uninstall = undefined;
  document.querySelector('meta[name="app-base-path"]')?.remove();
});

describe('document-scoped application URLs', () => {
  it('keeps public and personal pages at the root even after visiting the demo', () => {
    history.replaceState(null, '', '/demo/');
    expect(appUrl('/api/v1/progression')).toBe('/demo/api/v1/progression');
    history.replaceState(null, '', '/');
    expect(appUrl('/api/v1/progression')).toBe('/api/v1/progression');
    expect(appUrl('/trial/account')).toBe('/trial/account');
    expect(appUrl('/demo/')).toBe('/demo/');
  });

  it('uses the server mount declaration for application links and query strings', () => {
    const meta = document.createElement('meta');
    meta.name = 'app-base-path'; meta.content = '/demo'; document.head.append(meta);
    expect(appUrl('/comprehension?lesson=one#questions')).toBe('/demo/comprehension?lesson=one#questions');
    expect(appUrl('/trial/account')).toBe('/demo/trial/account');
    expect(appUrl('/#journey')).toBe('/demo/#journey');
    expect(appUrl(`${location.origin}/api/v1/assets/one?download=1`)).toBe(`${location.origin}/demo/api/v1/assets/one?download=1`);
  });

  it('scopes protected media but retains public assets and existing demo paths', () => {
    history.replaceState(null, '', '/demo/comprehension');
    for (const path of ['/static/media/voice.mp3', '/static/uploads/lesson.pdf', '/api/v1/assets/picture']) {
      expect(appUrl(path)).toBe(`/demo${path}`);
    }
    for (const path of ['/demo', '/demo/', '/demo/api/v1/progression', '/static/images/barsik.webp', '/static/js/reading.js', '/post/assets/main.js']) {
      expect(appUrl(path)).toBe(path);
    }
  });

  it('keeps authentication, external URLs, and document-relative targets intact', () => {
    history.replaceState(null, '', '/demo/');
    for (const path of ['/trial/sign-in', '/trial/sign-in/email?next=%2F', '/trial/callback/provider', '/trial/connect/provider', '/trial/sign-out',
      '//cdn.example.com/image.png', 'https://dictionary.example.com/word', 'mailto:hello@example.com', 'blob:recording', 'data:image/png;base64,AA==', '#activities', '?mode=read', 'relative.mp3']) {
      expect(appUrl(path)).toBe(path);
    }
  });
});

it('scopes rendered navigation, forms, and tenant media while preserving explicit exits', () => {
  history.replaceState(null, '', '/demo/');
  uninstall = installAppUrlVnodes();
  function Activity() {
    return <section>
      <a href="/comprehension">Read</a>
      <a href="/trial/account">Demo account</a>
      <a href="/trial/sign-in">Sign in</a>
      <a href="/" data-app-exit>Leave demo</a>
      <form action="/ui-language"><button formAction="/ui-navigation">Save</button></form>
      <audio data-testid="recording" src="/static/media/voice.mp3" />
      <img alt="Card" src="/api/v1/assets/card" />
      <img alt="Barsik" src="/static/images/barsik.webp" />
    </section>;
  }
  const { container, rerender } = render(<Activity />);
  expect(screen.getByRole('link', { name: 'Read' }).getAttribute('href')).toBe('/demo/comprehension');
  expect(screen.getByRole('link', { name: 'Demo account' }).getAttribute('href')).toBe('/demo/trial/account');
  expect(screen.getByRole('link', { name: 'Sign in' }).getAttribute('href')).toBe('/trial/sign-in');
  expect(screen.getByRole('link', { name: 'Leave demo' }).getAttribute('href')).toBe('/');
  expect(container.querySelector('form')?.getAttribute('action')).toBe('/demo/ui-language');
  expect(screen.getByRole('button', { name: 'Save' }).getAttribute('formaction')).toBe('/demo/ui-navigation');
  expect(screen.getByTestId('recording').getAttribute('src')).toBe('/demo/static/media/voice.mp3');
  expect(screen.getByRole('img', { name: 'Card' }).getAttribute('src')).toBe('/demo/api/v1/assets/card');
  expect(screen.getByRole('img', { name: 'Barsik' }).getAttribute('src')).toBe('/static/images/barsik.webp');
  rerender(<a href="/demo/writing/one">Continue</a>);
  expect(screen.getByRole('link', { name: 'Continue' }).getAttribute('href')).toBe('/demo/writing/one');
});
