# Data Collection Process Overview

This directory provides code to collect raw issue data using GitHub APIs and predefined patterns. This implementation currently supports collecting issues from repositories in Python, Java, JavaScript, and TypeScript. We welcome PRs to support more languages!


1. **Fetch Popular Repositories**

    - Use the `get_top_repos.py` script to find and save a list of the most popular (by stars) repositories for a given language.

    - **Note**: This script requires a GitHub Personal Access Token to be set as an environment variable.

        Example:
        ```bash
        export GITHUB_TOKEN=<your_token> # Set your token first
        python get_top_repos.py --language Python --output_path data/popular_repos --top_n 100
        ```
        Where:
        - `--language:` The programming language to search for (e.g., 'Python', 'Java'). (Required)
        - `--output_path`: The directory where the output JSON file will be saved. (Required)
        - `--top_n`: The number of top-starred repositories to fetch (default: 500).
        - The output will be saved in the specified path, in a file named, for instance, python_top_100_repos.json. 

2. **Raw PR Data Collection**
   
    - Use the `print_pulls.py` script to collect raw PR data from GitHub repositories.
        
       Example:
       ```bash
       export GITHUB_TOKEN=<your_token> # Set your token first
       python print_pulls.py python-attrs/attrs data/python-attrs/attrs/prs.jsonl
       ```

       Where:
       - `<repo_name>`: GitHub repository name in "owner/repo" format (e.g., "octocat/Hello-World").
       - `<output_file>`: Path for the output JSONL file (e.g., "data/prs.jsonl").
       - `--token`: GitHub personal access token (defaults to the `GITHUB_TOKEN` environment variable).
       
3. **Raw Task Instance Construction**
    - Use the `build_dataset.py` script to process collected PR data and construct task instances.

       Example:
       ```bash
       export GITHUB_TOKEN=<your_token> # Set your token first
       python build_dataset.py data/python-attrs/attrs/prs.jsonl data/python-attrs/attrs/instances.jsonl --language python
       ```  

       Where:
       - `<pr_file>`: Path to the input PR JSONL file from the previous step.
       - `<output_file>`: Path for the output task instance JSONL file.
       - `--language`: The programming language of the repository. Accepts `python`, `java`, or `js`. Use `js` for both JavaScript and TypeScript repositories.
       - `--token`: Optional GitHub token (defaults to the `GITHUB_TOKEN` environment variable).

4. **Versioning**
   - Use the `get_version.py` script to assign version numbers to the raw instances.
   
   - **Note on Strategy**: The script employs an automated strategy to avoid manual work. It checks out the `base_commit` for each instance, gets a version string via the `git describe --tags` command, and then parses the version number from that output. This is effective for most repositories.
    
    Example:
     ```bash
     python get_version.py --instance_path data/python-attrs/attrs/instances.jsonl --testbed github --max-workers 20
     ```
     
     Where:
     - `--instance_path`: Path to the task instances file (required).
     - `--testbed`: A temporary working directory for cloning repositories.
     - `--max-workers`: The number of parallel processes to use (default: 10).
     - The results will be saved to a new file with a `_versions` suffix (e.g., `instances_versions.jsonl`).