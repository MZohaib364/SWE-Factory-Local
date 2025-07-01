import os
import shutil
import subprocess
import re
import json
import argparse
from contextlib import contextmanager
from typing import List, Dict
from concurrent.futures import ProcessPoolExecutor, as_completed

@contextmanager
def cd(newdir):
    prevdir = os.getcwd()
    os.chdir(os.path.expanduser(newdir))
    try:
        yield
    finally:
        os.chdir(prevdir)

def run_command(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, check=True, **kwargs)
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {cmd}, {e}")
        raise

def get_version_by_git(cloned_dir: str) -> str:
    if not os.path.isdir(cloned_dir):
        raise NotADirectoryError(f"Invalid directory: {cloned_dir}")
    with cd(cloned_dir):
        result = run_command(["git", "describe", "--tags"], capture_output=True, text=True)
        version = result.stdout.strip()
        print(f"✔️ Current version: {version}")
        match = re.search(r"(\d+\.\d+)(?:\.\d+)?", version)
        if match:
            return match.group(1)
        raise RuntimeError(f"Unrecognized version: {version}")

def get_instances(instance_path: str) -> List[Dict]:
    if instance_path.endswith((".jsonl", ".jsonl.all")):
        with open(instance_path, encoding="utf-8") as f:
            return [json.loads(line) for line in f]
    with open(instance_path, encoding="utf-8") as f:
        return json.load(f)

def prepare_repo_cache(tasks: List[Dict], cache_dir: str) -> Dict[str, str]:
    os.makedirs(cache_dir, exist_ok=True)
    repo_cache = {}
    for task in tasks:
        repo = task["repo"]
        if repo in repo_cache:
            continue
        repo_url = f"https://github.com/{repo}.git"
        local_path = os.path.join(cache_dir, repo.replace("/", "__"))
        try:
            run_command(["git", "clone", repo_url, local_path], capture_output=True)
            repo_cache[repo] = local_path
            print(f"✅ Cached repo: {repo}")
        except Exception as e:
            print(f"❌ Failed to clone {repo}: {e}")
    return repo_cache

def process_repo_task(task: Dict, testbed: str, repo_cache: Dict[str, str]) -> Dict | None:
    instance_id = task["instance_id"]
    repo = task["repo"]
    base_commit = task["base_commit"]
    repo_dir = os.path.join(testbed, instance_id)
    os.makedirs(repo_dir, exist_ok=True)

    try:
        cached_repo = repo_cache.get(repo)
        if not cached_repo or not os.path.exists(cached_repo):
            raise RuntimeError(f"Missing cached repo for {repo}")
        shutil.copytree(cached_repo, repo_dir, dirs_exist_ok=True)
        with cd(repo_dir):
            run_command(["git", "checkout", base_commit], capture_output=True)
        version = get_version_by_git(repo_dir)
        result = task.copy()
        result["version"] = version
        return result
    except Exception as e:
        print(f"❌ Failed: {instance_id} | {e}")
        return None
    finally:
        shutil.rmtree(repo_dir, ignore_errors=True)

def process_repos(tasks: List[Dict], testbed: str, repo_cache: Dict[str, str], max_workers: int = 4) -> tuple[List[Dict], List[Dict]]:
    os.makedirs(testbed, exist_ok=True)
    results, failures = [], []
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        future_to_task = {
            executor.submit(process_repo_task, t, testbed, repo_cache): t for t in tasks
        }
        for future in as_completed(future_to_task):
            task = future_to_task[future]
            try:
                result = future.result()
                if result:
                    results.append(result)
                else:
                    failures.append(task)
            except Exception as e:
                print(f"Unexpected error in {task['instance_id']}: {e}")
                failures.append(task)
    return results, failures

def save_results(results: List[Dict], output_path: str):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    if output_path.endswith((".jsonl", ".jsonl.all")):
        with open(output_path, "w", encoding="utf-8") as f:
            for r in results:
                f.write(json.dumps(r) + "\n")
    else:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

def generate_output_path(instance_path: str, suffix="_versions") -> str:
    base, ext = os.path.splitext(instance_path)
    return f"{base}{suffix}{ext}"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--instance_path", type=str, required=True, help="Path to input task file (.json or .jsonl)")
    parser.add_argument("--testbed", type=str, required=True, help="Temp working directory for cloning repos")
    parser.add_argument("--max-workers", type=int, default=10, help="Number of processes (default: 4)")
    args = parser.parse_args()

    try:
        tasks = get_instances(args.instance_path)
    except Exception as e:
        print(f"❌ Error reading instance file: {e}")
        return

    required_keys = {"repo", "base_commit", "instance_id"}
    for t in tasks:
        if not required_keys.issubset(t):
            print(f"Invalid task format: {t}")
            return

    repo_cache_dir = os.path.join(args.testbed, "_cache")
    repo_cache = prepare_repo_cache(tasks, repo_cache_dir)

    results, failures = process_repos(tasks, args.testbed, repo_cache, args.max_workers)

    output_path = generate_output_path(args.instance_path, "_versions")
    save_results(results, output_path)
    print(f"\n✅ {len(results)} results saved to {output_path}")

    if failures:
        fail_path = generate_output_path(args.instance_path, "_failures")
        save_results(failures, fail_path)
        print(f"⚠️  {len(failures)} failures saved to {fail_path}")

    for r in results:
        print(json.dumps(r, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
