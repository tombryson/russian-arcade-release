import type { ComponentChildren } from 'preact';
import { useEffect, useRef } from 'preact/hooks';
import { bindHeaderMenu } from '../../static/js/header_menu.js';
import type { Language } from './review-types';

export function HeaderUtilities({language, children}: {language: Language; children: ComponentChildren}) {
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => root.current ? bindHeaderMenu(root.current) : undefined, []);
  const label = language === 'ru' ? 'Аккаунт и настройки' : 'Account and settings';
  return <div ref={root} class="header-controls" data-header-menu data-expanded="false">
    <button type="button" class="header-menu-toggle" aria-label={label} title={label} aria-expanded="false" aria-controls="header-utilities">
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" aria-hidden="true">
        <g class="header-menu-bars" fill="currentColor" stroke="none"><circle cx="5" cy="12" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="19" cy="12" r="1.5"/></g>
        <path class="header-menu-close" d="m6 6 12 12M18 6 6 18"/>
      </svg>
    </button>
    <div id="header-utilities" class="header-utilities" data-header-menu-panel>{children}</div>
  </div>;
}
