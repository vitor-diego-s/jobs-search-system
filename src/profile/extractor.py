"""PDF text extraction using pymupdf (optional dependency)."""

from pathlib import Path


def extract_text_from_pdf(path: str | Path) -> str:
    """Extract plain text from a PDF file.

    Args:
        path: Path to the PDF file.

    Returns:
        Concatenated text from all pages.

    Raises:
        FileNotFoundError: If the PDF file does not exist.
        ImportError: If pymupdf is not installed.
    """
    path = Path(path)
    if not path.exists():
        msg = f"PDF file not found: {path}"
        raise FileNotFoundError(msg)

    try:
        import pymupdf
    except ImportError:
        msg = (
            "pymupdf is required for PDF extraction. "
            "Install with: pip install 'jobs-search-engine[profile]'"
        )
        raise ImportError(msg) from None

    doc = pymupdf.open(str(path))
    text_parts: list[str] = []
    for page in doc:
        text_parts.append(page.get_text())
    doc.close()

    return "\n".join(text_parts)
