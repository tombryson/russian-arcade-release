import {useEffect, useRef, useState} from 'preact/hooks';
import {GameArtwork} from './GameBoards';
import {useGameText} from './GameLocale';
import {ApiError} from './learning-api';
import {getGames, purchaseGame, type GameCatalogueState, type GameSummary, type JourneyGameId} from './journey-games-api';
import shopArtwork from './assets/barsik-shop-v1.png';
import './styles/game-shop.css';

const profileErrors = new Set(['profile_required', 'learner_required', 'profile_changed', 'unauthorized', 'csrf_failed']);
const priceErrors = new Set(['price_changed', 'insufficient_funds', 'insufficient_coins']);
type ShopError = {message:string; kind:'load'|'purchase'|'profile'; gameId?:JourneyGameId};
type PurchaseAttempt = {gameId:JourneyGameId; requestId:string; price:number};

function Coin({amount}: {amount:number|string}) {
  return <span class="shop-coin-amount"><span class="shop-coin" aria-hidden="true">Л</span><span>{amount}</span></span>;
}

export function GameShop({profileHref='/post/profiles'}: {profileHref?:string}) {
  const t = useGameText();
  const [catalogue, setCatalogue] = useState<GameCatalogueState>();
  const [error, setError] = useState<ShopError>();
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState<JourneyGameId|'load'|null>('load');
  const [fresh, setFresh] = useState(false);
  const mounted = useRef(false);
  const heading = useRef<HTMLHeadingElement>(null);
  const pending = useRef(false);
  const owner = useRef<string|null|undefined>(undefined);
  // Keep the same id and quoted price if a response is lost after payment.
  const attempt = useRef<PurchaseAttempt>();

  function accept(next:GameCatalogueState) {
    if (!mounted.current) return;
    if (owner.current !== undefined && owner.current !== next.profile_id) {
      throw new ApiError(t('Your profile changed. Reopen this page before continuing.'), 'profile_changed');
    }
    owner.current = next.profile_id;
    setCatalogue(next);
    setFresh(true);
  }
  function report(cause:unknown, kind:'load'|'purchase', gameId?:JourneyGameId) {
    if (!mounted.current) return;
    const profile = cause instanceof ApiError && profileErrors.has(cause.code);
    if (profile) { setCatalogue(undefined); setFresh(false); }
    setError({message:cause instanceof Error ? cause.message : t('The shop could not load. Please try again.'), kind:profile ? 'profile' : kind, gameId});
  }
  async function reload() {
    if (pending.current) return;
    pending.current = true;
    setBusy('load');
    setFresh(false);
    setError(undefined);
    try { accept(await getGames()); }
    catch (cause) { report(cause, 'load'); }
    finally { pending.current = false; if (mounted.current) setBusy(null); }
  }
  useEffect(() => {
    mounted.current = true;
    heading.current?.focus({preventScroll:true});
    const controller = new AbortController();
    pending.current = true;
    void getGames(controller.signal).then(accept).catch(cause => {
      if (!controller.signal.aborted) report(cause, 'load');
    }).finally(() => {
      pending.current = false;
      if (mounted.current && !controller.signal.aborted) setBusy(null);
    });
    return () => { mounted.current = false; controller.abort(); };
  }, []);

  async function buy(game:GameSummary) {
    if (pending.current || !fresh || !catalogue?.shop?.enabled || catalogue.public_demo || game.purchase?.owned || !game.purchase?.can_purchase) return;
    if (attempt.current && attempt.current.gameId !== game.id) return;
    pending.current = true;
    setBusy(game.id);
    setError(undefined);
    setNotice('');
    attempt.current ??= {gameId:game.id, requestId:crypto.randomUUID(), price:game.purchase.price};
    try {
      const receipt = await purchaseGame(game.id, attempt.current.requestId, attempt.current.price);
      if (!mounted.current) return;
      attempt.current = undefined;
      setFresh(false);
      // Only the confirmed receipt changes ownership. Prices come from a fresh catalogue.
      setCatalogue(previous => previous && ({...previous,
        shop:previous.shop && {...previous.shop, balance:receipt.balance},
        games:previous.games.map(item => item.id===receipt.game_id ? {...item, unlocked:true, purchase:{...item.purchase!, owned:true, can_purchase:false}} : item)}));
      setNotice(t('{0} is yours. You can play it whenever you like.', {0:t(game.title)}));
      try { accept(await getGames()); }
      catch (cause) { report(cause, 'load'); }
    } catch (cause) {
      if (!mounted.current) return;
      if (cause instanceof ApiError && priceErrors.has(cause.code)) {
        attempt.current = undefined;
        setFresh(false);
        try { accept(await getGames()); report(cause, 'purchase', game.id); }
        catch (refreshError) { report(refreshError, 'load'); }
      } else report(cause, 'purchase', game.id);
    } finally {
      pending.current = false;
      if (mounted.current) setBusy(null);
    }
  }
  const shop = catalogue?.shop;
  const signedOut = catalogue && !catalogue.profile_id && !catalogue.public_demo;
  const games = catalogue?.games.filter(game => game.id !== 'pairs') ?? [];
  const balance = shop?.balance ?? null;
  return <section class="page game-shop" aria-labelledby="game-shop-title">
    <a class="text-link game-shop-back" href="#activities">← {t('All activities')}</a>
    <div class="game-shop-hero">
      <div class="game-shop-welcome">
        <h1 id="game-shop-title" ref={heading} tabIndex={-1}>{t('Shop')}</h1>
        <p class="game-shop-intro">{t('Unlock a game with Lingocoins. It’s yours to play whenever you like.')}</p>
        {!catalogue?.public_demo && <><div class="game-shop-wallet"><span>{t('Your balance')}</span><strong aria-label={balance===null ? t('Balance unavailable') : t('{0} Lingocoins', {0:balance})}><Coin amount={balance ?? '—'}/></strong></div>
        <p class="game-shop-prices">{t('Your first game costs 25 Lingocoins. Each game after that costs 50.')}</p>
        <a class="text-link" href="#activities">{t('Earn coins through practice')} <span aria-hidden="true">→</span></a></>}
      </div>
      <div class="game-shop-illustration"><img src={shopArtwork} alt={t('Barsik sitting at his little shop, ready to welcome you.')} width="1254" height="1254" fetchPriority="high"/></div>
    </div>
    <div class="game-shop-notices" aria-live="polite" aria-atomic="true">{notice && <p class="game-shop-success">{notice}</p>}</div>
    {error && <div class="game-shop-error" role="alert"><p>{error.message}</p>{error.kind==='profile' ? <a class="text-link" href={profileHref}>{t('Choose your profile')}</a> : error.kind==='load' ? <button class="text-link" disabled={!!busy} onClick={() => void reload()}>{t('Refresh shop')}</button> : attempt.current && <button class="text-link" disabled={!!busy} onClick={() => {const game=games.find(item=>item.id===error.gameId);if(game)void buy(game);}}>{t('Try again')}</button>}</div>}
    {signedOut && <p class="game-shop-profile"><a class="text-link" href={profileHref}>{t('Choose your profile')}</a> {t('to save your games and use your Lingocoins.')}</p>}
    {catalogue?.public_demo && <p class="game-shop-demo">{t('Try the sample games here. The shop is available in your own installation.')}</p>}
    {!catalogue && busy==='load' && <p role="status">{t('Opening the shop…')}</p>}
    {catalogue && <div class="game-shop-grid">{games.map(game => {
      const owned = game.purchase?.owned ?? game.unlocked;
      const sample = game.availability==='sample';
      const playable = (owned || !!game.active_session_id || sample) && game.availability!=='local-only';
      const price = game.purchase?.price ?? shop?.price ?? 50;
      const available = !!shop?.enabled && !catalogue.public_demo && !signedOut && game.availability!=='local-only';
      const shortfall = balance===null ? 0 : Math.max(0, price-balance);
      const content = <><div class="game-shop-art"><GameArtwork gameId={game.id}/></div><div class="game-shop-card-copy"><h2>{t(game.title)}</h2><p>{t(game.description)}</p></div></>;
      return playable ? <a class="game-shop-card is-owned" key={game.id} href={game.active_session_id ? `#games/session/${game.active_session_id}` : `#games/${game.id}`} aria-label={t('Play {0}', {0:t(game.title)})}>{content}<span class="game-shop-card-foot"><span>{t(sample ? 'Sample game' : 'Yours to play')}</span><strong>{t(game.active_session_id ? 'Continue' : 'Play')} <span aria-hidden="true">→</span></strong></span></a> : <article class="game-shop-card" key={game.id}>{content}<div class="game-shop-card-foot game-shop-buy">
        {available ? <><button class="game-shop-unlock" aria-label={t('Unlock {0} for {1} Lingocoins', {0:t(game.title),1:price})} disabled={!!busy || !fresh || !game.purchase?.can_purchase || !!attempt.current && attempt.current.gameId!==game.id} onClick={() => void buy(game)}>{busy===game.id ? t('Unlocking…') : <><span>{t('Unlock for')}</span><Coin amount={price}/></>}</button>{shortfall>0 && <small>{t('{0} more coins needed', {0:shortfall})}</small>}</> : <span>{t(catalogue.public_demo || game.availability==='local-only' ? 'Available in your own installation.' : 'Choose a profile to unlock games.')}</span>}
      </div></article>;
    })}</div>}
  </section>;
}
