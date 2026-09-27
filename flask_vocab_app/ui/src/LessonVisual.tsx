import './styles/lesson-visual.css';

const visualLabels:Record<string,string>={envelope:'An envelope',letter:'An envelope',bag:'A letter bag',map:'A map with a route',straight:'An arrow pointing straight ahead',left:'An arrow pointing left',right:'An arrow pointing right',apple:'An apple',cup:'A cup','post-office':'A post office',dialogue:'Two people talking'};
export function LessonVisual({kind='envelope',decorative=true}:{kind?:string;decorative?:boolean}) {
  return <div class="first-steps-art" aria-hidden={decorative ? 'true' : undefined}>
    <svg viewBox="0 0 140 140" fill="none" role={decorative ? undefined : 'img'} aria-label={decorative ? undefined : visualLabels[kind] ?? 'An envelope'}>
      <circle cx="70" cy="70" r="61" fill="#f3e5bd" />
      <g stroke="currentColor" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round">
        {kind==='apple' ? <><path d="M71 45c-11-16-28-12-35 2-14 28 4 64 25 60l10-3 10 3c21 4 39-32 25-60-7-14-24-18-35-2z" fill="#cd7658"/><path d="M71 46c-1-15 3-22 10-27"/><path d="M72 32c12 2 19-4 21-12-14-1-19 4-21 12z" fill="#81966e"/></> : kind==='cup' ? <><path d="M34 47h61v43a18 18 0 0 1-18 18H52a18 18 0 0 1-18-18z" fill="#fcf8ef"/><path d="M95 56h8c24 0 24 31 0 31h-8M29 113h75"/><path d="M51 36c-9-9 9-12 0-21"/><path d="M74 36c-9-9 9-12 0-21"/></> : kind==='bag' ? <><path d="M40 51V37c0-17 60-17 60 0v14"/><path d="M28 52v46a10 10 0 0 0 10 10h64a10 10 0 0 0 10-10V52z" fill="#bd6e47"/><path d="M29 52l41 25 41-25"/><path d="M65 72h10v17H65z" fill="#edc968"/></>
        : kind==='map' ? <><path d="M24 37l30-9 32 10 30-10v77l-30 9-32-10-30 10z" fill="#fcf8ef"/><path d="M54 28v76M86 38v76" opacity=".35"/><path d="M40 87c3-30 43 10 56-35" stroke-dasharray="3 8"/><circle cx="98" cy="46" r="6" fill="#bd6e47"/></>
        : ['left','right','straight'].includes(kind) ? <g transform={kind==='left' ? 'translate(140 0) scale(-1 1)' : kind==='straight' ? 'rotate(-90 70 70)' : undefined}><path d="M28 57h47V39l38 31-38 31V83H28z" fill="#fcf8ef"/></g>
        : kind==='post-office' ? <><path d="M26 55l44-27 44 27"/><path d="M34 52v59h72V52" fill="#fcf8ef"/><path d="M58 111V79h24v32"/><path d="M56 54h28v16H56z" fill="#edc968"/><path d="M57 55l13 10 13-10"/></>
        : kind==='dialogue' ? <><path d="M25 35h66v45H54L36 94V80H25z" fill="#fcf8ef"/><path d="M58 85h29l18 15V86h12V55h-17"/><circle cx="44" cy="57" r="2" fill="currentColor"/><circle cx="59" cy="57" r="2" fill="currentColor"/><circle cx="74" cy="57" r="2" fill="currentColor"/></>
        : <><rect x="24" y="39" width="92" height="66" rx="5" fill="#fcf8ef"/><path d="M27 43l43 34 43-34M27 102l30-34M113 102L83 68"/><rect x="91" y="47" width="15" height="18" rx="1" fill="#edc968" stroke-width="2"/></>}
      </g>
    </svg>
  </div>;
}

