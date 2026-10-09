import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { bindHeaderMenu } from '../../static/js/header_menu.js';

const markup = `
  <div class="header-controls" data-header-menu data-expanded="false">
    <button class="header-menu-toggle" type="button" aria-label="Account and settings" aria-controls="header-utilities" aria-expanded="false">More</button>
    <div id="header-utilities" class="header-utilities" data-header-menu-panel>
      <a href="#shop">Coins</a>
      <details class="language-picker"><summary>Language</summary><form class="language-picker-options"><button type="button">English</button></form></details>
      <details class="appearance-picker"><summary>Appearance</summary><form class="appearance-picker-options"><button type="button">Top navigation</button></form></details>
      <a class="account-link" href="#account"><span>Account</span></a>
    </div>
  </div>
  <button id="outside">Outside</button>`;

let root, toggle, nested, media, cleanup;
beforeEach(() => {
  document.body.innerHTML = markup;
  root = document.querySelector('[data-header-menu]');
  toggle = root.querySelector('button');
  nested = root.querySelector('details');
  media = new EventTarget();
  media.matches = true;
  vi.stubGlobal('matchMedia', vi.fn(() => media));
});
afterEach(() => {
  cleanup?.();
  cleanup = undefined;
  document.body.innerHTML = '';
  vi.unstubAllGlobals();
});

describe('shared mobile header controls', () => {
  it('opens from the button, keeps language disclosure clicks open, and resets nested menus when closed', () => {
    cleanup = bindHeaderMenu(root);
    expect(toggle.getAttribute('aria-controls')).toBe(root.querySelector('[data-header-menu-panel]').id);
    toggle.click();
    expect(root.dataset.expanded).toBe('true');
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    nested.querySelector('summary').click();
    expect(nested.open).toBe(true);
    expect(root.dataset.expanded).toBe('true');
    root.querySelector('.appearance-picker').open = true;
    toggle.click();
    expect(root.dataset.expanded).toBe('false');
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    expect(nested.open).toBe(false);
    expect(root.querySelector('.appearance-picker').open).toBe(false);
    toggle.click();
    expect(root.dataset.expanded).toBe('true');
    expect(root.querySelectorAll('details[open]')).toHaveLength(0);
  });

  it('closes on Escape before nested disclosure handlers can move focus into hidden content', () => {
    cleanup = bindHeaderMenu(root);
    toggle.click();
    nested.open = true;
    nested.querySelector('button').focus();
    const nestedEscape = vi.fn(() => nested.querySelector('summary').focus());
    document.addEventListener('keydown', nestedEscape);
    try {
      const escape = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true });
      document.activeElement.dispatchEvent(escape);
      expect(root.dataset.expanded).toBe('false');
      expect(nested.open).toBe(false);
      expect(document.activeElement).toBe(toggle);
      expect(escape.defaultPrevented).toBe(true);
      expect(nestedEscape).not.toHaveBeenCalled();
    } finally {
      document.removeEventListener('keydown', nestedEscape);
    }
  });

  it.each(['language', 'appearance'])('cooperates with the legacy %s picker and keeps its settings usable', picker => {
    const listeners = [];
    const scopedDocument = {
      addEventListener(type, listener, options) {
        document.addEventListener(type, listener, options);
        listeners.push([type, listener, options]);
      },
      querySelectorAll: selector => document.querySelectorAll(selector),
      get activeElement() { return document.activeElement; },
    };
    runInNewContext(readFileSync(`../static/js/${picker}_picker.js`, 'utf8'), {
      document: scopedDocument, location: window.location,
    });
    cleanup = bindHeaderMenu(root);
    try {
      toggle.click();
      const details = root.querySelector(`.${picker}-picker`);
      details.querySelector('summary').click();
      const setting = details.querySelector('button');
      setting.click();
      expect(root.dataset.expanded).toBe('true');
      expect(details.open).toBe(true);
      setting.focus();
      setting.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }));
      expect(root.dataset.expanded).toBe('false');
      expect(details.open).toBe(false);
      expect(document.activeElement).toBe(toggle);
      toggle.click();
      expect(details.open).toBe(false);
    } finally {
      listeners.forEach(([type, listener, options]) => document.removeEventListener(type, listener, options));
    }
  });

  it('dismisses on outside clicks without taking focus from the clicked control', () => {
    cleanup = bindHeaderMenu(root);
    toggle.click();
    const outside = document.querySelector('#outside');
    outside.focus();
    outside.click();
    expect(root.dataset.expanded).toBe('false');
    expect(document.activeElement).toBe(outside);
  });

  it('closes after selecting a destination without cancelling native navigation', () => {
    cleanup = bindHeaderMenu(root);
    toggle.click();
    nested.open = true;
    const click = new MouseEvent('click', { bubbles: true, cancelable: true });
    root.querySelector('.account-link span').dispatchEvent(click);
    expect(root.dataset.expanded).toBe('false');
    expect(nested.open).toBe(false);
    expect(click.defaultPrevented).toBe(false);
  });

  it('preserves modified clicks and links that open separately', () => {
    cleanup = bindHeaderMenu(root);
    const link = root.querySelector('a');
    for (const options of [{ ctrlKey: true }, { metaKey: true }, { shiftKey: true }, { altKey: true }, { button: 1 }]) {
      toggle.click();
      const click = new MouseEvent('click', { bubbles: true, cancelable: true, ...options });
      link.dispatchEvent(click);
      expect(root.dataset.expanded).toBe('true');
      expect(click.defaultPrevented).toBe(false);
      toggle.click();
    }
    for (const [attribute, value] of [['target', '_blank'], ['download', 'words.txt']]) {
      link.setAttribute(attribute, value);
      toggle.click();
      link.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
      expect(root.dataset.expanded).toBe('true');
      toggle.click();
      link.removeAttribute(attribute);
    }
  });

  it('leaves a draft guard in charge of a blocked navigation', () => {
    cleanup = bindHeaderMenu(root);
    const guard = event => { event.preventDefault(); event.stopImmediatePropagation(); };
    toggle.click();
    document.addEventListener('click', guard, true);
    try {
      root.querySelector('a').dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
      expect(root.dataset.expanded).toBe('true');
    } finally {
      document.removeEventListener('click', guard, true);
    }
    const link = root.querySelector('a');
    link.addEventListener('click', event => event.preventDefault(), { once: true });
    link.click();
    expect(root.dataset.expanded).toBe('true');
  });

  it('resets on hash navigation and switching to desktop, then can reopen on mobile', () => {
    cleanup = bindHeaderMenu(root);
    toggle.click();
    window.dispatchEvent(new HashChangeEvent('hashchange'));
    expect(root.dataset.expanded).toBe('false');
    toggle.click();
    nested.open = true;
    media.matches = false;
    media.dispatchEvent(new Event('change'));
    expect(root.dataset.expanded).toBe('false');
    expect(nested.open).toBe(false);
    toggle.click();
    expect(root.dataset.expanded).toBe('false');
    media.matches = true;
    media.dispatchEvent(new Event('change'));
    toggle.click();
    expect(root.dataset.expanded).toBe('true');
  });

  it('removes handlers when a native header unmounts', () => {
    cleanup = bindHeaderMenu(root);
    cleanup();
    toggle.click();
    expect(root.dataset.expanded).toBe('false');
    root.dataset.expanded = 'true';
    window.dispatchEvent(new HashChangeEvent('hashchange'));
    expect(root.dataset.expanded).toBe('true');
  });
});

describe('legacy mobile header integration', () => {
  it('binds each header once across repeated initialization and cleans up replaced headers', () => {
    const source = readFileSync('../static/js/header_menu_legacy.js', 'utf8').replace(/^import[^\n]+\n/, '');
    const dispose = vi.fn();
    const bind = vi.fn(() => dispose);
    const key = Symbol.for('russian-arcade.header-menu');
    const context = { document, Symbol, Map, bindHeaderMenu: bind };
    try {
      runInNewContext(source, { ...context });
      runInNewContext(source, { ...context });
      document.dispatchEvent(new Event('htmx:afterSwap'));
      expect(bind).toHaveBeenCalledTimes(1);
      root.outerHTML = markup;
      document.dispatchEvent(new Event('htmx:historyRestore'));
      expect(dispose).toHaveBeenCalledTimes(1);
      expect(bind).toHaveBeenCalledTimes(2);
    } finally {
      document.removeEventListener('htmx:afterSwap', document[key]);
      document.removeEventListener('htmx:historyRestore', document[key]);
      delete document[key];
    }
  });
});
