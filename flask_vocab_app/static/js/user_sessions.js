/* A profile change in another tab must not leave the old activity on screen. */
(() => {
  'use strict';
  function watch(marker) {
  const current=marker.dataset.profileId || '';
  const scope=marker.dataset.sessionScope;
  let checking=false,leaving=false;
  async function check() {
    if (checking || leaving || document.visibilityState!=='visible') return;
    checking=true;
    try {
      const response=await fetch('/api/v1/user-session',{credentials:'same-origin',cache:'no-store',headers:{Accept:'application/json'}});
      if (!response.ok) return;
      const state=await response.json();
      if ((scope && state.session_scope && state.session_scope!==scope) ||
          (state.mode==='personal' && (state.profile?.id || '')!==current)) {
        leaving=true;
        // A hash-only navigation would leave the old app/profile mounted.
        if (window.location.pathname==='/') {
          window.history.replaceState(null,'','/#home');
          window.location.reload();
        } else window.location.assign('/#home');
      }
    } catch (_) { /* Keep a draft during connection problems; the server rejects stale writes. */ }
    finally {checking=false;}
  }
  try {localStorage.setItem('russian-arcade-session',JSON.stringify({profile:current,scope,at:Date.now()}));} catch (_) { /* Storage is optional. */ }
  window.addEventListener('storage',event=>{if (event.key==='russian-arcade-session') void check();});
  document.addEventListener('visibilitychange',()=>{if (document.visibilityState==='visible') void check();});
  window.addEventListener('pageshow',event=>{if (event.persisted) void check();});
  setInterval(check,30000);
  }
  const marker=document.querySelector('[data-user-session]');
  if (marker) watch(marker);
  else {
    // The activity shell mounts after its JavaScript bundle has loaded.
    const observer=new MutationObserver(()=>{
      const mounted=document.querySelector('[data-user-session]');
      if (mounted) {observer.disconnect();watch(mounted);}
    });
    observer.observe(document.documentElement,{childList:true,subtree:true});
    setTimeout(()=>observer.disconnect(),30000);
  }
})();
