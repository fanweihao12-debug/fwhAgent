import asyncio
from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile

from app.knowledge_ingest_service import (
    get_pdf_upload_max_size_bytes,
    read_upload_file_with_limit,
    validate_pdf_upload_metadata,
)


def test_validate_pdf_upload_metadata_accepts_pdf_file() -> None:
    normalized_name = validate_pdf_upload_metadata("manual.pdf", "application/pdf")
    assert normalized_name == "manual.pdf"


def test_validate_pdf_upload_metadata_rejects_non_pdf_extension() -> None:
    with pytest.raises(HTTPException) as exc_info:
        validate_pdf_upload_metadata("manual.txt", "text/plain")
    assert exc_info.value.status_code == 400


def test_get_pdf_upload_max_size_bytes_defaults_to_20mb(monkeypatch) -> None:
    monkeypatch.delenv("PDF_UPLOAD_MAX_SIZE_MB", raising=False)
    assert get_pdf_upload_max_size_bytes() == 20 * 1024 * 1024


def test_read_upload_file_with_limit_rejects_oversized_payload() -> None:
    upload_file = UploadFile(filename="big.pdf", file=BytesIO(b"a" * 7))
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(read_upload_file_with_limit(upload_file=upload_file, max_size_bytes=6))
    assert exc_info.value.status_code == 413
