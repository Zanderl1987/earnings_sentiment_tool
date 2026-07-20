# Expert Brief — earnings_sentiment_tool

Written by Fable 5, 2026-07-06. CLAUDE.md has the commands and layout; this file is the
research judgment — how to run the study so its conclusion is credible, and the traps
that would quietly invalidate it.

## Current state

25/125 transcripts cached as of 2026-07-06 (pull restarted today after silently never
running for ~5 days — the automation in `AUTOMATION.md` now runs and *verifies* it daily).
At 25–50/day across two Alpha Vantage keys, the dataset completes ~2026-07-09.
Don't start the analysis before the pull finishes; partial panels bias everything toward
whichever tickers/quarters downloaded first.

## Methodology — decisions to make deliberately, not by default

The hypothesis: executives get more verbose/complex when delivering bad news.

1. **Define "bad news" OUTSIDE the transcript.** If bad news is inferred from transcript
   language, the study is circular. Use an independent label per (ticker, quarter):
   earnings surprise sign (financial-data-pipeline has `earnings_surprise` via Finnhub)
   and/or the stock's abnormal return around the call (`event_backtest.earnings_events`
   in that repo gives CARs). This cross-repo join is the single biggest credibility
   upgrade available and costs one afternoon.
2. **Split prepared remarks from Q&A.** Prepared remarks are lawyer-scrubbed; the
   verbosity/evasion signal, if it exists, lives mostly in Q&A answers. Alpha Vantage
   transcripts carry speaker turns — segment on them. Per-speaker analysis (CEO vs CFO)
   is the natural second cut.
3. **Measure more than length.** Word count confounds with "more analysts ask questions
   when things go wrong." Better per-answer measures: words per answer, readability
   (Gunning-Fog/Flesch), hedge-word rate ("approximately", "we believe", "challenging"),
   non-answer rate. Compute several, but see (5).
4. **IEP is a case study, not a data point like the others.** The pre/post-Hindenburg
   (May 2023) contrast is a natural experiment — analyze it as its own narrative arc.
   Pooling IEP with PLTR/AMD/VRT/VST (different sectors, different eras of scrutiny)
   into one regression will mostly measure ticker fixed effects.
5. **Frame honestly: N=5 tickers, ~25 quarters each is exploratory.** Within-ticker
   correlations with ticker fixed effects are defensible; a pooled p-value is not. With
   many metrics × few tickers, something WILL correlate by chance — decide the primary
   metric before looking, report the rest as secondary. The deliverable is "an
   interesting, well-visualized case study," not a significance claim.

## Data traps

- **Coverage gaps are expected, especially IEP** (thinly covered). Some (ticker, quarter)
  requests will legitimately return nothing. Distinguish "AV has no transcript" (park it,
  don't re-burn quota daily) from "rate-limited today" (retry tomorrow). If IEP coverage
  is too thin pre-2023, the Hindenburg contrast weakens — check IEP's file count first
  and consider extending its quarter range before spending quota elsewhere.
- **The 125 target assumes 25 quarters exist per ticker.** VRT only IPO'd via SPAC in
  2020 and VST spun off in 2016 — verify the requested quarter ranges actually exist
  per ticker before calling the dataset "incomplete."
- **Quota discipline:** 25 req/day/key, 2 keys. A wasted request on a known-missing
  quarter is 4% of a day's budget. The fetcher caches successes; make sure it also
  records permanent-misses so reruns skip them.

## After the dataset completes

1. Run `run_earnings_call_study()` as the first pass, but treat it as scaffolding —
   check what it computes against the methodology above before trusting output.
2. Join the bad-news labels from financial-data-pipeline (see its EXPERT_BRIEF.md,
   "Cross-repo synergy"). Use `scripts/run_labeled_study.py` (Stage 2).
3. Write up the IEP arc first — it's the story that motivated the project and the most
   likely publishable/shareable artifact.
