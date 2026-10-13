from orchestrator import run



if __name__ == "__main__":
    print("Choose a debate mode:")
    print("1. Research debate (proposal)")
    print("2. Knowledge debate (note)")
    mode_choice = input("Enter 1 or 2 [default: 1]: ").strip()
    if mode_choice not in ("", "1", "2"):
        raise ValueError("Please choose 1 for research debate or 2 for knowledge debate.")
    mode = "knowledge" if mode_choice == "2" else "research"

    topic_label = "research idea" if mode == "research" else "knowledge topic or question"
    idea = input(f"Enter your {topic_label}:\n").strip()
    run(idea, max_rounds=5, mode=mode)