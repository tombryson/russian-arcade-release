import { options } from 'preact';
import { appUrl } from './app-url';

/** Cover native JSX, including lazy components and URLs returned by the API. */
export function installAppUrlVnodes(): () => void {
  const previous = options.vnode;
  const rewrite: typeof options.vnode = vnode => {
    previous?.(vnode);
    if (typeof vnode.type !== 'string') return;
    const props = vnode.props as Record<string, unknown>;
    if (props['data-app-exit'] !== undefined && props['data-app-exit'] !== false) return;
    for (const attribute of ['href', 'src', 'action', 'formAction', 'formaction', 'poster']) {
      const value = props[attribute];
      if (typeof value === 'string') props[attribute] = appUrl(value);
    }
  };
  options.vnode = rewrite;
  return () => { if (options.vnode === rewrite) options.vnode = previous; };
}
