# DeepResearch

**Open infrastructure for AI-assisted research, starting with an interactive proposal, critique, and revision loop.**

[GitHub repository](https://github.com/Lawson-Dong/DeepResearch) · [Lawson Dong's personal website](https://lawson-dong.vercel.app/)

DeepResearch is an open-source command-line prototype powered by DeepSeek. Three prompted roles help turn a raw research idea into a small, feasible proposal: an undergraduate **PROPOSER**, a professor **CRITIC**, and an **EVALUATOR** that adjusts the critic's rigor for the next round.

The user can review each revision, add instructions, and decide when to stop. These roles are separate calls to the same model.

## Motivation

Moving from an interesting idea to a testable research plan involves more than generating an answer. It requires finding related work, questioning assumptions, narrowing the scope, responding to criticism, and recording why a proposal changed.

DeepResearch brings those steps into an explicit workflow that a researcher can inspect and steer. Its longer-term goal is to support end-to-end research agents: connecting proposal refinement to experiment design, execution, evaluation, and reproducible reporting. The current implementation covers the planning and revision stage.

## Infrastructure and technical stack

The infrastructure is a small Python orchestration layer around model calls, retrieval tools, human feedback, and JSON records. Prompts define the roles; Python controls their execution order, validates evaluator scores, updates critic strictness, and writes the logs.

| Component | Implementation |
| --- | --- |
| Runtime and interface | Python 3.10+ and an interactive command-line interface. |
| Model access | DeepSeek `deepseek-chat` through the OpenAI-compatible Python SDK. |
| Literature retrieval | The `arxiv` package; generated search queries, category filtering, and deduplication. |
| Code context | `requests` retrieves one public GitHub file; notebook markdown and code cells are extracted. |
| Local configuration | `python-dotenv` loads the API key from a local environment file. |
| Orchestration and records | Explicit role sequencing, adaptive critic rigor, human feedback, and per-round JSON logs. |

## Implemented capabilities

- Convert a research idea into a structured proposal with a method, feasibility assessment, risks, and questions.
- Retrieve arXiv references for each revision round.
- Ground proposal and critique prompts in a linked public script or notebook.
- Run a proposer–critic–evaluator loop with configurable defense level and adaptive critic strictness.
- Accept human instructions between rounds and support explicit finalization.
- Record proposals before and after revision, critique, evaluation, reference context, and feedback.

## Contributors wanted

We welcome people interested in research agents, open-source infrastructure, and AI-assisted science. Useful next steps include:

- **Experiment execution:** connect proposals to explicit experiment specifications and controlled Python execution.
- **Evaluation and reproducibility:** introduce baselines, meaningful evaluation criteria, recorded configurations, and traceable experiment artifacts.
- **Retrieval and evidence:** improve reference relevance, citation verification, and support for more research domains.
- **Workflow reliability:** add complete response schemas, recovery, session resumption, and mocked integration tests.
- **Developer experience:** improve configuration, model-provider support, and interfaces for reviewing revisions.

These are contribution directions rather than completed features. Start by trying the current workflow, reporting a reproducible issue, or proposing a focused change. See [CONTRIBUTING.md](CONTRIBUTING.md).

## How it works

1. Read your research idea and optionally fetch a public GitHub file linked in it.
2. Generate the initial structured proposal.
3. Generate three arXiv search queries, retrieve relevant papers, and deduplicate them.
4. Ask CRITIC to review the proposal, then ask PROPOSER to revise it.
5. Ask EVALUATOR to score the revision and recommend the next round's critic strictness.
6. Print the feedback and revised proposal, save a JSON round log, and wait for your input.

The arXiv search currently keeps papers categorized under `cs.CV`, `cs.LG`, `cs.AI`, or `cs.CL`, with up to two papers per query from a candidate pool of 15. Other research fields may need changes to this filter in `tools.py`.

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

For example, enter:

> I want to study how local label entropy changes across layers of a pretrained ResNet-18 using a small cat/dog dataset. Help me design a feasible pilot with appropriate controls.

After each round:

| Input | Behavior |
| --- | --- |
| Enter | Continue to the next round. |
| Any other text | Use it as an instruction for the next round. |
| `ok`, `done`, `accept`, `stop`, `q`, or `quit` | Save the current revised proposal as `final.json` and stop. |

End-of-input also finalizes the current revision. The default limit is five rounds, set by `run(idea, max_rounds=5)` in `main.py`.

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
| `MODEL` | `deepseek-chat` | Model used for every role and search-query generation. |
| `DEFENSE_LEVEL` | `0.3` | How readily PROPOSER accepts or defends choices during revision. Intended range: 0–1. |
| `CRITIC_STRICTNESS` | `0.4` | Initial critic rigor. EVALUATOR recommends subsequent values in 0–1. |
| `GITHUB_REPO_URL` | A project directory URL | Currently unused by the orchestrator. Put a supported file URL in the idea instead. |

The client uses `DEEPSEEK_API_KEY` from the environment or `.env`, with `https://api.deepseek.com` as its base URL. `llm.py` sets an 8,000-token output limit per call. A complete run uses one initial model call plus four calls per round; API usage is billed by the provider.

## Output and included examples

Each run creates a `debate_YYYYMMDD_HHMMSS/` directory in the working directory. Each `round_XX.json` records:

- Proposals before and after revision, plus the critic's feedback.
- Defense level, strictness used, and next-round strictness.
- Evaluator scores and reasoning.
- Retrieved arXiv context, GitHub context length, and the feedback used for that round.

`final.json` is written when the user explicitly finalizes or input ends. Reaching the round limit returns the last proposal without writing `final.json`; the last `round_XX.json` still contains that proposal in `after`.

The two supplied example logs are preserved in their original directories:

- [LLE pilot, round 1](debate_20261005_213256/round_01.json)
- [Architectural-boundary permutation study, round 1](debate_20261005_214831/round_01.json)

Both are single-round records, not complete finalized sessions. New run directories are ignored by Git by default; intentionally add a reviewed example with `git add -f debate_YYYYMMDD_HHMMSS/round_01.json`.

## Repository layout

| File | Responsibility |
| --- | --- |
| `main.py` | Interactive entry point and round limit. |
| `orchestrator.py` | Debate loop, evaluator validation, user feedback, and log persistence. |
| `agents.py` | Role input builders, behavior instructions, and terminal rendering. |
| `prompts.py` | Role prompts, reference instructions, and JSON response schemas. |
| `llm.py` | DeepSeek calls and JSON extraction. |
| `tools.py` | arXiv retrieval and public GitHub file / notebook extraction. |
| `config.py` | API client and debate settings. |
| `requirements.txt` | Direct dependency versions from the supplied environment. |

## Current limitations

This is a research planning prototype. Model scores are subjective assessments, and references and methodological claims need human verification. The code retrieves abstracts rather than full papers and does not execute experiments or edit the reviewed repository.

Model output must parse as JSON. Evaluator scores and reasoning are validated, but proposer and critic responses do not have complete schema validation. Network failures and malformed responses can interrupt a run; there is no resume mechanism.

## Contributing and license

See [CONTRIBUTING.md](CONTRIBUTING.md) for maintenance conventions. The project is released under the [MIT License](LICENSE).
