import type { ComponentChildren, Ref } from 'preact';

type ActivityHeaderProps = {
  title: string;
  description?: string;
  actions?: ComponentChildren;
  headingRef?: Ref<HTMLHeadingElement>;
  headingId?: string;
  headingTabIndex?: number;
};

export function ActivityHeader({ title, description, actions, headingRef, headingId, headingTabIndex }: ActivityHeaderProps) {
  return <header class="activity-header">
    <div class="activity-header-copy">
      <h1 ref={headingRef} id={headingId} tabIndex={headingTabIndex}>{title}</h1>
      {description && <p class="activity-description">{description}</p>}
    </div>
    {actions && <div class="activity-header-actions">{actions}</div>}
  </header>;
}
