import { useEffect, useRef } from 'preact/hooks';
import type { Language } from './review-types';
import '../../static/css/appearance_picker.css';

type AppearancePickerProps = {
  language: Language;
  navigationLayout: 'top' | 'sidebar';
  csrfToken: string;
};

const currentPath = () => window.location.pathname + window.location.search + window.location.hash;

export function AppearancePicker({ language, navigationLayout, csrfToken }: AppearancePickerProps) {
  const picker = useRef<HTMLDetailsElement>(null);
  const summary = useRef<HTMLElement>(null);
  const next = useRef<HTMLInputElement>(null);
  const label = language === 'ru' ? 'Внешний вид' : 'Appearance';

  useEffect(() => {
    const closeOutside = (event: MouseEvent) => {
      if (picker.current?.open && event.target instanceof Node && !picker.current.contains(event.target)) picker.current.open = false;
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && picker.current?.open) {
        picker.current.open = false;
        summary.current?.focus();
      }
    };
    document.addEventListener('click', closeOutside);
    document.addEventListener('keydown', closeOnEscape);
    return () => {
      document.removeEventListener('click', closeOutside);
      document.removeEventListener('keydown', closeOnEscape);
    };
  }, []);

  return <details ref={picker} class="appearance-picker">
    <summary ref={summary} title={label} aria-label={label}>
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" aria-hidden="true"><path d="M4 7h2m6 0h8M4 17h8m6 0h2"/><circle cx="9" cy="7" r="3"/><circle cx="15" cy="17" r="3"/></svg>
    </summary>
    <form class="appearance-picker-options" method="post" action="/ui-navigation" onSubmit={() => { if (next.current) next.current.value = currentPath(); }}>
      <input type="hidden" name="csrf_token" value={csrfToken} />
      <input ref={next} type="hidden" name="next" value={currentPath()} />
      {(['top', 'sidebar'] as const).map(layout => <button key={layout} type="submit" name="layout" value={layout} aria-pressed={navigationLayout === layout}>
        <span>{layout === 'top' ? language === 'ru' ? 'Верхнее меню' : 'Top navigation' : language === 'ru' ? 'Боковая панель' : 'Sidebar'}</span>
        <span class="appearance-picker-check" aria-hidden="true">{navigationLayout === layout ? '✓' : ''}</span>
      </button>)}
    </form>
  </details>;
}
