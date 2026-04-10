import pytest

from app.langchain_agent_service import embedding_to_vector_literal, extract_pdf_page_texts


def test_embedding_to_vector_literal_uses_configured_dimension(monkeypatch) -> None:
    monkeypatch.setenv("EMBEDDING_DIMENSION", "3")
    vector_literal = embedding_to_vector_literal([0.1, 0.2, 0.3])
    assert vector_literal.startswith("[")
    assert vector_literal.endswith("]")


def test_extract_pdf_page_texts_rejects_invalid_pdf() -> None:
    with pytest.raises(ValueError):
        extract_pdf_page_texts(b"not-a-valid-pdf")
