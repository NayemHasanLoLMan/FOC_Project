# India Fix 9: vision runtime and unnecessary-call review

Reviewed 23 October 2026. Task 9 is complete as a measured review. **Production source, model/settings, limits, templates and invoice behavior are unchanged.** Existing caching already avoids repeat inference; no accuracy-reducing skip or speculative residency/crop optimization is added. Unseen-document validation remains task 10.

## Measurements

Exact image/prompt/schema/options requests from Fix 8 were replayed three times each using the existing transport/cache. Real Ollama model-tag resolution remained enabled. A guard rejected any chat endpoint call: all nine responses were cache hits, identical to the original responses, with zero new inference requests. This includes completed readings rejected by the goods-description policy; those rejections do not need fresh inference on an identical request.

| Reader / exact Fix 8 request | Earlier fresh wall time | Current cache-hit median, 3 runs |
|---|---:|---:|
| qwen3.5:4b / highlight-separated crop | 46.875 s | 0.0785 s |
| qwen3.5:4b / original color crop | 60.000 s | 0.0777 s |
| qwen3-vl:latest / highlight-separated crop | 252.984 s | 0.0724 s |

Fresh measurements are the actual completed Fix 8 requests, not new cold runs performed in Fix 9. Their exact inputs/options/digests are retained. Warm times are current measured wall times, not historical model durations carried in cache telemetry. These are transcription requests for one handwritten note, not timings for an entire cold invoice or a representative sample of new shipments.

The real QueueWorker also processed the same India shipment under original, neutral and conflicting filenames in fresh isolated job folders. Attempt durations were **2.215, 3.056 and 3.350 seconds**. Each attempt had three model-derived cached responses, zero fresh calls, and an accepted invoice-number contribution. A real HTTP guard again forbade chat inference; only nine tag requests occurred across those three attempts. All structured facts/values/diagnostics remain identical to Fix 8 apart from source_file, and manual-reference reads were zero. Only the cache directory was redirected; no OCR/parser/model response was mocked. These are three filename cases for one shipment, not three independent PDFs. Timings exclude folder-settling/scanner delay and do not predict unseen-PDF throughput. Cached model-derived invoices must still be labelled as vision-assisted, not OCR-only.

## Decisions

- Keep readable quantities and declared package/gross values on their existing source-rule paths. Keep PDF-first invoice reading: skipping its model crop just because a filename exists would discard the approved accuracy improvement.
- Keep selective handwriting review and its printed fallback. Completed rejected responses are already cached. Do not skip future different crops just because this one note was unreadable.
- Keep image/model-digest/prompt/schema/output/context keyed caching. Model identity is resolved before reuse; no stale offline shortcut or filename-based answer cache is introduced. Completed null/rejected answers can be reused; truncated/failed requests cannot.
- Keep existing one-page-at-a-time image retention in quantity/package stages. Vision-derived field evidence is rebuilt with source images and lower-level cache hits; blindly returning a saved field total would lose review provenance and may bypass current model identity. Its remaining render/local-OCR work is not the hundreds-of-seconds inference bottleneck measured here.
- Retain 4096 output / 8192 context tokens, 7200 seconds, temperature 0, think=false and keep_alive=0. No faster reader is substituted globally; differing reader accuracy has already been demonstrated. No crop shrink, token cutoff, retry suppression, model download or API/UI change is added.

Fresh qwen3-vl telemetry for the Fix 8 request attributes about 38.715 seconds to loading, 178.192 seconds to prompt/image evaluation and 35.338 seconds to generation. The other reader's prompt evaluation took 32.405–35.009 seconds. Image/model execution dominates cold work. Lowering the generous output ceiling cannot remove the image-evaluation cost and may truncate harder cases. Longer model residency could avoid some repeated loading, but needs a separate RAM/model-switching benchmark before changing the memory-release policy. Faster hardware or a separately validated faster reader may help cold latency; neither guarantees better transcription. None was changed in this review.

## Acceptance and remaining limits

All **47 focused transport, package/weight, invoice-reader and runtime-settings tests pass**. Eleven private HTTP-stubbed cache-contract assertions also pass: identical reuse; changed image, prompt, schema, model digest, output budget and context invalidation; timeout-only reuse of a completed answer; retry after truncation/transport errors; and reuse of a completed null answer without inventing a value. These contract checks test cache behavior, not reader accuracy.

All 20 Bangladesh parser results and 20 valuation results remain exact. Production modules have no changed hashes; all 169 other protected files and the 20 jobs/20 attempts/832 events plus queue/admin history match the stopped backup. SQLite integrity is OK. No production invoice was reset/reprocessed. The service is restored, eight dashboard/API/preview/download routes return HTTP 200, and watching remains Bangladesh only.

The code is byte-identical to Fix 7's 421-test full gate. That full suite and native print export were not repeated for this documentation-only review; focused tests, cache contracts, real cached requests/queue runs and preservation checks were run. There is no claimed new speed improvement from a code change. **New unseen PDFs can still require minutes of fresh model inference.** Only one real India PDF is available, so task 10 remains pending additional shipments.

Evidence: reports/india_fix9_20261023 contains pre-fix9-backup.zip/before.json; cache-benchmark.json/log; cache-contract.json and private assertion code; focused-tests.log; acceptance.json/worker-acceptance.log and worker-run-final artifacts; warm-queue-times.json/warm-queue-http.json; bd-parser-after.json; verification.json, startup-status.json and release-verification.json. Actual fresh cold responses/exact crops are retained under the Fix 8 report. Development artifacts are excluded by the production release allowlist.

Before testing, 197 stopped-state/application/data files were backed up with verified hashes, excluding transient logs/native locks/WAL files. Production restore is unnecessary because source/data are unchanged. Stop/drain before restoring matching files and never overwrite a live SQLite database. No destructive restore, physical reboot, GPU/residency benchmark or unseen-shipment accuracy test was performed.

Next: **Fix 10 — validate additional unseen India PDFs**. New shipment samples are required before this can be completed.
