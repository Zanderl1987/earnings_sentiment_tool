# One-time AV EARNINGS pull wrapper (stage-2 label join).
# Registered as Windows Scheduled Task "ClaudeAuto-EarningsSurprisePull" for a single
# 10:05 run, then deletes itself. See AUTOMATION.md and the docstring of
# scripts\pull_earnings_surprise.py.
#
# Why 10:05 and why this exists: the 7 EARNINGS calls must land BEFORE the daily
# transcript task (10:30) spends the day's 25-call budget, and AFTER the previous
# day's calls roll off the rolling-24h window (~10:05). This wrapper claims that gap.
#
# Same posture as daily_transcript_pull.ps1: a run that fails must leave a VISIBLE
# trace (EARNINGS_PULL_FAILED.txt), never silence. It does NOT touch the transcript
# task - that one runs at 10:30 on its own and takes whatever quota is left.

$repo = "C:\Users\zande\earnings_sentiment_tool"
$py = "C:\ProgramData\anaconda3\python.exe"
$log = Join-Path $repo "storage\earnings_pull_log.txt"
$flag = Join-Path $repo "EARNINGS_PULL_FAILED.txt"
$cacheDir = Join-Path $repo "storage\earnings_surprise"
$stamp = Get-Date -Format "yyyy-MM-dd HH:mm"

Set-Location $repo
$env:PYTHONIOENCODING = "utf-8"

# Capture rather than tee: the output must be SCRUBBED before it touches disk.
# Alpha Vantage echoes the API key verbatim in quota/error messages, and
# pull_earnings_surprise.py prints AV's error text (this has leaked keys into
# storage\pull_log.txt twice before - 2026-07-11 and 07-12).
$out = & cmd /c "`"$py`" scripts\pull_earnings_surprise.py 2>&1"
$exit = $LASTEXITCODE
$out = ($out | Out-String)

# Mask every configured key value by exact match. Parse .env directly - the keys are
# never echoed, only used as replacement targets.
$envFile = Join-Path $repo ".env"
if (Test-Path $envFile) {
    foreach ($line in (Get-Content $envFile)) {
        if ($line -match '^\s*ALPHA_VANTAGE_API_KEY(_\d+)?\s*=\s*(.+?)\s*$') {
            $secret = $matches[2].Trim('"').Trim("'")
            if ($secret.Length -ge 8) {
                $out = $out.Replace($secret, "***REDACTED***")
            }
        }
    }
}

$cached = (Get-ChildItem $cacheDir -File -Filter *.json -ErrorAction SilentlyContinue | Measure-Object).Count
$hardStop = $out -match "HARD STOP"

Add-Content $log "===== $stamp | exit=$exit | cached=$cached/7 ====="
Add-Content $log $out

if ($hardStop) {
    $status = "HARD STOP - derivation failed live verification"
    @"
EARNINGS pull HARD-STOPPED $stamp.

The fiscal-quarter derivation did NOT reproduce the probe's ground truth against
live Alpha Vantage data. This is the designed hard stop: an unverified join key
would silently mislabel every quarter in the study.

DO NOT run scripts\run_labeled_study.py. Do not "fix" the derivation to make the
check pass - the check is the thing protecting the dataset.

Read storage\earnings_pull_log.txt (already key-scrubbed) and report to Zander.
Spec: docs\superpowers\specs\2026-07-13-label-join-design.md (Error handling).
"@ | Out-File $flag -Encoding utf8
} elseif ($exit -ne 0 -or $cached -lt 7) {
    $status = "INCOMPLETE - $cached/7 cached (exit=$exit)"
    @"
EARNINGS pull did not complete $stamp ($cached/7 tickers cached, exit=$exit).

Most likely the 25/day per-IP AV quota was already spent, or a key is unset.
This is SAFE to retry: the fetcher caches successes only and never caches errors,
so a rerun resumes and re-spends nothing. Rerun on a morning before the 10:30
transcript task, per AUTOMATION.md.

Read storage\earnings_pull_log.txt (already key-scrubbed).
"@ | Out-File $flag -Encoding utf8
} else {
    $status = "OK - 7/7 tickers cached, derivation VERIFIED"
    if (Test-Path $flag) { Remove-Item $flag -Force }
}

Add-Content $log "$stamp | $status"

# One-shot task: remove itself so it cannot fire again and re-spend quota.
schtasks /Delete /TN "ClaudeAuto-EarningsSurprisePull" /F 2>&1 | Out-Null
