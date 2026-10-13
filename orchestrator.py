import json
import os
import re
from datetime import datetime

from llm import call_llm, extract_json
from agents import (
    build_proposer_input,
    build_critic_input,
    build_evaluator_input,
    build_paper_reader_input,
    render,
    render_knowledge_note,
    get_defense_instruction,
    get_critic_strictness_instruction,
    get_knowledge_critic_strictness_instruction,
)
from config import DEFENSE_LEVEL, CRITIC_STRICTNESS
from prompts import (
    CRITIC_SYSTEM,
    EVALUATOR_SYSTEM,
    KNOWLEDGE_CRITIC_SYSTEM,
    KNOWLEDGE_EVALUATOR_SYSTEM,
    KNOWLEDGE_PROPOSER_SYSTEM,
    PAPER_READER_SYSTEM,
    PROPOSER_SYSTEM,
)
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


def run(original_idea, max_rounds=5, mode="research"):
    if max_rounds < 1:
        raise ValueError("max_rounds must be at least 1.")
    if mode not in {"research", "knowledge"}:
        raise ValueError("mode must be either 'research' or 'knowledge'.")

    log_dir = f"debate_{mode}_{datetime.now():%Y%m%d_%H%M%S}"
    os.makedirs(log_dir, exist_ok=True)
    print(f"Mode: {mode}")
    print(f"Logs will be saved to: {log_dir}")
    proposer_prompt = PROPOSER_SYSTEM if mode == "research" else KNOWLEDGE_PROPOSER_SYSTEM
    critic_prompt = CRITIC_SYSTEM if mode == "research" else KNOWLEDGE_CRITIC_SYSTEM
    evaluator_prompt = EVALUATOR_SYSTEM if mode == "research" else KNOWLEDGE_EVALUATOR_SYSTEM
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
    paper_context = ""

    for r in range(1, max_rounds + 1):
        version = r - 1
        subject_name = "proposal" if mode == "research" else "knowledge note"
        print(f"\n--- Round {r} starts ({subject_name} v{version}) ---")

        if proposal is None or mode == "research":
            search_source = proposal if proposal is not None else original_idea
        else:
            search_source = {
                "title": proposal.get("title", ""),
                "problem": proposal.get("core_question", ""),
                "method": proposal.get("current_understanding", ""),
            }
        keywords = arxiv_tool.generate_keywords(search_source, n=3)
        print(f"Generated arXiv keywords: {keywords}")
        arxiv_context = arxiv_tool.search(keywords)
        print("arXiv search done.")

        defense_rate_used = current_defense_rate
        strictness_used = current_strictness
        paper_context_used = paper_context
        proposer_system = (
            proposer_prompt
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
                    paper_context=paper_context_used,
                    mode=mode,
                ),
                temperature=0.5,
            )
        )

        strictness_instruction = (
            get_critic_strictness_instruction(strictness_used)
            if mode == "research"
            else get_knowledge_critic_strictness_instruction(strictness_used)
        )
        critic_system = critic_prompt + "\n\n" + strictness_instruction
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
                    paper_context=paper_context_used,
                    mode=mode,
                ),
                temperature=0.5,
            )
        )

        print(
            f"EVALUATOR is assessing the {subject_name} and adjusting agent rates..."
        )
        evaluation = extract_json(
            call_llm(
                evaluator_prompt,
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
                    mode=mode,
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

        critic_needs = [
            str(issue.get("issue", ""))
            + " "
            + str(issue.get("how_to_fix", ""))
            for issue in critique.get("main_issues", [])
            if isinstance(issue, dict)
        ]
        critic_needs.extend(
            str(question)
            for question in revised_proposal.get(
                "questions_for_professor" if mode == "research" else "questions_for_critic",
                [],
            )
        )
        suggested_reading = critique.get("suggested_reading", {})
        if isinstance(suggested_reading, dict):
            critic_needs.append(str(suggested_reading.get("paper", "")))
        if mode == "research":
            reader_search_source = {
                "title": revised_proposal.get("title", ""),
                "problem": revised_proposal.get("problem", ""),
                "method": " ".join(
                    critic_needs + [str(revised_proposal.get("method", ""))]
                ),
            }
        else:
            reader_search_source = {
                "title": revised_proposal.get("title", ""),
                "problem": revised_proposal.get("core_question", ""),
                "method": " ".join(
                    critic_needs + [str(revised_proposal.get("current_understanding", ""))]
                ),
            }
        paper_keywords = arxiv_tool.generate_keywords(reader_search_source, n=3)
        print(f"PAPER_READER search keywords: {paper_keywords}")
        paper_search_context = arxiv_tool.search(paper_keywords)
        paper_candidates = arxiv_tool.parse_results(paper_search_context)[:1]
        full_texts = [
            {
                **paper,
                **arxiv_tool.fetch_full_text(paper["url"]),
            }
            for paper in paper_candidates
        ]
        for document in full_texts:
            if document.get("error"):
                print(
                    f"PAPER_READER could not retrieve {document.get('url')}: "
                    f"{document['error']}"
                )
            else:
                print(
                    f"PAPER_READER retrieved {document.get('url')} "
                    f"from {document.get('source')} "
                    f"({len(document.get('text', ''))} chars)."
                )

        print("PAPER_READER is summarizing full texts for the next round...")
        paper_reader_result = extract_json(
            call_llm(
                PAPER_READER_SYSTEM,
                build_paper_reader_input(
                    original_idea,
                    revised_proposal,
                    critique,
                    r,
                    paper_keywords,
                    paper_search_context,
                    paper_candidates,
                    full_texts,
                    mode=mode,
                ),
                temperature=0.2,
            )
        )
        if not isinstance(paper_reader_result, dict):
            raise ValueError("PAPER_READER response must be a JSON object.")
        summaries = paper_reader_result.get("papers")
        unavailable = paper_reader_result.get("unavailable_papers")
        if not isinstance(summaries, list) or not isinstance(unavailable, list):
            raise ValueError(
                "PAPER_READER response must contain papers and unavailable_papers lists."
            )
        available_urls = {
            document["url"]
            for document in full_texts
            if isinstance(document.get("text"), str) and document["text"].strip()
        }
        for summary in summaries:
            if not isinstance(summary, dict) or summary.get("arxiv_url") not in available_urls:
                raise ValueError(
                    "PAPER_READER returned a summary without a matching retrieved full text."
                )
        paper_context = json.dumps(
            paper_reader_result,
            ensure_ascii=False,
            indent=2,
        )
        print(
            f"PAPER_READER prepared {len(summaries)} paper summary(ies) "
            "for the next round."
        )

        renderer = render if mode == "research" else render_knowledge_note
        renderer(proposal or {"version": "start"}, revised_proposal, critique, r)

        round_record = {
            "round": r,
            "mode": mode,
            "proposer_defense_rate_used": defense_rate_used,
            "next_proposer_defense_rate": next_defense_rate,
            "strictness_used": strictness_used,
            "next_strictness": next_strictness,
            "evaluation": evaluation,
            "arxiv_context": arxiv_context,
            "paper_context_used": paper_context_used,
            "paper_context_for_next_round": paper_reader_result,
            "paper_search_keywords": paper_keywords,
            "paper_search_context": paper_search_context,
            "paper_full_text_status": [
                {
                    "url": document.get("url"),
                    "source": document.get("source"),
                    "truncated": document.get("truncated"),
                    "error": document.get("error"),
                }
                for document in full_texts
            ],
            "repo_context_length": len(repo_context),
            "critique": critique,
            "user_feedback": user_feedback,
        }
        if mode == "research":
            round_record.update(
                {
                    "proposal_version": version,
                    "before": proposal,
                    "after": revised_proposal,
                }
            )
        else:
            round_record.update(
                {
                    "note_version": version,
                    "note_before": proposal,
                    "note_after": revised_proposal,
                }
            )

        with open(f"{log_dir}/round_{r:02d}.json", "w", encoding="utf-8") as f:
            json.dump(round_record, f, ensure_ascii=False, indent=2)

        # Wait for user feedback
        try:
            fb = input(
                "\n>>> Evaluate (Enter=next round / ok=finalize / other text=inject as new instruction): "
            ).strip()
        except EOFError:
            fb = "ok"

        if fb.lower() in ("ok", "done", "accept", "stop", "q", "quit"):
            print(
                f"\nFinalized {subject_name}: v{revised_proposal.get('version')} "
                f"- {revised_proposal.get('title')}"
            )
            final_name = "final.json" if mode == "research" else "final_note.json"
            with open(f"{log_dir}/{final_name}", "w", encoding="utf-8") as f:
                json.dump(revised_proposal, f, ensure_ascii=False, indent=2)
            return revised_proposal

        user_feedback = fb or None
        proposal = revised_proposal

    print(
        f"\nReached max rounds, stopped at {subject_name} "
        f"v{proposal.get('version')}"
    )
    return proposal