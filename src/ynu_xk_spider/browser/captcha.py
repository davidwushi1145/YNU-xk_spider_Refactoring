"""Captcha solver abstraction with ddddocr implementation."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

from ..exceptions import CaptchaError

logger = logging.getLogger(__name__)


class CaptchaSolver(ABC):
    """Abstract interface for captcha solving."""

    @abstractmethod
    def solve(self, image_bytes: bytes) -> str:
        """Recognize text from captcha image.

        Args:
            image_bytes: Raw image data (PNG/JPEG).

        Returns:
            Recognized captcha text.

        Raises:
            CaptchaError: If recognition fails or result is invalid.
        """


class DdddocrSolver(CaptchaSolver):
    """Captcha solver using ddddocr library.

    Attributes:
        _ocr: ddddocr instance (lazy initialized).
        _min_length: Minimum valid captcha length.
        _max_length: Maximum valid captcha length.
    """

    def __init__(
        self,
        min_length: int = 1,
        max_length: int = 10,
        show_ad: bool = False,
    ) -> None:
        """Initialize solver with validation parameters.

        Args:
            min_length: Minimum expected captcha length.
            max_length: Maximum expected captcha length.
            show_ad: Whether to show ddddocr advertisement.
        """
        if min_length < 1:
            raise ValueError("min_length must be >= 1")
        if max_length < min_length:
            raise ValueError("max_length must be >= min_length")
        self._min_length = min_length
        self._max_length = max_length
        self._show_ad = show_ad
        self._ocr: Optional[Any] = None

    def _get_ocr(self) -> Any:
        """Lazy initialize ddddocr instance."""
        if self._ocr is None:
            try:
                import ddddocr

                self._ocr = ddddocr.DdddOcr(show_ad=self._show_ad)
                logger.debug("ddddocr initialized")
            except ImportError as exc:
                raise CaptchaError("ddddocr not installed") from exc
            except Exception as exc:
                raise CaptchaError(f"Failed to initialize ddddocr: {exc}") from exc
        return self._ocr

    def solve(self, image_bytes: bytes) -> str:
        """Recognize captcha using ddddocr.

        Args:
            image_bytes: Raw image data.

        Returns:
            Recognized and validated captcha text.

        Raises:
            CaptchaError: If recognition fails or result is invalid.
        """
        if not image_bytes:
            raise CaptchaError("Empty image data")

        try:
            ocr = self._get_ocr()
            result = ocr.classification(image_bytes)  # type: ignore

            if not result:
                raise CaptchaError("OCR returned empty result")

            result_str = str(result).strip()

            if len(result_str) < self._min_length:
                raise CaptchaError(
                    f"Captcha too short: {len(result_str)} < {self._min_length}"
                )

            if len(result_str) > self._max_length:
                raise CaptchaError(
                    f"Captcha too long: {len(result_str)} > {self._max_length}"
                )

            logger.debug("Captcha recognized: %s", result_str)
            return result_str

        except CaptchaError:
            raise
        except Exception as exc:
            raise CaptchaError(f"OCR failed: {exc}") from exc
