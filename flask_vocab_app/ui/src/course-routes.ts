/** Course locations include their release; saved attempts already have unique IDs. */
export function courseHref(releaseId?:string, chapterId?:string) {
  const base=releaseId ? `#journey/release/${encodeURIComponent(releaseId)}` : '#journey';
  return chapterId ? `${base}/chapter/${encodeURIComponent(chapterId)}` : base;
}

export function coursePracticeHref(releaseId:string|undefined, sectionId:string) {
  return `${courseHref(releaseId)}/practice/start/${encodeURIComponent(sectionId)}`;
}

export function courseEndpoint(releaseId?:string) {
  return `/api/v1/course${releaseId ? `?release_id=${encodeURIComponent(releaseId)}` : ''}`;
}

export function parseReleasedCourse(hash:string) {
  const route=/^journey\/release\/([A-Za-z0-9_-]+)(?:\/(chapter|practice\/start)\/([A-Za-z0-9_-]+))?$/.exec(hash);
  if(!route)return undefined;
  return {courseReleaseId:route[1], ...(route[2]==='chapter' ? {chapterId:route[3]} : route[2]==='practice/start' ? {courseSectionId:route[3]} : {})};
}
