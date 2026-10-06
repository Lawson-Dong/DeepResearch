from orchestrator import run



if __name__ == "__main__":
    idea = input("Enter your research idea:\n").strip()
    run(idea, max_rounds=5)