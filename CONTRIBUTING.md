# Contributing to DeepResearch

Use English for documentation, code comments, issue descriptions, and commit messages. Keep changes focused and explain any change to prompts, output fields, or debate behavior.

## Local checks

Set up the project using the README, then check syntax:

```bash
python -m py_compile main.py config.py llm.py agents.py prompts.py tools.py orchestrator.py
```

For behavioral changes, verify the relevant flow: a plain idea, an optional supported GitHub file URL, feedback followed by another round, explicit finalization, or reaching the round limit. Prefer mocked API calls when possible. State whether validation used mocks or live services.

Keep API keys in the local environment or `.env`. Commit `.env.example` with placeholders only. Exclude virtual environments, bytecode, and machine-specific files. Review generated logs before deliberately adding them as examples.

Update the README when setup, configuration, supported URLs, log fields, or stopping behavior changes. If dependencies change, update `requirements.txt` and record the versions and Python environment used for validation.

## Where to contribute

DeepResearch currently implements proposal refinement, literature retrieval, critique, evaluation, and human feedback. Experiment execution and reproducible research reporting are planned extensions.

Good starting points include response schema validation, mocked integration tests, session recovery, retrieval quality, and configurable providers. Larger contributions can explore explicit experiment specifications, controlled execution, baselines, and artifact tracking. Describe the scope and expected behavior before introducing major infrastructure changes.

Project: [DeepResearch](https://github.com/Lawson-Dong/ideas-debate). Maintainer: [Lawson Dong](https://lawson-dong.vercel.app/).
