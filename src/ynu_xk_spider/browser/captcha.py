"""Captcha solver abstraction with ddddocr implementation."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

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
    """Captcha solver using ddddocr library optimized for 4-char alphanumeric codes.

    Optimized for YNU captcha format:
    - Length: 4 characters
    - Charset: 0-9, a-z, A-Z (alphanumeric)
    - Format: Mixed case letters and numbers

    Attributes:
        _ocr: ddddocr instance (lazy initialized).
        _min_length: Minimum valid captcha length.
        _max_length: Maximum valid captcha length.
        _beta: Use beta OCR model.
        _charset_range: Character set constraint (6 = a-z + A-Z + 0-9).
        _png_fix: Enable PNG transparent background fix.
    """

    def __init__(
        self,
        min_length: int = 4,
        max_length: int = 4,
        show_ad: bool = False,
        beta: bool = False,
        charset_range: int = 6,
        png_fix: bool = True,
    ) -> None:
        """Initialize solver with validation parameters.

        Args:
            min_length: Minimum expected captcha length (default: 4).
            max_length: Maximum expected captcha length (default: 4).
            show_ad: Whether to show ddddocr advertisement.
            beta: Use beta OCR model (alternative recognition engine).
            charset_range: Character set constraint:
                0 = digits only (0-9)
                1 = lowercase only (a-z)
                2 = uppercase only (A-Z)
                3 = letters (a-z + A-Z)
                4 = lowercase + digits (a-z + 0-9)
                5 = uppercase + digits (A-Z + 0-9)
                6 = alphanumeric (a-z + A-Z + 0-9) [default for YNU]
                7 = full charset
            png_fix: Enable PNG transparent background fix.
        """
        if min_length < 1:
            raise ValueError("min_length must be >= 1")
        if max_length < min_length:
            raise ValueError("max_length must be >= min_length")
        self._min_length = min_length
        self._max_length = max_length
        self._show_ad = show_ad
        self._beta = beta
        self._charset_range = charset_range
        self._png_fix = png_fix
        self._ocr: Any | None = None

    def _get_ocr(self) -> Any:
        """Lazy initialize ddddocr instance with optimized settings."""
        if self._ocr is None:
            try:
                import ddddocr

                self._ocr = ddddocr.DdddOcr(show_ad=self._show_ad, beta=self._beta)

                # Set character range for alphanumeric recognition
                self._ocr.set_ranges(self._charset_range)

                logger.info(
                    "ddddocr initialized: beta=%s, charset_range=%d, png_fix=%s",
                    self._beta,
                    self._charset_range,
                    self._png_fix,
                )
            except ModuleNotFoundError as exc:
                raise CaptchaError("ddddocr is not installed") from exc
            except ImportError as exc:
                raise CaptchaError(
                    "ddddocr import failed. Installed package may be incompatible "
                    f"or broken: {exc}. Try reinstalling with `pip install \"ddddocr<1.6.0\"`."
                ) from exc
            except Exception as exc:
                raise CaptchaError(f"Failed to initialize ddddocr: {exc}") from exc
        return self._ocr

    def solve(self, image_bytes: bytes) -> str:
        """Recognize captcha using ddddocr with optimized settings.

        Args:
            image_bytes: Raw image data (PNG/JPEG).

        Returns:
            Recognized and validated captcha text (4 alphanumeric characters).

        Raises:
            CaptchaError: If recognition fails or result is invalid.
        """
        if not image_bytes:
            raise CaptchaError("Empty image data")

        try:
            ocr = self._get_ocr()

            # Use png_fix for transparent background PNG images
            result = ocr.classification(image_bytes, png_fix=self._png_fix)

            if not result:
                raise CaptchaError("OCR returned empty result")

            result_str = str(result).strip()

            if len(result_str) < self._min_length:
                raise CaptchaError(
                    f"Captcha too short: {len(result_str)} < {self._min_length} (got: '{result_str}')"
                )

            if len(result_str) > self._max_length:
                raise CaptchaError(
                    f"Captcha too long: {len(result_str)} > {self._max_length} (got: '{result_str}')"
                )

            logger.debug("Captcha recognized: %s (length: %d)", result_str, len(result_str))
            return result_str

        except CaptchaError:
            raise
        except Exception as exc:
            raise CaptchaError(f"OCR failed: {exc}") from exc
