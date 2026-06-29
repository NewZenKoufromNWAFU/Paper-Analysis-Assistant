from state import AgentState
from tools.paper_downloader import batch_download
from config import DOWNLOAD_PAPER_COUNT

def downloader_agent(state: AgentState) -> AgentState:
    papers = state.get("search_results", [])
    papers_with_id = [pp for pp in papers if pp.get("arxiv_id")][:DOWNLOAD_PAPER_COUNT]
    if not papers_with_id:
        state["downloaded_papers"] = []
        state["status_message"] = "[Downloader] No papers with arXiv ID found"
        return state
    downloaded = batch_download(papers_with_id, max_workers=5)
    state["downloaded_papers"] = downloaded
    state["status_message"] = f"[Downloader] Downloaded {len(downloaded)}/{len(papers_with_id)} PDFs"
    return state
