# Speaking task evidence

New Fluent A1 sessions support nine narrowly defined speaking diagnostics:

| Scenario | Variants | Observed task |
| --- | --- | --- |
| Asking directions | Park, pharmacy, post office | Ask where the specified place is. |
| At the café | Takeaway, warm lunch, two drinks | Request the specified food or drinks. |
| Meeting people | Classmate, neighbour, club | Give your name and ask the other person's name. |

Each situation has one criterion. It does not assess every scenario goal, all of A1, or introduce a progression gate.

The existing conversation, original recordings, tutor feedback and goal review remain in place. A closed **What this recording shows** disclosure adds a natural label, outcome and short explanation. It does not show a new proficiency score.

## Task and source scope

At session creation, the server checks the situation identity, A1 level and authored demands. It freezes the complete scenario, selected goal IDs and criterion. Directions and name exchanges refer to `a1.speaking.ask-and-answer`; café requests refer to `a1.speaking.request-and-response`. The new café and meeting mappings are in `data/speaking_evidence_targets.json`. Previously issued directions contracts remain unchanged.

Criteria accept intelligible short replies and natural alternatives. They do not require perfect grammar or completion of unrelated goals. Giving a name without asking the other person's name is partial evidence for the name-exchange task. Grammar feedback remains separate. Labels come from the frozen criterion, rather than always using the scenario's first goal.

The recorded assessment pilot elicits a monologue. Live dialogue contracts retain interaction-specific instructions; the pilot's monologue instruction is not applied to café or meeting conversations.

Contract creation is atomic with the session. An idempotent start reuses the original snapshot. Existing sessions, Step-through Speaking and unmapped situations receive no retrospective contract. Their ordinary review behavior is retained. A changed authored demand under the same mapped identity fails validation instead of silently reusing the old criterion.

`independent_speaking` identifies the elicited response mode. It does not establish that the learner worked independently. Live support use is incompletely observed; every saved audio source records `independence: "unverified"`. An empty shared support list must not be interpreted as proof that no help was used.

## Original-audio identity

The review uses the contiguous, untrimmed learner microphone recordings, including silence. Learner ASR captions and corrected examples are not sent as learner evidence. Other-speaker captions remain fallible context only.

The server builds a manifest with:

- The SHA-256 digest of the assembled mono PCM16/24 kHz WAV sent for review.
- Its duration in milliseconds, derived from the total sample count.
- Ordered recording IDs, ordinals, start samples, sample counts, sample rates and individual original-WAV digests.
- The audio manifest version and unverified independence state.

Assembly rejects missing samples, gaps, inconsistent formats, unfinished segments, symlinks and non-regular files. After provider work, the server rereads the saved metadata and original files and compares their identity before saving any feedback or rewards. The temporary assembled copy is removed; the original segments remain saved. The shared criterion report's response hash is the assembled-audio digest, never a transcript hash.

The shared evidence audit always validates session ownership, scenario content, saved review and manifest-to-recording bindings. Supplying an audio root additionally verifies the files. A DB-only audit cannot establish that files still match their stored hashes. Import must explicitly verify available source media and keep its media-copy status honest.

## Judgements and failure behavior

The existing audio model and 6,000-token request budget are unchanged. That provider path does not support strict structured output, so the application requests JSON and validates the complete result locally.

The additional report must match the saved contract hash and criterion IDs. Scored judgements require bounded integer intervals in the supplied untrimmed audio. The outcomes are satisfied, partial, not satisfied and insufficient evidence, with scores consistent with the saved criterion maximum. Insufficient evidence is `null`, not a zero. Unclear or non-Russian speech forces abstention. Any reported uncertain phrase also conservatively leaves this diagnostic unscored because the existing uncertainty fields do not identify acoustic intervals.

A clear short question such as «Где парк?» can satisfy this narrow communication criterion even when the existing grammar and fluency scores are null, or the general speech status is insufficient for those broader scores. The report must still locate actual audible learner speech; neither a completed goal nor a transcript alone establishes criterion evidence.

The normal review, audio manifest and criterion report commit together before existing reward and goal-observation hooks. Invalid output, changed audio or a database failure leaves no partial successful review or criterion report. Original recordings remain available for the existing explicit retry. Once saved, the report is reused. Session deletion removes its shared reports and contract in the same transaction before removing the session and audio files.

The new diagnostic does not establish a demonstrated curriculum target or a milestone. Existing Speaking hooks may still record supported goal practice, with independence unverified, under their existing policy.

## Validation limits

Tests cover frozen scenario scope, short replies with null general scores, original-file integrity, timestamp bounds, uncertainty, provider failure, rollback, ownership, retries, deletion, SDK payloads and the compact UI. They use mocked provider reports and synthetic PCM. They establish structural and transactional behavior, **not acoustic recognition or grading accuracy**.

CU-09 acoustic release acceptance remains outstanding. Human-reviewed recordings should cover clear and ambiguous case endings, grammatical errors, self-repairs, natural alternatives, short questions, silence, noise and speaker echo. Their expected judgements and time intervals must be compared with live original-audio reviews before claiming reliable criterion assessment. Timestamp bounds prove only that an interval exists, not that its speech was heard correctly. This implementation remains diagnostic practice, without new access restrictions or proficiency claims.

Implementation: [`speaking_evidence.py`](../flask_vocab_app/services/speaking_evidence.py), [`speaking_assessment.py`](../flask_vocab_app/services/speaking_assessment.py), [`speaking_review.py`](../flask_vocab_app/services/speaking_review.py), [`live_conversation.py`](../flask_vocab_app/services/live_conversation.py), and [`activity_evidence.py`](../flask_vocab_app/services/activity_evidence.py). It reuses migration 049's shared evidence tables; no new schema is required.
