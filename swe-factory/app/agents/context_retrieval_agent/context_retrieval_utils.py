import os
from typing import Dict, List, Any
from loguru import logger
import inspect
import re
from typing import Any
from app.data_structures import MessageThread
from app.model import common
from app.utils import parse_function_invocation
import json
from app.post_process import ExtractStatus, is_valid_json
import itertools
class RepoBrowseManager:
    def __init__(self, project_path: str):
        self.project_path = os.path.abspath(project_path)  # Ensure absolute path
        self.index: Dict = {}
        self._build_index()

    def _build_index(self):
        """Build the index by parsing the repository structure."""
        self._update_index(self.project_path)

    def _update_index(self, current_path: str):
        """Recursively update the index with files and directories."""
        for root, dirs, files in os.walk(current_path):
            relative_root = os.path.relpath(root, self.project_path)
            current_level = self.index
            if relative_root != ".":  # Handle nested directories
                for part in relative_root.split(os.sep):
                    if part not in current_level:
                        current_level[part] = {}
                    current_level = current_level[part]
            for file in files:
                current_level[file] = None  # Mark files as leaf nodes

    def browse_folder(self, path: str, depth: int) -> tuple[str, str, bool]:
        """Browse a folder in the repository from the given path and depth.
        
        Args:
            path: The folder path to browse, relative to the project root
            depth: How many levels deep to browse the folder structure
            
        Returns:
            A formatted string showing the folder structure
            
        Raises:
            ValueError: If the path is outside the project directory
        """
        if not path or path == "/":
            abs_path = self.project_path
        else:
            # Check if the path is an absolute path
            if os.path.isabs(path):
                abs_path = path  # If absolute, use it directly
            else:
                # If relative path, join with project root and convert to absolute
                abs_path = os.path.abspath(os.path.join(self.project_path, path))
    

        if not abs_path.startswith(self.project_path):
            return 'Path does not exist', 'Path does not exist',False
          
        
        relative_path = os.path.relpath(abs_path, self.project_path)
        if relative_path == ".":
            current_level = self.index
        else:
            current_level = self.index
            for part in relative_path.split(os.sep):
                if part not in current_level:
                    return "Path not found", "Path not found", False  # Path not found
                current_level = current_level[part]
        
        structure_result = self._get_structure(current_level, depth)
        structure = self._format_structure(structure_result)
        result = f"You are browsing the path: {abs_path}. The browsing Depth is {depth}.\nStructure of this path:\n\n{self._format_structure(structure_result)}"

        return result, 'folder structure collected', True


    def search_files_by_keyword(self, keyword: str) -> tuple[str, str, bool]:
        """Search for files in the repository whose names contain the given keyword.
        
        Args:
            keyword: The keyword to search for in file names
            
        Returns:
            tuple: (formatted result string, summary message, success flag)
        """
        matching_files = []
        self._search_index(self.index, keyword, "", matching_files)
        
        if not matching_files:
            return f"No files found containing the keyword '{keyword}'.", "No matching files found", True

        max_files = 50
        if len(matching_files) > max_files:
            result = f"Found {len(matching_files)} files containing the keyword '{keyword}'. Showing the first {max_files}:\n\n"
            matching_files = matching_files[:max_files]
        else:
            result = f"Found {len(matching_files)} files containing the keyword '{keyword}':\n\n"
        
        formatted_files = "\n".join([f"- {os.path.normpath(file)}" for file in matching_files])
        result += formatted_files
        return result, "File search completed successfully", True

    def _search_index(self, current_level: Dict, keyword: str, current_path: str, matching_files: List[str]):
        """Recursively search the index for files containing the keyword in their names."""
        for key, value in current_level.items():
            new_path = os.path.join(current_path, key)
            if value is None:  # It's a file
                if keyword.lower() in key.lower():
                    matching_files.append(new_path)
            else:  # It's a directory
                self._search_index(value, keyword, new_path, matching_files)

    def _get_structure(self, structure: Dict, depth: int) -> Dict:
        """Get the structure of the repository from the given path and depth."""
        if depth == 0:
            return {}
        result = {}
        for key, value in structure.items():
            if value is None:  # It's a file
                result[key] = None
            else:  # It's a directory
                result[key] = self._get_structure(value, depth - 1)
        return result

    def _format_structure(self, structure: Dict, indent: int = 0) -> str:
        """Format the structure into a string with proper indentation."""
        result = ""
        for key, value in structure.items():
            if value is None:  # It's a file
                result += "    " * indent + key + "\n\n"
            else:  # It's a directory
                result += "    " * indent + key + "/\n\n"
                result += self._format_structure(value, indent + 1)
        return result

    def browse_file(self, file_path: str) -> str:
        """Browse and return the contents of a specific file.
        
        Args:
            file_path: The path to the file to browse, relative to the project root
            
        Returns:
            The contents of the file as a string
            
        Raises:
            ValueError: If the file path is outside the project directory
            FileNotFoundError: If the file does not exist
        """
        # abs_path = os.path.abspath(file_path)
        # if not abs_path.startswith(self.project_path):
        #     raise ValueError(f"The file path {file_path} is not within the project path {self.project_path}.")
            
        # if not os.path.isfile(abs_path):
        #     raise FileNotFoundError(f"File not found: {file_path}")
            
        with open(file_path, 'r') as file:
            if file_path.endswith('package-lock.json'):
              
                lines = itertools.islice(file, 1000)
                content = ''.join(lines)
                content +='\nTruncated this file because it is too long.'
            else:
                content = file.read()
        return content

    def get_webpage_content(self, url: str, timeout: int = 60) -> str:
        """Fetch and return the content of a web page using Jina Reader API.
        
        Args:
            url: The URL of the web page to fetch
            timeout: Maximum time in seconds to wait for the response (default: 10)
            
        Returns:
            The content of the web page as a string
            
        Raises:
            ValueError: If the URL is invalid or the request fails
            TimeoutError: If the request times out
        """
        if not url.startswith(('http://', 'https://')):
            raise ValueError("Invalid URL - must start with http:// or https://")
            
        jina_reader_url = f"https://r.jina.ai/{url}"
        
        try:
            response = requests.get(jina_reader_url, timeout=timeout)
            response.raise_for_status()
            
            # Validate content type
            content_type = response.headers.get('Content-Type', '')
            if 'text/html' not in content_type and 'text/plain' not in content_type:
                raise ValueError(f"Unsupported content type: {content_type}")
                
            return response.text
            
        except requests.exceptions.Timeout:
            raise TimeoutError(f"Request timed out after {timeout} seconds")
        except requests.exceptions.RequestException as e:
            raise ValueError(f"Failed to fetch web content: {str(e)}")
        
    def browse_file_for_environment_info(self, file_path: str, custom_query: str = "") -> tuple[str, str, bool]:
        """Browse a file and extract environment setup information.
        
        Args:
            repo_browse_manager: Instance for managing repo browsing.
            file_path: The path to the file to browse, relative to the project root.
            
        Returns:
            A string containing extracted environment setup info.
        """
        try:
            logger.info('entering browse')
            # Step 1: Browse the file content
            file_content = self.browse_file(file_path)
            logger.info(f"{file_content}")
            file_content = f"The content of {file_path} is:\n"+file_content 
            # Step 2: Use LLM to extract environment information
            extracted_info = browse_file_run_with_retries(file_content, custom_query)

            # Step 3: Return extracted information
            return extracted_info,'Get File Info', True

        except ValueError as e:
            logger.info(f"Invalid file path: {str(e)}")
            return 'Invalid file path:','Invalid file path:', False
            
            # raise
        except FileNotFoundError as e:
            logger.info(f"File not found: {str(e)}")
            return 'File not found','File not found', False
            
            # raise
        except Exception as e:
            logger.info(f"Unexpected error browsing file: {str(e)}")
            return 'Unexpected error browsing file','Unexpected error browsing file', False
            
            # raise RuntimeError(f"Failed to browse file: {str(e)}") from e


    def browse_webpage_for_environment_info(self, url: str) -> str:
        """Fetch a web page and extract environment setup information.
        
        Args:
            repo_browse_manager: Instance for managing repo browsing.
            url: The URL of the web page to fetch and analyze.
            
        Returns:
            A string containing extracted environment setup info.
        """
        try:
            # Step 1: Fetch the webpage content
            webpage_content = self.get_webpage_content(url)
            
            # Step 2: Use LLM to extract environment information
            extracted_info = browse_file_run_with_retries(webpage_content)

            # Step 3: Return extracted information
            return extracted_info, 'Get Web Info', True

    
        except Exception as e:
            logger.info(f"Unexpected error browsing webpage: {str(e)}")
            return 'Unexpected error browsing web','Unexpected error browsing web', False



PROXY_PROMPT = """
You are an agent whose job is to:

1. **Extract API calls** from a context-retrieval analysis text.  
2. **Decide whether to terminate** the context-retrieval process.  

---

### Input
The text you receive is **an analysis of the context retrieval process**.  

The text will consist of two parts:
1. **Do we need to collect more context?**  
   - Identify if additional files, folders, or webpages should be browsed for environment setup details.
   - Extract API calls from this section (leave empty if none are needed).

2. **Should we terminate the context retrieval process?**  
   - If all necessary information has been collected, set `"terminate": true`.  
     - You should extract detailed collected information form analyssis of the context retrieval agent. This information will be used by other agent.
   - Otherwise, set `"terminate": false` and provide all collected details.

API List:

- browse_folder(path: str, depth: str): Browse and return the folder structure for a given path in the repository.  The depth is a string representing a number of folder levels to include in the output such as ``1''. 
- browse_file_for_environment_info(file_path: str, custom_query: str): Call an agent to browse a file such as README or CONTRIBUTING.md and extract environment setup and running tests information. Use the `custom_query` parameter to tell the agent any extra details it should pay special attention to (for example, 'pom.xml dependency versions').
- search_files_by_keyword(keyword: str): Search for files in the repository whose names contain the given keyword.

### **IMPORTANT RULES**:
- **Extract all relevant API calls from the text**:
  - If files like `requirements.txt`, `setup.cfg`, `setup.py` are mentioned, call `browse_file_for_environment_info()` on them.
  - If a directory needs exploration, use `browse_folder()`, ensuring `depth` defaults to `"1"` if unspecified.
- If the API call includes a path, the default format should use Linux-style with forward slashes (/).
- Ensure all API calls are valid Python expressions.
- browse_file_for_environment_info("path.to.file") should be written as browse_file_for_environment_info("path/to/file")
- the browse_folder API call MUST include the depth parameter, defaulting to "1" if not provided.
- You MUST ignore the argument placeholders in API calls. For example:
    Invalid Example: browse_folder(path="src", depth=1) 
    Valid Example: browse_folder("src",1)
- Provide your answer in JSON structure like this:
{
    "API_calls": ["api_call_1(args)", "api_call_2(args)", ...],
    "collected_information": <Content of collected information>.
    "terminate": true/false
}

"""


def proxy_apis_with_retries(text: str, retries=5) -> tuple[str | None, list[MessageThread]]:
    msg_threads = []
    for idx in range(1, retries + 1):
        logger.debug(
            "Trying to select search APIs in json. Try {} of {}.", idx, retries
        )

        res_text, new_thread = run_proxy(text)
        msg_threads.append(new_thread)
        res_text = extract_json_from_response(res_text)
        res_text = res_text.lstrip('```json').rstrip('```')
        logger.debug(res_text)
        extract_status, data = is_valid_json(res_text)

        if extract_status != ExtractStatus.IS_VALID_JSON:
            logger.debug("Invalid json. Will retry.")
            continue

        valid, diagnosis = is_valid_response_proxy(data)
        if not valid:
            logger.debug(f"{diagnosis}. Will retry.")
            continue

        logger.debug("Extracted a valid json")
        return res_text, msg_threads
    return None, msg_threads


def run_proxy(text: str) -> tuple[str, MessageThread]:
    """
    Run the agent to extract issue to json format.
    """

    msg_thread = MessageThread()
    msg_thread.add_system(PROXY_PROMPT)
    msg_thread.add_user(f'<analysis>\n{text}</analysis>')
    res_text, *_ = common.SELECTED_MODEL.call(
        msg_thread.to_msg(), response_format="json_object"
    )

    msg_thread.add_model(res_text, [])  # no tools

    return res_text, msg_thread


def is_valid_response_proxy(data: Any) -> tuple[bool, str]:
    if not isinstance(data, dict):
        return False, "Json is not a dict"

    if not data.get("terminate"):
        terminate = data.get("terminate")
        if terminate is None:
            return False, "'terminate' parameter is missing"

        if not isinstance(terminate, bool):
            return False, "'terminate' parameter must be a boolean (true/false)"

    else:
        if not data.get("collected_information"):
            summary = data.get("collected_information")
            if summary is None:
                return False, "'collected_information' parameter is missing"

            if not isinstance(summary, str):
                return False, "'collected_information' parameter must be a str"   

        for api_call in data["API_calls"]:
            if not isinstance(api_call, str):
                return False, "Every API call must be a string"

            try:
                func_name, func_args = parse_function_invocation(api_call)
            except Exception:
                return False, "Every API call must be of form api_call(arg1, ..., argn)"
            function = getattr( RepoBrowseManager, func_name, None)
            if function is None:
                return False, f"the API call '{api_call}' calls a non-existent function"

            arg_spec = inspect.getfullargspec(function)
            arg_names = arg_spec.args[1:]  # first parameter is self

            if len(func_args) != len(arg_names):
                return False, f"the API call '{api_call}' has wrong number of arguments"

    return True, "OK"


def extract_json_from_response(res_text: str):
    """
    从文本响应中提取 JSON 代码块
    """
    json_extracted = None

    # Pattern 1: 识别 ```json 标记的代码块
    json_matches = re.findall(r"```json([\s\S]*?)```", res_text, re.IGNORECASE)
    if json_matches:
        json_extracted = json_matches[0].strip()

    # Pattern 2: 识别普通的 ``` 代码块
    if not json_extracted:
        json_code_blocks = re.findall(r"```([\s\S]*?)```", res_text, re.IGNORECASE)
        for content in json_code_blocks:
            clean_content = content.strip()
            # 尝试解析为 JSON，确保是 JSON 格式
            try:
                json.loads(clean_content)  # 测试是否有效 JSON
                json_extracted = clean_content
                break
            except json.JSONDecodeError:
                continue  # 跳过非 JSON 代码块

    return json_extracted if json_extracted else res_text  # 返回提取的 JSON 或原始文本


BROWSE_CONTENT_PROMPT = """
You are an autonomous file-browsing and analysis agent. Now the user gives you a file, your overall mission is:
1. To review the given file content.
2. To extract any details necessary for setting up the project's environment and running its test suite.
3. To pay special attention to contents realted to custom query of user.

Primary objectives:
- Identify libraries, packages, and their versions.
- List any environment variables or configuration files.
- Extract the exact commands or scripts used to run tests, including flags/options.
- Note any prerequisites (e.g., required OS packages, language runtimes).

Formatting rules:
- Return your answer enclosed within `<analysis></analysis>` tags.
- Use bullet lists for clarity.
- Keep it concise and human-readable.
- Preserve original value formats (e.g., version strings, paths, flags).

Example format:
<analysis>
List of libraries:
- flask==2.0.3
- gunicorn
- pytest==7.1.2

Key environment variables:
- DEBUG=true
- SECRET_KEY=this-is-a-secret

Runtime Requirements:
- Python >=3.8
- Node.js 16.x

Testing:
- Test framework: pytest
- Test command: pytest tests/ --disable-warnings --maxfail=5
</analysis>
"""

def browse_file_run_with_retries(content: str, custom_query: str, retries: int=3) -> str | None:
    """Run file content analysis with retries and return the parsed <analysis> content."""
    parsed_result=None
    for idx in range(1, retries + 1):
        logger.debug("Analyzing file content. Try {} of {}", idx, retries)
        
        res_text, _ = browse_file_run(content, custom_query)

        # Extract <analysis> content if valid
        parsed_result = parse_analysis_tags(res_text)
        if parsed_result:
            logger.success("Successfully extracted environment config")
            logger.info("*"*6)
            logger.info(parsed_result)
            logger.info("*"*6)
            return parsed_result
        else:
            content += 'Please wrap result in clean xml identifier, do not use ```to wrap results. '
            logger.debug(res_text)
            logger.debug("Invalid response or missing <analysis> tags, retrying...")
    if parsed_result:
        return parsed_result
    else:
        return 'Do not get the content of the file.'


def browse_file_run(content: str, custom_query: str) -> tuple[str, MessageThread]:
    """Run the simplified content analysis agent."""
    msg_thread = MessageThread()
    msg_thread.add_system(BROWSE_CONTENT_PROMPT)
    msg_thread.add_user(f"File content:\n{content}\n")  # Truncate to prevent overflow
    msg_thread.add_user(f"Custom query from user:\n{custom_query}\n") 
    res_text, *_ = common.SELECTED_MODEL.call(
        msg_thread.to_msg()
    )
    msg_thread.add_model(res_text, [])
    return res_text, msg_thread


def parse_analysis_tags(data: str) -> str | None:
    """Extract and return the content within <analysis>...</analysis> tags."""
    pattern = r"<analysis>([\s\S]+?)</analysis>"
    match = re.search(pattern, data)
    if match:
        return match.group(1).strip()  # Return the content inside <analysis> tags
    return None




SYSTEM_PROMPT = """You are a repository maintainer responsible for ensuring that new pull requests can be properly tested.  
A developer has submitted a pull request containing a **test patch**, which introduces or modifies test cases.  
Before running the tests, we need to ensure that the environment is correctly set up.  

Your role is to **gather all necessary information** about the repository's environment and testing setup.  
This information will be used to generate:
- A **Dockerfile** that correctly configures the environment.
- An **evaluation script** that executes the provided test files.

### What you need to do:
1. **Understand the environment setup**  
   - Identify required dependencies (e.g., `pip`, `conda`, `npm`, `apt`, `yum`).  
   - Find out language versions (e.g., Python 3.9, Node.js 18, Java 17).  
   - Look for configuration files (`.env`, environment variables, setup scripts).  
   - Review existing setup files (`pow.xml`, `setup.py`, CI/CD config, etc.).  
   - Check OS requirements (We use Linux here, pay more attention to ).  

2. **Determine how to execute the tests**  
   - You will be provided with a list of test files that need to be run.  
   - Find out the correct way to execute these tests (e.g., `pytest tests/test_x.py`, `npm test`, `make test`).  
   - Identify any required setup steps before running the tests (e.g., database migrations, service startups).  

3. **Provide structured information**  
   - Organize your findings so that other agents can use them to generate the Dockerfile and evaluation script.  

### Important Notes:
- The repository has already been **cloned locally**; you are working within the local repository directory.  
- **The pull request has NOT been applied yet**, so you should analyze the repository in its current state.  
- **Focus on what is needed to set up the environment and run the tests successfully.**  

Start by checking the repository structure, configuration files, and dependency manifests.  
Your objective is to ensure that the necessary environment is in place and that the test files can be executed reliably in an isolated container."""

USER_PROMPT = (
        "Your task is to gather sufficient context from the repository and external sources to understand how to set up the project's environment. To achieve this, you can use the following APIs to browse and extract relevant information:"
        "\n- browse_folder(path: str, depth: str): Browse and return the folder structure for a given path in the repository.  The depth is a string representing a number of folder levels to include in the output such as ``1''. "
        "\n- browse_file_for_environment_info(file_path: str, custom_query: str): Call an agent to browse a file such as README or CONTRIBUTING.md and extract environment setup and running tests information. Use the `custom_query` parameter to tell the agent any extra details it should pay special attention to (for example, 'pom.xml dependency versions')."
        "\n- search_files_by_keyword(keyword: str): Search for files in the repository whose names contain the given keyword."
        "\n\nYou may invoke multiple APIs in one round as needed to gather the required information."
        "\n\nNow analyze the repository and use the necessary APIs to gather the information required to understand and set up the environment. Ensure each API call has concrete arguments as inputs."
        )