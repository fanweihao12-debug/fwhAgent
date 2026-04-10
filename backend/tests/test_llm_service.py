from app.llm_service import parse_deepseek_response


def test_parse_deepseek_response_extracts_message_content() -> None:
    payload = {
        "id": "chatcmpl-123",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "This is a DeepSeek answer."},
            }
        ],
    }

    assert parse_deepseek_response(payload) == "This is a DeepSeek answer."
