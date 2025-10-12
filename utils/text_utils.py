import re

def clean_text(s: str) -> str:
    if not s:
        return ""
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def simple_match_score(text: str, query: str) -> float:
    """Return a simple score based on keyword overlap between text and query.
    This is a toy function for quick prototyping.
    """
    t = set(clean_text(text).split())
    q = set(clean_text(query).split())
    if not q:
        return 0.0
    common = t.intersection(q)
    return len(common) / len(q)
