import type { ComponentChildren } from 'preact';
import type { Language } from './review-types';

export function HeaderNavigation({language, children}: {language: Language; children: ComponentChildren}) {
  return <div class="header-navigation">
    <nav id="primary-navigation" class="nav" aria-label={language === 'ru' ? 'Главное меню' : 'Main navigation'}>{children}</nav>
  </div>;
}
