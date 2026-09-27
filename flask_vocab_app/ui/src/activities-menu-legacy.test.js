import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

const script = readFileSync('../static/js/activities_menu.js', 'utf8');

describe('legacy Activities dropdown', () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <details data-activities-menu>
        <summary>Activities</summary>
        <div><a href="#writing"><span>Writing</span></a></div>
      </details>
      <details class="sidebar-activity-group" open><summary>Sidebar activities</summary></details>
      <button>Outside</button>`;
    runInNewContext(script, {document, Symbol});
  });

  afterEach(() => {
    document.body.innerHTML = '';
    vi.restoreAllMocks();
  });

  function openMenu() {
    const menu = document.querySelector('[data-activities-menu]');
    menu.open = true;
    return menu;
  }

  it('keeps the menu open for content clicks and closes after selecting a link', () => {
    const menu = openMenu();
    menu.querySelector('div').click();
    expect(menu.open).toBe(true);
    menu.querySelector('a span').click();
    expect(menu.open).toBe(false);
    expect(document.querySelector('.sidebar-activity-group').open).toBe(true);
  });

  it('closes on outside click without moving focus from the clicked control', () => {
    const menu = openMenu();
    const outside = document.querySelector('button');
    outside.focus();
    outside.click();
    expect(menu.open).toBe(false);
    expect(document.activeElement).toBe(outside);
  });

  it('returns keyboard focus to the trigger on Escape', () => {
    const menu = openMenu();
    menu.querySelector('a').focus();
    document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));
    expect(menu.open).toBe(false);
    expect(document.activeElement).toBe(menu.querySelector('summary'));
  });

  it('preserves native keyboard navigation for other keys', () => {
    const menu = openMenu();
    const event = new KeyboardEvent('keydown', {key: 'Tab', cancelable: true});
    document.dispatchEvent(event);
    expect(menu.open).toBe(true);
    expect(event.defaultPrevented).toBe(false);
  });

  it('binds once across repeated script evaluations and handles replacement menus', () => {
    const addEventListener = vi.spyOn(document, 'addEventListener');
    runInNewContext(script, {document, Symbol});
    expect(addEventListener).not.toHaveBeenCalled();
    document.querySelector('[data-activities-menu]').outerHTML = `
      <details data-activities-menu open><summary>Activities</summary></details>`;
    document.querySelector('button').click();
    expect(document.querySelector('[data-activities-menu]').open).toBe(false);
  });
});
