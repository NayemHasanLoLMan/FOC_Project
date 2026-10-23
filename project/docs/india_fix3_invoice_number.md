# India Fix 3: PDF invoice-number extraction

Completed 22 October 2026. Only checklist task 3 is implemented. Header date/marks/destination variations remain task 4; regional watching/editing remain disabled.

## Problem and smallest supported change

Whole-page OCR read the handwritten cover reference as 1196/)6. The earlier invoice number came from the filename, so renaming the PDF left the number empty. India now prefers a recognizable source-PDF reference without a filename hint. When OCR misses it, the existing local vision transport reads one bounded header crop derived from labels and neighbouring OCR fields. There are no shipment-specific numbers or absolute crop coordinates in production code.

Explicit invoice-number labels take priority; the known cover form's To The Agent area is a secondary location. Numeric OCR evidence must exist near the label before a crop is requested. A blue-ink mask can remove black form lines; black/uncoloured crops retain the original appearance. Original PDF and OCR are unchanged. Source candidates, exact model input, coordinates, preprocessing, raw answer, acceptance and model identity are retained for image review.

The configured primary reader is unchanged. A completed invalid header answer may use the installed qwen3.5:4b reader as an optional fallback. It uses the same transport, limits and cache; there is no new API, dependency, model installation, settings form or global model change. A valid source-OCR/primary reading needs no second model. Missing/unavailable readers retain the existing filename fallback or blank. The optional fallback is specific to India invoice numbers; Bangladesh and other field readers remain unchanged.

Only the established S prefix can normalize an S/5/8 glyph. Serial digits and the two-digit year are copied without adding/removing digits to match a filename or reference. The current format remains 3–5 serial digits; a four-digit-only restriction was not assumed. This is best-effort extraction, not a guarantee that every syntactically valid model answer is correct.

## Actual reader comparison

No expected serial/year or filename was supplied in the model prompt. The handwritten source was visually inspected separately for QA.

| Reader / source crop | Time | Actual response | Outcome |
|---|---:|---|---|
| qwen3-vl:latest, original focused crop | 260.297 s | 8/5/196/1/26 | Invalid grouping; rejected |
| qwen3-vl:latest, blue-ink crop | 337.297 s | 8/5/196/1/26 | Invalid grouping; rejected |
| qwen3.5:4b, blue-ink crop | 29.953 s | 8/5196/26 | Accepted as S/5196/26 using only the known-prefix normalization |
| qwen3-vl:latest, experimental separate serial/year request | 269.109 s | serial 55196; year 26 | Wrong serial; this request format was not adopted |
| Existing PaddleOCR, focused original/blue crop | 10.547 s combined | Original: incomplete text and 6; blue crop: no text | Extra OCR pass did not help and was not added to production |

Ollama reported the configured qwen3-vl model on CPU with no VRAM allocation during the test. Larger hardware can reduce reading time, but it does not by itself resolve the demonstrated recognition errors. A cold uncached primary-plus-fallback read can take several minutes. Existing image/model/prompt-keyed caching prevents repeating completed responses for identical inputs.

## End-to-end acceptance

The real QueueWorker processed the same actual three-page PDF under its original name, neutral unseen_shipment.pdf and deliberately conflicting 29S9999-D.pdf. These are three filename cases for one shipment, not three independent shipments.

All three published invoices contain **S/5196/26**, with identical structured data apart from source_file. Goods, source date, address/identifiers, shipping marks, packages, gross weight and USD 82.40 remain unchanged from Fix 2. The old filename-hint diagnostic is replaced only when a PDF reading is used. No manual expected invoice was read during conversion; the guard recorded zero reference reads. The queue run reused verified source-keyed OCR/model caches from the actual fresh benchmarks; no OCR/parser/model response was mocked. Only the worker cache directory was redirected for isolation.

Both header calls have separate call IDs; the rejected primary and accepted optional response, exact model images and provenance are recorded. The final processing summary correctly reports invoice_number as a vision contribution without tagging goods quantities. Native hidden read-only Excel exports for original/neutral filenames are one page each, print S/5196/26 and USD 82.40, and have identical printed text. The neutral-file print was visually inspected.

Final frozen-code regression: **358 tests passed in 95.048 seconds**, including 14 focused tests for bounded geometry, source priority, slash/prefix handling, rejection/fallback, no-model/offline behavior, separate fallback evidence, image preprocessing and final pipeline contribution reporting. All 20 Bangladesh parser results, including diagnostics, and all 20 valuation results remain identical. Final verification records protected production file/history preservation, healthy dashboard checks and restarted service status. No production invoice was reset/reprocessed.

## Remaining limits, evidence and next task

A valid-looking wrong model reading can still be accepted; additional unseen PDFs are needed before a general accuracy claim. Unsupported reference locations or unreadable/no-digit crops may retain a filename hint or blank. The optional fallback model is a small fixed local policy for now; configurable regional model preferences and performance review belong to the later regional-watching/runtime work. No four-digit-only constraint was imposed without a standing rule. No warning/review text is added to the printed invoice.

Development evidence is under reports/india_fix3_20261022: verified pre-fix3-backup.zip/before.json; fresh benchmark responses/crops; focused-tests.log; final-acceptance.log; acceptance.json with original/neutral/conflicting cases; worker-run output/evidence; bd-parser-after.json; native print/verification.json; final verification.json and release-verification.json. The backup excludes transient native lock files and contains matching stopped state, source snapshots, output, masters, backend/frontend and configuration/rates. The previous India-Fix-2 release supplies matching entry points/dependency/docs files. Stop/drain before restoring matching application and data together; never overwrite a live SQLite database. A destructive restore and physical reboot were not performed.

Next: **Fix 4 — header layout tolerance for date, shipping marks and destination**. Obtain user approval before proceeding. Jordan remains the last checklist stage.
