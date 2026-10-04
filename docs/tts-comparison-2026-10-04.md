# Russian text-to-speech comparison

Completed on 4 October 2026: twelve recordings from the original three models, followed by four from standard MAI Voice 2.1. All sixteen succeeded without retries. Listening judgements remain pending. This comparison does not change production speech generation.

## Models and voices

The comparison uses four Russian passages. Both ElevenLabs models use one voice from the application's existing pool. Both MAI variants use the Russian Masha voice from their own catalogue.

| Model | Voice | Request settings |
| --- | --- | --- |
| `eleven_multilingual_v2` — current production model | TatanaLuke, `ymDCYd8puC7gYjxIamPt` | Stability `0.8`, similarity `0.85`, style `0.0`; MP3, 44.1 kHz, 128 kbps |
| `microsoft/mai-voice-2.1-flash` — through OpenRouter | `ru-RU-Masha:MAI-Voice-2.1-Flash` | Plain text, MP3; no style controls |
| `microsoft/mai-voice-2.1` — added separately | `ru-RU-Masha:MAI-Voice-2.1` | Plain text, MP3; no style controls |
| `eleven_v4` | Same TatanaLuke voice | Stability `0.8`, similarity `0.85`; MP3, 44.1 kHz, 128 kbps |

The application continues to select randomly from its four configured ElevenLabs voices. Pinning one voice here makes the two ElevenLabs results easier to compare. MAI's different voice means this is a comparison of usable model-and-voice combinations, not an isolated measurement of model quality.

None of the four production voices reported completed v4 training during the account check. They are professional voice clones, for which ElevenLabs documents a separate v4 rollout. All four v4 requests accepted the selected voice and produced decodable audio. This establishes synthesis compatibility, but does not establish equivalent clone fidelity. The runner requires `--allow-unverified-voice` to attempt this combination. It does not train voices or substitute another one. [ElevenLabs v4 documentation](https://elevenlabs.io/docs/overview/capabilities/text-to-speech/eleven-v4)

## Published pricing

Rates checked on 4 October 2026:

| Model | USD per 1,000 input characters |
| --- | ---: |
| ElevenLabs Multilingual v2 | $0.080 |
| MAI Voice 2.1 Flash | $0.015 |
| MAI Voice 2.1 | $0.022 |
| ElevenLabs v4, promotion ending 12 October 2026 | $0.022 |
| ElevenLabs v4, listed standard rate | $0.080 |

At these rates, v4's standard price matches v2. MAI is cheaper. These are published estimates; subscription credits, taxes and actual account charges may differ. [ElevenLabs API pricing](https://elevenlabs.io/pricing/api), [OpenRouter MAI pricing](https://openrouter.ai/microsoft/mai-voice-2.1-flash)

The four passages contain 768 characters in total. The original three-model run required 12 synthesis calls: approximately **$0.089856** at the promotional rates, or **$0.1344** using v4's standard rate. The runner rejects a batch estimated above $1, makes no automatic retries and stops after the first synthesis or audio-processing failure. This local test budget is separate from the application's demo allowance.

The standard MAI addition costs an estimated **$0.016896** for four more calls. Its published rate is $22 per million characters. The combined four-model estimate is **$0.106752** at the current promotional rates, or **$0.151296** at standard rates. [MAI Voice 2.1 pricing](https://openrouter.ai/microsoft/mai-voice-2.1)

## Test material

The exact inputs are stored in [tts_comparison_samples.json](../scripts/tts_comparison_samples.json).

| Passage | What to check |
| --- | --- |
| Words and endings | Clear standalone words, audible endings, and correct pronunciation of **ё** |
| Short story | Natural phrasing, case endings, sentence rhythm and consistent pace |
| Café dialogue | Questions, polite requests and clear changes of speaker without reading the dashes aloud |
| Contextual stress | Correct stress where identical spelling has different meanings |

Expected stress in the final passage is **замо́к** on the door, **за́мок** on the hill, **плачу́** when paying, **пла́чу** when crying, **мука́** for flour and **му́ка** for torment. The synthesis input deliberately omits stress marks. These are diagnostic contrasts, not a model lesson for beginners.

For each recording, note any changed, omitted or added words first. Then judge stress, intelligibility, pacing and expression. Russian vowel reduction is normal; clear endings should not mean unnatural syllable-by-syllable reading. A dialogue rendered by one voice need not sound like two actors, but the exchange should remain easy to follow.

## Running the comparison

[compare_tts.py](../scripts/compare_tts.py) defaults to a dry run. It uses the project's Python environment, `requests`, `python-dotenv`, `pydub` and an available ffmpeg installation.

```sh
python scripts/compare_tts.py
```

For a paid run, use an existing local environment file and a **new directory outside the repository**:

```sh
python scripts/compare_tts.py --live \
  --env-file /absolute/path/to/existing/.env \
  --output /absolute/path/outside/repository/tts-comparison-2026-10-04 \
  --eleven-voice ymDCYd8puC7gYjxIamPt \
  --allow-unverified-voice
```

The required variables are `ELEVENLABS_API_KEY` and `OPENROUTER_API_KEY`. Process variables take precedence over the file. The file is read without modification, and keys are never included in the result files. The runner refuses hosted/demo configurations; it is not a production API endpoint.

The output directory contains:

- `listen.html`: shuffled A/B/C players, with models and timings hidden until revealed.
- `manifest.json`: exact requests without credentials, text and audio hashes, timings, outcomes and price estimates.
- `transcripts.json`: the passages used in this run.
- `*.raw.mp3`: original provider recordings, retained before normalization.
- `*.listen.mp3`: listening copies at the same average audio level, mono, 44.1 kHz, 128 kbps.

Serve only that output directory on localhost to use the listening page. The raw recordings remain available for checking artifacts introduced by normalization. Matching average level is not a perceptual loudness guarantee.

To add standard MAI to a completed three-model run:

```sh
python scripts/add_mai_tts_comparison.py /absolute/path/to/comparison
python scripts/add_mai_tts_comparison.py /absolute/path/to/comparison --live \
  --env-file /absolute/path/to/existing/.env
```

The first command validates the saved text and audio hashes and reports the price without requesting credentials or speech. The second generates only four new clips, using `OPENROUTER_API_KEY`. It rejects duplicate additions, stops after a failure and preserves the original manifest, page and recordings. Its separate generation receipt records timestamps, cost estimates and outcomes. Existing A/B/C labels stay fixed; the added sample is D, so this addition is not a newly blinded four-way trial.

## Results and decision

All twelve synthesis requests succeeded without retries. Each original recording and normalized copy passed decoding and duration checks. The sixteen offline runner tests also passed.

| Model | Median first response chunk | Median complete response |
| --- | ---: | ---: |
| ElevenLabs Multilingual v2 | 2.928 s | 3.136 s |
| MAI Voice 2.1 Flash | 0.543 s | 1.521 s |
| ElevenLabs v4 | 3.061 s | 3.280 s |

These medians cover four requests per model from one local run. MAI was quickest here. The short-word recording lasted 21.696 seconds with MAI, compared with 11.053 seconds for v2 and 8.960 seconds for v4. Faster generation does not imply faster speech or better pacing.

The browser played the words-and-endings recording from each model to completion without media errors. Model reveal/hide worked, and no console errors were recorded. All twelve files passed offline decoding; the other nine were not played to completion in this browser check. The local listening page is `http://127.0.0.1:5084/listen.html` while its server is running. Audio and manifests stay outside the public repository.

Pronunciation, naturalness and preference have not been scored. Actual account charges were not measured; the published-rate estimate for the completed batch is $0.089856. Production still uses Multilingual v2 and the existing random voice pool.

The manifest distinguishes time to the first response chunk from time to the complete recording. Neither proves when a browser could begin playing. Normalization time is recorded separately. Four short passages are sufficient for an initial comparison, not a latency benchmark or a complete Russian pronunciation assessment.

Select a replacement only after listening to all four passages. Keep the current provider if a cheaper model loses Russian stress or endings. If v4 cannot use the existing voice reliably, assess voice migration as a separate decision rather than silently changing the application's voice pool.

### Standard MAI addition

All four standard MAI requests succeeded on the first attempt. They use the original passages and Masha voice identity, with the `MAI-Voice-2.1` suffix. The original twelve result rows and all raw/listening audio hashes are unchanged. Sample D identifies the addition in each passage; existing A/B/C labels retain their meanings.

Median first-chunk time was **1.267 seconds**, and median complete-response time was **2.151 seconds**. This was a later sequential batch, not an interleaved latency benchmark. Its short-word recording lasts **19.920 seconds**, and its story lasts **28.224 seconds**. These measurements do not establish pronunciation quality.

The seven extension tests passed, including preserved recordings, duplicate prevention, price checks and restoration of the original page if publication fails. All four new clips passed decoding and normalization checks. The browser played the short-word sample to completion without media or console errors. The other three new clips were not played to completion during this check. No production provider setting changed.
