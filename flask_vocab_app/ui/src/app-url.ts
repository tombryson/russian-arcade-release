/** The public page and a demo can be open together; scope URLs to this document. */
export function appBasePath(): string {
  if (typeof document === 'undefined') return '';
  const declared = document.querySelector<HTMLMetaElement>('meta[name="app-base-path"]')?.content;
  return declared?.replace(/\/$/, '') === '/demo' || /^\/demo(?:\/|$)/.test(document.location.pathname) ? '/demo' : '';
}

function scopedPath(url: string, base: string): string {
  const path = url.split(/[?#]/, 1)[0];
  if (path === base || path.startsWith(`${base}/`)
    || (/^\/static(?:\/|$)/.test(path) && !/^\/static\/(?:media|uploads)(?:\/|$)/.test(path))
    || /^\/post\/assets(?:\/|$)/.test(path)
    || /^\/trial\/(?:sign-in|callback|connect|sign-out)/.test(path)) return url;
  return `${base}${url}`;
}

/** Resolve application URLs without moving public assets or authentication into a demo. */
export function appUrl(url: string): string {
  const base = appBasePath();
  if (!base || url.startsWith('//')) return url;
  if (url.startsWith('/')) return scopedPath(url, base);
  if (/^https?:\/\//i.test(url)) {
    try {
      const parsed = new URL(url);
      if (parsed.origin === document.location.origin) {
        const path = scopedPath(parsed.pathname, base);
        if (path !== parsed.pathname) {
          parsed.pathname = path;
          return parsed.href;
        }
      }
    } catch { /* Leave invalid URLs to the browser, as on the public page. */ }
  }
  return url;
}
