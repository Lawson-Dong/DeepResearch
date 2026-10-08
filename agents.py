import json
from prompts import ARXIV_CONTEXT_NOTE, GITHUB_CONTEXT_NOTE, PAPER_CONTEXT_NOTE

def get_defense_instruction(level: float) -> str:
    """
    Return a dynamic instruction for the undergraduate PROPOSER.
    level: 0.0 (fully deferential) to 1.0 (strongly defensive)
    """
    if level <= 0.2:
        return (
            "DEFENSE MODE: fully deferential. Accept almost every point from the professor. "
            "If you don't understand something, say so and ask for clarification instead of defending."
        )
    elif level <= 0.4:
        return (
            "DEFENSE MODE: mostly deferential. Accept what you understand. "
            "If you have a simple, honest reason for one of your choices, you may mention it briefly — "
            "but only if you can explain it without jargon. Otherwise, ask for clarification."
        )
    elif level <= 0.6:
        return (
            "DEFENSE MODE: balanced. You may defend a choice if you genuinely believe it is right, "
            "but always be open to being wrong. When in doubt, ask the professor to explain rather than argue."
        )
    return (
        "DEFENSE MODE: you feel confident about your core idea. Explain why you think it is worth keeping, "
        "but remain respectful and curious. Remember: you are still learning, and the professor knows more than you do."
    )


def get_critic_strictness_instruction(level: float) -> str:
    """Return a dynamic CRITIC instruction for a validated strictness level."""
    if level <= 0.2:
        return (
            "CRITIC MODE: Gentle. Focus on 1-2 high-value improvements, be especially encouraging, "
            "and avoid demanding advanced statistics."
        )
    elif level <= 0.5:
        return (
            "CRITIC MODE: Balanced professor. Identify 2-3 main issues with plain-language explanations "
            "and concrete, feasible next steps."
        )
    elif level <= 0.8:
        return (
            "CRITIC MODE: Rigorous professor. Examine assumptions and evidence carefully, explain "
            "unsupported claims directly, and give actionable steps without using unexplained jargon."
        )
    return (
        "CRITIC MODE: Very rigorous professor. Identify the core issues that require substantial rethinking, "
        "explain why they matter, and propose a feasible direction. Remain patient and respectful; "
        "strictness is not hostility."
    )


def build_proposer_input(
    original_idea,
    current,
    critique,
    user_feedback,
    round_idx,
    arxiv_context="",
    repo_context="",
    paper_context="",
):
    """Build input for PROPOSER"""
    parts = [f"# Original user idea\n{original_idea}"]

    if repo_context:
        parts.append(f"{GITHUB_CONTEXT_NOTE}\n# GitHub file content\n{repo_context}")

    if arxiv_context:
        parts.append(f"{ARXIV_CONTEXT_NOTE}\n# arXiv references\n{arxiv_context}")

    if paper_context:
        parts.append(f"{PAPER_CONTEXT_NOTE}\n{paper_context}")

    if current is None:
        parts.append("# Task\nThis is round 1. Turn the original idea into structured proposal v0.")
    else:
        parts.append(f"# Current version\n{json.dumps(current, ensure_ascii=False, indent=2)}")
        parts.append(f"# CRITIC's critique on current version\n{json.dumps(critique, ensure_ascii=False, indent=2)}")
        if user_feedback:
            parts.append(f"# Latest user instruction\n{user_feedback}")
        parts.append(f"# Task\nAddress the critiques point by point and produce version v{round_idx}.")

    parts.append(f"Output JSON with version={round_idx}.")
    return "\n\n".join(parts)


def build_critic_input(
    original_idea,
    proposal,
    user_feedback,
    round_idx,
    arxiv_context="",
    repo_context="",
    paper_context="",
):
    """Build input for CRITIC"""
    parts = [
        f"# Original user idea\n{original_idea}",
        f"# Version under review\n{json.dumps(proposal, ensure_ascii=False, indent=2)}",
    ]

    if repo_context:
        parts.append(f"{GITHUB_CONTEXT_NOTE}\n# GitHub file content\n{repo_context}")

    if arxiv_context:
        parts.append(f"{ARXIV_CONTEXT_NOTE}\n# arXiv references\n{arxiv_context}")

    if paper_context:
        parts.append(f"{PAPER_CONTEXT_NOTE}\n{paper_context}")

    if user_feedback:
        parts.append(f"# Latest user instruction\n{user_feedback}")

    parts.append(
        f"# Task\nReview this version as a warm, patient professor. Prioritize the most important issues "
        f"and give concrete next steps. Output JSON with round={round_idx}."
    )
    return "\n\n".join(parts)


def build_paper_reader_input(
    original_idea,
    proposal,
    critique,
    round_idx,
    paper_keywords,
    paper_search_context,
    paper_candidates,
    full_texts,
):
    """Build the isolated full-text summarization input for PAPER_READER."""
    return "\n\n".join(
        [
            f"# Original user idea\n{original_idea}",
            f"# Proposal from round {round_idx}\n"
            f"{json.dumps(proposal, ensure_ascii=False, indent=2)}",
            f"# CRITIC's literature needs from round {round_idx}\n"
            f"{json.dumps(critique, ensure_ascii=False, indent=2)}",
            f"# Search keywords based on this round's proposal and critique\n"
            f"{json.dumps(paper_keywords, ensure_ascii=False)}",
            f"# Candidate arXiv papers\n"
            f"{json.dumps(paper_candidates, ensure_ascii=False, indent=2)}",
            f"# Search results and retrieval status\n{paper_search_context}",
            f"# Retrieved full text (at most one complete paper)\n"
            f"{json.dumps(full_texts, ensure_ascii=False, indent=2)}",
            "# Task\nRead the supplied full texts and return the evidence-grounded JSON summary "
            "required by your system instructions. These notes will be provided to PROPOSER "
            "and CRITIC at the start of the next round.",
        ]
    )


def build_evaluator_input(
    original_idea,
    proposal,
    critique,
    round_idx,
    arxiv_context="",
    repo_context="",
    user_feedback=None,
    defense_rate=0.0,
    critic_strictness=0.0,
):
    """Build an evaluator prompt with the same source context given to both agents."""
    parts = [
        f"# Original user idea\n{original_idea}",
        f"# Proposal under evaluation (round {round_idx})\n"
        f"{json.dumps(proposal, ensure_ascii=False, indent=2)}",
        f"# CRITIC feedback from this round\n"
        f"{json.dumps(critique, ensure_ascii=False, indent=2)}",
        f"# Current PROPOSER defense rate\n{defense_rate:.2f}",
        f"# Current CRITIC strictness\n{critic_strictness:.2f}",
    ]

    if repo_context:
        parts.append(f"{GITHUB_CONTEXT_NOTE}\n# GitHub file content\n{repo_context}")

    if arxiv_context:
        parts.append(f"{ARXIV_CONTEXT_NOTE}\n# arXiv references\n{arxiv_context}")

    if user_feedback:
        parts.append(f"# Latest user instruction\n{user_feedback}")

    parts.append(
        "# Task\nEvaluate this proposal using the original idea and all supplied evidence. "
        "Recommend the next round's PROPOSER defense rate and CRITIC strictness. "
        "Output the JSON requested by your system instructions."
    )
    return "\n\n".join(parts)


def render(old, new, critique, round_idx):
    """Pretty-print the current round to terminal"""
    print("\n" + "=" * 70)
    print(f"Round {round_idx}   v{old.get('version')} -> v{new.get('version')}")
    print("=" * 70)

    print(f"\n[CRITIC verdict] {critique.get('verdict', '?')}")

    if critique.get("encouragement"):
        print(f"\n[CRITIC encouragement] {critique['encouragement']}")

    for issue in critique.get("main_issues", []):
        print(f"\n- {issue.get('issue')}")
        if issue.get("why_it_matters"):
            print(f"  Why it matters: {issue['why_it_matters']}")
        if issue.get("how_to_fix"):
            print(f"  Next step: {issue['how_to_fix']}")

    if critique.get("explanation_for_beginner"):
        print(f"\n[Explanation] {critique['explanation_for_beginner']}")

    suggested_reading = critique.get("suggested_reading", {})
    if suggested_reading.get("paper"):
        print(f"\n[Suggested reading] {suggested_reading['paper']}")
        if suggested_reading.get("why_relevant"):
            print(f"  Why it's relevant: {suggested_reading['why_relevant']}")

    if critique.get("acknowledged_improvements"):
        print("\n[CRITIC acknowledged improvements]")
        for x in critique["acknowledged_improvements"]:
            print(f"- {x}")

    if critique.get("alternative_directions"):
        print("\n[Alternative directions]")
        for x in critique["alternative_directions"]:
            print(f"- {x}")

    print(f"\n[PROPOSER response]\n{new.get('response_to_critic') or '(none)'}")

    if new.get("questions_for_professor"):
        print("\n[Questions for professor]")
        for question in new["questions_for_professor"]:
            print(f"- {question}")

    print(f"\n[New proposal v{new.get('version')}] {new.get('title', '')}")
    print(f"\nProblem: {new.get('problem', '')}")
    print(f"\nMotivation: {new.get('motivation', '')}")
    print(f"\nMethod: {new.get('method', '')}")
    print(f"\nFeasibility: {new.get('feasibility', '')}")

    if new.get("contributions"):
        print("\nContributions:")
        for x in new["contributions"]:
            print(f"- {x}")

    if new.get("risks"):
        print("\nRisks:")
        for x in new["risks"]:
            print(f"- {x}")

    if new.get("changelog"):
        print("\nChangelog:")
        for x in new["changelog"]:
            print(f"- {x}")

    print("=" * 70)
