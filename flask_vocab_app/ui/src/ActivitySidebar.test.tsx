import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, within } from '@testing-library/preact';
import { App } from './App';
import type { ActivityNavigation } from './ActivitySidebar';

const navigation: ActivityNavigation = {
  title: 'Activities & tools', more: 'More tools',
  main: [
    {page:'home', href:'/#home', label:'Home', boost:false},
    {page:'activities', href:'/#activities', label:'All activities', boost:false},
    {page:'vocab', href:'/vocab', label:'My words', boost:false},
  ],
  activities: [
    {page:'native_flashcards', href:'/#flashcards', label:'Flashcards', boost:false},
    {page:'writing', href:'/writing', label:'Writing', boost:true},
    {page:'speaking', href:'/#speaking', label:'Speaking', boost:false},
  ],
  tools: [
    {page:'flashcards', href:'/tools/anki/', label:'Anki card tools', boost:true},
    {page:'sentences_saved', href:'/sentences/saved', label:'Phrasebook', boost:false},
  ],
};
async function navigate(hash: string) {
  await act(() => {
    window.history.replaceState(null, '', `/#${hash}`);
    window.dispatchEvent(new HashChangeEvent('hashchange'));
  });
}
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe('Saved navigation layout', () => {
  it.each(['en', 'ru'] as const)('contains the brand, profile and introduced controls in a self-contained %s sidebar', async language => {
    vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ok:false, json:async () => ({error:{message:'Offline'}})}));
    await navigate('words');
    const {container} = render(<App navigation={navigation} navigationLayout="sidebar" language={language} initialProfile={null} csrfToken="test-token" initialOnboarding={{profile_id:null,coins_introduced:true,progress_introduced:true}} />);
    const sidebar = container.querySelector<HTMLElement>('.activity-sidebar')!;
    const brand = sidebar.querySelector<HTMLElement>('.sidebar-brand-row')!;
    const footer = sidebar.querySelector<HTMLElement>('.sidebar-footer')!;
    const account = sidebar.querySelector<HTMLElement>('.sidebar-account')!;
    const shortcuts = footer.querySelector<HTMLElement>('.sidebar-shortcuts')!;
    const menuScroll = sidebar.querySelector<HTMLElement>('.sidebar-menu-scroll')!;
    expect(container.querySelector('header.top')).toBeNull();
    expect(sidebar.querySelector('a[href="/tools/anki/"]')?.textContent).toBe('Anki card tools');
    expect(within(brand).getByRole('link', {name:language === 'ru' ? 'Russian Arcade — главная' : 'Russian Arcade home'}).getAttribute('href')).toBe('#home');
    expect(brand.querySelector('.user-session-link')).toBeNull();
    expect(within(account).getByRole('link', {name:language === 'ru' ? 'Выбрать профиль' : 'Choose a profile'}).getAttribute('href')).toBe('/post/profiles');
    expect(account.querySelector('.sidebar-utilities')?.firstElementChild?.classList.contains('user-session-link')).toBe(true);
    expect(container.querySelectorAll('.user-session-link')).toHaveLength(1);
    expect(container.querySelectorAll('.post-language')).toHaveLength(1);
    expect(container.querySelectorAll('.appearance-picker')).toHaveLength(1);
    const appearance = account.querySelector<HTMLDetailsElement>('.appearance-picker')!;
    expect(appearance).toBeTruthy();
    expect(within(appearance).getByLabelText(language === 'ru' ? 'Внешний вид' : 'Appearance')).toBeTruthy();
    expect(appearance.querySelector('form')?.getAttribute('action')).toBe('/ui-navigation');
    expect(appearance.querySelector<HTMLInputElement>('input[name="csrf_token"]')?.value).toBe('test-token');
    expect(appearance.querySelector('button[value="sidebar"]')?.getAttribute('aria-pressed')).toBe('true');
    expect(container.querySelector('[href="/appearance"]')).toBeNull();
    expect(within(footer).getByRole('link', {name:language === 'ru' ? 'Лингокоины: 0' : 'Lingo coins: 0'})).toBeTruthy();
    expect(within(footer).getByRole('link', {name:language === 'ru' ? 'Лингокоины: 0' : 'Lingo coins: 0'}).getAttribute('href')).toBe('#shop');
    expect(within(menuScroll).getByRole('link', {name:language === 'ru' ? 'Магазин' : 'Shop'}).getAttribute('href')).toBe('#shop');
    expect(footer.querySelector('.skill-rail')).toBeTruthy();
    expect(account.querySelector('form')?.getAttribute('action')).toBe('/ui-language');
    expect(account.querySelector<HTMLInputElement>('input[name="csrf_token"]')?.value).toBe('test-token');
    expect(account.querySelector<HTMLInputElement>('input[name="next"]')?.value).toBe('/#words');
    expect(footer.querySelector('.sidebar-utilities')).toBeNull();
    for (const [label, href] of [[language === 'ru' ? 'Мои слова' : 'My words', '/vocab'], [language === 'ru' ? 'Разговорник' : 'Phrasebook', '/sentences/saved']]) {
      const link = within(shortcuts).getByRole('link', {name:label});
      expect(link.getAttribute('href')).toBe(href);
      expect(link.getAttribute('title')).toBe(label);
      expect(link.querySelector('svg[aria-hidden="true"]')).toBeTruthy();
      expect(within(menuScroll).queryByRole('link', {name:label})).toBeNull();
    }
    expect(shortcuts.querySelector('[href="/vocab"]')?.getAttribute('aria-current')).toBe('page');
    expect(sidebar.querySelector('nav')?.contains(footer)).toBe(true);
    expect(footer.nextElementSibling).toBe(account);
    sidebar.addEventListener('click', event => { if ((event.target as Element).closest('a')) event.preventDefault(); });
    const toggle = within(sidebar).getByRole('button', {name:'Activities & tools'});
    fireEvent.click(toggle);
    fireEvent.click(account.querySelector('.post-language summary')!);
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    fireEvent.click(appearance.querySelector('summary')!);
    expect(appearance.open).toBe(true);
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    fireEvent.click(within(footer).getByRole('link', {name:language === 'ru' ? 'Лингокоины: 0' : 'Lingo coins: 0'}));
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    fireEvent.click(toggle);
    fireEvent.click(footer.querySelector('.skill-rail-link')!);
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    fireEvent.click(toggle);
    fireEvent.click(account.querySelector('.user-session-link')!);
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
  });

  it('keeps coins and skill progress hidden until their introductions', async () => {
    vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ok:false, json:async () => ({error:{message:'Offline'}})}));
    await navigate('words');
    const {container} = render(<App navigation={navigation} navigationLayout="sidebar" initialProfile={null} />);
    expect(container.querySelector('.sidebar-footer .progression-badge')).toBeNull();
    expect(container.querySelector('.sidebar-footer .skill-rail')).toBeNull();
    expect(container.querySelector('.sidebar-account .post-language')).toBeTruthy();
  });

  it('clears desktop header offsets and measures only the compact mobile shell', async () => {
    vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ok:false, json:async () => ({error:{message:'Offline'}})}));
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
      if (this.classList.contains('top')) return new DOMRect(0, 0, 1000, 143);
      if (this.classList.contains('activity-menu-toggle')) return new DOMRect(0, 56, 260, 48);
      if (this.classList.contains('activity-sidebar')) return new DOMRect(0, 0, 260, 700);
      return new DOMRect();
    });
    await navigate('words');
    const {container,rerender} = render(<App navigation={navigation} initialProfile={null} />);
    await vi.waitFor(() => expect(document.documentElement.style.getPropertyValue('--skill-header-height')).toBe('143px'));
    const style = document.createElement('style');
    style.textContent = '.activity-menu-toggle { display: none; }';
    document.head.append(style);
    try {
      rerender(<App navigation={navigation} navigationLayout="sidebar" initialProfile={null} />);
      await vi.waitFor(() => expect(document.documentElement.style.getPropertyValue('--skill-header-height')).toBe('0px'));
      const sidebar = container.querySelector<HTMLElement>('.activity-sidebar')!;
      const toggle = sidebar.querySelector<HTMLElement>('.activity-menu-toggle')!;
      toggle.style.display = 'block';
      sidebar.style.paddingBottom = '12px';
      fireEvent(window, new Event('resize'));
      expect(document.documentElement.style.getPropertyValue('--skill-header-height')).toBe('116px');
      fireEvent.click(toggle);
      fireEvent(window, new Event('resize'));
      expect(document.documentElement.style.getPropertyValue('--skill-header-height')).toBe('116px');
    } finally {
      style.remove();
    }
  });

  it.each(['child', 'locked', 'adult'])('keeps library shortcuts appropriate for a %s household session', async mode => {
    vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
    const profile = mode === 'child' ? {id:'learner',display_name:'Learner'} : null;
    vi.stubGlobal('fetch', vi.fn((url:string) => Promise.resolve({ok:true,json:async () => url.endsWith('/household')
      ? {adult:mode === 'adult',profile,csrf_token:'csrf'} : url.endsWith('/post')
      ? {profile,content:[],sessions:[]} : {profile_id:profile?.id,evidence:[]}})));
    await navigate('words');
    const {container} = render(<App householdEnabled navigation={navigation} navigationLayout="sidebar" />);
    if (mode === 'locked') await screen.findByRole('heading', {name:'Choose a learner to see their words.'});
    else if (mode === 'child') await screen.findByRole('heading', {name:'No word practice saved yet.'});
    else await screen.findByRole('link', {name:/Open vocabulary library/});
    const shortcuts = container.querySelector<HTMLElement>('.sidebar-shortcuts')!;
    expect(within(shortcuts).getByRole('link', {name:'My words'}).getAttribute('href')).toBe(mode === 'adult' ? '/vocab' : '#words');
    expect(!!within(shortcuts).queryByRole('link', {name:'Phrasebook'})).toBe(mode === 'adult');
  });

  it('keeps the menu through collection, generator and review routes, including loading or error states', async () => {
    vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ok:false, json:async () => ({error:{message:'Temporarily offline'}})}));
    await navigate('flashcards?word_id=4');
    render(<App navigation={navigation} navigationLayout="sidebar" />);
    const menu = screen.getByRole('navigation', {name:'Activities & tools'});
    for (const hash of ['flashcards', 'generate?word_id=4', 'generate/batch-1', 'review/session-1']) {
      await navigate(hash);
      expect(screen.getByRole('navigation', {name:'Activities & tools'})).toBe(menu);
      expect(within(menu).getByRole('link', {name:'Flashcards'}).getAttribute('aria-current')).toBe('page');
      expect(within(menu).getByRole('link', {name:'Writing'}).getAttribute('href')).toBe('/writing');
    }
    await navigate('home');
    expect(screen.getByRole('navigation', {name:'Activities & tools'})).toBe(menu);
    expect(screen.getByRole('link', {name:'Russian Arcade home'}).getAttribute('href')).toBe('#home');
    expect(within(menu).queryByRole('link', {name:'Home'})).toBeNull();
    expect(within(menu).getByRole('link', {name:'Activities & tools'}).getAttribute('href')).toBe('#activities');
    expect(within(menu).getByRole('link', {name:'Flashcards'}).hasAttribute('aria-current')).toBe(false);
    expect(screen.queryByRole('navigation', {name:'Main navigation'})).toBeNull();
    expect(screen.getByText('Hello! I’m Barsik.')).toBeTruthy();
    await navigate('speaking');
    expect(within(menu).getByRole('link', {name:'Speaking'}).getAttribute('aria-current')).toBe('page');
  });

  it('lets the compact menu expand and keeps Anki inside the optional tools disclosure', async () => {
    vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ok:false, json:async () => ({error:{message:'Offline'}})}));
    await navigate('flashcards');
    render(<App navigation={navigation} navigationLayout="sidebar" />);
    const toggle = screen.getByRole('button', {name:'Activities & tools'});
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    fireEvent.click(toggle);
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    const menu = screen.getByRole('navigation', {name:'Activities & tools'});
    const tools = within(menu).getByText('More tools').closest('details')!;
    expect(tools.open).toBe(false);
    expect(tools.querySelector('a')?.getAttribute('href')).toBe('/tools/anki/');
    fireEvent.click(within(menu).getByRole('link', {name:'Flashcards'}));
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
  });

  it('defaults to the top menu on both home and flashcards without a second menu', async () => {
    vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ok:false,json:async()=>({error:{message:'Offline'}})}));
    await navigate('home');
    render(<App navigation={navigation} />);
    for (const hash of ['home','flashcards','generate','activities']) {
      await navigate(hash);
      expect(screen.getByRole('navigation',{name:'Main navigation'})).toBeTruthy();
      expect(screen.queryByRole('navigation',{name:'Activities & tools'})).toBeNull();
      expect(document.querySelector('header.top')).toBeTruthy();
    }
    expect(document.querySelectorAll('.appearance-picker')).toHaveLength(1);
    const appearance = document.querySelector<HTMLDetailsElement>('header.top .appearance-picker')!;
    expect(appearance).toBeTruthy();
    expect(within(appearance).getByLabelText('Appearance')).toBeTruthy();
    expect(appearance.querySelector('button[value="top"]')?.getAttribute('aria-pressed')).toBe('true');
    expect(document.querySelector('[href="/appearance"]')).toBeNull();
  });
});
