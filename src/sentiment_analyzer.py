import re
import csv

# Starter word lists representing the four Loughran-McDonald (LM) Master
# Dictionary categories most used in earnings-call sentiment research
# (Negative, Positive, Uncertainty, Litigious). This is a small representative
# subset for finance text, NOT the full ~4,000-word LM dictionary - that file
# is distributed by Notre Dame's SRAF (https://sraf.nd.edu/loughranmcdonald-master-dictionary/)
# free for academic use but only via a Google Drive link that can't be
# fetched programmatically. Call EarningsCallAnalyzer.load_lm_dictionary(path)
# with a downloaded copy of the real CSV to replace these defaults.
DEFAULT_LM_WORDS = {
    "negative": {
        "adverse", "adversely", "against", "against", "bankrupt", "bankruptcy", "breach", "claims",
        "closure", "closures", "concern", "concerns", "decline", "declined", "declines", "declining",
        "default", "defaults", "deficiency", "deficit", "delay", "delays", "deteriorate", "deteriorated",
        "deterioration", "difficult", "difficulties", "difficulty", "disappointing", "disruption",
        "disruptions", "downturn", "failure", "failures", "fail", "failed", "fails", "impairment",
        "impairments", "layoff", "layoffs", "litigation", "loss", "losses", "negative", "negatively",
        "penalty", "penalties", "recession", "restructuring", "risk", "risks", "risky", "severe",
        "severely", "shortfall", "shortfalls", "slowdown", "slower", "sluggish", "termination",
        "unable", "unfavorable", "unfavorably", "volatile", "volatility", "weak", "weaker", "weakness",
        "weaknesses", "write-down", "writedown", "writedowns",
    },
    "positive": {
        "achieve", "achieved", "achievement", "achievements", "advantage", "advantages", "beneficial",
        "benefit", "benefits", "best", "boost", "boosted", "delight", "delighted", "encouraging",
        "excellent", "exceptional", "exceed", "exceeded", "exceeds", "favorable", "favorably", "gain",
        "gains", "great", "growth", "improve", "improved", "improvement", "improvements", "improves",
        "increase", "increased", "increases", "increasing", "leadership", "opportunities",
        "opportunity", "outperform", "outperformed", "positive", "positively", "profit", "profitable",
        "profits", "progress", "record", "strength", "strengthen", "strengthened", "strong",
        "stronger", "success", "successful", "successfully", "upside", "win", "winning",
    },
    "uncertainty": {
        "ambiguity", "ambiguous", "anticipate", "anticipates", "approximate", "approximately",
        "assume", "assumes", "assumption", "assumptions", "believe", "believes", "contingency",
        "contingent", "depend", "depending", "depends", "estimate", "estimated", "estimates",
        "fluctuate", "fluctuated", "fluctuates", "fluctuation", "fluctuations", "indefinite", "likely",
        "might", "possible", "possibly", "predict", "predicted", "probability", "probable", "risk",
        "seem", "seems", "should", "uncertain", "uncertainty", "uncertainties", "unclear", "unknown",
        "unpredictable", "variability", "variable",
    },
    "litigious": {
        "allegation", "allegations", "arbitration", "attorney", "claimant", "complaint", "complaints",
        "counsel", "court", "damages", "defendant", "hereinafter", "indemnification", "infringement",
        "injunction", "jurisdiction", "lawsuit", "lawsuits", "litigant", "litigate", "litigation",
        "plaintiff", "pursuant", "regulatory", "settlement", "sue", "sued", "sues", "suit", "tribunal",
    },
}

_WORD_RE = re.compile(r"[a-zA-Z']+")
_SENTENCE_SPLIT_RE = re.compile(r"[.!?]+")
_VOWEL_GROUP_RE = re.compile(r"[aeiouy]+", re.IGNORECASE)


def _count_syllables(word):
    """Rough heuristic: counts vowel-sound groups, drops a trailing silent 'e'."""
    word = word.lower()
    if word.endswith("e") and not word.endswith("le"):
        word = word[:-1]
    groups = _VOWEL_GROUP_RE.findall(word)
    return max(1, len(groups))


class EarningsCallAnalyzer:
    """
    Computes verbosity and sentiment metrics for a single earnings-call
    transcript (or one speaker turn), to test the hypothesis that executives
    get more verbose/complex when there's bad news to bury: negative
    sentiment should correlate with higher word count and complexity.
    """

    def __init__(self, lm_words=None):
        self.lm_words = lm_words or DEFAULT_LM_WORDS

    def load_lm_dictionary(self, csv_path):
        """
        Loads the real Loughran-McDonald Master Dictionary CSV (columns include
        'Word', 'Negative', 'Positive', 'Uncertainty', 'Litigious' - LM's
        convention is a nonzero year value in a category column means the word
        belongs to that category). Replaces the built-in starter word lists.
        """
        words = {"negative": set(), "positive": set(), "uncertainty": set(), "litigious": set()}
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                word = row["Word"].lower()
                for category in words:
                    col = category.capitalize()
                    if col in row and row[col] and row[col] != "0":
                        words[category].add(word)
        self.lm_words = words
        return self

    def analyze_text(self, text):
        """Returns verbosity + LM lexicon-based sentiment metrics for a block of text."""
        words = [w.lower() for w in _WORD_RE.findall(text)]
        word_count = len(words)
        sentences = [s for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
        sentence_count = max(1, len(sentences))

        if word_count == 0:
            return {
                "word_count": 0, "sentence_count": 0, "avg_sentence_length": None,
                "complex_word_ratio": None, "fog_index": None,
                "negative_count": 0, "positive_count": 0, "uncertainty_count": 0, "litigious_count": 0,
                "lm_net_sentiment": None,
            }

        negative_count = sum(1 for w in words if w in self.lm_words["negative"])
        positive_count = sum(1 for w in words if w in self.lm_words["positive"])
        uncertainty_count = sum(1 for w in words if w in self.lm_words["uncertainty"])
        litigious_count = sum(1 for w in words if w in self.lm_words["litigious"])

        complex_words = sum(1 for w in words if _count_syllables(w) >= 3)
        avg_sentence_length = word_count / sentence_count
        complex_word_ratio = complex_words / word_count
        # Gunning Fog Index: standard readability/complexity metric, higher = harder to read.
        fog_index = 0.4 * (avg_sentence_length + 100 * complex_word_ratio)

        return {
            "word_count": word_count,
            "sentence_count": sentence_count,
            "avg_sentence_length": avg_sentence_length,
            "complex_word_ratio": complex_word_ratio,
            "fog_index": fog_index,
            "negative_count": negative_count,
            "positive_count": positive_count,
            "uncertainty_count": uncertainty_count,
            "litigious_count": litigious_count,
            "lm_net_sentiment": (positive_count - negative_count) / word_count,
        }

    def analyze_transcript(self, transcript_entries, speakers=None):
        """
        transcript_entries: list of Alpha Vantage speaker-turn dicts
        ({'speaker', 'title', 'content', 'sentiment'}). If speakers is given,
        only turns from those speaker names are included (e.g. restrict to the
        CEO/CFO's prepared remarks, excluding analyst Q&A).

        Combines all matching turns into one block for the lexicon/verbosity
        metrics, and separately averages Alpha Vantage's own per-turn
        'sentiment' field (word-count weighted) as av_sentiment - a second,
        independently-produced sentiment signal to compare against lm_net_sentiment.
        """
        turns = transcript_entries
        if speakers:
            speakers_lower = {s.lower() for s in speakers}
            turns = [t for t in turns if str(t.get("speaker", "")).lower() in speakers_lower]

        combined_text = " ".join(t.get("content", "") for t in turns)
        metrics = self.analyze_text(combined_text)

        av_scores, av_weights = [], []
        for t in turns:
            score = t.get("sentiment")
            content = t.get("content", "")
            if score is None or not content:
                continue
            try:
                av_scores.append(float(score))
                av_weights.append(len(_WORD_RE.findall(content)))
            except (TypeError, ValueError):
                continue

        metrics["av_sentiment"] = (
            float(sum(s * w for s, w in zip(av_scores, av_weights)) / sum(av_weights))
            if av_weights else None
        )
        metrics["num_speaker_turns"] = len(turns)
        return metrics
