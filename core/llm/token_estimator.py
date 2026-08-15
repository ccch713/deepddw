"""P3: Token approximate calculation (PRD v5.7 §32.4).

One API: Uses tiktoken encoder for precise calculation (slow init, ~2s).
DDW: Provides two modes:
1. Fast mode: len(text) * 0.38 (init 0ms, good enough for pre-consumption)
2. Precise mode: tiktoken encoding (init ~2s, but exact)

Usage:
- Pre-consumption phase: fast mode (sufficient)
- Post-consumption phase: precise mode (if available)
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class TokenEstimator:
    """Token count estimator with fast and precise modes.

    For Chinese+English mixed text, experience shows:
    - Chinese text: ~0.38 tokens per character
    - English text: ~0.25 tokens per character (≈4 chars per token)
    """

    # Experience coefficients for mixed Chinese/English text
    CHINESE_RATIO = 0.38
    ENGLISH_RATIO = 0.25

    # tiktoken encoder instance (cached after first load)
    _tiktoken_encoder = None
    _tiktoken_loaded = False

    @classmethod
    def estimate_fast(cls, text: str) -> int:
        """Fast token estimation (0ms initialization).

        Uses character counting with language-adaptive coefficient.
        Good enough for quota pre-checks and rough estimates.

        Args:
            text: Input text to estimate token count for.

        Returns:
            Estimated token count (minimum 1).
        """
        if not text:
            return 1

        total_chars = len(text)
        if total_chars == 0:
            return 1

        # Count Chinese characters
        chinese_chars = sum(
            1 for c in text if "\u4e00" <= c <= "\u9fff"
        )
        chinese_ratio = chinese_chars / total_chars

        # Use Chinese coefficient if >30% Chinese characters
        ratio = cls.CHINESE_RATIO if chinese_ratio > 0.3 else cls.ENGLISH_RATIO
        return max(1, int(total_chars * ratio))

    @classmethod
    def estimate_precise(cls, text: str) -> int:
        """Precise token count using tiktoken (requires tiktoken package).

        Falls back to fast estimation if tiktoken is not installed.

        Args:
            text: Input text to count tokens for.

        Returns:
            Exact token count (or fast estimate as fallback).
        """
        if not cls._tiktoken_loaded:
            cls._load_tiktoken()

        if cls._tiktoken_encoder is not None:
            try:
                return len(cls._tiktoken_encoder.encode(text))
            except Exception as exc:  # noqa: BLE001
                logger.debug("tiktoken encode failed, falling back to fast: %s", exc)

        return cls.estimate_fast(text)

    @classmethod
    def _load_tiktoken(cls) -> None:
        """Lazily load tiktoken encoder."""
        cls._tiktoken_loaded = True
        try:
            import tiktoken

            cls._tiktoken_encoder = tiktoken.encoding_for_model("gpt-4")
            logger.info("tiktoken encoder loaded successfully")
        except ImportError:
            logger.info("tiktoken not installed, using fast estimation only")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load tiktoken: %s", exc)

    @classmethod
    def estimate_batch(cls, texts: list[str], precise: bool = False) -> list[int]:
        """Estimate token counts for a batch of texts.

        Args:
            texts: List of input texts.
            precise: If True, use precise mode (slower).

        Returns:
            List of estimated token counts.
        """
        estimator = cls.estimate_precise if precise else cls.estimate_fast
        return [estimator(t) for t in texts]
