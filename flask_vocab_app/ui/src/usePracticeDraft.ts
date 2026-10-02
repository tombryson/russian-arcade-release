import {useEffect, useLayoutEffect, useRef, useState} from 'preact/hooks';
import {api, ApiError, type PracticeDraft, type PracticeSession} from './learning-api';
import {appUrl} from './app-url';

/** Draft acknowledgements never replace input typed while the request was in flight. */
export function usePracticeDraft(session: PracticeSession | undefined, text: string, setText: (text: string) => void, language: 'en' | 'ru') {
  const t = (en: string, ru: string) => language === 'ru' ? ru : en;
  const [state, setState] = useState<'saved'|'dirty'|'saving'|'failed'|'conflict'|'blocked'>('saved');
  const [message, setMessage] = useState('');
  const [leaving, setLeaving] = useState<string>();
  const active = !!session?.draft_enabled && session.item?.type === 'controlled_text' && session.status === 'active';
  const identity = session ? `${session.profile_id}:${session.id}:${session.item?.id ?? ''}` : '';
  const current = useRef({session, text, identity, active});
  current.current = {session, text, identity, active};
  const version = useRef(0);
  const stored = useRef('');
  const storedIdentity = useRef('');
  const halted = useRef(false);
  const pending = useRef<{identity:string;body:{submission_id:string;item_id:string;expected_revision:number;expected_draft_revision:number;response:{text:string}}}>();
  const inFlight = useRef<Promise<boolean>>();
  const alive = useRef(true);

  useLayoutEffect(() => {
    storedIdentity.current = identity; stored.current = session?.draft?.response.text ?? '';
    version.current = session?.draft?.revision ?? 0; pending.current = undefined; inFlight.current = undefined; halted.current = false;
    setState('saved'); setMessage(''); setLeaving(undefined);
    if (active) setText(stored.current);
  }, [identity, active]);
  useEffect(() => {alive.current = true; return () => {alive.current = false;};}, []);

  async function flush(): Promise<boolean> {
    const value = current.current;
    if (!value.active || storedIdentity.current !== value.identity) return true;
    if (halted.current) return false;
    if (inFlight.current) {if (!await inFlight.current) return false; return flush();}
    if (!pending.current && value.text === stored.current) return true;
    const task = value.session!;
    const command = pending.current ?? {identity:value.identity, body:{submission_id:crypto.randomUUID(), item_id:task.item!.id,
      expected_revision:task.revision, expected_draft_revision:version.current, response:{text:value.text}}};
    pending.current = command; setState('saving'); setMessage('');
    const request = (async () => {
      try {
        const result = await api<{draft:PracticeDraft}>(`/api/v1/learning-sessions/${task.id}/draft`, command.body);
        if (!alive.current || current.current.identity !== command.identity) return false;
        version.current = result.draft.revision; stored.current = command.body.response.text; pending.current = undefined;
        setState(current.current.text === stored.current ? 'saved' : 'dirty'); return true;
      } catch (reason) {
        if (!alive.current || current.current.identity !== command.identity) return false;
        const conflict = reason instanceof ApiError && ['stale_revision','stale_draft','stale_draft_revision'].includes(reason.code);
        const blocked = reason instanceof ApiError && ['profile_changed','account_changed','access_required','locked','csrf_failed','not_found'].includes(reason.code);
        if (conflict || blocked) {halted.current = true; pending.current = undefined;}
        setState(conflict ? 'conflict' : blocked ? 'blocked' : 'failed');
        setMessage(conflict ? t('This draft changed in another tab. Copy your text before loading the saved version.', 'Черновик изменился в другой вкладке. Скопируйте текст перед загрузкой сохранённой версии.')
          : blocked ? t('Your workspace changed. Your unsaved text is still here to copy.', 'Рабочая область изменилась. Несохранённый текст можно скопировать.')
            : t('Your draft could not be saved. Your text is still here.', 'Не удалось сохранить черновик. Текст остался на странице.'));
        return false;
      } finally {if (current.current.identity === command.identity) inFlight.current = undefined;}
    })();
    inFlight.current = request;
    const success = await request;
    if (success && current.current.identity === command.identity && current.current.text !== stored.current) return flush();
    return success;
  }

  useEffect(() => {
    if (!active || storedIdentity.current !== identity || halted.current || pending.current) return;
    if (text === stored.current) {setState('saved'); return;}
    setState('dirty');
    const timer = setTimeout(() => {void flush();}, 800);
    return () => clearTimeout(timer);
  }, [text, identity, active, session?.revision]);

  useEffect(() => {
    let previousUrl = window.location.href;
    const dirty = () => current.current.active && (current.current.text !== stored.current || !!pending.current);
    const unload = (event: BeforeUnloadEvent) => {if (dirty()) {event.preventDefault(); event.returnValue = '';}};
    const click = (event: MouseEvent) => {
      const link = event.target instanceof Element ? event.target.closest<HTMLAnchorElement>('a[href]') : null;
      if (!link || event.defaultPrevented || event.button || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || link.target || link.hasAttribute('download') || !dirty()) return;
      const destination = new URL(link.href, window.location.href);
      if (destination.href === window.location.href) return;
      event.preventDefault(); event.stopImmediatePropagation();
      const href = destination.href; setLeaving(href);
      void flush().then(saved => {if (saved && alive.current) window.location.assign(appUrl(href));});
    };
    const hash = (event: HashChangeEvent) => {
      if (!dirty()) {previousUrl = window.location.href; return;}
      const destination = window.location.href;
      event.stopImmediatePropagation();
      window.history.replaceState(window.history.state, '', previousUrl);
      setLeaving(destination);
      void flush().then(saved => {if (saved && alive.current) window.location.assign(destination);});
    };
    window.addEventListener('beforeunload', unload); document.addEventListener('click', click, true);
    window.addEventListener('hashchange', hash, true);
    return () => {window.removeEventListener('beforeunload', unload); document.removeEventListener('click', click, true);window.removeEventListener('hashchange', hash, true);};
  }, []);

  function discardAndLeave() {const destination=leaving;if (!destination) return;stored.current=current.current.text;pending.current=undefined;window.location.assign(appUrl(destination));}
  return {active, state, message, leaving, flush, discardAndLeave,
    cancelLeave: () => setLeaving(undefined),
    status: state === 'saving' ? t('Saving…','Сохраняем…') : state === 'saved' ? t('Saved','Сохранено') : state === 'dirty' ? t('Unsaved changes','Есть несохранённые изменения') : t('Save not confirmed','Сохранение не подтверждено')};
}
