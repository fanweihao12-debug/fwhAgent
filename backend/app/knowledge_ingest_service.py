import os
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

DEFAULT_PDF_UPLOAD_MAX_SIZE_MB = 20
UPLOAD_READ_CHUNK_SIZE_BYTES = 1024 * 1024
PDF_CONTENT_TYPE = "application/pdf"


def get_pdf_upload_max_size_bytes() -> int:
    """Resolve PDF upload limit from env and return bytes."""
    configured_size_mb = int(os.getenv("PDF_UPLOAD_MAX_SIZE_MB", str(DEFAULT_PDF_UPLOAD_MAX_SIZE_MB)))
    if configured_size_mb <= 0:
        raise ValueError("PDF_UPLOAD_MAX_SIZE_MB must be a positive integer.")
    return configured_size_mb * 1024 * 1024


def validate_pdf_upload_metadata(file_name: str | None, content_type: str | None) -> str:
    """Validate file metadata and return normalized filename."""
    if not file_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="PDF filename is required.")

    normalized_name = Path(file_name).name
    if Path(normalized_name).suffix.lower() != ".pdf":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only .pdf files are supported.")

    if content_type and content_type.lower() != PDF_CONTENT_TYPE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file content type. Expected application/pdf.",
        )

    return normalized_name


async def read_upload_file_with_limit(upload_file: UploadFile, max_size_bytes: int) -> bytes:
    """Read upload bytes with hard size limit and reject oversized payloads."""
    collected_chunks: list[bytes] = []
    total_size = 0

    while True:
        chunk = await upload_file.read(UPLOAD_READ_CHUNK_SIZE_BYTES)
        if not chunk:
            break
        total_size += len(chunk)
        if total_size > max_size_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"PDF file size exceeds limit ({max_size_bytes // 1024 // 1024}MB).",
            )
        collected_chunks.append(chunk)

    if total_size == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded PDF file is empty.")

    return b"".join(collected_chunks)
