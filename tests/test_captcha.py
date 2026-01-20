"""Tests for captcha solver."""

import pytest
from unittest.mock import Mock, patch, MagicMock
import sys

from ynu_xk_spider.browser.captcha import DdddocrSolver, CaptchaSolver
from ynu_xk_spider.exceptions import CaptchaError


class TestDdddocrSolver:
    """Test cases for DdddocrSolver."""

    def test_initialization_defaults(self):
        """Test default initialization parameters."""
        solver = DdddocrSolver()
        assert solver._min_length == 4
        assert solver._max_length == 4
        assert solver._beta is False
        assert solver._charset_range == 6
        assert solver._png_fix is True

    def test_initialization_custom(self):
        """Test custom initialization parameters."""
        solver = DdddocrSolver(
            min_length=3,
            max_length=6,
            beta=True,
            charset_range=0,
            png_fix=False,
        )
        assert solver._min_length == 3
        assert solver._max_length == 6
        assert solver._beta is True
        assert solver._charset_range == 0
        assert solver._png_fix is False

    def test_initialization_invalid_min_length(self):
        """Test invalid min_length raises ValueError."""
        with pytest.raises(ValueError, match="min_length must be >= 1"):
            DdddocrSolver(min_length=0)

    def test_initialization_invalid_max_length(self):
        """Test invalid max_length raises ValueError."""
        with pytest.raises(ValueError, match="max_length must be >= min_length"):
            DdddocrSolver(min_length=5, max_length=3)

    def test_solve_empty_image(self):
        """Test empty image raises CaptchaError."""
        solver = DdddocrSolver()
        with pytest.raises(CaptchaError, match="Empty image data"):
            solver.solve(b"")

    def test_solve_success(self):
        """Test successful captcha solving."""
        mock_ocr = Mock()
        mock_ocr.classification.return_value = "ab12"
        mock_ocr.set_ranges = Mock()
        
        mock_ddddocr = Mock()
        mock_ddddocr.DdddOcr.return_value = mock_ocr
        
        with patch.dict(sys.modules, {'ddddocr': mock_ddddocr}):
            solver = DdddocrSolver()
            solver._ocr = None  # Reset to force lazy init
            result = solver.solve(b"fake_image_data")

        assert result == "ab12"

    def test_solve_too_short(self):
        """Test captcha too short raises error."""
        mock_ocr = Mock()
        mock_ocr.classification.return_value = "ab"  # Too short (min=4)
        mock_ocr.set_ranges = Mock()
        
        mock_ddddocr = Mock()
        mock_ddddocr.DdddOcr.return_value = mock_ocr
        
        with patch.dict(sys.modules, {'ddddocr': mock_ddddocr}):
            solver = DdddocrSolver()
            solver._ocr = None
            with pytest.raises(CaptchaError, match="Captcha too short"):
                solver.solve(b"fake_image_data")

    def test_solve_too_long(self):
        """Test captcha too long raises error."""
        mock_ocr = Mock()
        mock_ocr.classification.return_value = "abcdef"  # Too long (max=4)
        mock_ocr.set_ranges = Mock()
        
        mock_ddddocr = Mock()
        mock_ddddocr.DdddOcr.return_value = mock_ocr
        
        with patch.dict(sys.modules, {'ddddocr': mock_ddddocr}):
            solver = DdddocrSolver()
            solver._ocr = None
            with pytest.raises(CaptchaError, match="Captcha too long"):
                solver.solve(b"fake_image_data")

    def test_solve_empty_result(self):
        """Test empty OCR result raises error."""
        mock_ocr = Mock()
        mock_ocr.classification.return_value = ""
        mock_ocr.set_ranges = Mock()
        
        mock_ddddocr = Mock()
        mock_ddddocr.DdddOcr.return_value = mock_ocr
        
        with patch.dict(sys.modules, {'ddddocr': mock_ddddocr}):
            solver = DdddocrSolver()
            solver._ocr = None
            with pytest.raises(CaptchaError, match="OCR returned empty result"):
                solver.solve(b"fake_image_data")


class TestCaptchaSolverInterface:
    """Test CaptchaSolver interface."""

    def test_is_abstract(self):
        """Test CaptchaSolver is abstract and cannot be instantiated."""
        with pytest.raises(TypeError):
            CaptchaSolver()

    def test_ddddocr_is_captcha_solver(self):
        """Test DdddocrSolver implements CaptchaSolver."""
        solver = DdddocrSolver()
        assert isinstance(solver, CaptchaSolver)
