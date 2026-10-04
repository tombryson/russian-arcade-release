import type {ComponentChildren,Ref} from 'preact';
import './styles/intro-lesson.css';

/** Shared frame for introductory teaching, recall, feedback and completion. */
export function IntroLessonCard({title,counter,readingHelp,readingKey,illustration,headingRef,children,actions,className='',contentClass='',actionClass=''}:{
  title:string;counter?:string;readingHelp?:string;readingKey?:string;headingRef:Ref<HTMLHeadingElement>;
  illustration?:ComponentChildren;children:ComponentChildren;actions:ComponentChildren;className?:string;contentClass?:string;actionClass?:string;
}) {
  return <div class={`intro-lesson-card ${className}`}>
    <header class={`intro-lesson-heading${readingHelp ? ' has-reading-help' : ''}${illustration ? ' has-illustration' : ''}`}>
      <h1 ref={headingRef} tabIndex={-1}>{title}</h1>
      {counter && <p class="lesson-counter">{counter}</p>}
      {readingHelp && <details key={readingKey} class="intro-lesson-reading-help"><summary>Read this word</summary><p>{readingHelp}</p></details>}
      {illustration && <div class="intro-lesson-illustration">{illustration}</div>}
    </header>
    <div class={`intro-lesson-content ${contentClass}`}>{children}</div>
    <div class={`intro-lesson-actions ${actionClass}`}>{actions}</div>
  </div>;
}
