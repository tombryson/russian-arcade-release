import type { ComponentChildren } from 'preact';
import { useEffect, useRef } from 'preact/hooks';
import { bindHeaderMenu } from '../../static/js/header_menu.js';
import type { Language } from './review-types';

export function HeaderNavigation({language, children}: {language: Language; children: ComponentChildren}) {
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => root.current ? bindHeaderMenu(root.current) : undefined, []);

  return <div ref={root} class="header-navigation" data-expanded="false">
    <button type="button" class="header-menu-toggle" aria-label={language === 'ru' ? 'Меню' : 'Menu'} aria-expanded="false" aria-controls="primary-navigation">
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" aria-hidden="true">
        <path class="header-menu-bars" d="M4 6h16M4 12h16M4 18h16"/>
        <path class="header-menu-close" d="m6 6 12 12M18 6 6 18"/>
      </svg>
    </button>
    <nav id="primary-navigation" class="nav" aria-label={language === 'ru' ? 'Главное меню' : 'Main navigation'}>{children}</nav>
  </div>;
}
