/** Display policy only. Never translate, correct or splice a recognition result.
 * Keep the raw hypothesis for the audio/assessment pipeline. A whole display
 * group containing another script is omitted, including incomplete Latin words.
 * This is not a grammar check or proof of which language the recording contains.
 */
export function russianTranscript(text: string): string | null {
  if (!text.trim()) return null;
  const letters = text.match(/\p{L}/gu) ?? [];
  if (letters.some(letter => !/^[А-Яа-яЁё]$/u.test(letter))) return null;
  return /[А-Яа-яЁё\d]/u.test(text) ? text : null;
}
