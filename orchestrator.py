import json
import os
import re
from datetime import datetime

from llm import call_llm, extract_json
from agents import (
    build_proposer_input,
    build_critic_input,
    build_evaluator_input,
    render,
    get_defense_instruction,
    get_critic_strictness_instruction,
)
from config import DEFENSE_LEVEL, CRITIC_STRICTNESS
from prompts import PROPOSER_SYSTEM, CRITIC_SYSTEM, EVALUATOR_SYSTEM
from tools import ArxivSearcher, GitHubRepo


def extract_github_url(text: str) -> str:
    """Pull the first GitHub URL out of the user's idea text."""
    match = re.search(r"https?://github\.com/\S+", text)
    if match:
        return match.group(0).rstrip(".,;)")
    return ""


def _validated_score(evaluation: dict, field: str) -> float:
    """Return a finite score in [0, 1], rejecting malformed evaluator output."""
    if not isinstance(evaluation, dict):
        raise ValueError("EVALUATOR response must be a JSON object.")
    value = evaluation.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"EVALUATOR returned an invalid {field}: expected a number from 0.0 to 1.0.")
    score = float(value)
    if not 0.0 <= score <= 1.0:
        raise ValueError(f"EVALUATOR returned an out-of-range {field}: {score}.")
    return score


def run(original_idea, max_rounds=5):
    if max_rounds < 1:
        raise ValueError("max_rounds must be at least 1.")

    log_dir = f"debate_{datetime.now():%Y%m%d_%H%M%S}"
    os.makedirs(log_dir, exist_ok=True)
    print(f"Logs will be saved to: {log_dir}")
    current_defense_rate = _validated_score(
        {"defense_rate": DEFENSE_LEVEL},
        "defense_rate",
    )
    current_strictness = _validated_score(
        {"strictness": CRITIC_STRICTNESS},
        "strictness",
    )
    print(f"[Config] Initial PROPOSER defense rate = {current_defense_rate:.2f}")
    print(f"[Config] Initial CRITIC strictness = {current_strictness:.2f}")

    arxiv_tool = ArxivSearcher(candidate_pool=15, per_query_keep=2)
    github_tool = GitHubRepo()

    repo_context = ""
    github_url = extract_github_url(original_idea)
    if github_url:
        print(f"Fetching GitHub file: {github_url}")
        repo_context = github_tool.fetch(github_url)
        if repo_context.startswith("[GitHub "):
            raise RuntimeError(f"GitHub file fetch failed: {repo_context}")
        print(f"Fetched file: {len(repo_context)} chars")
    else:
        print("No GitHub URL found in the idea; skipping repo fetch.")

    proposal = None
    critique = None
    user_feedback = None

    for r in range(1, max_rounds + 1):
        version = r - 1
        print(f"\n--- Round {r} starts (proposal v{version}) ---")

        search_source = proposal if proposal is not None else original_idea
        keywords = arxiv_tool.generate_keywords(search_source, n=3)
        print(f"Generated arXiv keywords: {keywords}")
        arxiv_context = arxiv_tool.search(keywords)
        print("arXiv search done.")

        defense_rate_used = current_defense_rate
        strictness_used = current_strictness
        proposer_system = (
            PROPOSER_SYSTEM
            + "\n\n"
            + get_defense_instruction(defense_rate_used)
        )

        print(
            f"PROPOSER is generating v{version} "
            f"(defense rate = {defense_rate_used:.2f})..."
        )
        revised_proposal = extract_json(
            call_llm(
                proposer_system,
                build_proposer_input(
                    original_idea,
                    proposal,
                    critique,
                    user_feedback,
                    version,
                    arxiv_context,
                    repo_context=repo_context,
                ),
                temperature=0.5,
            )
        )

        critic_system = (
            CRITIC_SYSTEM
            + "\n\n"
            + get_critic_strictness_instruction(strictness_used)
        )
        print(f"CRITIC is reviewing (strictness = {strictness_used:.2f})...")
        critique = extract_json(
            call_llm(
                critic_system,
                build_critic_input(
                    original_idea,
                    revised_proposal,
                    user_feedback,
                    r,
                    arxiv_context,
                    repo_context=repo_context,
                ),
                temperature=0.5,
            )
        )

        print("EVALUATOR is assessing the proposal and adjusting agent rates...")
        evaluation = extract_json(
            call_llm(
                EVALUATOR_SYSTEM,
                build_evaluator_input(
                    original_idea,
                    revised_proposal,
                    critique,
                    r,
                    arxiv_context,
                    repo_context=repo_context,
                    user_feedback=user_feedback,
                    defense_rate=defense_rate_used,
                    critic_strictness=strictness_used,
                ),
                temperature=0.3,
            )
        )
        completeness_score = _validated_score(evaluation, "completeness_score")
        next_strictness = _validated_score(evaluation, "suggested_critic_strictness")
        next_defense_rate = _validated_score(
            evaluation,
            "suggested_proposer_defense_rate",
        )
        reasoning = evaluation.get("reasoning")
        if not isinstance(reasoning, str) or not reasoning.strip():
            raise ValueError("EVALUATOR returned missing or invalid reasoning.")
        evaluation["completeness_score"] = completeness_score
        evaluation["suggested_critic_strictness"] = next_strictness
        evaluation["suggested_proposer_defense_rate"] = next_defense_rate
        current_strictness = next_strictness
        current_defense_rate = next_defense_rate
        print(
            f"EVALUATOR: completeness={completeness_score:.2f}, "
            f"next proposer defense={next_defense_rate:.2f}, "
            f"next critic strictness={next_strictness:.2f}"
        )
        print(f"EVALUATOR reasoning: {reasoning}")

        render(proposal or {"version": "start"}, revised_proposal, critique, r)

        with open(f"{log_dir}/round_{r:02d}.json", "w", encoding="utf-8") as f:
            json.dump(
                {
                    "round": r,
                    "proposal_version": version,
                    "proposer_defense_rate_used": defense_rate_used,
                    "next_proposer_defense_rate": next_defense_rate,
                    "strictness_used": strictness_used,
                    "next_strictness": next_strictness,
                    "evaluation": evaluation,
                    "arxiv_context": arxiv_context,
                    "repo_context_length": len(repo_context),
                    "critique": critique,
                    "before": proposal,
                    "after": revised_proposal,
                    "user_feedback": user_feedback,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

        # Wait for user feedback
        try:
            fb = input(
                "\n>>> Evaluate (Enter=next round / ok=finalize / other text=inject as new instruction): "
            ).strip()
        except EOFError:
            fb = "ok"

        if fb.lower() in ("ok", "done", "accept", "stop", "q", "quit"):
            print(
                f"\nFinalized: v{revised_proposal.get('version')} "
                f"- {revised_proposal.get('title')}"
            )
            with open(f"{log_dir}/final.json", "w", encoding="utf-8") as f:
                json.dump(revised_proposal, f, ensure_ascii=False, indent=2)
            return revised_proposal

        user_feedback = fb or None
        proposal = revised_proposal

    print(f"\nReached max rounds, stopped at v{proposal.get('version')}")
    return proposal