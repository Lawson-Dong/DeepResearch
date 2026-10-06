import json
import re
from urllib.parse import quote, unquote

import arxiv
import requests

from llm import call_llm


def search_arxiv(query: str, max_results: int = 3) -> str:
    """Search arXiv for papers matching the query and return a formatted string of results."""
    try:
        client = arxiv.Client()
        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.Relevance,
        )

        results = []
        for paper in client.results(search):
            authors = ", ".join(a.name for a in paper.authors[:3])
            if len(paper.authors) > 3:
                authors += " et al."
            summary = paper.summary.replace("\n", " ")[:500]
            results.append(
                f"Title: {paper.title}\n"
                f"Authors: {authors}\n"
                f"Published: {paper.published.strftime('%Y-%m-%d')}\n"
                f"Summary: {summary}...\n"
                f"URL: {paper.entry_id}"
            )

        if not results:
            return "No arXiv papers found for this query."

        return "\n\n---\n\n".join(results)

    except Exception as e:
        return f"arXiv search failed (possibly no internet or rate limit): {e}"


def generate_search_keywords(proposal: dict, n: int = 3) -> list:
    """Generate short arXiv search queries from the current proposal."""
    prompt = f"""Based on this research proposal, generate {n} short arXiv search queries (2-5 words each).
Rules:
- Each query should target a different aspect (problem, method, evaluation, related field).
- Output only the queries, one per line. No numbering, no quotes, no extra text.

Title: {proposal.get('title', '')}
Problem: {proposal.get('problem', '')}
Method: {proposal.get('method', '')[:600]}
"""
    text = call_llm(
        "You are a research librarian who writes concise arXiv search queries.",
        prompt,
        temperature=0.3,
    )

    keywords = []
    for line in text.strip().split("\n"):
        clean = line.strip().lstrip("-*•0123456789. )\t").strip().strip('"').strip("'")
        if clean and len(clean) > 3:
            keywords.append(clean)
    return keywords[:n]


def search_arxiv_multi(keywords: list, per_query_keep: int = 2, candidate_pool: int = 15) -> str:
    """Search arXiv for each keyword, keep CS papers, and deduplicate results."""
    seen_ids = set()
    merged = []

    for keyword in keywords:
        try:
            client = arxiv.Client()
            search = arxiv.Search(
                query=keyword,
                max_results=candidate_pool,
                sort_by=arxiv.SortCriterion.Relevance,
            )
            kept = 0
            for paper in client.results(search):
                if not any(
                    category.startswith(("cs.CV", "cs.LG", "cs.AI", "cs.CL"))
                    for category in paper.categories
                ):
                    continue
                if paper.entry_id in seen_ids:
                    continue
                seen_ids.add(paper.entry_id)

                authors = ", ".join(a.name for a in paper.authors[:3])
                if len(paper.authors) > 3:
                    authors += " et al."
                summary = paper.summary.replace("\n", " ")[:500]
                merged.append(
                    f"Title: {paper.title}\n"
                    f"Authors: {authors}\n"
                    f"Published: {paper.published.strftime('%Y-%m-%d')}\n"
                    f"Summary: {summary}...\n"
                    f"URL: {paper.entry_id}"
                )
                kept += 1
                if kept >= per_query_keep:
                    break
        except Exception as e:
            merged.append(f"[Search failed for '{keyword}': {e}]")

    if not merged:
        return "No arXiv papers found for any of the generated keywords."

    return "\n\n---\n\n".join(merged)


class ArxivSearcher:
    """Configurable wrapper around the existing arXiv search helpers."""

    def __init__(self, candidate_pool: int = 15, per_query_keep: int = 2):
        self.candidate_pool = candidate_pool
        self.per_query_keep = per_query_keep

    def generate_keywords(self, proposal: dict, n: int = 3) -> list:
        return generate_search_keywords(proposal, n=n)

    def search(self, keywords: list) -> str:
        return search_arxiv_multi(
            keywords,
            per_query_keep=self.per_query_keep,
            candidate_pool=self.candidate_pool,
        )


class GitHubRepo:
    """Fetch a single file from a public GitHub repository."""

    @staticmethod
    def parse_url(url: str) -> dict:
        cleaned_url = url.rstrip("/").split("?")[0].split("#")[0]
        match = re.fullmatch(
            r"https?://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.+)",
            cleaned_url,
            flags=re.IGNORECASE,
        )
        if not match:
            raise ValueError(f"Expected a GitHub /blob/ file URL: {cleaned_url}")
        owner, repo, branch, path = (unquote(part) for part in match.groups())
        return {"owner": owner, "repo": repo, "branch": branch, "path": path.strip("/")}

    def _fetch_file(self, owner: str, repo: str, branch: str, path: str) -> str:
        url = (
            f"https://raw.githubusercontent.com/{quote(owner)}/{quote(repo)}"
            f"/{quote(branch, safe='')}/{quote(path, safe='/')}"
        )
        response = requests.get(url, timeout=20)
        response.raise_for_status()
        return response.text

    @staticmethod
    def _extract_notebook(raw_json: str, max_chars: int = 20000) -> str:
        """Convert notebook JSON into readable markdown and code cells."""
        try:
            notebook = json.loads(raw_json)
        except json.JSONDecodeError:
            return raw_json[:max_chars]

        parts = []
        for index, cell in enumerate(notebook.get("cells", [])):
            cell_type = cell.get("cell_type", "")
            source = cell.get("source", [])
            if isinstance(source, list):
                source = "".join(source)
            if not isinstance(source, str) or not source.strip():
                continue
            if cell_type == "markdown":
                parts.append(f"### [Markdown cell {index}]\n{source}")
            elif cell_type == "code":
                parts.append(f"### [Code cell {index}]\n```python\n{source}\n```")

        text = "\n\n".join(parts)
        if len(text) > max_chars:
            text = text[:max_chars] + f"\n... [truncated, total {len(text)} chars]"
        return text

    def fetch(self, url: str, max_chars: int = 20000) -> str:
        """Fetch one file, extracting cells when the file is a notebook."""
        try:
            parsed = self.parse_url(url)
        except ValueError as e:
            return f"[GitHub URL parse error: {e}]"

        try:
            content = self._fetch_file(
                parsed["owner"],
                parsed["repo"],
                parsed["branch"],
                parsed["path"],
            )
        except requests.RequestException as e:
            return f"[GitHub file fetch error: {e}]"

        if parsed["path"].lower().endswith(".ipynb"):
            content = self._extract_notebook(content, max_chars=max_chars)
        elif len(content) > max_chars:
            content = content[:max_chars] + f"\n... [truncated, total {len(content)} chars]"

        return (
            f"# GitHub file: {parsed['owner']}/{parsed['repo']} "
            f"(branch: {parsed['branch']})\n"
            f"## Path: {parsed['path']}\n\n"
            f"{content}"
        )
