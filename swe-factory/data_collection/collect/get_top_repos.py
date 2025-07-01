import requests
import json
import argparse
import os
import sys

def fetch_top_repos(language: str, output_path: str, top_n: int, token: str):
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"token {token}"
    }

    url = "https://api.github.com/search/repositories"
    params = {
        "q": f"language:{language}",
        "sort": "stars",
        "order": "desc",
        "per_page": 100,
        "page": 1
    }

    print(f"📡 Fetching top {top_n} repositories for language: {language}")
    repos = []

    while len(repos) < top_n:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200:
            print(f"❌ Error: {response.status_code} - {response.json().get('message')}")
            break

        data = response.json().get("items", [])
        if not data:
            break

        for repo in data:
            repos.append({
                "name": repo["full_name"],
                "stars": repo["stargazers_count"],
                "url": repo["html_url"],
                "description": repo["description"],
                "owner": repo["owner"]["login"],
                "language": repo["language"]
            })

        params["page"] += 1

    os.makedirs(output_path, exist_ok=True)
    output_file = os.path.join(output_path, f"{language.lower()}_top_{top_n}_repos.json")
    print(f"💾 Saving {min(top_n, len(repos))} repos to {output_file}")
    with open(output_file, mode='w', encoding='utf-8') as f:
        json.dump(repos[:top_n], f, indent=2, ensure_ascii=False)

    print("✅ Done!")

def main():
    parser = argparse.ArgumentParser(description="Fetch top GitHub repos by language")
    parser.add_argument("--language", type=str, required=True, help="Programming language (e.g., Python)")
    parser.add_argument("--output_path", type=str, required=True, help="Directory to save the result JSON")
    parser.add_argument("--top_n", type=int, default=500, help="Number of top repositories to fetch")
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("❌ GitHub token not found. Please set the environment variable `github_token`.")
        sys.exit(1)

    fetch_top_repos(
        language=args.language,
        output_path=args.output_path,
        top_n=args.top_n,
        token=token
    )

if __name__ == "__main__":
    main()
