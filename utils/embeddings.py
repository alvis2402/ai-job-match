import os
import json
import time
import math
from typing import Dict, List, Any

import requests


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _get_api_key() -> str:
    key = os.environ.get("HUGGINGFACE_API_KEY")
    if not key:
        raise RuntimeError("HUGGINGFACE_API_KEY environment variable is not set")
    return key


def _cache_path_for_model(model: str) -> str:
    safe = model.replace("/", "__").replace(":", "_")
    return os.path.join(BASE_DIR, f"embeddings_cache_{safe}.json")


def _call_hf_model(text: str, model: str) -> List[float]:
    """Call Hugging Face inference API to obtain an embedding vector for `text`.
    Uses the /models/{model} endpoint. Returns a flat list of floats.
    """
    key = _get_api_key()
    url = f"https://api-inference.huggingface.co/models/{model}"
    headers = {"Authorization": f"Bearer {key}"}
    payload = {"inputs": text}
    # Some models take longer; allow a reasonable timeout
    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    # Responses can be a nested list (list of token vectors) or a flat vector.
    if isinstance(data, list) and data and isinstance(data[0], list):
        # Average token vectors to get a sentence vector
        # data is list[list[float]]
        vec_len = len(data[0])
        agg = [0.0] * vec_len
        count = 0
        for item in data:
            if isinstance(item, list):
                for i, v in enumerate(item):
                    agg[i] += float(v)
                count += 1
        if count:
            return [x / count for x in agg]
        # fallback: flatten first
        return [float(v) for v in data[0]]
    if isinstance(data, list) and all(isinstance(x, (int, float)) for x in data):
        return [float(x) for x in data]
    # Unexpected shape
    raise RuntimeError(f"Unexpected response shape from Hugging Face API: {type(data)}")


def cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b:
        return 0.0
    if len(a) != len(b):
        # can't compute; return 0
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def load_cache(model: str) -> Dict[str, List[float]]:
    path = _cache_path_for_model(model)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_cache(model: str, cache: Dict[str, List[float]]) -> None:
    path = _cache_path_for_model(model)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f)
    try:
        os.replace(tmp, path)
    except Exception:
        # best-effort
        os.remove(tmp)


def ensure_job_embeddings(jobs: Any, model: str = "sentence-transformers/all-MiniLM-L6-v2") -> Dict[str, List[float]]:
    """Ensure embeddings exist for all jobs (pandas DataFrame or iterable of dicts).
    Returns a mapping job_id(str) -> embedding (list of floats).
    """
    cache = load_cache(model)
    # jobs can be a DataFrame or list; iterate rows
    for row in (jobs.to_dict(orient="records") if hasattr(jobs, "to_dict") else jobs):
        jid = str(row.get("id"))
        if not jid:
            continue
        if jid in cache:
            continue
        text = "".join([str(row.get("title", "")), ". ", str(row.get("description", ""))])
        try:
            emb = _call_hf_model(text, model)
            cache[jid] = emb
            # be polite to the API
            time.sleep(0.3)
        except Exception as e:
            # If embedding one job fails, skip it and continue; callers should tolerate missing ids
            print(f"Warning: failed to embed job {jid}: {e}")
    save_cache(model, cache)
    return cache


def embed_text(text: str, model: str = "sentence-transformers/all-MiniLM-L6-v2") -> List[float]:
    return _call_hf_model(text, model)


def rank_jobs_by_embedding(resume_text: str, jobs: Any, job_emb_cache: Dict[str, List[float]], top: int = 5, model: str = "sentence-transformers/all-MiniLM-L6-v2") -> List[Dict[str, Any]]:
    """Return top jobs ranked by cosine similarity between resume_text embedding and job embeddings.
    `jobs` should be iterable of dict-like rows (DataFrame.to_dict records works).
    """
    try:
        resume_emb = embed_text(resume_text, model)
    except Exception as e:
        raise
    rows = jobs.to_dict(orient="records") if hasattr(jobs, "to_dict") else jobs
    results = []
    for row in rows:
        jid = str(row.get("id"))
        job_emb = job_emb_cache.get(jid)
        if not job_emb:
            continue
        score = cosine_similarity(resume_emb, job_emb)
        results.append({
            "id": row.get("id"),
            "title": row.get("title"),
            "location": row.get("location"),
            "score": score,
        })
    results = sorted(results, key=lambda r: r["score"], reverse=True)[:top]
    return results
