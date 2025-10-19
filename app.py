import os
from flask import Flask, jsonify, request, render_template, redirect, url_for
from werkzeug.utils import secure_filename
import pandas as pd
from utils.text_utils import clean_text, simple_match_score
from utils.resume_parser import parse_resume

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

@app.route("/jobs", methods=["GET"])
def list_jobs():
    """Return all jobs (simple JSON)."""
    return jsonify(jobs_df.to_dict(orient="records"))


@app.route("/", methods=["GET"])
def index():
    """Render main page with upload form."""
    return render_template("index.html")


def score_jobs_from_resume_text(resume_text, top=5):
    """Return top job matches given resume text (basic keyword overlap).
    Returns list of dicts with id, title, location, score.
    """
    results = []
    for _, row in jobs_df.iterrows():
        title = row.get("title", "") or ""
        desc = row.get("description", "") or ""
        # score both title and description
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
    matches = score_jobs_from_resume_text(text, top=top)
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

    results = []
    for _, row in jobs_df.iterrows():
        score = simple_match_score(row.get("description", ""), q)
        results.append({"id": row.get("id"), "title": row.get("title"), "location": row.get("location"), "score": score})

    results = sorted(results, key=lambda r: r["score"], reverse=True)[:top]
    return jsonify(results)

if __name__ == "__main__":
    # Allow overriding the port with the PORT environment variable.
    # This is helpful on systems where port 5000 may be bound by other services
    # (for example macOS AirPlay/AirTunes can occupy that port). Use a free
    # port like 5001 if you encounter a conflict.
    port = int(os.environ.get("PORT", 5000))
    app.run(port=port, debug=True)
