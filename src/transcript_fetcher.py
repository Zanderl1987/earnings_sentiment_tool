import os
import time
import json
import requests

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TranscriptFetcher:
    """
    Fetches earnings call transcripts via Alpha Vantage's EARNINGS_CALL_TRANSCRIPT
    endpoint (function=EARNINGS_CALL_TRANSCRIPT, symbol, quarter=YYYYQN). Each
    response entry is a speaker turn: {speaker, title, content, sentiment}, where
    'sentiment' is Alpha Vantage's own precomputed score for that turn (not
    something we compute ourselves).

    Reuses DataIngestor's key-rotation/caching pattern since transcripts share
    the same Alpha Vantage account and 25-req/day free-tier quota as price data.
    """

    AV_URL = "https://www.alphavantage.co/query"

    def __init__(self, cache_dir=None):
        if cache_dir is None:
            cache_dir = os.path.join(PROJECT_ROOT, "storage", "transcripts")
        self.cache_dir = cache_dir
        self.api_keys = [k for k in [os.getenv("ALPHA_VANTAGE_API_KEY"), os.getenv("ALPHA_VANTAGE_API_KEY_2")] if k]
        self.key_index = 0
        self.exhausted = False
        os.makedirs(self.cache_dir, exist_ok=True)

    @property
    def api_key(self):
        if self.key_index >= len(self.api_keys):
            return None
        return self.api_keys[self.key_index]

    def fetch_transcript(self, ticker, quarter):
        """
        quarter: string like '2024Q1'. Returns a list of speaker-turn dicts, or
        an empty list if unavailable (delisted symbol, quarter has no call yet,
        quota exhausted, etc). Cached to disk so repeat analysis doesn't burn
        the shared 25-req/day quota.
        """
        cache_file = os.path.join(self.cache_dir, f"{ticker}_{quarter}.json")
        if os.path.exists(cache_file):
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)

        if not self.api_key:
            print(f"No usable Alpha Vantage key (quota exhausted or unset). Skipping {ticker} {quarter}.")
            return []

        if self.exhausted:
            print(f"Skipping {ticker} {quarter}: all API keys already exhausted their daily quota this run.")
            return []

        print(f"Fetching {ticker} {quarter} transcript from Alpha Vantage...")
        time.sleep(12)  # same free-tier rate limit as DataIngestor (5 calls/min)
        response = requests.get(self.AV_URL, params={
            "function": "EARNINGS_CALL_TRANSCRIPT",
            "symbol": ticker,
            "quarter": quarter,
            "apikey": self.api_key,
        })
        data = response.json()

        transcript = data.get("transcript")
        if transcript is None:
            error_msg = data.get("Information") or data.get("Error Message") or data.get("Note") or "Unknown error"
            print(f"Error fetching {ticker} {quarter}: {error_msg}")
            if "requests per day" in error_msg or "rate limit" in error_msg.lower():
                self.key_index += 1
                if self.api_key:
                    print(f"Daily quota hit on previous key, switching to backup key ({self.key_index + 1}/{len(self.api_keys)}).")
                    return self.fetch_transcript(ticker, quarter)
                print("All API keys have hit their daily quota.")
                self.exhausted = True
            return []

        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(transcript, f)
        return transcript

    def fetch_recent_transcripts(self, ticker, quarters):
        """quarters: list of 'YYYYQN' strings. Returns {quarter: transcript} for
        whichever quarters actually returned data."""
        results = {}
        for q in quarters:
            transcript = self.fetch_transcript(ticker, q)
            if transcript:
                results[q] = transcript
        return results
