# Beta: faster subscription transcription and recipe reader

The selected ChatGPT model is preserved. New subscription defaults are formatted
transcription, low reasoning, original image detail and two concurrent pages.
Formatting happens in the transcription request; no second cleanup is made in
formatted mode. The legacy mode and other providers retain their saved prompts
and cleanup settings. Existing queued approvals must be renewed when effective
processing settings change.

## Measured comparison

Model: GPT-5.6 Sol. Six authored, machine-printed reference pages cover English,
Norwegian, Hungarian, dense size sequences, abbreviations, repeat symbols,
nonconsecutive row numbers, a size table and chart references. These are
controlled fixtures, not the user's four-page NAS recipe or photographs.

| Variant | Six-page time | Input tokens | Output tokens | Total tokens |
| --- | ---: | ---: | ---: | ---: |
| Original beta, sequential, cleanup off | 57.74 s | 22,746 | 1,829 | 24,575 |
| Original beta, repeated baseline | 56.73 s | 22,746 | 1,950 | 24,696 |
| Formatted, low, original, two pages | 31.05 s | 23,340 | 1,966 | 25,306 |
| Formatted, none, original, two pages | 28.97 s | 23,340 | 1,889 | 25,229 |

The default completed about **46% faster**, with the first completed page visible
in polling after 9.62 seconds. Its total token count increased about **3%** versus
the original baseline; this is not a demonstrated quota saving. Low reasoning
used 75 reasoning tokens; none used zero. The original beta did not retain a
separate reasoning or per-request timing breakdown.

All four runs matched the reference word sequence after Unicode/whitespace and
Markdown-escape normalization, and matched every numeric sequence. Review of
the formatted output confirmed table alignment, paragraph order, abbreviations,
literal repeat markers and no added instructions. These checks do not guarantee
equal performance on dense scans, blurred photos or every real pattern.

Exactly 24 page scans were requested: two baseline runs, low reasoning and no
reasoning. The planned high-detail run was omitted because the repeated baseline
consumed its reservation; the cap was not increased. Original image detail and
low reasoning remain the quality-first defaults. High detail and no reasoning
are advanced, explicit settings, not automatic downgrades.

## Reading and editing

New formatted editions use the GFM reader with readable headings, paragraphs,
tables, contents links, text-size/spacing controls and focus mode. Preview and
editing use the same renderer. A formatting toolbar edits the existing Markdown
without introducing another document format. Literal knitting symbols and
explicit ordered-list numbers remain visible. Raw HTML, executable links and
external images are disabled; authenticated diagram assets remain supported.

Existing editions keep their text and legacy rendering; the user can explicitly
switch to enhanced preview. Opening or previewing a document does not save or
convert it. Unsaved edits are guarded before navigation, and browser unloads
retain the normal unsaved-change warning.

## Diagnostics and recovery

`GET /api/admin/ai/chatgpt/jobs/{job_id}/diagnostics` is administrator-only. It
returns content-free request settings, preparation/first-text/total timings,
input/output/reasoning/cache tokens and outcome. Missing usage remains unknown,
including failed/interrupted attempts; it is not reported as zero.

The work queue exposes total/completed pages and active page numbers. Only one
recipe job runs at a time, with at most two page requests in flight. Completed
pages are checkpointed in source order. Errors stop new dispatch while in-flight
requests settle. There are no automatic inference retries; owner-approved retry
reuses unchanged completed pages. Approval includes all effective settings and
the versioned prompt.

## Validation and release

- Backend suite: 71 tests, including a subprocess covering 21 subscription
  integration scenarios (concurrency, ordering, accounting, recovery, approval,
  format publication, redaction and disconnect).
- Frontend: 18 policy/viewer tests plus a real JSX-renderer test; six locale
  checks and production build. Runtime npm audit: zero findings.
- Desktop browser checks cover reader content, table rendering, focus/contents
  navigation and edit/preview/save behavior. Responsive rules provide mobile
  layouts and horizontal table scrolling; no physical phone or NAS was available.
- Rebuild the Windows helper from the updated shared protocol. Build, smoke-test
  and scan the exact revision-labelled Docker image before moving beta.
- Publish only GitHub `beta` and Docker Hub `zeetlex/knitting-library:beta`.
  Keep the preceding beta index for rollback:
  `sha256:f6a688b88607432c9fc803388be6ede1791248757a41bec17c80aca5068b2c3e`.
  `main` and `latest` are not promoted.

## Reproduce

Run `tools/benchmark_transcription.py --help` for the bounded benchmark driver.
It uses an isolated server and a corpus directory with six PNGs and
`reference.json`. Its persistent reservation ledger prevents silent restart or
repetition; `--resume` continues only fully recorded completed variants. Do not
remove the ledger to bypass a previously authorized cap.

Frontend verification: `node --test src/utils/readerPolicy.test.mjs
src/utils/viewerResume.test.mjs`, then `node scripts/test-recipe-markdown.mjs`.
Backend verification: `python -m unittest discover -s tests` inside the release
image.
