# A1 situation quality and vocabulary integration

Implementation note, 4 October 2026. This pass addresses the first two priorities in the [TORFL assessment build plan](torfl-assessment-build-plan.md#next-implementation-pass): improve generated reading/listening for three detailed A1 units, and connect their saved passages to vocabulary lookup and saving. It does not extend Writing or Speaking coverage, change assessment claims, or establish deployment. Software and browser verification are recorded separately from the language review.

## Language plans and prose

`curriculum-language-plan-v4` supplies two situation families for each of the three units. A family changes the relationship the learner must understand, before the generator chooses names, places or dates. Recent semantic exposure selects the least encountered family, with recency breaking ties. Cosmetic changes retain the same family identity.

Known v3 recipe identities are mapped into this history when preparing new requests. Issued v4 requests keep their original fields, prompt and schema hashes. Only ready tasks with an issued learning session count; accepted text awaiting or failing audio preparation does not. Other units cannot crowd this unit’s history out of the twelve-task window.

| Unit | First family | Second family |
| --- | --- | --- |
| Location and destination | Find two friends at separate current places before one moves on. | Understand a shared starting place and two separate next destinations. |
| Dates and duration | Understand one completed stay, its place and elapsed duration. | Understand time spent reading a book, its venue and the beginning of that activity. |
| Conversation topics | Locate two friends and distinguish their conversation subjects. | Identify a person mentioned in conversation and a thought explicitly shared by that same speaker. |

Calendar reading includes a written starting date; listening instead identifies another person present. Listening does not test untaught spoken ordinal dates. The reading-activity family is now reachable. Its supplied `читал/читала` and `начал/начала читать` expressions distinguish elapsed reading from starting it without claiming that the book was finished. A week of library reading may include breaks and repeated visits. The thought family uses a named speaker’s direct disclosure, rather than an inferred private thought. It does not claim that the disclosed thought was never spoken about.

Sampled location options exclude broad overlapping categories such as «на работе» against a specific workplace. Conventional place forms remain verified lexical inputs. Each family retains exactly three assessed facts and three meaning questions. Options use grammatical parallel phrases; a distractor can describe another participant without answering the current question.

`source-v5` makes the writer, addressee, medium and timeline explicit. It retains the removal of the earlier sentence-count floor, permits natural connections and pronouns within a grounded source span, and asks the writer to stop once the message is useful. Prompt refinements after batch A address ambiguous vocatives, repeated subject inventories and source-item boundaries. Earlier issued requests retain their versioned adapters and frozen content.

A provider-free audit covers 600 unit/mode/seed combinations. Both families appear in each mode: location splits 58/42, calendar 52/48, and conversation topics 49/51 across 100 seeds. A separate twenty-start sequence selects each family ten times using recent history. These checks are distinct from the live prose results below; a valid plan cannot establish natural generated Russian.

## Eighteen first-attempt text calls

The [saved validation record](validation/curriculum-situations-2026-10-04.json) retains requests, writer briefs, raw responses, provenance hashes, structural outcomes and assistant reviews, including rejected material. Each of three bounded batches made six calls: the three units in reading and listening. The configured model was `gpt-5.6-luna`. No automatic retries, learner data or audio-generation calls were used.

| Batch and seed | Synthetic familiar-word profile | Structural acceptance | Assistant verdict: usable / revise / rejected |
| --- | --- | --- | --- |
| A — `pass-20261004-a` | `everyday-core` | 5/6 | 3 / 2 / 1 |
| B — `pass-20261004-b` | `places-visits` | 6/6 | 6 / 0 / 0 |
| C — `pass-20261004-c` | `books-interests` | 6/6 | 5 / 1 / 0 |
| Total | Three synthetic profiles | 17/18 | 14 / 3 / 1 |

“Usable” means suitable for this narrow supported-comprehension task. It does not mean polished prose, independent learner performance or a production success-rate estimate. The review was performed by an assistant, not an independent human assessor. Batch A used an earlier prompt hash; B and C used the same refined prompt. The aggregate must not be described as a trial of one unchanged prompt.

Recorded call latency ranged from 2.878 to 18.733 seconds, with a median of 4.461 seconds. The total application-budget estimate was US$0.018195, assuming uncached input at the configured budget rates. This is not a provider invoice.

The review separates eight dimensions so that a schema pass cannot conceal a linguistic weakness:

| Dimension | Review question |
| --- | --- |
| Russian grammar | Do case, government, agreement and aspect express the intended meaning? |
| Purpose and viewpoint | Is this a credible message with a consistent writer, addressee and register? |
| Timeline and referents | Are people, events and times identifiable without contradictory or guessed facts? |
| Supporting constructions | Is the language taught or deliberately supplied, rather than inferred from an A1 label? |
| Whole-passage vocabulary | Which content words are unfamiliar, including words omitted from annotations? |
| Questions and answerability | Do the Russian and English questions match, with one source-supported answer each? |
| Distractors | Are alternatives grammatical, plausible and at the same semantic scale? |
| Economy and cohesion | Does the message connect useful facts without repetition or padding? |

No core Russian grammar error was found in these 18 samples. Material weaknesses nevertheless remained:

- A01 opens «Дима, Олег и Миша сейчас в аптеке». Дима can be read as an addressee or a third coordinated subject.
- A03 puts two sentences in one array item, then cites nonexistent `s2`; rejection was correct. Its essential «в библиотеке» also lacks vocabulary annotation.
- A05 repeats «Олег… Олег… Олег…», producing an inventory rather than a natural message. Its disclosed thought and assessed answers are otherwise sound.
- C06 leaves `new_vocabulary` empty although the central location word «парк» is absent from the declared known lemmas.
- B04, C02 and C03 combine a greeting and statement in one source item despite the prompt instruction. Their IDs still refer to valid array items and their answer keys remain grounded. Orthographic splitting must not silently renumber issued references.
- B03’s «Лена жила в Самаре один день» is understandable but less natural for a brief city visit. C03 unnecessarily repeats «книгу». Common time words and particles receive inconsistent annotation.

Both location and calendar families appeared in both modes. The thought-and-speech family appeared only in A05 reading, which needed prose revision. It has no final-prompt sample and no listening sample in these calls. This gap remains visible despite the broader provider-free plan audit.

The fixtures exercise requests with synthetic vocabulary, but they do not measure adaptation. Seeds changed with profiles, and the prompt also changed after A. Some reused words were already in unit teaching. Morphology candidates are review aids, not an automatic count of unfamiliar words: names, common linking language, supported expressions and content lemmas need contextual interpretation. A familiar lemma does not establish knowledge of its full paradigm. This review did not verify learner-visible presentation of every newly supplied supporting expression, nor pronunciation, stress or prosody.

## Vocabulary integration

Generated passages now offer optional word lookup and saving in the existing practice player. Selecting an occurrence sends its surface form and offset; the server derives the sentence from the learner’s owned, frozen passage. The client cannot supply replacement context or claim its own annotation. Existing morphology resolution presents ambiguous lexical readings for selection and checks the chosen reading on save. Capture uses the shared vocabulary, mnemonic and metered enrichment pipeline. A saved word survives unavailable enrichment and can finish its details on an explicit retry.

Lookup and capture retain the existing session ownership, revision and idempotency checks. Reading word help records support for unanswered questions sharing that passage. Listening word help requires the transcript to be opened first and retains transcript/help exposure; it cannot restore an unaided-listening result.

The owned `GET /api/v1/learning-sessions/<session_id>/words` route retrieves explicit capture receipts after the activity finishes without another lookup or provider call. Each record retains the selected form, lemma/POS, original sentence, passage hash, occurrence offsets and source identifiers. Repeated captures of the same occurrence and reading collapse to one returned source record.

These are retained source records, not complete prepared flashcard examples. A generated passage has no guaranteed full-sentence translation, and an unannotated word has no established contextual gloss. The implementation marks these records `prepared_example: false` and does not place incomplete examples into the complete-example cache. Ordinary vocabulary card generation remains available; **automatic flashcard reuse of the original passage sentence is still pending**.

## Software and browser checks

TypeScript and the production build pass. The complete UI suite passes 838 tests in 64 files. Backend discovery passes 2,134 tests. That run started before the final history fixes; the affected suites were also run against those final changes, as recorded below. The build retains a JavaScript chunk-size warning. Tests cover uncertain-response retry, exact occurrence selection, transcript gating, pending enrichment and a profile change during lookup.

After the final history fixes, 80 content, plan and service regressions pass. The nine passage-vocabulary tests cover exact occurrence validation, repeated homographs, idempotent capture, unavailable enrichment, source retrieval after completion, profile isolation and support receipts. A frozen source-v4 fixture retains its original generated document and provider prompt.

An isolated browser workspace verified lookup of «аптекой» as «аптека», explicit saving through a mocked enrichment service, and assisted reading feedback. The transcript remained hidden before disclosure. A 1.5-second fixture recording played to its native ended event, enabling the answer controls. After opening the transcript, the second «печь» in «Она видит печь и хочет печь» offered noun and verb readings. A saved listening reply retained transcript support after reload. No browser console errors were observed. This was a transport and interaction check with synthetic text and a tone recording, not a speech-quality or provider-enrichment evaluation.

Changed source and evidence files contain no literal matches for the configured credentials checked locally. No credentials, databases or personal learner content were included in the commit. This check is narrower than a full security audit.

## Next priorities

This is the earlier pass record. The subsequent [extension report](curriculum-expansion-2026-10-04.md) updates the status of these items; the results above remain historical evidence.

1. Evaluate the thought-and-speech family with the final prompt in both modes; preserve weak results as well as successes. The existing 18 calls do not complete that check.
2. Make learner-visible support for selected new constructions explicit. Fix missing central-word annotations and define consistent treatment of common linking words, without treating every morphology candidate as an unfamiliar lemma.
3. Prepare complete contextual examples from captured passage receipts before enabling automatic original-sentence card reuse: sentence translation, contextual meaning and appropriate morphology must be established.
4. Review accepted listening text audibly before making claims about speech quality. These batches assess text only.
5. Extend plans to the remaining 14 units in small reviewed groups. Broader original Writing/Speaking, diagnostic expansion and later-level courses remain separate work.
