import {readFileSync} from 'node:fs';
import {afterEach, describe, expect, it, vi} from 'vitest';

const script = readFileSync('../static/js/game_unlock_celebration.js', 'utf8');
const css = readFileSync('../static/css/game_unlock_celebration.css', 'utf8');
const options = {scope: '/post', language: 'en', shopHref: '/post/#shop'};
const offers = [{id: 'word-drop', price: 200}, {id: 'word-grid', price: 400}];
const payload = (balance, patch = {}) => ({profile_id: 'learner-one', balance,
  game_shop: {enabled: true, policy: 'game-shop-v2', offers}, ...patch});
const withOffers = (balance, prices) => payload(balance, {game_shop: {enabled: true, policy: 'game-shop-v2', offers: prices}});
const scene = () => document.querySelector('.game-unlock-confetti');
const notice = () => document.querySelector('.game-unlock-notice');

function setup({reducedMotion = false, preserveStorage = false} = {}) {
  window.arcadeGameUnlocks?.reset();
  delete window.arcadeGameUnlocks;
  if (!preserveStorage) localStorage.clear();
  vi.useFakeTimers();
  window.matchMedia = vi.fn(() => ({matches: reducedMotion}));
  window.eval(script);
  return (data, overrides) => {
    const crossed = window.arcadeGameUnlocks.update(data, {...options, ...overrides});
    // jsdom queues zero-delay localStorage events for each persisted snapshot.
    vi.advanceTimersByTime(0);
    return crossed;
  };
}

afterEach(() => {
  window.arcadeGameUnlocks?.reset();
  delete window.arcadeGameUnlocks;
  vi.restoreAllMocks();
  vi.useRealTimers();
  document.body.replaceChildren();
  localStorage.clear();
});

describe('game unlock celebrations', () => {
  it('celebrates an earned threshold exactly once without changing progression data', () => {
    const update = setup();
    expect(update(payload(199))).toBe(false);
    const earned = payload(200);
    const original = JSON.stringify(earned);
    expect(update(earned)).toBe(true);
    expect(JSON.stringify(earned)).toBe(original);
    expect(scene().children).toHaveLength(40);
    expect(scene().getAttribute('aria-hidden')).toBe('true');
    expect(notice().querySelector('[role="status"]').textContent).toBe('You can unlock a game!');
    expect(notice().querySelector('a').getAttribute('href')).toBe('/post/#shop');
    expect(vi.getTimerCount()).toBe(2);
    const firstScene = scene();
    const firstNotice = notice();
    for (let i = 0; i < 20; i += 1) expect(update(payload(200))).toBe(false);
    expect(scene()).toBe(firstScene);
    expect(notice()).toBe(firstNotice);
    expect(vi.getTimerCount()).toBe(2);
    expect(document.querySelector('[style]')).toBeNull();
  });

  it('establishes a rich profile baseline without celebrating or replaying after spending', () => {
    const update = setup();
    expect(update(payload(350))).toBe(false);
    expect(scene()).toBeNull();
    expect(notice()).toBeNull();
    expect(vi.getTimerCount()).toBe(0);
    update(payload(20));
    expect(update(payload(200))).toBe(false);
    expect(update(payload(400))).toBe(true);
  });

  it.each([false, true])('celebrates a negative balance reaching a 500-coin offer (reload=%s)', reload => {
    let update = setup();
    const milestone = [{id: 'word-drop', price: 500}];
    expect(update(withOffers(-3, milestone))).toBe(false);
    expect(notice()).toBeNull();
    if (reload) update = setup({preserveStorage: true});
    expect(update(withOffers(500, milestone))).toBe(true);
    expect(scene().children).toHaveLength(40);
    expect(update(withOffers(500, milestone))).toBe(false);
  });

  it('combines multiple crossed offers into one scene and remembers each milestone', () => {
    const update = setup();
    update(payload(100));
    expect(update(payload(450))).toBe(true);
    expect(document.querySelectorAll('.game-unlock-confetti')).toHaveLength(1);
    expect(document.querySelectorAll('.game-unlock-notice')).toHaveLength(1);
    update(payload(0));
    expect(scene()).toBeNull();
    expect(notice()).toBeNull();
    expect(update(payload(450))).toBe(false);
  });

  it('celebrates a later, higher milestone while replacing the previous scene and timers', () => {
    const update = setup();
    update(payload(199));
    update(payload(200));
    const first = scene();
    vi.advanceTimersByTime(1000);
    expect(update(payload(400))).toBe(true);
    expect(first.isConnected).toBe(false);
    expect(scene().children).toHaveLength(40);
    expect(vi.getTimerCount()).toBe(2);
  });

  it('retains baselines and consumed milestones across reloads and route changes', () => {
    let update = setup();
    update(payload(199));
    update = setup({preserveStorage: true});
    expect(update(payload(200))).toBe(true);
    update = setup({preserveStorage: true});
    window.history.replaceState(null, '', '/writing');
    expect(update(payload(200))).toBe(false);
    update(payload(0));
    expect(update(payload(201))).toBe(false);
    expect(update(payload(400))).toBe(true);
  });

  it('keeps profile, deployment scope and price policy milestones independent', () => {
    const update = setup();
    update(payload(199));
    update(payload(200));
    expect(update(payload(199, {profile_id: 'learner-two'}))).toBe(false);
    expect(notice()).toBeNull();
    expect(update(payload(200, {profile_id: 'learner-two'}))).toBe(true);
    expect(update(payload(199), {scope: '/demo'})).toBe(false);
    expect(notice()).toBeNull();
    expect(update(payload(200), {scope: '/demo'})).toBe(true);
    const nextPolicy = balance => payload(balance, {game_shop: {enabled: true, policy: 'game-shop-v3', offers}});
    expect(update(nextPolicy(199))).toBe(false);
    expect(notice()).toBeNull();
    expect(update(nextPolicy(200))).toBe(true);
    window.arcadeGameUnlocks.reset();
    expect(update(payload(200))).toBe(false);
  });

  it('does not treat a price reduction or an introduced offer as earned coins', () => {
    const update = setup();
    update(payload(150));
    const reduced = [{id: 'word-drop', price: 100}, offers[1]];
    expect(update(withOffers(150, reduced))).toBe(false);
    expect(notice()).toBeNull();
    update(withOffers(50, reduced));
    expect(update(withOffers(100, reduced))).toBe(false);
    const introduced = [...reduced, {id: 'new-game', price: 110}];
    expect(update(withOffers(120, introduced))).toBe(false);
    expect(notice()).toBeNull();
    expect(update(withOffers(400, introduced))).toBe(true);
  });

  it('does not celebrate another profile\'s accumulated coins when switching back', () => {
    const update = setup();
    update(payload(199));
    update(payload(100, {profile_id: 'learner-two'}));
    expect(update(payload(200))).toBe(false);
    expect(notice()).toBeNull();
    expect(update(payload(400))).toBe(true);
  });

  it('treats the first update after logout or explicit profile reset as a baseline', () => {
    const update = setup();
    update(payload(199));
    window.arcadeGameUnlocks.reset();
    expect(update(payload(200))).toBe(false);
    expect(notice()).toBeNull();
    expect(update(payload(400))).toBe(true);
  });

  it('requires a stable price even if balance and price change together', () => {
    const update = setup();
    update(payload(150));
    const reduced = [{id: 'word-drop', price: 175}];
    expect(update(withOffers(180, reduced))).toBe(false);
    expect(notice()).toBeNull();
  });

  it('can celebrate a repriced offer on a later genuine crossing from below', () => {
    const update = setup();
    update(payload(100));
    const repriced = [{id: 'word-drop', price: 250}];
    expect(update(withOffers(150, repriced))).toBe(false);
    expect(update(withOffers(250, repriced))).toBe(true);
  });

  it('clears the notice after an offer is purchased and absent from the catalogue', () => {
    const update = setup();
    update(payload(199));
    update(payload(200));
    expect(update(withOffers(200, [offers[1]]))).toBe(false);
    expect(notice()).toBeNull();
    expect(scene()).toBeNull();
    expect(vi.getTimerCount()).toBe(0);
  });

  it('never celebrates disabled shops and establishes a new baseline on re-enabling', () => {
    const update = setup();
    update(payload(199));
    expect(update(payload(200, {game_shop: {enabled: false, policy: 'game-shop-v2', offers}}))).toBe(false);
    expect(notice()).toBeNull();
    expect(update(payload(200))).toBe(false);
    expect(update(payload(400))).toBe(true);
  });

  it.each([
    null,
    {},
    payload(NaN),
    payload(1.5),
    payload(Number.MAX_SAFE_INTEGER + 1),
    payload('200'),
    payload(200, {profile_id: null}),
    payload(200, {game_shop: {enabled: true, offers}}),
    payload(200, {game_shop: {enabled: true, policy: 'game-shop-v2'}}),
    withOffers(200, [{id: 'word-drop', price: '200'}]),
    withOffers(200, [{id: 'word-drop', price: 0}]),
    withOffers(200, [{id: 'word-drop', price: -1}]),
    withOffers(200, [offers[0], offers[0]]),
  ])('ignores malformed progression without timers or stale threshold celebrations: %j', data => {
    const update = setup();
    update(payload(199));
    expect(update(data)).toBe(false);
    expect(notice()).toBeNull();
    expect(vi.getTimerCount()).toBe(0);
    expect(update(payload(200))).toBe(false);
    expect(update(payload(400))).toBe(true);
  });

  it('handles damaged stored data as an initial baseline', () => {
    const update = setup();
    update(payload(199));
    const key = localStorage.key(0);
    localStorage.setItem(key, '{invalid json');
    const reloaded = setup({preserveStorage: true});
    expect(reloaded(payload(200))).toBe(false);
    expect(reloaded(payload(400))).toBe(true);
  });

  it.each(['all', 'writes'])('deduplicates in memory when %s storage access is blocked', blocked => {
    const update = setup();
    update(payload(199));
    if (blocked === 'all') vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('Blocked'); });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Blocked'); });
    expect(update(payload(200))).toBe(true);
    window.arcadeGameUnlocks.reset();
    update(payload(0));
    expect(update(payload(200))).toBe(false);
    expect(update(payload(400))).toBe(true);
  });

  it('keeps the localized notice while skipping confetti for reduced motion', () => {
    const update = setup({reducedMotion: true});
    update(payload(199));
    expect(update(payload(200), {language: 'ru', shopHref: '/demo/#shop'})).toBe(true);
    expect(scene()).toBeNull();
    expect(notice().textContent).toContain('Вы можете открыть игру!');
    expect(notice().querySelector('a').textContent).toBe('В магазин');
    expect(notice().querySelector('button').getAttribute('aria-label')).toBe('Закрыть уведомление');
    expect(notice().querySelector('a').getAttribute('href')).toBe('/demo/#shop');
    expect(vi.getTimerCount()).toBe(1);
    expect(css).toContain('@media (prefers-reduced-motion: reduce)');
    expect(css).toContain('pointer-events: none');
  });

  it.each(['javascript:alert(1)', 'https://other.example/shop', '//other.example/shop'])('keeps the shop link local for unsafe destinations: %s', shopHref => {
    const update = setup();
    update(payload(199));
    update(payload(200), {shopHref});
    expect(notice().querySelector('a').getAttribute('href')).toBe('/#shop');
  });

  it('automatically removes the scene and notice without moving focus from learning', () => {
    const update = setup();
    const draft = document.createElement('textarea');
    draft.value = 'Я учусь.';
    document.body.append(draft);
    draft.focus();
    draft.setSelectionRange(1, 3);
    update(payload(199));
    update(payload(200));
    expect(document.activeElement).toBe(draft);
    vi.advanceTimersByTime(2800);
    expect(scene()).toBeNull();
    expect(notice()).not.toBeNull();
    vi.advanceTimersByTime(5200);
    expect(notice()).toBeNull();
    expect(vi.getTimerCount()).toBe(0);
    expect(document.activeElement).toBe(draft);
    expect(draft.value).toBe('Я учусь.');
    expect([draft.selectionStart, draft.selectionEnd]).toEqual([1, 3]);
  });

  it('lets keyboard users finish interacting with the notice after its timeout', () => {
    const update = setup();
    const draft = document.createElement('textarea');
    document.body.append(draft);
    update(payload(199));
    update(payload(200));
    const link = notice().querySelector('a');
    link.focus();
    vi.advanceTimersByTime(8000);
    expect(notice()).not.toBeNull();
    expect(document.activeElement).toBe(link);
    expect(vi.getTimerCount()).toBe(0);
    draft.focus();
    expect(notice()).toBeNull();
    expect(document.activeElement).toBe(draft);
  });

  it('dismisses and resets immediately without losing deduplication history', () => {
    const update = setup();
    update(payload(199));
    update(payload(200));
    notice().querySelector('button').click();
    expect(notice()).toBeNull();
    expect(scene()).toBeNull();
    expect(vi.getTimerCount()).toBe(0);
    expect(update(payload(400))).toBe(true);
    window.arcadeGameUnlocks.reset();
    expect(notice()).toBeNull();
    expect(scene()).toBeNull();
    expect(vi.getTimerCount()).toBe(0);
    expect(update(payload(400))).toBe(false);
  });

  it('tolerates loading in both shells without losing the active controller', () => {
    const update = setup();
    update(payload(199));
    const controller = window.arcadeGameUnlocks;
    window.eval(script);
    expect(window.arcadeGameUnlocks).toBe(controller);
    expect(update(payload(200))).toBe(true);
    expect(vi.getTimerCount()).toBe(2);
  });
});
