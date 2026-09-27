import type { ComponentChildren } from 'preact';
import artwork from './assets/barsik.webp';
export function Art() {
  return <img class="courier-art" src={artwork} width="1254" height="1254" alt="Barsik, a ginger cat in a blue coat, holding a letter beside a red postbox on a little yellow moon." />;
}
export function Sheet({ children }: { children: ComponentChildren }) { return <div class="letter">{children}</div>; }
export function Feedback({ children }: { children: ComponentChildren }) { return <div class="feedback" role="status" aria-atomic="true">{children}</div>; }
export function ActivityLink({ title, description, href, mark, detail }: { title: string; description: string; href: string; mark: string; detail?: string }) {
  return <a class="activity-link" href={href}><span class="activity-mark" aria-hidden="true">{mark}</span><span class="activity-copy">{detail && <><span class="activity-detail">{detail}</span>{' '}</>}<strong>{title}</strong>{' '}<span>{description}</span></span><span class="activity-arrow" aria-hidden="true">↗</span></a>;
}
