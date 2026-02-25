"""Tests for PDF text extractor."""

from unittest.mock import MagicMock, patch

import pytest

from src.profile.extractor import extract_text_from_pdf


class TestExtractTextFromPdf:
    def test_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError, match="PDF file not found"):
            extract_text_from_pdf("/nonexistent/resume.pdf")

    def test_missing_pymupdf_import(self, tmp_path: pytest.TempPathFactory) -> None:  # type: ignore[type-arg]
        pdf_path = tmp_path / "resume.pdf"  # type: ignore[operator]
        pdf_path.write_bytes(b"%PDF-1.4 fake")

        with (
            patch.dict("sys.modules", {"pymupdf": None}),
            pytest.raises(ImportError, match="pymupdf is required"),
        ):
            extract_text_from_pdf(pdf_path)

    def test_successful_extraction(self, tmp_path: pytest.TempPathFactory) -> None:  # type: ignore[type-arg]
        pdf_path = tmp_path / "resume.pdf"  # type: ignore[operator]
        pdf_path.write_bytes(b"%PDF-1.4 fake")

        mock_page = MagicMock()
        mock_page.get_text.return_value = "Jane Doe\nSenior Python Engineer"

        mock_doc = MagicMock()
        mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))

        mock_pymupdf = MagicMock()
        mock_pymupdf.open.return_value = mock_doc

        with patch.dict("sys.modules", {"pymupdf": mock_pymupdf}):
            result = extract_text_from_pdf(pdf_path)

        assert "Jane Doe" in result
        assert "Senior Python Engineer" in result
        assert len(result) > 0
