import json
import ast
import contextlib
import glob
import os
import subprocess
from os.path import dirname as pdirname
from os.path import join as pjoin
from pathlib import Path
from subprocess import CalledProcessError
import re
# from app.log import print


@contextlib.contextmanager
def cd(newdir):
    """
    Context manager for changing the current working directory
    :param newdir: path to the new directory
    :return: None
    """
    prevdir = os.getcwd()
    os.chdir(os.path.expanduser(newdir))
    try:
        yield
    finally:
        os.chdir(prevdir)


def run_command(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """
    Run a command in the shell.
    Args:
        - cmd: command to run
    """
    try:
        cp = subprocess.run(cmd, check=True, **kwargs)
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {cmd}, {e}")
        raise e
    return cp

def get_version_by_git(cloned_dir: str) -> str:
    """
    Get the major.minor version of a Git repository using 'git describe --tags'.
    
    Args:
        cloned_dir: Path to the Git repository directory.
        
    Returns:
        str: The version string in 'major.minor' format (e.g., '3.6' from '3.6.7+21sadd').
        
    Raises:
        FileNotFoundError: If the directory does not exist.
        NotADirectoryError: If the path is not a directory.
        RuntimeError: If the directory is not a Git repository, no tags are found,
                      or the version format is invalid.
    """
    if not os.path.exists(cloned_dir):
        raise FileNotFoundError(f"Directory does not exist: {cloned_dir}")
    if not os.path.isdir(cloned_dir):
        raise NotADirectoryError(f"Path is not a directory: {cloned_dir}")

    command = ["git", "describe", "--tags"]
    try:
        with cd(cloned_dir):
            result = run_command(command, capture_output=True, text=True)
            version = result.stdout.strip()
            # 使用正则表达式提取 major.minor
            match = re.match(r"^(\d+\.\d+)", version)
            if match:
                return match.group(1)
            else:
                raise RuntimeError(f"Invalid version format: {version}")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to get version for {cloned_dir}. "
                          "Is it a Git repository with tags?") from e


def is_git_repo() -> bool:
    """
    Check if the current directory is a git repo.
    """
    git_dir = ".git"
    return os.path.isdir(git_dir)


def initialize_git_repo_and_commit(logger=None):
    """
    Initialize the current directory as a git repository and make an initial commit.
    """
    init_cmd = ["git", "init"]
    add_all_cmd = ["git", "add", "."]
    commit_cmd = ["git", "commit", "-m", "Temp commit made by ACR."]
    run_command(init_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    run_command(add_all_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    run_command(commit_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)



def get_current_commit_hash() -> str:
    command = ["git", "rev-parse", "HEAD"]
    cp = subprocess.run(command, text=True, capture_output=True)
    try:
        cp.check_returncode()
        return cp.stdout.strip()
    except CalledProcessError as e:
        raise RuntimeError(f"Failed to get SHA-1 of HEAD: {cp.stderr}") from e


def repo_commit_current_changes():
    """
    Commit the current active changes so that it's safer to do git reset later on.
    Use case: for storing the changes made in pre_install and test_patch in a commit.
    """
    add_all_cmd = ["git", "add", "."]
    commit_cmd = ["git", "commit", "-m", "Temporary commit for storing changes"]
    run_command(add_all_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    run_command(commit_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def clone_repo(clone_link: str, cloned_dir: str):
    """
    Clone a repo to dest_dir.

    Returns:
        - path to the newly cloned directory.
    """
    dest_dir = os.path.dirname(cloned_dir)  # 获取目录路径
    cloned_name = os.path.basename(cloned_dir)
    clone_cmd = ["git", "clone", clone_link, cloned_name]
    create_dir_if_not_exists(dest_dir)
    with cd(dest_dir):
        run_command(clone_cmd)
    # cloned_dir = pjoin(dest_dir, cloned_name)
    # return cloned_dir


def clone_repo_and_checkout(
    clone_link: str, commit_hash: str, cloned_dir: str,
    # dest_dir: str, cloned_name: str
):
    """
    Clone a repo to dest_dir, and checkout to commit `commit_hash`.

    Returns:
        - path to the newly cloned directory.
    """
    # cloned_dir = 
    clone_repo(clone_link, cloned_dir)
    checkout_cmd = ["git", "checkout", commit_hash]
    with cd(cloned_dir):
        run_command(checkout_cmd)
    # return cloned_dir




def repo_clean_changes() -> None:
    """
    Reset repo to HEAD. Basically clean active changes and untracked files on top of HEAD.

    A lightweight version of `repo_reset_and_clean_checkout`. This is also used in different scenarios.
    """
    reset_cmd = ["git", "reset", "--hard"]
    clean_cmd = ["git", "clean", "-fd"]
    run_command(reset_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    run_command(clean_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def repo_reset_and_clean_checkout(commit_hash: str) -> None:
    """
    Run commands to reset repo to the original commit state.
    Cleans both the uncommited changes and the untracked files, and submodule changes.
    Assumption: The current directory is the git repository.
    """
    # NOTE: do these before `git reset`. This is because some of the removed files below
    # may actually be in version control. So even if we deleted such files here, they
    # will be brought back by `git reset`.
    # Clean files that might be in .gitignore, but could have been created by previous runs
    if os.path.exists(".coverage"):
        os.remove(".coverage")
    if os.path.exists("tests/.coveragerc"):
        os.remove("tests/.coveragerc")
    other_cov_files = glob.glob(".coverage.TSS.*", recursive=True)
    for f in other_cov_files:
        os.remove(f)

    reset_cmd = ["git", "reset", "--hard", commit_hash]
    clean_cmd = ["git", "clean", "-fd"]
    checkout_cmd = ["git", "checkout", commit_hash]
    run_command(reset_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    run_command(clean_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # need to checkout before submodule init. Otherwise submodule may init to another version
    run_command(checkout_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # this is a fail-safe combo to reset any changes to the submodule: first unbind all submodules
    # and then make a fresh checkout of them.
    # Reference: https://stackoverflow.com/questions/10906554/how-do-i-revert-my-changes-to-a-git-submodule
    submodule_unbind_cmd = ["git", "submodule", "deinit", "-f", "."]
    submodule_init_cmd = ["git", "submodule", "update", "--init"]
    run_command(
        submodule_unbind_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    run_command(
        submodule_init_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )


def run_script_in_conda(
    args: list[str], env_name: str, **kwargs
) -> subprocess.CompletedProcess:
    """
    Run a python command in a given conda environment.
    """
    cmd = ["conda", "run", "-n", env_name, "python", *args]
    return subprocess.run(cmd, **kwargs)


def run_string_cmd_in_conda(
    command: str, env_name: str, **kwargs
) -> subprocess.CompletedProcess:
    """
    Run a complete command in a given conda environment, where the command is a string.

    This is useful when the command to be run contains &&, etc.

    NOTE: use `conda activate` instead of `conda run` in this verison, so that we can
          run commands that contain `&&`, etc.
    """
    conda_bin_path = os.getenv("CONDA_EXE")  # for calling conda
    if conda_bin_path is None:
        raise RuntimeError("Env variable CONDA_EXE is not set")
    conda_root_dir = pdirname(pdirname(conda_bin_path))
    conda_script_path = pjoin(conda_root_dir, "etc", "profile.d", "conda.sh")
    conda_cmd = f"source {conda_script_path} ; conda activate {env_name} ; {command} ; conda deactivate"
    print(f"Running command: {conda_cmd}")
    return subprocess.run(conda_cmd, shell=True, **kwargs)


def create_dir_if_not_exists(dir_path: str):
    """
    Create a directory if it does not exist.
    Args:
        dir_path (str): Path to the directory.
    """
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)


def to_relative_path(file_path: str, project_root: str) -> str:
    """Convert an absolute path to a path relative to the project root.

    Args:
        - file_path (str): The absolute path.
        - project_root (str): Absolute path of the project root dir.

    Returns:
        The relative path.
    """
    if Path(file_path).is_absolute():
        return str(Path(file_path).relative_to(project_root))
    else:
        return file_path


def to_absolute_path(file_path: str, project_root: str) -> str:
    """Convert a relative path to an absolute path.

    Args:
        - file_path (str): The relative path.
        - project_root (str): Absolute path of a root dir.
    """
    return pjoin(project_root, file_path)


def find_file(directory, filename) -> str | None:
    """
    Find a file in a directory. filename can be short name, relative path to the
    directory, or an incomplete relative path to the directory.
    Returns:
        - the relative path to the file if found; None otherwise.
    """

    # Helper method one
    def find_file_exact_relative(directory, filename) -> str | None:
        if os.path.isfile(os.path.join(directory, filename)):
            return filename
        return None

    # Helper method two
    def find_file_shortname(directory, filename) -> str | None:
        for root, dirs, files in os.walk(directory):
            for file in files:
                if file == filename:
                    return os.path.relpath(os.path.join(root, file), directory)
        return None

    # if the filename is exactly the relative path.
    found = find_file_exact_relative(directory, filename)
    if found is not None:
        return found

    # if the filename is a short name without any directory
    found = find_file_shortname(directory, filename)
    if found is not None:
        return found

    # if the filename has some directory, but is not a relative path to
    # the directory
    parts = filename.split(os.path.sep)
    shortname = parts[-1]
    found = find_file_shortname(directory, shortname)
    if found is None:
        # really cannot find this file
        return None
    # can find this shortname, but we also need to check whether the intermediate
    # directories match
    if filename in found:
        return found
    else:
        return None


def parse_function_invocation(
    invocation_str: str,
) -> tuple[str, list[str]]:
    try:
        tree = ast.parse(invocation_str)
        expr = tree.body[0]
        assert isinstance(expr, ast.Expr)
        call = expr.value
        assert isinstance(call, ast.Call)
        func = call.func
        assert isinstance(func, ast.Name)
        function_name = func.id
        raw_arguments = [ast.unparse(arg) for arg in call.args]
        # clean up spaces or quotes, just in case
        arguments = [arg.strip().strip("'").strip('"') for arg in raw_arguments]

        try:
            new_arguments = [ast.literal_eval(x) for x in raw_arguments]
            if new_arguments != arguments:
                print(
                    f"Refactored invocation argument parsing gives different result on "
                    f"{invocation_str!r}: old result is {arguments!r}, new result "
                    f" is {new_arguments!r}"
                )
        except Exception as e:
            print(
                f"Refactored invocation argument parsing failed on {invocation_str!r}: {e!s}"
            )
    except Exception as e:
        raise ValueError(f"Invalid function invocation: {invocation_str}") from e

    return function_name, arguments


import os
import shutil
import subprocess
import re
import json
import argparse
from contextlib import contextmanager
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed

@contextmanager
def cd(newdir):
    """
    Context manager for changing the current working directory
    """
    prevdir = os.getcwd()
    os.chdir(os.path.expanduser(newdir))
    try:
        yield
    finally:
        os.chdir(prevdir)

def run_command(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """
    Run a command in the shell.
    """
    try:
        cp = subprocess.run(cmd, check=True, **kwargs)
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {cmd}, {e}")
        raise e
    return cp

def get_version_by_git(cloned_dir: str) -> str:
    """
    Get the major.minor version of a Git repository using 'git describe --tags'.
    """
    if not os.path.exists(cloned_dir):
        raise FileNotFoundError(f"Directory does not exist: {cloned_dir}")
    if not os.path.isdir(cloned_dir):
        raise NotADirectoryError(f"Path is not a directory: {cloned_dir}")

    command = ["git", "describe", "--tags"]
    try:
        with cd(cloned_dir):
            result = run_command(command, capture_output=True, text=True)
            version = result.stdout.strip()
            match = re.match(r"^(?:v)?(\d+\.\d+)", version)
            if match:
                return match.group(1)
            else:
                raise RuntimeError(f"Invalid version format: {version}")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to get version for {cloned_dir}. "
                          "Is it a Git repository with tags?") from e

def get_instances(instance_path: str) -> list:
    """
    Get task instances from given path

    Args:
        instance_path (str): Path to task instances
    Returns:
        task_instances (list): List of task instances
    """
    if any([instance_path.endswith(x) for x in [".jsonl", ".jsonl.all"]]):
        task_instances = list()
        with open(instance_path) as f:
            for line in f.readlines():
                task_instances.append(json.loads(line))
        return task_instances

    with open(instance_path) as f:
        task_instances = json.load(f)
    return task_instances

def process_repo_task(task: Dict, testbed: str) -> Dict:
    """
    Process a single repository task: clone, checkout, get version, and clean up.
    """
    instance_id = task["instance_id"]
    repo = task["repo"]
    sha = task["sha"]
    repo_dir = os.path.join(testbed, instance_id)
    
    result = {"instance_id": instance_id}
    
    try:
        # 验证 instance_id 安全性
        if not re.match(r"^[\w-]+$", instance_id):
            raise ValueError(f"Invalid instance_id: {instance_id}")
        
        # 克隆仓库
        repo_url = f"https://github.com/{repo}.git"
        run_command(["git", "clone", repo_url, repo_dir], capture_output=True)
        
        # 切换到指定 SHA
        with cd(repo_dir):
            run_command(["git", "checkout", sha], capture_output=True)
        
        # 获取 major.minor 版本
        version = get_version_by_git(repo_dir)
        result["version"] = version
        
    except Exception as e:
        result["error"] = str(e)
        
    finally:
        # 清理临时目录
        if os.path.exists(repo_dir):
            shutil.rmtree(repo_dir, ignore_errors=True)
            
    return result

def process_repos(tasks: List[Dict], testbed: str, max_workers: int = 4) -> List[Dict]:
    """
    Process a list of repository tasks in parallel.
    """
    # 确保 testbed 目录存在
    os.makedirs(testbed, exist_ok=True)
    
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_task = {
            executor.submit(process_repo_task, task, testbed): task
            for task in tasks
        }
        
        for future in as_completed(future_to_task):
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                task = future_to_task[future]
                results.append({
                    "instance_id": task["instance_id"],
                    "error": f"Unexpected error: {str(e)}"
                })
                
    return results

def main():
    """
    Main function to parse arguments and process repositories.
    """
    parser = argparse.ArgumentParser(description="Clone GitHub repos, checkout SHA, get version, and clean up.")
    parser.add_argument(
        "--instance_path",
        type=str,
        required=True,
        help="Path to task instances file (.json or .jsonl)"
    )
    parser.add_argument(
        "--testbed",
        type=str,
        required=True,
        help="Base directory for temporary repositories"
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=4,
        help="Number of parallel workers (default: 4)"
    )
    
    args = parser.parse_args()
    
    # 读取任务
    try:
        tasks = get_instances(args.instance_path)
    except Exception as e:
        print(f"Error reading instances from {args.instance_path}: {e}")
        return
    
    # 验证任务格式
    required_fields = {"repo", "sha", "instance_id"}
    for task in tasks:
        if not all(field in task for field in required_fields):
            print(f"Invalid task format: {task}. Missing required fields: {required_fields}")
            return
    
    # 处理任务
    results = process_repos(tasks, args.testbed, args.max_workers)
    
    # 输出结果
    for result in results:
        print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()

def split_instances(input_list: list, n: int) -> list:
    """
    Split a list into n approximately equal length sublists

    Args:
        input_list (list): List to split
        n (int): Number of sublists to split into
    Returns:
        result (list): List of sublists
    """
    avg_length = len(input_list) // n
    remainder = len(input_list) % n
    result, start = [], 0

    for i in range(n):
        length = avg_length + 1 if i < remainder else avg_length
        sublist = input_list[start : start + length]
        result.append(sublist)
        start += length

    return result
