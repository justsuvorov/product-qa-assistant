import pytest
from product_assistant.scraper.document_parser import _get_extension, _clean, SUPPORTED_EXTENSIONS


def test_get_extension_pdf():
    assert _get_extension("https://example.com/file.pdf") == ".pdf"


def test_get_extension_docx():
    assert _get_extension("https://example.com/doc.docx") == ".docx"


def test_get_extension_pptx():
    assert _get_extension("https://example.com/presentation.pptx") == ".pptx"


def test_get_extension_unknown():
    assert _get_extension("https://example.com/image.png") == ""


def test_get_extension_case_insensitive():
    assert _get_extension("https://example.com/file.PDF") == ".pdf"


def test_get_extension_with_query_params():
    assert _get_extension("https://example.com/doc.pdf?v=2") == ".pdf"


def test_clean_normalizes_triple_newlines():
    result = _clean("a\n\n\n\nb")
    assert "\n\n\n" not in result
    assert "a" in result
    assert "b" in result


def test_clean_strips_whitespace():
    assert _clean("  text  ") == "text"


def test_clean_preserves_double_newlines():
    result = _clean("a\n\nb")
    assert result == "a\n\nb"


def test_supported_extensions_set():
    assert ".pdf" in SUPPORTED_EXTENSIONS
    assert ".docx" in SUPPORTED_EXTENSIONS
    assert ".pptx" in SUPPORTED_EXTENSIONS
