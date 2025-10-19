import os


def parse_resume(path: str) -> str:
    """Extract plain text from a resume file. Supports .txt and .pdf.
    Raises RuntimeError if the format is unsupported or parsing fails.
    """
    path = os.path.abspath(path)
    if path.lower().endswith(".txt"):
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    if path.lower().endswith(".pdf"):
        try:
            from PyPDF2 import PdfReader
        except Exception as e:
            raise RuntimeError("PyPDF2 is required to parse PDF resumes") from e
        text_parts = []
        reader = PdfReader(path)
        for p in reader.pages:
            text_parts.append(p.extract_text() or "")
        return "\n".join(text_parts)
    raise RuntimeError("Unsupported resume format. Please upload a .pdf or .txt file")
