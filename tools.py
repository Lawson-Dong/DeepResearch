import gzip
import io
import json
import posixpath
import re
import tarfile
from html.parser import HTMLParser
from urllib.parse import quote, unquote

import arxiv
import requests


class _PaperHTMLParser(HTMLParser):
    """Extract readable text from arXiv HTML papers."""

    _ignored_tags = {"script", "style", "nav", "header", "footer"}
    _line_break_tags = {"article", "div", "h1", "h2", "h3", "h4", "li", "p", "section"}

    def __init__(self):
        super().__init__()
        self._ignored_depth = 0
        self._parts = []

    def handle_starttag(self, tag, _attrs):
        if tag in self._ignored_tags:
            self._ignored_depth += 1
        elif not self._ignored_depth and tag in self._line_break_tags:
            self._parts.append("\n")
        elif not self._ignored_depth and tag == "img":
            alt_text = next(
                (value for name, value in _attrs if name == "alt" and value),
                None,
            )
            if alt_text:
                self._parts.append(f"\n[Figure: {alt_text}]\n")

    def handle_endtag(self, tag):
        if tag in self._ignored_tags and self._ignored_depth:
            self._ignored_depth -= 1
        elif not self._ignored_depth and tag in self._line_break_tags:
            self._parts.append("\n")

    def handle_data(self, data):
        if not self._ignored_depth:
            self._parts.append(data)

    def get_text(self):
        lines = (" ".join(line.split()) for line in "".join(self._parts).splitlines())
        return "\n".join(line for line in lines if line)


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
    """Create arXiv queries locally without consuming an LLM API call."""
    stop_words = {
        "about", "across", "after", "based", "between", "could", "first",
        "from", "into", "more", "over", "project", "research", "should",
        "study", "that", "their", "there", "these", "this", "through",
        "using", "what", "which", "with",
    }
    if isinstance(proposal, str):
        fields = [proposal]
    else:
        fields = [
            str(proposal.get(field, ""))
            for field in ("title", "problem", "method")
        ]
    keywords = []
    for text in fields:
        text = re.sub(r"https?://\S+", " ", text)
        words = [
            word.lower()
            for word in re.findall(r"[A-Za-z][A-Za-z0-9-]*", text)
            if word.lower() not in stop_words
        ]
        query = " ".join(words[:5])
        if len(words) >= 2 and len(query) > 3 and query not in keywords:
            keywords.append(query)
        if len(keywords) >= n:
            break
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

    max_paper_text_chars = 24000

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

    @staticmethod
    def parse_results(context: str) -> list:
        """Parse the formatted arXiv search output into paper metadata."""
        papers = []
        for block in context.split("\n\n---\n\n"):
            paper = {}
            for line in block.splitlines():
                for field in ("Title", "Authors", "Published", "Summary", "URL"):
                    prefix = f"{field}: "
                    if line.startswith(prefix):
                        paper[field.lower()] = line[len(prefix):]
                        break
            if paper.get("url", "").startswith("https://arxiv.org/abs/"):
                papers.append(paper)
        return papers

    @staticmethod
    def _extract_source_text(content: bytes) -> str:
        """Read the main TeX source from an arXiv source archive."""
        try:
            with tarfile.open(fileobj=io.BytesIO(content), mode="r:*") as archive:
                tex_files = [
                    member for member in archive.getmembers()
                    if member.isfile() and member.name.lower().endswith(".tex")
                ]
                if not tex_files:
                    raise ValueError("The arXiv source archive contains no TeX files.")
                sources = {}
                for member in tex_files:
                    source_file = archive.extractfile(member)
                    if source_file is not None:
                        member_name = posixpath.normpath(member.name.removeprefix("./"))
                        sources[member_name] = source_file.read().decode(
                            "utf-8",
                            errors="replace",
                        )
                if not sources:
                    raise ValueError("Could not read the TeX source files.")
                main_name = max(
                    sources,
                    key=lambda name: (
                        "\\documentclass" in sources[name][:4096],
                        len(sources[name]),
                    ),
                )

                def expand_includes(name, visited):
                    if name in visited:
                        return ""
                    visited.add(name)
                    text = sources[name]

                    def replace_include(match):
                        include_name = posixpath.normpath(
                            posixpath.join(
                                posixpath.dirname(name),
                                match.group(1).strip(),
                            )
                        )
                        candidates = (include_name, include_name + ".tex")
                        for candidate in candidates:
                            if candidate in sources:
                                return expand_includes(candidate, visited)
                        return match.group(0)

                    return re.sub(
                        r"\\(?:input|include)\s*\{([^{}]+)\}",
                        replace_include,
                        text,
                    )

                source = expand_includes(main_name, set())
        except (tarfile.TarError, OSError):
            try:
                source = gzip.decompress(content).decode("utf-8", errors="replace")
            except (OSError, EOFError) as error:
                raise ValueError("The arXiv source was not a readable TeX archive.") from error

        source = re.sub(r"(?m)(?<!\\)%.*$", "", source)
        source = re.sub(r"\\begin\{document\}|\\end\{document\}", "\n", source)
        source = re.sub(r"\\(?:section|subsection|subsubsection|paragraph)\*?\s*\{([^{}]*)\}", r"\n\1\n", source)
        source = re.sub(r"\\(?:cite|citep|citet|ref|label)\*?\s*\{([^{}]*)\}", r" [\1] ", source)
        source = re.sub(r"\\[A-Za-z]+(?:\*?)(?:\[[^\]]*\])?", " ", source)
        source = source.replace("{", " ").replace("}", " ")
        return re.sub(r"[ \t]+\n", "\n", source).strip()

    def fetch_full_text(
        self,
        paper_url: str,
        max_chars: int = max_paper_text_chars,
    ) -> dict:
        """Fetch an arXiv paper as readable HTML text, with TeX source fallback."""
        match = re.fullmatch(
            r"https?://arxiv\.org/abs/([^?#]+)",
            paper_url.strip(),
            flags=re.IGNORECASE,
        )
        if not match:
            return {"url": paper_url, "error": "Not a supported arXiv abstract URL."}

        paper_id = unquote(match.group(1))
        encoded_id = quote(paper_id, safe="/")
        html_error = None
        try:
            response = requests.get(
                f"https://arxiv.org/html/{encoded_id}",
                timeout=30,
            )
            response.raise_for_status()
            parser = _PaperHTMLParser()
            parser.feed(response.text)
            text = parser.get_text()
            has_paper_content = re.search(
                r"<article\b|ltx_document",
                response.text,
                flags=re.IGNORECASE,
            )
            if len(text) >= 300 and has_paper_content:
                return {
                    "url": paper_url,
                    "source": "arXiv HTML",
                    "text": text[:max_chars],
                    "truncated": len(text) > max_chars,
                }
            html_error = "The arXiv HTML page did not contain enough paper text."
        except requests.RequestException as error:
            html_error = str(error)

        try:
            response = requests.get(
                f"https://export.arxiv.org/e-print/{encoded_id}",
                timeout=30,
            )
            response.raise_for_status()
            source = self._extract_source_text(response.content)
            return {
                "url": paper_url,
                "source": "arXiv TeX source",
                "text": source[:max_chars],
                "truncated": len(source) > max_chars,
                "html_fallback_reason": html_error,
            }
        except (requests.RequestException, ValueError) as error:
            return {
                "url": paper_url,
                "error": f"Could not retrieve HTML ({html_error}) or TeX source ({error}).",
            }


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
