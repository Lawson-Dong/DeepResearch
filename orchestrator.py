import json
import os
import re
from datetime import datetime

from llm import call_llm, extract_json
from agents import (
    build_proposer_input,
    build_critic_input,
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
    log_dir = f"debate_{datetime.now():%Y%m%d_%H%M%S}"
    os.makedirs(log_dir, exist_ok=True)
    print(f"Logs will be saved to: {log_dir}")
    print(f"[Config] DEFENSE_LEVEL = {DEFENSE_LEVEL}  (0=deferential, 1=defensive)")
    current_strictness = _validated_score(
        {"strictness": CRITIC_STRICTNESS},
        "strictness",
    )
    print(f"[Config] CRITIC_STRICTNESS = {current_strictness:.2f}")

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

    defense_note = get_defense_instruction(DEFENSE_LEVEL)
    proposer_system = PROPOSER_SYSTEM + "\n\n" + defense_note

    user_feedback = None

    # Generate initial proposal v1 (no defense note needed for round 1)
    print("\nGenerating initial proposal v1, please wait...")
    proposal = extract_json(
        call_llm(
            PROPOSER_SYSTEM,
            build_proposer_input(original_idea, None, None, None, 1, repo_context=repo_context),
            temperature=0.5,
        )
    )

    for r in range(1, max_rounds + 1):
        print(f"\n--- Round {r} starts ---")
        strictness_used = current_strictness
        critic_system = (
            CRITIC_SYSTEM
            + "\n\n"
            + get_critic_strictness_instruction(strictness_used)
        )

        # Search arXiv for relevant papers
        keywords = arxiv_tool.generate_keywords(proposal, n=3)
        print(f"Generated arXiv keywords: {keywords}")
        arxiv_context = arxiv_tool.search(keywords)
        print("arXiv search done.")

        # CRITIC reviews the proposal using this round's strictness.
        print(f"CRITIC is reviewing (strictness = {strictness_used:.2f})...")
        critique = extract_json(
            call_llm(
                critic_system,
                build_critic_input(
                    original_idea,
                    proposal,
                    user_feedback,
                    r,
                    arxiv_context,
                    repo_context=repo_context,
                ),
                temperature=0.5,
            )
        )

        # PROPOSER revises
        print(f"PROPOSER is revising (defense level = {DEFENSE_LEVEL})...")
        new_proposal = extract_json(
            call_llm(
                proposer_system,
                build_proposer_input(
                    original_idea,
                    proposal,
                    critique,
                    user_feedback,
                    r + 1,
                    arxiv_context,
                    repo_context=repo_context,
                ),
                temperature=0.5,
            )
        )

        print("EVALUATOR is scoring the revised proposal...")
        evaluator_input = (
            f"# Revised proposal\n{json.dumps(new_proposal, ensure_ascii=False, indent=2)}\n\n"
            f"# CRITIC feedback from this round\n"
            f"{json.dumps(critique, ensure_ascii=False, indent=2)}"
        )
        evaluation = extract_json(
            call_llm(
                EVALUATOR_SYSTEM,
                evaluator_input,
                temperature=0.3,
            )
        )
        completeness_score = _validated_score(evaluation, "completeness_score")
        next_strictness = _validated_score(evaluation, "suggested_critic_strictness")
        reasoning = evaluation.get("reasoning")
        if not isinstance(reasoning, str) or not reasoning.strip():
            raise ValueError("EVALUATOR returned missing or invalid reasoning.")
        evaluation["completeness_score"] = completeness_score
        evaluation["suggested_critic_strictness"] = next_strictness
        current_strictness = next_strictness
        print(
            f"EVALUATOR: completeness={completeness_score:.2f}, "
            f"next strictness={next_strictness:.2f}"
        )
        print(f"EVALUATOR reasoning: {reasoning}")

        # Show to user
        render(proposal, new_proposal, critique, r)

        # Save round log
        with open(f"{log_dir}/round_{r:02d}.json", "w", encoding="utf-8") as f:
            json.dump(
                {
                    "round": r,
                    "defense_level": DEFENSE_LEVEL,
                    "strictness_used": strictness_used,
                    "next_strictness": next_strictness,
                    "evaluation": evaluation,
                    "arxiv_context": arxiv_context,
                    "repo_context_length": len(repo_context),
                    "critique": critique,
                    "before": proposal,
                    "after": new_proposal,
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
            print(f"\nFinalized: v{new_proposal.get('version')} - {new_proposal.get('title')}")
            with open(f"{log_dir}/final.json", "w", encoding="utf-8") as f:
                json.dump(new_proposal, f, ensure_ascii=False, indent=2)
            return new_proposal

        user_feedback = fb or None
        proposal = new_proposal

    print(f"\nReached max rounds, stopped at v{proposal.get('version')}")
    return proposal