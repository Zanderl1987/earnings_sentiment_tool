# NLP Earnings Call Sentiment & Verbosity Study

This document details the methodology, metrics, and data integration patterns of the **NLP Earnings Call Sentiment Study**.

---

## 1. Study Goals and Hypothesis

The study tests the following behavioral finance hypothesis:
> **Hypothesis**: Corporate executives become more verbose and use more complex language to bury or deflect bad news during quarterly earnings calls.

To test this without circular logic, we correlate transcript text complexity metrics against **external labels** of quarterly performance (earnings surprise and post-event abnormal returns).

---

## 2. Text Analysis Metrics

The text analyzer ([sentiment_analyzer.py](file:///C:/Users/zande/custom_index_tool/src/nlp/sentiment_analyzer.py)) parses transcript segments to extract:

### A. Readability / Complexity (Gunning Fog Index)
The Gunning Fog Index calculates the grade level required to read a piece of text. A higher index indicates more complex, potentially obfuscated prose.
$$\text{Fog Index} = 0.4 \times \left( \text{Average Sentence Length} + 100 \times \frac{\text{Complex Words}}{\text{Total Words}} \right)$$

*   **Average Sentence Length**: $\frac{\text{Total Words}}{\text{Total Sentences}}$.
*   **Complex Words**: Words containing three or more syllables (excluding common suffixes/rules).

### B. Loughran-McDonald (LM) Sentiment Lexicon
The analyzer uses the Loughran-McDonald Master Dictionary, which is the academic standard for financial text mining. Words are mapped to four primary emotional/functional groups:
1.  **Negative**: Words representing decline, delay, difficulties, or failure.
2.  **Positive**: Words representing growth, improvement, record, or profit.
3.  **Uncertainty**: Words representing fluctuation, estimate, risk, or likelihood.
4.  **Litigious**: Words representing lawsuits, attorneys, regulations, or claims.

The primary net score is calculated as:
$$\text{Net Sentiment} = \frac{\text{Positive Count} - \text{Negative Count}}{\text{Total Words}}$$

---

## 3. Labeling and Avoiding Circularity

As highlighted in [EXPERT_BRIEF.md](file:///C:/Users/zande/custom_index_tool/EXPERT_BRIEF.md), checking if "negative transcripts are verbose" by using in-transcript sentiment is circular. To solve this, the pipeline joins transcripts with two independent labels:

1.  **Earnings Surprise**:
    $$\text{Surprise \%} = \frac{\text{Reported EPS} - \text{Estimated EPS}}{\text{Estimated EPS}}$$
2.  **Cumulative Abnormal Return (CAR)**:
    The cumulative return of the stock around the event date $T_0$ (e.g., $T_0$ to $T_{+1}$) minus the return of the benchmark ($SPY$) over the same window:
    $$CAR = R_{\text{stock}, [T_0, T_1]} - R_{\text{SPY}, [T_0, T_1]}$$

---

## 4. Technical Architecture: Fiscal Offset Mapping

Alpha Vantage transcript queries label files by fiscal quarters (e.g., `2024Q3`). However, many companies do not align their fiscal calendars with the standard calendar year (e.g., Oracle `ORCL` or Nvidia `NVDA`).

To map these correctly:
1.  We query the Alpha Vantage `EARNINGS` API endpoint for the company.
2.  We parse the JSON output to extract both the `fiscalDateEnding` (which matches the $quarter$ label) and the `reportedDate` (which is the actual calendar date the call occurred).
3.  This mapping:
    $$\text{(Ticker, Fiscal Quarter)} \longrightarrow \text{Reported Date}$$
    is used to index the correct pricing windows for calculating CARs, preventing alignment errors.

---

## 5. Daily Task Pipeline and Quota Discipline

The study expands to **29 tickers across 25 quarters** (2020Q2 - 2026Q2), totaling **725 transcripts**.

Due to Alpha Vantage's strict IP-based limit of **25 calls per day**:
*   The script uses a resumable sqlite or file cache (`storage/transcripts/`).
*   A Windows Scheduled Task (`ClaudeAuto-TranscriptPull`) runs everyday at 10:30 AM.
*   The fetcher checks if a transcript is already cached; if yes, it skips it at 0 quota cost.
*   If the task encounters rate limits, it exits cleanly, logging the progress in `storage/pull_log.txt`.
*   If the pull yields zero new files, it flags a stall by writing `PULL_STALLED.txt` to the root, alerting the user to audit current coverage.
