# Automation — earnings_sentiment_tool

Set up 2026-07-06 (by Claude, with Zander's approval). Moved to dedicated repo 2026-07-19.

## ClaudeAuto-TranscriptPull (Windows Scheduled Task)

- **What:** runs `scripts\daily_transcript_pull.ps1` daily at **10:30 AM**
  (9:00 -> 10:00 on 2026-07-11 after a quota-window collision; 10:00 -> 10:30 on
  2026-07-15 to open a quota gap for the one-shot EARNINGS pull below, and kept
  there since later is strictly safer against the rolling-24h boundary; catches up
  after boot if the machine was off). Pulls the next batch of earnings transcripts
  and **verifies the cache file count actually grew**. Quota: Alpha Vantage free
  tier = 25 requests/day TOTAL, enforced per IP (a second key does NOT double the
  budget, proven 2026-07-14/15).
- **Success trail:** one line per day in `storage\pull_log.txt`
  (`before=N after=M target=725 | OK/STALLED/COMPLETE`).
- **Failure signal:** `PULL_STALLED.txt` appears at repo root when a run produced no new
  files. Any future Claude session working in this repo should check for that file.
  It auto-clears on the next successful run.
- **Done condition:** 725 files in `storage\transcripts\` (29 tickers × 25 quarters,
  expanded 2026-07-13 — completion ≈ 2026-08-06, at 25 files/day). Expected usable
  yield ~660–690: by-design `[]` markers include pre-listing quarters (ARM listed
  2023-09, GEV spun off 2024-04, PLTR pre-2020Q3), calendar-FY tickers' 2026Q2
  until ~mid-Aug, and known AV gaps (VST_2021Q1). If the count plateaus below 725
  with STALLED lines, check quarter availability before suspecting a bug
  (EXPERT_BRIEF.md "Data traps").

## Managing

```powershell
Get-ScheduledTask ClaudeAuto-TranscriptPull | Get-ScheduledTaskInfo   # last/next run
Start-ScheduledTask ClaudeAuto-TranscriptPull                         # run now
Unregister-ScheduledTask ClaudeAuto-TranscriptPull -Confirm:$false    # remove
```

> **Note:** After moving to the new repo, update the `$repo` path in
> `scripts\daily_transcript_pull.ps1` if needed (already set to `C:\Users\zande\earnings_sentiment_tool`).

## ClaudeAuto-EarningsSurprisePull (one-shot, scheduled 2026-07-16 10:05)

- **What:** runs `scripts\earnings_surprise_pull.ps1` ONCE, then deletes itself. Spends
  7 AV calls on `scripts\pull_earnings_surprise.py` in the 10:05 gap - after the
  previous day's calls roll off the rolling-24h window, and before the 10:30 transcript
  task takes the rest of the 25. It does NOT touch the transcript task, so if this
  run fails the transcript pull still happens on schedule.
- **Success trail:** `storage\earnings_pull_log.txt` (key-scrubbed - see below).
- **Failure signal:** `EARNINGS_PULL_FAILED.txt` at repo root, distinguishing a
  HARD STOP (derivation failed live verification -> do NOT run the labeled study, do
  NOT "fix" the check, report) from INCOMPLETE (quota/key -> safe to rerun any
  morning; the fetcher caches successes only and never caches errors).
- **Key safety:** the wrapper captures python's output and masks every configured
  `ALPHA_VANTAGE_API_KEY*` value by exact match BEFORE writing the log, because AV
  echoes the key verbatim in quota errors (it leaked into `pull_log.txt` on
  2026-07-11 and 07-12). Never bypass that scrub when copying log text elsewhere.

## Spending quota on non-transcripts (e.g., earnings surprise pulls)

The shared AV budget is 25/day per IP, and the daily transcript task consumes all of
it. To spend quota on something else while keeping that task running, claim the gap
between the window rolling off (~10:05) and the task firing (10:30):

1. Run your pull at ~10:05, e.g.:
     C:\ProgramData\anaconda3\python.exe scripts\pull_earnings_surprise.py
2. Do nothing else - the 10:30 task takes whatever quota is left, automatically.

Prefer this over disabling the task: a disabled task that never gets re-enabled
silently costs a day of fill (25 files), whereas an unused gap costs nothing.
Safe to rerun any script (cached tickers are skipped at zero quota cost). If AV
prints quota errors, scrub any copied log text - AV error messages can echo the API key.
