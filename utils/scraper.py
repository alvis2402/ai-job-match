import requests
from bs4 import BeautifulSoup

def scrape_jobs_from_url(url, limit=10):
    """A minimal placeholder job scraper.
    This function fetches the page and returns a list of job dicts with keys: title, description, location.
    It is intentionally generic — adapt selectors for real sites.
    """
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
    except Exception as e:
        print(f"Failed to fetch {url}: {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    results = []

    # Generic scraping attempt: look for job-like containers
    job_elems = soup.select("article, .job, .listing, .job-card")[:limit]
    for el in job_elems:
        title = el.select_one("h1, h2, .title")
        desc = el.select_one("p, .description, .summary")
        loc = el.select_one(".location, .loc")
        results.append({
            "title": title.get_text(strip=True) if title else "",
            "description": desc.get_text(strip=True) if desc else "",
            "location": loc.get_text(strip=True) if loc else "",
        })
    return results
