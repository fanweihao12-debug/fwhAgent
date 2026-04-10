from app.langchain_agent_service import embedding_to_vector_literal


def test_embedding_to_vector_literal_uses_configured_dimension(monkeypatch) -> None:
    monkeypatch.setenv("EMBEDDING_DIMENSION", "3")
    vector_literal = embedding_to_vector_literal([0.1, 0.2, 0.3])
    assert vector_literal.startswith("[")
    assert vector_literal.endswith("]")
