import io
import re
from zipfile import BadZipFile
from collections.abc import Mapping
from typing import Any

from pypdf.errors import PdfReadError


class ResumeParseError(Exception):
    """Raised when an uploaded resume cannot be parsed."""


def extract_resume_text(filename: str, content: bytes) -> str:
    extension = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    try:
        if extension == "pdf":
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(content))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        if extension == "docx":
            from docx import Document

            document = Document(io.BytesIO(content))
            return "\n".join(paragraph.text for paragraph in document.paragraphs)
    except (PdfReadError, BadZipFile, ValueError, OSError, KeyError) as exc:
        raise ResumeParseError(f"Could not read this {extension.upper()} resume: {exc}") from exc
    raise ResumeParseError("Please upload a PDF or DOCX resume.")


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-Z][a-zA-Z+#.]{1,}", text.lower())
        if token not in {"with", "from", "this", "that", "have", "will", "your", "their"}
    }


def match_score(resume_text: str, job: Mapping[str, Any]) -> int:
    if not resume_text.strip():
        return 0
    job_text = " ".join(
        str(job.get(field, "")) for field in ("title", "description", "company")
    )
    job_text += " " + " ".join(str(item) for item in job.get("extensions", []))
    resume_tokens = _tokens(resume_text)
    job_tokens = _tokens(job_text)
    if not resume_tokens or not job_tokens:
        return 0
    return round(100 * len(resume_tokens & job_tokens) / len(job_tokens))
