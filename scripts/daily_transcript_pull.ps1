# Daily transcript-dataset pull with output verification.
# Registered as Windows Scheduled Task "ClaudeAuto-TranscriptPull" (see AUTOMATION.md).
# The whole point of this wrapper: a run that executes but produces no new files is a
# FAILURE and must leave a visible trace (PULL_STALLED.txt), not silence.

$repo = "C:\Users\zande\earnings_sentiment_tool"
$py = "C:\ProgramData\anaconda3\python.exe"
$dir = Join-Path $repo "storage\transcripts"
$log = Join-Path $repo "storage\pull_log.txt"
$flag = Join-Path $repo "PULL_STALLED.txt"
# Keep in sync with len(TICKERS) * NUM_QUARTERS in src\build_transcript_dataset.py
# (29 x 25 = 725; tests\test_dataset_config.py enforces the match).
$target = 725

New-Item -ItemType Directory -Force -Path $dir | Out-Null
$before = (Get-ChildItem $dir -File -ErrorAction SilentlyContinue | Measure-Object).Count

if ($before -ge $target) {
    Add-Content $log "$(Get-Date -Format 'yyyy-MM-dd HH:mm') | before=$before | COMPLETE - dataset full, nothing to do"
    exit 0
}

Set-Location $repo
# Force UTF-8 python output so the log stays single-encoding (it was mojibake
# before 2026-07-11 from mixed PS 5.1 / python encodings).
$env:PYTHONIOENCODING = "utf-8"
# cmd /c does the redirection: PS 5.1 would wrap python's stderr lines in
# NativeCommandError records and pollute the log
cmd /c "`"$py`" -m src.build_transcript_dataset >> `"$log`" 2>&1"
$exit = $LASTEXITCODE

$after = (Get-ChildItem $dir -File -ErrorAction SilentlyContinue | Measure-Object).Count
$stamp = Get-Date -Format "yyyy-MM-dd HH:mm"

if ($after -gt $before) {
    $status = "OK (+$($after - $before))"
    if (Test-Path $flag) { Remove-Item $flag -Force }
} else {
    $status = "STALLED - no new files (exit=$exit)"
    "Daily transcript pull ran $stamp but produced no new files ($after/$target cached, python exit=$exit).`nCheck storage\pull_log.txt. Possible causes: rate limit already spent, API key issue, or all remaining quarters unavailable on Alpha Vantage." |
        Out-File $flag -Encoding utf8
}
Add-Content $log "$stamp | before=$before after=$after target=$target | $status"
