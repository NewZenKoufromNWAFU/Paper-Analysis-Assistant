"""Download PDFs from arXiv."""
import os
import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import PAPERS_DIR

def download_arxiv_pdf(arxiv_id: str) -> str | None:
    if not arxiv_id:
        return None
    safe_name = arxiv_id.replace("/", "_")
    filepath = os.path.join(PAPERS_DIR, f"{safe_name}.pdf")
    if os.path.exists(filepath):
        return filepath
    url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    try:
        resp = requests.get(url, timeout=60, stream=True)
        resp.raise_for_status()
        with open(filepath, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        time.sleep(0.5)
        return filepath
    except Exception as e:
        print(f"Download failed for {arxiv_id}: {e}")
        return None

def batch_download(papers: list, max_workers: int = 5) -> list:
    downloaded = []
    tasks = [(p.get("arxiv_id",""), p) for p in papers if p.get("arxiv_id")]
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(download_arxiv_pdf, aid): p for aid, p in tasks}
        for future in as_completed(futures):
            p = futures[future]
            try:
                path = future.result()
                if path:
                    p["local_path"] = path
                    downloaded.append(p)
            except Exception as e:
                print(f"Download error: {e}")
    return downloaded
