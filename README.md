# DeepResearch

**Open infrastructure for AI-assisted research and learning through an interactive, evidence-aware debate.**

[GitHub repository](https://github.com/Lawson-Dong/DeepResearch) · [Lawson Dong's personal website](https://lawson-dong.vercel.app/)

DeepResearch is an open-source command-line prototype powered by DeepSeek with two selectable modes: **research debate**, which develops a feasible research proposal, and **knowledge debate**, which clarifies a topic and produces a structured note rather than a proposal. Both modes use four prompted roles: **PROPOSER**, **CRITIC**, **EVALUATOR**, and **PAPER_READER**.

The user can review each revision, add instructions, and decide when to stop. These roles are separate calls to the same model.

## Motivation

Developing a research plan or understanding a difficult topic involves more than generating an answer. It requires finding relevant evidence, questioning assumptions, clarifying concepts, responding to criticism, and recording how an explanation improves.

DeepResearch brings those steps into an explicit workflow that a researcher can inspect and steer. Its longer-term goal is to support end-to-end research agents: connecting proposal refinement to experiment design, execution, evaluation, and reproducible reporting. The current implementation covers the planning and revision stage.

## Infrastructure and technical stack

The infrastructure is a small Python orchestration layer around model calls, retrieval tools, human feedback, and JSON records. Prompts define the roles; Python controls their execution order, validates evaluator scores, updates both adaptive behavior settings, and writes the logs.

| Component | Implementation |
| --- | --- |
| Runtime and interface | Python 3.10+ and an interactive command-line interface. |
| Model access | DeepSeek `deepseek-chat` through the OpenAI-compatible Python SDK. |
| Literature retrieval | The `arxiv` package; locally generated search queries, category filtering, and deduplication. |
| Code context | `requests` retrieves one public GitHub file; notebook markdown and code cells are extracted. |
| Local configuration | `python-dotenv` loads the API key from a local environment file. |
| Orchestration and records | Four model calls per round, adaptive proposer defense and critic rigor, human feedback, and per-round JSON logs. |

## Implemented capabilities

- In research mode, convert an idea into a structured proposal with a method, feasibility assessment, risks, and questions.
- In knowledge mode, debate the accuracy and clarity of a topic and produce a structured note with key claims, distinctions, sources, and uncertainties.
- Retrieve arXiv references for each revision round.
- Ground the discussion in a linked public script or notebook when one is provided.
- Run a four-agent debate with adaptive PROPOSER defense and CRITIC rigor.
- Retrieve and summarize one relevant arXiv paper per round; share the summary with PROPOSER and CRITIC in the following round.
- Accept human instructions between rounds and support explicit finalization.
- Record proposals or notes before and after revision, critique, evaluation, paper-reading results, reference context, and feedback.

## Contributors wanted

We welcome people interested in research agents, open-source infrastructure, and AI-assisted science. Useful next steps include:

- **Experiment execution:** connect proposals to explicit experiment specifications and controlled Python execution.
- **Evaluation and reproducibility:** introduce baselines, meaningful evaluation criteria, recorded configurations, and traceable experiment artifacts.
- **Retrieval and evidence:** improve reference relevance, citation verification, and support for more research domains.
- **Workflow reliability:** add complete response schemas, recovery, session resumption, and mocked integration tests.
- **Developer experience:** improve configuration, model-provider support, and interfaces for reviewing revisions.

These are contribution directions rather than completed features. Start by trying the current workflow, reporting a reproducible issue, or proposing a focused change. See [CONTRIBUTING.md](CONTRIBUTING.md).

## How it works

1. Choose research or knowledge debate. Enter the research idea or knowledge topic; either mode can optionally fetch the single public GitHub file linked in the input.
2. At the start of each round, derive up to three arXiv search queries locally from the input (round 1) or current proposal/note (later rounds), then retrieve relevant papers.
3. Call PROPOSER to create proposal v0 or knowledge note v0 in round 1, and revise that artifact in later rounds.
4. Call CRITIC to review the proposal or note.
5. Call EVALUATOR with the original input, current artifact, CRITIC feedback, and the same GitHub and arXiv context. It scores the artifact and recommends the next round's PROPOSER defense rate and CRITIC strictness.
6. Call PAPER_READER to search using this round's artifact and CRITIC's needs, retrieve at most one paper's full text, and produce an evidence-grounded summary.
7. Print the feedback and artifact, save a JSON round log, and wait for your input.

PROPOSER, CRITIC, and EVALUATOR receive the original input and available source context: the linked GitHub file and that round's arXiv results. In research mode, their roles focus on the research proposal. In knowledge mode, they focus on conceptual accuracy and the evolving note; they do not ask for experiments, novelty, or project feasibility. PAPER_READER receives the current proposal or note, CRITIC's feedback, arXiv search results, and retrieved paper text. Its summaries are passed to PROPOSER and CRITIC starting in the next round; PAPER_READER does not take part in the debate, and EVALUATOR does not receive its summaries. Each round makes exactly four DeepSeek API calls, in this order: PROPOSER, CRITIC, EVALUATOR, PAPER_READER. arXiv query generation is local and does not make an LLM call.

Knowledge mode produces versioned notes with a central question, current understanding, key claims and their sources, important distinctions, uncertainties, questions, and a changelog. The final note is saved as `final_note.json`; research mode continues to save `final.json`.

The debate's arXiv search currently keeps papers categorized under `cs.CV`, `cs.LG`, `cs.AI`, or `cs.CL`, with up to two papers per query from a candidate pool of 15. PAPER_READER performs a separate search based on the proposal and CRITIC's feedback, then retrieves at most one candidate's full text. It prefers arXiv HTML and falls back to the TeX source, including referenced `\input` and `\include` files when available. The text passed to PAPER_READER is capped at 24,000 characters; truncation and retrieval failures are reported in its input and round log. Other research fields may need changes to the category filter in `tools.py`.

## Quick start

Use Python **3.10 or later**, an internet connection, and a DeepSeek API key.

```bash
git clone https://github.com/Lawson-Dong/DeepResearch.git
cd DeepResearch
python -m venv .venv
```

Activate the virtual environment:

```bash
# macOS / Linux
source .venv/bin/activate
```

```powershell
# Windows PowerShell
.venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env` and replace the placeholder with your key:

```dotenv
DEEPSEEK_API_KEY=your_deepseek_api_key_here
```

Then run:

```bash
python main.py
```

For a research debate, enter:

> I want to study how local label entropy changes across layers of a pretrained ResNet-18 using a small cat/dog dataset. Help me design a feasible pilot with appropriate controls.

For a knowledge debate, choose option 2 and enter a topic or question, for example:

> Explain the difference between correlation and causation, when confounding occurs, and how randomized experiments address it.

After each round:

| Input | Behavior |
| --- | --- |
| Enter | Continue to the next round. |
| Any other text | Use it as an instruction for the next round. |
| `ok`, `done`, `accept`, `stop`, `q`, or `quit` | Save the current artifact (`final.json` in research mode or `final_note.json` in knowledge mode) and stop. |

End-of-input also finalizes the current revision. The default limit is five rounds, set by `run(idea, max_rounds=5, mode=...)` in `main.py`. The interactive entry point defaults to research mode when you press Enter at the mode prompt; choose option 2 for knowledge mode.

## Reviewing a GitHub file

Include a public GitHub **file** URL in the initial idea:

```text
Please review this script and help improve its experimental design:
https://github.com/OWNER/REPOSITORY/blob/main/path/to/script.py
```

Only the first GitHub URL is used. The current fetcher accepts `/blob/` URLs with a single path segment for the branch or ref; repository home pages, `/tree/` directories, raw URLs, private files, and branch names containing slashes are not supported. An invalid URL or failed fetch stops the run before proposal generation.

For notebooks, the fetcher extracts markdown and code cells with zero-based cell indices; it does not include cell outputs. File context is capped at 20,000 characters, so long files may be truncated.

## Configuration

Edit `config.py` to change the current settings:

| Setting | Default | Purpose |
| --- | --- | --- |
| `MODEL` | `deepseek-chat` | Model used for all four agents. arXiv search queries are generated locally. |
| `DEFENSE_LEVEL` | `0.3` | Initial PROPOSER defense rate. EVALUATOR recommends the rate for each following round. Intended range: 0–1. |
| `CRITIC_STRICTNESS` | `0.4` | Initial critic rigor. EVALUATOR recommends subsequent values in 0–1. |
| `GITHUB_REPO_URL` | A project directory URL | Legacy setting; currently unused. Put a supported file URL in the idea instead. |

The client uses `DEEPSEEK_API_KEY` from the environment or `.env`, with `https://api.deepseek.com` as its base URL. `llm.py` sets an 8,000-token output limit per call. A five-round run makes up to 20 model calls; API usage is billed by the provider.

## Output and included examples

Each run creates a `debate_{mode}_YYYYMMDD_HHMMSS/` directory in the working directory. Each `round_XX.json` records:

- Proposals or knowledge notes before and after revision, plus the critic's feedback.
- Proposer defense rate and critic strictness used and recommended for the next round.
- Evaluator scores and reasoning.
- The PAPER_READER summary prepared for the next round, the summary used in this round, search keywords, and full-text retrieval status.
- Retrieved arXiv context, GitHub context length, and the feedback used for that round.

The final artifact is written when the user explicitly finalizes or input ends. Reaching the round limit returns the last proposal or note without writing a separate final file; the last `round_XX.json` still contains it in `after` (research mode) or `note_after` (knowledge mode).

The two supplied example logs are preserved in their original directories:

- [LLE pilot, round 1](debate_20261005_213256/round_01.json)
- [Architectural-boundary permutation study, round 1](debate_20261005_214831/round_01.json)

Both are single-round records, not complete finalized sessions. New run directories are ignored by Git by default; intentionally add a reviewed example with `git add -f debate_YYYYMMDD_HHMMSS/round_01.json`.

## Repository layout

| File | Responsibility |
| --- | --- |
| `main.py` | Interactive mode selection, entry point, and round limit. |
| `orchestrator.py` | Four-agent round loop, evaluator validation, paper retrieval, user feedback, and log persistence. |
| `agents.py` | Role input builders, behavior instructions, and terminal rendering. |
| `prompts.py` | Four role prompts, reference instructions, and JSON response schemas. |
| `llm.py` | DeepSeek calls and JSON extraction. |
| `tools.py` | arXiv search and full-text retrieval, plus public GitHub file / notebook extraction. |
| `config.py` | API client and debate settings. |
| `requirements.txt` | Direct dependency versions from the supplied environment. |

## Current limitations

This is a research planning prototype. Model scores are subjective assessments, and references and methodological claims need human verification. PAPER_READER summarizes retrieved text, which may be truncated or unavailable for some papers, and does not independently verify that a cited source supports a claim. The application does not execute experiments or edit the reviewed repository.

Model output must parse as JSON. Evaluator scores and reasoning are validated, but proposer and critic responses do not have complete schema validation. Network failures and malformed responses can interrupt a run; there is no resume mechanism.

## Contributing and license

See [CONTRIBUTING.md](CONTRIBUTING.md) for maintenance conventions. The project is released under the [MIT License](LICENSE).
