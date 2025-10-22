import os
from flask import Flask, jsonify, request, render_template, redirect, url_for
from werkzeug.utils import secure_filename
import pandas as pd
from utils.text_utils import clean_text, simple_match_score
from utils.resume_parser import parse_resume
# optional embeddings integration
try:
    from utils.embeddings import ensure_job_embeddings, rank_jobs_by_embedding
    HF_AVAILABLE = True
except Exception:
    HF_AVAILABLE = False

app = Flask(__name__)

# Load sample jobs from a path relative to this file so the app works
# regardless of current working directory when launched.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JOBS_CSV = os.path.join(BASE_DIR, "sample_jobs.csv")
try:
    jobs_df = pd.read_csv(JOBS_CSV)
except Exception as e:
    # Print a warning so users can see why the dataset is missing.
    print(f"Warning: failed to read {JOBS_CSV}: {e}")
    jobs_df = pd.DataFrame(columns=["id", "title", "description", "location"]) 

# If Hugging Face key is present, precompute job embeddings (cached) so ranking by
# embeddings can be used on uploads. If anything fails, we'll simply fall back to
# the existing keyword scorer.
JOB_EMB_CACHE = {}
EMBEDDING_MODEL = os.environ.get("HF_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
if HF_AVAILABLE and os.environ.get("HUGGINGFACE_API_KEY"):
    try:
        JOB_EMB_CACHE = ensure_job_embeddings(jobs_df, model=EMBEDDING_MODEL)
        print(f"Loaded job embeddings for {len(JOB_EMB_CACHE)} jobs using model {EMBEDDING_MODEL}")
    except Exception as e:
        print(f"Warning: failed to prepare job embeddings: {e}")
        JOB_EMB_CACHE = {}

@app.route("/jobs", methods=["GET"])
def list_jobs():
    """Return all jobs (simple JSON)."""
    return jsonify(jobs_df.to_dict(orient="records"))


@app.route("/", methods=["GET"])
def index():
    """Render main page with upload form."""
    return render_template("index.html", HUGGINGFACE_AVAILABLE=(HF_AVAILABLE and bool(os.environ.get("HUGGINGFACE_API_KEY"))), HF_MODEL=EMBEDDING_MODEL)


def score_jobs_from_resume_text(resume_text, top=5):
    """Return top job matches given resume text (basic keyword overlap).
    Returns list of dicts with id, title, location, score.
    """
    results = []
    for _, row in jobs_df.iterrows():
        title = row.get("title", "") or ""
        desc = row.get("description", "") or ""
        # score both title and description using adjustable weights (defaults match prior behavior)
        score_title = simple_match_score(title, resume_text)
        score_desc = simple_match_score(desc, resume_text)
        score = 0.4 * score_title + 0.6 * score_desc
        results.append({
            "id": row.get("id"),
            "title": title,
            "location": row.get("location"),
            "score": round(score, 4),
        })
    results = sorted(results, key=lambda r: r["score"], reverse=True)[:top]
    return results


def _sanitize_and_normalize_weights(title_w, desc_w):
    """Clamp title and description weights to [0,1] and normalize so they sum to 1.
    If both are zero or invalid, return defaults (0.4, 0.6).
    """
    try:
        t = float(title_w)
    except Exception:
        t = None
    try:
        d = float(desc_w)
    except Exception:
        d = None
    if t is None and d is None:
        return 0.4, 0.6
    if t is None:
        t = 0.0
    if d is None:
        d = 0.0
    # clamp
    t = max(0.0, min(1.0, t))
    d = max(0.0, min(1.0, d))
    s = t + d
    if s == 0:
        return 0.4, 0.6
    return t / s, d / s


def _sanitize_alpha(alpha):
    try:
        a = float(alpha)
    except Exception:
        return 0.5
    # clamp to [0,1]
    return max(0.0, min(1.0, a))


@app.route("/upload", methods=["POST"])
def upload_resume():
    """Handle resume upload (expects form field 'resume')."""
    if "resume" not in request.files:
        return redirect(url_for("index"))
    f = request.files["resume"]
    if f.filename == "":
        return redirect(url_for("index"))

    filename = secure_filename(f.filename)
    upload_dir = os.path.join(BASE_DIR, "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    filepath = os.path.join(upload_dir, filename)
    f.save(filepath)

    try:
        text = parse_resume(filepath)
    except Exception as e:
        # parsing failed: render index with error message
        return render_template("index.html", error=str(e))

    # compute top matches
    top = int(request.form.get("top", 5))
    # ranking method: 'keywords', 'embeddings', or 'hybrid'
    method = request.form.get("method", "auto")
    # weights for title/description (used by keyword scoring)
    title_w_raw = request.form.get("title_weight", 0.4)
    desc_w_raw = request.form.get("description_weight", 0.6)
    title_w, desc_w = _sanitize_and_normalize_weights(title_w_raw, desc_w_raw)
    # hybrid alpha: 0.0 -> keywords only, 1.0 -> embeddings only
    hybrid_alpha = _sanitize_alpha(request.form.get("hybrid_alpha", 0.5))
    # sanitize method value
    method_raw = request.form.get("method", "auto")
    allowed_methods = {"auto", "keywords", "embeddings", "hybrid"}
    method = method_raw if method_raw in allowed_methods else "auto"

    matches = []

    def keyword_scores(res_text, topn=5):
        results = []
        for _, row in jobs_df.iterrows():
            title = row.get("title", "") or ""
            desc = row.get("description", "") or ""
            score_title = simple_match_score(title, res_text)
            score_desc = simple_match_score(desc, res_text)
            score = title_w * score_title + desc_w * score_desc
            results.append({
                "id": row.get("id"),
                "title": title,
                "location": row.get("location"),
                "score": score,
            })
        return sorted(results, key=lambda r: r["score"], reverse=True)[:topn]

    # Determine actual mode: if method == auto, prefer embeddings when available
    if method == "auto":
        if HF_AVAILABLE and JOB_EMB_CACHE:
            actual = "embeddings"
        else:
            actual = "keywords"
    else:
        actual = method

    if actual == "embeddings":
        if HF_AVAILABLE and JOB_EMB_CACHE:
            try:
                matches = rank_jobs_by_embedding(text, jobs_df, JOB_EMB_CACHE, top=top, model=EMBEDDING_MODEL)
                for m in matches:
                    m["score"] = round(m.get("score", 0.0), 4)
            except Exception as e:
                print(f"Warning: embedding-based ranking failed: {e}")
                matches = keyword_scores(text, top)
        else:
            matches = keyword_scores(text, top)
    elif actual == "hybrid":
        # compute both and combine
        kw = keyword_scores(text, topn=len(jobs_df))
        emb = []
        if HF_AVAILABLE and JOB_EMB_CACHE:
            try:
                emb = rank_jobs_by_embedding(text, jobs_df, JOB_EMB_CACHE, top=len(jobs_df), model=EMBEDDING_MODEL)
            except Exception as e:
                print(f"Warning: embedding ranking failed for hybrid mode: {e}")
                emb = []
        # map id -> score
        kw_map = {str(d["id"]): d["score"] for d in kw}
        emb_map = {str(d["id"]): d["score"] for d in emb}
        combined = []
        for _, row in jobs_df.iterrows():
            jid = str(row.get("id"))
            kw_s = kw_map.get(jid, 0.0)
            emb_s = emb_map.get(jid, 0.0)
            score = (1 - hybrid_alpha) * kw_s + hybrid_alpha * emb_s
            combined.append({
                "id": row.get("id"),
                "title": row.get("title"),
                "location": row.get("location"),
                "score": score,
            })
        matches = sorted(combined, key=lambda r: r["score"], reverse=True)[:top]
        for m in matches:
            m["score"] = round(m.get("score", 0.0), 4)
    else:
        # keywords
        matches = keyword_scores(text, top)
        for m in matches:
            m["score"] = round(m.get("score", 0.0), 4)
    return render_template("results.html", matches=matches, filename=filename)

@app.route("/match", methods=["GET"])
def match_jobs():
    """Return jobs matched to a query string via a simple keyword score.
    Query params:
      - q: the user query (required)
      - top: number of results to return (optional, default 5)
    """
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "missing query parameter 'q'"}), 400
    top = int(request.args.get("top", 5))

    # Optional weights for title/description passed as query params. Server-side
    # sanitize and normalize so they sum to 1 and are clamped to [0,1]. This
    # makes the endpoint robust to clients that don't normalize.
    title_w_raw = request.args.get("title_weight", None)
    desc_w_raw = request.args.get("description_weight", None)
    title_w, desc_w = _sanitize_and_normalize_weights(title_w_raw, desc_w_raw)

    results = []
    for _, row in jobs_df.iterrows():
        title = row.get("title", "") or ""
        desc = row.get("description", "") or ""
        score_title = simple_match_score(title, q)
        score_desc = simple_match_score(desc, q)
        score = title_w * score_title + desc_w * score_desc
        results.append({"id": row.get("id"), "title": row.get("title"), "location": row.get("location"), "score": round(score, 4)})

    results = sorted(results, key=lambda r: r["score"], reverse=True)[:top]
    return jsonify(results)

if __name__ == "__main__":
    # Allow overriding the port with the PORT environment variable.
    # This is helpful on systems where port 5000 may be bound by other services
    # (for example macOS AirPlay/AirTunes can occupy that port). Use a free
    # port like 5001 if you encounter a conflict.
    port = int(os.environ.get("PORT", 5000))
    app.run(port=port, debug=True)
