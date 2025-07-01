#!/usr/bin/env python3

import argparse
import json
import logging
import os
from typing import Optional
from datetime import datetime
from utils import Repo, extract_patches, extract_problem_statement_and_hints, extract_problem_statement_and_hints_with_official_github_api

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def create_instance(repo: Repo, pull: dict, output_path: str, mode: str ='swebench') -> dict:
    """
    Create a single task instance from a pull request, where task instance is:

    {
        repo (str): owner/repo this task instance is from,
        pull_number (int): number of PR this task instance is from,
        base_commit (str): SHA of the base commit PR is based on,
        patch (str): reference solution as .patch (apply to base commit),
        test_patch (str): test suite as .patch (apply to base commit),
    }
    """
    # try: 
    patch, test_patch, request_success = extract_patches(pull, repo)
    # except Exception as e:
    #     logger.info(e)
    #     patch = ""
    #     test_patch = ""
    instance_id  = (repo.repo.full_name + "-" + str(pull["number"])).replace("/", "__")
    successful_path = os.path.join(os.path.dirname(output_path), "successful_requests.txt")
    if request_success:
        with open(successful_path, "a") as f:
            f.write(instance_id + "\n")

    if mode =='swebench':

        problem_statement, hints = extract_problem_statement_and_hints(pull, repo)
    else:
        problem_statement, hints = extract_problem_statement_and_hints_with_official_github_api(pull, repo)
    return {
        "repo": repo.repo.full_name,
        "pull_number": pull["number"],
        "instance_id": instance_id,
        "issue_numbers": pull["resolved_issues"],
        "base_commit": pull["base"]["sha"],
        "patch": patch,
        "test_patch": test_patch,
        "problem_statement": problem_statement,
        "hints_text": hints,
        "created_at": pull["created_at"],
    }


def is_valid_pull(pull: dict) -> bool:
    """
    Check whether PR has an associated issue and is merged

    Args:
        pull (dict): pull request object
    Returns:
        bool: whether PR is valid
    """
    if pull["merged_at"] is None:
        # logger.info(f" not merged")
        return False
    if "resolved_issues" not in pull or len(pull["resolved_issues"]) < 1:
        # logger.info(f"no resolved_issues")
        return False

    return True


def is_valid_instance(instance: dict) -> bool:
    """
    Check whether task instance has all required fields for task instance creation

    Args:
        instance (dict): task instance object
    Returns:
        bool: whether task instance is valid
    """
    if instance["patch"] is None or instance["patch"] == "":
        logger.info(f"Instance {instance['pull_number']} no patch")
        return False
    if instance["problem_statement"] is None or instance["problem_statement"] == "":
        logger.info(f"Instance {instance['pull_number']} no problem statement")
        return False
    return True


def has_test_patch(instance: dict) -> bool:
    """
    Check whether task instance has a test suite

    Args:
        instance (dict): task instance object
    Returns:
        bool: whether task instance has a test suite
    """
    if instance["test_patch"] is None or instance["test_patch"].strip() == "":
        logger.info(f"Instance {instance['pull_number']} no test patch")
        return False
    return True

def main(pr_file: str, output: str, token: Optional[str] = None,mode: Optional[str] = 'swebench',language: Optional[str] = 'python', cutoff_date: Optional[str] = None):
    """
    Main thread for creating task instances from pull requests

    Args:
        pr_file (str): path to pull request JSONL file
        output (str): output file name
        token (str): GitHub token
    """
    logger.info(f'Language: {language}')
    logger.info(f'mode: {mode}')
    cutoff_date = datetime.strptime(cutoff_date, "%Y-%m-%dT%H:%M:%SZ")
    if token is None:
        # Get GitHub token from environment variable if not provided
        token = os.environ["GITHUB_TOKEN"]

    def load_repo(repo_name,language):
        # Return repo object for a given repo name
        owner, repo = repo_name.split("/")
        return Repo(owner, repo, token=token,language=language)

    repos = dict()
    completed = 0
    with_tests = 0
    total_instances = 0
    all_output = output + ".all"
    seen_prs = set()

    successful_path = os.path.join(os.path.dirname(output), "successful_requests.txt")

    if not os.path.exists(successful_path):
        with open(successful_path, "w") as f:
            pass  

    successful_instances = set()
    with open(successful_path, "r") as f:
        for line in f:
            successful_instances.add(line.strip())

    # Continue where we left off if output file already exists
    if os.path.exists(all_output):
        with open(all_output) as f:
            for line in f:
                pr = json.loads(line)
                # Safely get full_name for instance_id
                repo_full_name = ""
                if "repo" in pr and isinstance(pr["repo"], dict):
                    repo_full_name = pr["repo"].get("full_name", "")
                pr["instance_id"] = (
                    repo_full_name + "-" + str(pr.get("pull_number", ""))
                ).replace("/", "__")
                instance_id = pr["instance_id"]
                seen_prs.add(instance_id)
                created_at = pr.get('created_at')
                if not created_at or not isinstance(created_at, str):
                    continue
                try:
                    created_at_dt = datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%SZ")
                except Exception:
                    continue
                if not isinstance(cutoff_date, datetime):
                    cutoff_date_dt = datetime.strptime(str(cutoff_date), "%Y-%m-%dT%H:%M:%SZ")
                else:
                    cutoff_date_dt = cutoff_date
                if created_at_dt >= cutoff_date_dt:
                    logger.info(f"Instance {instance_id} created_at {created_at} exceeds cutoff_date {cutoff_date_dt}")
                    continue
                if is_valid_instance(pr):
                    completed += 1
                    if has_test_patch(pr):
                        with_tests += 1
    logger.info(f"{len(seen_prs)} instance_ids previously recorded")
    original_output_path = output
    # Write to .all file for all PRs
    write_mode_all = "w" if not os.path.exists(all_output) else "a"
    with open(all_output, write_mode_all) as all_output_f:
        # Write to output file for PRs with test suites
        write_mode = "w" if not os.path.exists(output) else "a"
        with open(output, write_mode) as output_f:
            for ix, line in enumerate(open(pr_file)):
                total_instances += 1
                pull = json.loads(line)
                # Safely get full_name for logging and instance_id
                repo_full_name = ""
                if "repo" in pull["base"] and isinstance(pull["base"]["repo"], dict):
                    repo_full_name = pull["base"]["repo"].get("full_name", "")
                if ix % 100 == 0:
                    logger.info(
                        f"[{repo_full_name}] ( Up to {ix} checked ) {completed} valid, {with_tests} with tests."
                    )
                instance_id = (
                    repo_full_name + "-" + str(pull.get("number", ""))
                )
                instance_id = instance_id.replace("/", "__")
                
                if instance_id in seen_prs:
                    seen_prs -= {instance_id}
                    continue

                if instance_id in successful_instances:
                    continue
    
                if not is_valid_pull(pull):
                    # Throw out invalid PRs
                    continue
                # Create task instance
                repo_name = pull["base"]["repo"]["full_name"]
                if repo_name not in repos:
                    repos[repo_name] = load_repo(repo_name,language)
                repo = repos[repo_name]
                # Ensure mode is a string
                mode_str = str(mode) if mode is not None else 'swebench'
                instance = create_instance(repo, pull,original_output_path,mode_str)
                if is_valid_instance(instance):
                    # If valid, write to .all output file
                    print(
                        json.dumps(instance), end="\n", flush=True, file=all_output_f
                    )  # write all instances to a separate file
                    completed += 1
                    if has_test_patch(instance):
                        # If has test suite, write to output file
                        print(json.dumps(instance), end="\n", flush=True, file=output_f)
                        with_tests += 1
    logger.info(
        f"Total instances: {total_instances}, completed: {completed}, with tests: {with_tests}"
    )
    logger.info(f"Didn't see {len(seen_prs)} instances previously recorded")
    logger.info("\n".join(sorted(seen_prs)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("pr_file", type=str, help="Path to pull request JSONL file")
    parser.add_argument("output", type=str, help="Output file name")
    parser.add_argument("--token", type=str, help="GitHub token")
    parser.add_argument("--mode", type=str, default='omnigirl',help="collecting mode")
    parser.add_argument("--cutoff_date", type=str, default="2025-03-31T23:59:59Z", help="Cutoff date for filtering PRs in YYYY-MM-DDTHH:MM:SSZ format")
    parser.add_argument("--language", type=str, help="language (python, java, js, cpp, c++)")
    
    args = parser.parse_args()
    print(">>> reached main()")
    # Normalize C++ language argument
    if args.language is not None and args.language.lower() in ["c++", "cpp"]:
        args.language = "cpp"
    main(**vars(args))
