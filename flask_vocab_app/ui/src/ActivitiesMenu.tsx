import { useEffect, useRef } from 'preact/hooks';
import type { ActivityNavigation } from './ActivitySidebar';
import type { Language } from './review-types';
import '../../static/css/activities_menu.css';

type ActivitiesMenuProps = {
  items: ActivityNavigation['activities'];
  language: Language;
  active: boolean;
  activePage: string;
};

export function ActivitiesMenu({ items, language, active, activePage }: ActivitiesMenuProps) {
  const menu = useRef<HTMLDetailsElement>(null);
  const summary = useRef<HTMLElement>(null);
  const close = () => { if (menu.current) menu.current.open = false; };

  useEffect(() => {
    const outside = (event: MouseEvent) => {
      if (event.target instanceof Node && !menu.current?.contains(event.target)) close();
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || !menu.current?.open) return;
      close();
      summary.current?.focus({ preventScroll: true });
    };
    document.addEventListener('click', outside);
    document.addEventListener('keydown', escape);
    window.addEventListener('hashchange', close);
    return () => {
      document.removeEventListener('click', outside);
      document.removeEventListener('keydown', escape);
      window.removeEventListener('hashchange', close);
    };
  }, []);

  const label = language === 'ru' ? 'Занятия' : 'Activities';
  return <details ref={menu} class="activities-menu">
    <summary ref={summary} aria-label={label} data-active={active ? 'true' : undefined}>
      {label}<svg class="activities-menu-chevron" viewBox="0 0 16 16" aria-hidden="true"><path d="m4 6 4 4 4-4" /></svg>
    </summary>
    <div class="activities-menu-options" onClick={event => { if ((event.target as Element).closest('a')) close(); }}>
      {items.filter(item => item.page !== 'curriculum').map(item => <a key={item.page} href={item.href.startsWith('/#') ? item.href.slice(1) : item.href} aria-current={activePage === item.page ? 'page' : undefined}>{item.label}</a>)}
      <a href="#games" aria-current={activePage === 'games' ? 'page' : undefined}>{language === 'ru' ? 'Игры' : 'Games'}</a>
      <a class="activities-menu-all" href="#activities" aria-current={activePage === 'activities' ? 'page' : undefined}>
        {language === 'ru' ? 'Все занятия' : 'All activities'}<span aria-hidden="true">↗</span>
      </a>
      {items.filter(item => item.page === 'curriculum').map(item => <a key={item.page} href={item.href} aria-current={activePage === item.page ? 'page' : undefined}>{item.label}</a>)}
    </div>
  </details>;
}
