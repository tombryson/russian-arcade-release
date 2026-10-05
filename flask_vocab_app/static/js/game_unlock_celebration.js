(() => {
  'use strict';
  // Both application shells can load this file. Keep one controller per page.
  if (window.arcadeGameUnlocks) return;

  const storagePrefix = 'arcade.game-unlocks.v1:';
  const snapshots = new Map();
  const unwritableKeys = new Set();
  let activeKey = null;
  let baselineNext = false;
  let confetti = null;
  let notice = null;
  let confettiTimer = null;
  let noticeTimer = null;

  const identifier = value => typeof value === 'string' && value.length > 0 && value.length <= 256;
  // Reward reversals can leave a signed ledger balance; offer prices stay positive.
  const coins = value => Number.isSafeInteger(value);
  const validOffers = offers => Array.isArray(offers) && offers.length <= 256 &&
    offers.every(offer => offer && identifier(offer.id) && coins(offer.price) && offer.price > 0) &&
    new Set(offers.map(offer => offer.id)).size === offers.length;

  function read(key) {
    if (unwritableKeys.has(key)) return snapshots.get(key);
    let saved;
    try {
      saved = JSON.parse(window.localStorage.getItem(key));
      if (!saved || saved.version !== 1 || !coins(saved.balance) || !validOffers(saved.prices) ||
          !Array.isArray(saved.celebrated) || !saved.celebrated.every(identifier)) saved = null;
    } catch (_) { /* Private browsing and blocked storage still work for this page. */ }
    const remembered = snapshots.get(key);
    if (saved) {
      saved.celebrated = [...new Set([...saved.celebrated, ...(remembered?.celebrated || [])])];
      snapshots.set(key, saved);
    }
    return saved || remembered;
  }

  function write(key, snapshot) {
    snapshots.set(key, snapshot);
    try { window.localStorage.setItem(key, JSON.stringify(snapshot)); }
    catch (_) {
      // A readable but unwritable store may contain an older balance/price.
      // Prefer the current page's snapshot after a failed write.
      unwritableKeys.add(key);
    }
  }

  function clearConfetti() {
    window.clearTimeout(confettiTimer);
    confettiTimer = null;
    confetti?.remove();
    confetti = null;
  }

  function clearNotice() {
    window.clearTimeout(noticeTimer);
    noticeTimer = null;
    notice?.remove();
    notice = null;
  }

  function reset() {
    clearConfetti();
    clearNotice();
    if (activeKey) baselineNext = true;
    activeKey = null;
  }

  function pause() {
    // A missing/disabled catalogue cannot prove that a later balance crossed
    // an unchanged price. Establish fresh offer baselines when it returns.
    const previous = activeKey && read(activeKey);
    if (previous) write(activeKey, {...previous, prices: []});
    reset();
  }

  function shopUrl(href) {
    try {
      const url = new URL(href, window.location.href);
      if (url.origin === window.location.origin && /^https?:$/.test(url.protocol)) {
        return url.pathname + url.search + url.hash;
      }
    } catch (_) { /* Use the local shop if a caller supplied an invalid URL. */ }
    return '/#shop';
  }

  function celebrate(options) {
    clearConfetti();
    clearNotice();
    if (!document.body) return;
    const russian = options.language === 'ru';
    notice = document.createElement('aside');
    notice.className = 'game-unlock-notice';
    notice.setAttribute('aria-label', russian ? 'Новая игра доступна' : 'Game unlock available');
    const message = document.createElement('strong');
    message.className = 'game-unlock-notice-message';
    message.setAttribute('role', 'status');
    message.textContent = russian ? 'Вы можете открыть игру!' : 'You can unlock a game!';
    const link = document.createElement('a');
    link.className = 'game-unlock-notice-link';
    link.href = shopUrl(options.shopHref || '/#shop');
    link.textContent = russian ? 'В магазин' : 'Visit shop';
    link.setAttribute('hx-boost', 'false');
    link.addEventListener('click', () => { clearConfetti(); clearNotice(); });
    const close = document.createElement('button');
    close.type = 'button';
    close.className = 'game-unlock-notice-close';
    close.setAttribute('aria-label', russian ? 'Закрыть уведомление' : 'Dismiss notification');
    close.textContent = '×';
    close.addEventListener('click', () => { clearConfetti(); clearNotice(); });
    notice.append(message, link, close);
    document.body.append(notice);
    // Do not remove a link or button while a keyboard user is interacting with
    // it. Finish the existing timeout on focusout without starting more timers.
    let expired = false;
    notice.addEventListener('focusout', event => {
      if (expired && !notice?.contains(event.relatedTarget)) clearNotice();
    });
    noticeTimer = window.setTimeout(() => {
      noticeTimer = null;
      expired = true;
      if (!notice?.contains(document.activeElement)) clearNotice();
    }, 8000);

    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return;
    confetti = document.createElement('div');
    confetti.className = 'game-unlock-confetti';
    confetti.setAttribute('aria-hidden', 'true');
    for (let i = 0; i < 40; i += 1) confetti.append(document.createElement('i'));
    document.body.append(confetti);
    confettiTimer = window.setTimeout(clearConfetti, 2800);
  }

  function update(data, options = {}) {
    const shop = data?.game_shop;
    const profile = typeof data?.profile_id === 'number' && Number.isSafeInteger(data.profile_id)
      ? String(data.profile_id) : data?.profile_id;
    const scope = options.scope || window.location.origin;
    if (!identifier(profile) || !identifier(scope) || !coins(data?.balance) ||
        !shop || !identifier(shop.policy) || typeof shop.enabled !== 'boolean' ||
        !validOffers(shop.offers)) {
      pause();
      return false;
    }

    const key = storagePrefix + JSON.stringify([scope, profile, shop.policy]);
    if (activeKey && activeKey !== key) reset();
    activeKey = key;
    const previous = read(key);
    const celebrated = new Set(previous?.celebrated || []);
    const prices = new Map((previous?.prices || []).map(offer => [offer.id, offer.price]));
    const offers = shop.enabled ? shop.offers : [];
    const crossed = !baselineNext && offers.some(offer => !celebrated.has(offer.id) &&
      prices.get(offer.id) === offer.price && previous.balance < offer.price &&
      data.balance >= offer.price && data.balance > previous.balance);

    // Affordable offers on the first observation, new offers, and changed
    // prices establish a baseline; spending coins cannot replay these moments.
    offers.forEach(offer => { if (data.balance >= offer.price) celebrated.add(offer.id); });
    write(key, {version: 1, balance: data.balance, prices: offers.map(({id, price}) => ({id, price})), celebrated: [...celebrated]});
    baselineNext = false;

    if (!offers.some(offer => data.balance >= offer.price)) {
      clearConfetti();
      clearNotice();
    }
    if (crossed) celebrate(options);
    return crossed;
  }

  window.arcadeGameUnlocks = {update, reset};
})();
