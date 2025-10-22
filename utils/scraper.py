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


def write_jobs_to_csv(jobs, csv_path, overwrite=False):
    """Write a list of job dicts to a CSV file with columns id,title,description,location.
    If overwrite is False, append to existing file and continue id numbering.
    """
    import csv
    import os

    file_exists = os.path.exists(csv_path)
    start_id = 1
    if file_exists and not overwrite:
        # find max existing id
        try:
            with open(csv_path, newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                ids = [int(row['id']) for row in reader if row.get('id')]
                if ids:
                    start_id = max(ids) + 1
        except Exception:
            start_id = 1

    mode = 'w' if overwrite or not file_exists else 'a'
    with open(csv_path, mode, newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['id', 'title', 'description', 'location'])
        if mode == 'w':
            writer.writeheader()
        for i, job in enumerate(jobs, start=start_id):
            writer.writerow({
                'id': i,
                'title': job.get('title', ''),
                'description': job.get('description', ''),
                'location': job.get('location', ''),
            })


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Scrape jobs from a URL and save to sample_jobs.csv')
    parser.add_argument('url', help='URL to scrape')
    parser.add_argument('--limit', type=int, default=10, help='Max number of jobs to scrape')
    parser.add_argument('--out', default=None, help='Output CSV path (default: project sample_jobs.csv)')
    parser.add_argument('--overwrite', action='store_true', help='Overwrite existing CSV')
    args = parser.parse_args()

    out = args.out
    if out is None:
        import os
        out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'sample_jobs.csv')

    jobs = scrape_jobs_from_url(args.url, limit=args.limit)
    if not jobs:
        print('No jobs found or failed to scrape')
    else:
        write_jobs_to_csv(jobs, out, overwrite=args.overwrite)
        print(f'Wrote {len(jobs)} jobs to {out}')
