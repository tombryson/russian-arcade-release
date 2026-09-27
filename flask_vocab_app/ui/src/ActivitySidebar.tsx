import type { ComponentChildren } from 'preact';
import { useState } from 'preact/hooks';

type ActivityLink = { page: string; href: string; label: string; boost: boolean };
export type ActivityNavigation = { title: string; more: string; main?: ActivityLink[]; activities: ActivityLink[]; tools: ActivityLink[] };

type ActivitySidebarProps = {
  navigation: ActivityNavigation;
  activePage?: string;
  language?: 'en' | 'ru';
  profileControl?: ComponentChildren;
  coinBalance?: ComponentChildren;
  languageControl?: ComponentChildren;
  appearanceControl?: ComponentChildren;
  skillProgress?: ComponentChildren;
  wordsHref?: string;
  showSavedSentences?: boolean;
};

export function ActivitySidebar({ navigation, activePage, language = 'en', profileControl, coinBalance, languageControl, appearanceControl, skillProgress, wordsHref = '/vocab', showSavedSentences = true }: ActivitySidebarProps) {
  const [expanded, setExpanded] = useState(false);
  const close = () => setExpanded(false);
  const tools = navigation.tools.filter(item => item.page !== 'sentences_saved');
  const wordsLabel = language === 'ru' ? 'Мои слова' : 'My words';
  const savedLabel = language === 'ru' ? 'Разговорник' : 'Phrasebook';
  return <aside class="activity-sidebar">
    <div class="sidebar-brand-row" onClick={event => { if ((event.target as Element).closest('a')) close(); }}>
      <a class="sidebar-brand" href="#home" aria-label={language === 'ru' ? 'Russian Arcade — главная' : 'Russian Arcade home'} onClick={close}>
        <span class="mark" lang="ru" aria-hidden="true">Я</span><span class="brand-name">Russian Arcade</span>
      </a>
    </div>
    <button class="activity-menu-toggle" type="button" aria-expanded={expanded} aria-controls="activity-navigation" onClick={() => setExpanded(value => !value)}>
      {navigation.title}<span aria-hidden="true">{expanded ? '−' : '+'}</span>
    </button>
    <nav id="activity-navigation" class="activity-navigation" data-expanded={expanded} aria-label={navigation.title}>
      <div class="sidebar-menu-scroll">
        <a class="activity-sidebar-title" href="#activities" onClick={close}>{navigation.title}</a>
        <div class="activity-sidebar-links">
          {navigation.activities.filter(item => item.page !== 'curriculum').map(item => <a key={item.page} href={item.href} aria-current={item.page === activePage ? 'page' : undefined} onClick={close}>{item.label}</a>)}
          <a href="#shop" aria-current={activePage === 'shop' ? 'page' : undefined} onClick={close}>{language === 'ru' ? 'Магазин' : 'Shop'}</a>
          {navigation.activities.filter(item => item.page === 'curriculum').map(item => <a key={item.page} href={item.href} aria-current={item.page === activePage ? 'page' : undefined} onClick={close}>{item.label}</a>)}
        </div>
        {!!tools.length && <details class="activity-sidebar-more">
          <summary>{navigation.more}</summary>
          {tools.map(item => <a key={item.page} href={item.href} onClick={close}>{item.label}</a>)}
        </details>}
      </div>
      <div class="sidebar-footer" onClick={event => { if ((event.target as Element).closest('a')) close(); }}>
        <div class="sidebar-shortcuts">
          {showSavedSentences && <a class="sidebar-shortcut" href="/sentences/saved" title={savedLabel} aria-label={savedLabel} aria-current={activePage === 'sentences_saved' ? 'page' : undefined} onClick={close}>
            <svg class="sidebar-icon-book" fill="currentColor" aria-hidden="true" viewBox="0 0 448 512">{/*! Font Awesome Free 6.5.1 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free (Icons: CC BY 4.0, Fonts: SIL OFL 1.1, Code: MIT License) Copyright 2023 Fonticons, Inc. */}<path d="M96 0C43 0 0 43 0 96V416c0 53 43 96 96 96H384h32c17.7 0 32-14.3 32-32s-14.3-32-32-32V384c17.7 0 32-14.3 32-32V32c0-17.7-14.3-32-32-32H384 96zm0 384H352v64H96c-17.7 0-32-14.3-32-32s14.3-32 32-32zm32-240c0-8.8 7.2-16 16-16H336c8.8 0 16 7.2 16 16s-7.2 16-16 16H144c-8.8 0-16-7.2-16-16zm16 48H336c8.8 0 16 7.2 16 16s-7.2 16-16 16H144c-8.8 0-16-7.2-16-16s7.2-16 16-16z"/></svg>
          </a>}
          <a class="sidebar-shortcut" href={wordsHref} title={wordsLabel} aria-label={wordsLabel} aria-current={activePage === 'vocab' ? 'page' : undefined} onClick={close}>
            <svg class="sidebar-icon-list" fill="currentColor" aria-hidden="true" viewBox="0 0 512 512">{/*! Font Awesome Free 6.5.1 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free (Icons: CC BY 4.0, Fonts: SIL OFL 1.1, Code: MIT License) Copyright 2023 Fonticons, Inc. */}<path d="M40 48C26.7 48 16 58.7 16 72v48c0 13.3 10.7 24 24 24H88c13.3 0 24-10.7 24-24V72c0-13.3-10.7-24-24-24H40zM192 64c-17.7 0-32 14.3-32 32s14.3 32 32 32H480c17.7 0 32-14.3 32-32s-14.3-32-32-32H192zm0 160c-17.7 0-32 14.3-32 32s14.3 32 32 32H480c17.7 0 32-14.3 32-32s-14.3-32-32-32H192zm0 160c-17.7 0-32 14.3-32 32s14.3 32 32 32H480c17.7 0 32-14.3 32-32s-14.3-32-32-32H192zM16 232v48c0 13.3 10.7 24 24 24H88c13.3 0 24-10.7 24-24V232c0-13.3-10.7-24-24-24H40c-13.3 0-24 10.7-24 24zM40 368c-13.3 0-24 10.7-24 24v48c0 13.3 10.7 24 24 24H88c13.3 0 24-10.7 24-24V392c0-13.3-10.7-24-24-24H40z"/></svg>
          </a>
        </div>
        <div class="sidebar-balance">{coinBalance}</div>
        {skillProgress}
      </div>
      <div class="sidebar-account" onClick={event => { if ((event.target as Element).closest('a')) close(); }}>
        <div class="sidebar-utilities">
          {profileControl}
          {languageControl}
          {appearanceControl}
        </div>
      </div>
    </nav>
  </aside>;
}
