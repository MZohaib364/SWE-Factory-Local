import json
import os
from pathlib import Path
import re
import requests

import fnmatch
from argparse import ArgumentTypeError
from datasets import Dataset, load_dataset
from datetime import datetime
from dotenv import load_dotenv
from functools import cache
# from git import Repo
from typing import cast
from typing import TypedDict
# from constants import (
#     SWEbenchInstance,
#     MAP_REPO_TO_ENV_YML_PATHS,
#     MAP_REPO_TO_REQS_PATHS,
#     NON_TEST_EXTS,
#     SWE_BENCH_URL_RAW,
# )

load_dotenv()

# Constants - Task Instance Class
class SWEbenchInstance(TypedDict):
    repo: str
    instance_id: str
    base_commit: str
    patch: str
    test_patch: str
    problem_statement: str
    hints_text: str
    created_at: str
    version: str
    FAIL_TO_PASS: str
    PASS_TO_PASS: str
    environment_setup_commit: str
    dockerfile: str
    eval_script: str

def load_omnigirl_dataset(name="princeton-nlp/SWE-bench", split="test") -> list[SWEbenchInstance]:
    """
    Load SWE-bench dataset from Hugging Face Datasets or local .json/.jsonl file
    """
    # Load from local .json/.jsonl file
    if name.endswith(".json"):
        return [
            cast(SWEbenchInstance, instance)
            for instance in json.loads(Path(name).read_text())
        ]
    elif name.endswith(".jsonl"):
        return [
            cast(SWEbenchInstance, json.loads(line.strip()))
            for line in Path(name).read_text().splitlines()
        ]

    # Load from Hugging Face Datasets
    if name.lower() in {"swe-bench", "swebench", "swe_bench"}:
        name = "princeton-nlp/SWE-bench"
    elif name.lower() in {"swe-bench-lite", "swebench-lite", "swe_bench_lite", "swe-bench_lite", "lite"}:
        name = "princeton-nlp/SWE-bench_Lite"
    dataset = cast(Dataset, load_dataset(name, split=split))
    return [cast(SWEbenchInstance, instance) for instance in dataset]


### MARK - Patch Correction
PATCH_PATTERN = re.compile(
    r"(?:diff[\w\_\.\ \/\-]+\n)?\-\-\-\s+a\/(?:.*?)\n\+\+\+\s+b\/(?:.*?)(?=diff\ |\-\-\-\ a\/|\Z)",
    re.DOTALL,
)
PATCH_FILE_PATTERN = re.compile(r"\-\-\-\s+a\/(?:.+)\n\+\+\+\s+b\/(?:.+)")
PATCH_HUNK_PATTERN = re.compile(
    r"\@\@\s+\-(\d+),(\d+)\s+\+(\d+),(\d+)\s+\@\@(.+?)(?=diff\ |\-\-\-\ a\/|\@\@\ \-|\Z)",
    re.DOTALL,
)


def get_first_idx(charlist):
    """Get index of first occurrence of "-" or "+" in charlist"""
    first_min = charlist.index("-") if "-" in charlist else len(charlist)
    first_plus = charlist.index("+") if "+" in charlist else len(charlist)
    return min(first_min, first_plus)


def get_last_idx(charlist):
    """Get index of last occurrence of "-" or "+" in charlist"""
    char_idx = get_first_idx(charlist[::-1])
    last_idx = len(charlist) - char_idx
    return last_idx + 1


def strip_content(hunk):
    """Remove trailing non +/- lines and trailing whitespace per line per hunk"""
    first_chars = list(map(lambda x: None if not len(x) else x[0], hunk.split("\n")))
    first_idx = get_first_idx(first_chars)
    last_idx = get_last_idx(first_chars)
    new_lines = list(map(lambda x: x.rstrip(), hunk.split("\n")[first_idx:last_idx]))
    new_hunk = "\n" + "\n".join(new_lines) + "\n"
    return new_hunk, first_idx - 1


def get_hunk_stats(pre_start, pre_len, post_start, post_len, hunk, total_delta):
    """Recalculate hunk start/end position and diff delta"""
    stats = {"context": 0, "added": 0, "subtracted": 0}
    hunk = hunk.split("\n", 1)[-1].strip("\n")
    for line in hunk.split("\n"):
        if line.startswith("-"):
            stats["subtracted"] += 1
        elif line.startswith("+"):
            stats["added"] += 1
        else:
            stats["context"] += 1
    context = stats["context"]
    added = stats["added"]
    subtracted = stats["subtracted"]
    pre_len = context + subtracted
    post_start = pre_start + total_delta
    post_len = context + added
    total_delta = total_delta + (post_len - pre_len)
    return pre_start, pre_len, post_start, post_len, total_delta


def extract_minimal_patch(model_patch):
    """
    Wrapper function that takes hunk and
    * Removes trailing non +/- lines and trailing whitespace per line per hunk
    * Recalculates hunk start/end position and diff delta
    * Returns new patch
    """
    model_patch = model_patch.lstrip("\n")
    new_patch = ""
    for patch in PATCH_PATTERN.findall(model_patch):
        total_delta = 0
        patch_header = PATCH_FILE_PATTERN.findall(patch)[0]
        if patch_header:
            new_patch += patch_header + "\n"
        for hunk in PATCH_HUNK_PATTERN.findall(patch):
            pre_start, pre_len, post_start, post_len, content = hunk
            pre_start, pre_len, post_start, post_len, content = list(
                map(lambda x: int(x) if x.isnumeric() else x, hunk)
            )
            content, adjust_pre_start = strip_content(content)
            pre_start += adjust_pre_start
            pre_start, pre_len, post_start, post_len, total_delta = get_hunk_stats(
                pre_start, pre_len, post_start, post_len, content, total_delta
            )
            new_patch += (
                f"@@ -{pre_start},{pre_len} +{post_start},{post_len} @@{content}"
            )
    return new_patch


def has_attribute_or_import_error(log_before):
    """
    Check to see if Attribute/Import-prefix is in log text

    Args:
        log_before (str): Validation log text before patch application
    """
    log_before = log_before.lower()

    if any([x in log_before for x in ["attribute", "import"]]):

        def get_lines_with_word(text, target_word):
            # Function to extract line(s) that contains target_word
            text, target_word = text.lower(), target_word.lower()
            lines, hits = text.split("\n")[::-1], []
            for line in lines:
                if target_word in line:
                    hits.append(line)
            return hits

        # Get line with Attribute/Import error
        lines_1 = get_lines_with_word(log_before, "attribute")
        lines_2 = get_lines_with_word(log_before, "import")
        lines_1 = " ".join(lines_1)
        lines_2 = " ".join(lines_2)

        if any([(x in lines_1 or x in lines_2) for x in ["error", "fail"]]):
            return True
    return False


# @cache
# def get_environment_yml_by_commit(repo: str, commit: str, env_name: str) -> str:
#     for req_path in MAP_REPO_TO_ENV_YML_PATHS[repo]:
#         reqs_url = os.path.join(SWE_BENCH_URL_RAW, repo, commit, req_path)
#         reqs = requests.get(reqs_url)
#         if reqs.status_code == 200:
#             break
#     else:
#         raise ValueError(
#             f"Could not find environment.yml at paths {MAP_REPO_TO_ENV_YML_PATHS[repo]} for repo {repo} at commit {commit}"
#         )

#     lines = reqs.text.split("\n")
#     cleaned = []
#     for line in lines:
#         # Rename environment to given name
#         if line.startswith("name:"):
#             cleaned.append(f"name: {env_name}")
#             continue
#         cleaned.append(line)

#     return "\n".join(cleaned)


# def get_environment_yml(instance: SWEbenchInstance, env_name: str) -> str:
#     """
#     Get environment.yml for given task instance

#     Args:
#         instance (dict): SWE Bench Task instance
#         env_name (str): Rename retrieved environment.yml to this name
#     Returns:
#         environment.yml (str): Returns environment.yml as string
#     """
#     # Attempt to find environment.yml at each path based on task instance's repo

#     commit = (
#         instance["environment_setup_commit"]
#         if "environment_setup_commit" in instance
#         else instance["base_commit"]
#     )

#     return get_environment_yml_by_commit(instance["repo"], commit, env_name)


# @cache
# def get_requirements_by_commit(repo: str, commit: str) -> str:
#     for req_path in MAP_REPO_TO_REQS_PATHS[repo]:
#         # if 'mypy' in repo:
           
#         #     reqs_url = os.path.join('https://raw.githubusercontent.com', repo,'blob', commit, req_path)
#         # else:
#         reqs_url = os.path.join(SWE_BENCH_URL_RAW, repo, commit, req_path)
#         # print(reqs_url)
#         # input()
#         reqs = requests.get(reqs_url)
#         if reqs.status_code == 200:
#             break
#     else:
#         raise ValueError(
#             f"Could not find requirements.txt at paths {MAP_REPO_TO_REQS_PATHS[repo]} for repo {repo} at commit {commit}"
#         )

#     lines = reqs.text
#     original_req = []
#     additional_reqs = []
#     req_dir = "/".join(req_path.split("/")[:-1])
#     exclude_line = lambda line: any(
#         [line.strip().startswith(x) for x in ["-e .", "#", ".[test"]]
#     )

#     for line in lines.split("\n"):
#         if line.strip().startswith("-r"):
#             # Handle recursive requirements
#             file_name = line[len("-r") :].strip()
#             reqs_url = os.path.join(
#                 SWE_BENCH_URL_RAW,
#                 repo,
#                 commit,
#                 req_dir,
#                 file_name,
#             )
#             reqs = requests.get(reqs_url)
#             if reqs.status_code == 200:
#                 for line_extra in reqs.text.split("\n"):
#                     if not exclude_line(line_extra):
#                         additional_reqs.append(line_extra)
#         else:
#             if not exclude_line(line):
#                 original_req.append(line)

#     # Combine all requirements into single text body
#     additional_reqs.append("\n".join(original_req))
#     all_reqs = "\n".join(additional_reqs)

#     return all_reqs


def get_requirements(instance: SWEbenchInstance) -> str:
    """
    Get requirements.txt for given task instance

    Args:
        instance (dict): task instance
    Returns:
        requirements.txt (str): Returns requirements.txt as string
    """
    # Attempt to find requirements.txt at each path based on task instance's repo
    commit = (
        instance["environment_setup_commit"]
        if "environment_setup_commit" in instance
        else instance["base_commit"]
    )

    return get_requirements_by_commit(instance["repo"], commit)





def generate_pytest_command(test_file_path: str) -> str:
    test_file_mapping = [
        ("check-*.test", "testcheck.py", "TypeCheckSuite",'mypy'),  
        ("cmdline*.test", "testcmdline.py", "PythonCmdlineSuite",'mypy'),  
        ("daemon.test", "testdaemon.py", "DaemonSuite",'mypy'),  
        ("fine-grained-cache*.test", "testfinegrainedcache.py", "FineGrainedCacheSuite",'mypy'),  
        ("fine-grained*.test", "testfinegrained.py", "FineGrainedSuite",'mypy'),  
        ("semanal-error*.test", "testsemanal.py", "SemAnalErrorSuite",'mypy'),  
        ("semanal-symtable*.test", "testsemanal.py", "SemAnalSymtableSuite",'mypy'),  
        ("semanal-typeinfo*.test", "testsemanal.py", "SemAnalTypeInfoSuite",'mypy'),  
        ("semanal-*.test", "testsemanal.py", "SemanticAnalyzerSuite",'mypy'),  
        ("deps.test", "testdeps.py", "GetDependenciesSuite",'mypy'), 
        ("deps-*.test", "testdeps.py", "GetDependenciesSuite",'mypy'),  
        ("diff.test", "testdiff.py", "ASTDiffSuite",'mypy'),  
        ("pep561.test", "testpep561.py", "PEP561Suite",'mypy'),  
        ("pythoneval*.test", "testpythoneval.py", "PythonEvaluationSuite",'mypy'),  
        ("ref-info.test", "test_ref_info.py", "RefInfoSuite",'mypy'),  
        ("reports.test", "testreports.py", "CoberturaReportSuite",'mypy'),  
        ("stubgen.test", "teststubgen.py", "StubgenPythonSuite",'mypy'),  
        ("errorstream.test", "testerrorstream.py", "ErrorStreamSuite",'mypy'),  
        ("merge.test", "testmerge.py", "ASTMergeSuite",'mypy'),  
        ("outputjson.test", "testoutput.py", "OutputJSONsuite",'mypy'),  
        ("pythoneval.test","testpythoneval.py","PythonEvaluationSuite",'mypy'),
        ("python2eval.test","testpythoneval.py","PythonEvaluationSuite",'mypy'),
        ("pythoneval-asyncio.test","testpythoneval.py","PythonEvaluationSuite",'mypy'),
        ("parse*.test", "testparse.py", "ParseSuite",'mypy'),  
        ('typexport-basic*.test','testtypegen.py','TypeExportSuite','mypy'),
        ("alwaysdefined.test", "test_alwaysdefined.py", "TestAlwaysDefined",'mypyc'),  
        ("analysis.test", "test_analysis.py", "TestAnalysis",'mypyc'),  
        ("commandline.test", "test_commandline.py", "TestCommandLine",'mypyc'),  
        ("exceptions*.test", "test_exceptions.py", "TestExceptionTransform",'mypyc'),  
   
        ("irbuild-*.test", "test_irbuild.py", "TestGenOps",'mypyc'),  
        # ("ircheck.test", "test_ircheck.py", "IRCheckSuite"),  
        # ("literals.test", "test_literals.py", "LiteralsSuite"),  
        ("lowering-*.test", "test_lowering.py", "TestLowering",'mypyc'),  
        # ("namegen.test", "test_namegen.py", "NameGenSuite"),  
        ("opt-copy-propagation.test", "test_optimizations.py", "TestCopyPropagation",'mypyc'),  
        ("opt-flag-elimination.test", "test_optimizations.py", "TestFlagElimination",'mypyc'),  
        # ("pprint.test", "test_pprint.py", "PPrintSuite"),  
        # ("rarray.test", "test_rarray.py", "RArraySuite"),  
        ("refcount.test", "test_refcount.py", "TestRefCountTransform",'mypyc'),  
        ("run-*.test", "test_run.py", "TestRun",'mypyc'),  
        # ("serialization.test", "test_serialization.py", "SerializationSuite"),  
        # ("struct.test", "test_struct.py", "StructSuite"),  
        ("tuplename.test", "test_tuplename.py", "TupleNameSuite",'mypyc'),  
        ("typeops.test", "test_typeops.py", "TypeOpsSuite",'mypyc')  
        # ("testutil.test", "testutil.py", "TestUtilSuite")
    ]

    test_file_name = os.path.basename(test_file_path)
    
    for pattern, test_py, suite_class,prefix in test_file_mapping:
        if fnmatch.fnmatch(test_file_name, pattern):
      
            pytest_command = f"{prefix}/test/{test_py}::{suite_class}::{test_file_name}"
       
            return pytest_command
    print(test_file_path)
    raise ValueError(f"No matching test suite for the test file: {test_file_path}")


# Add C++/cpp test command generation

def generate_cpp_test_command(test_file_path: str) -> str:
    """
    Generate a plausible C++ test command for a given test file path.
    For Catch2/GoogleTest, typically the test binary is built and run directly, or ctest is used.
    """
    # Assume test binaries are built in build/tests or build/
    # For Catch2, often ctest is used after cmake build
    # For GoogleTest, test binaries are run directly
    # This is a heuristic; you may want to customize per repo
    import os
    test_file = os.path.basename(test_file_path)
    test_name = os.path.splitext(test_file)[0]
    # Common convention: test binary named after test file, or all tests run via ctest
    return f"ctest --output-on-failure"  # Default to ctest for C++


def get_test_directives(instance):
    """
    Get test directives from the test_patch of a task instance.
    For C++/cpp repos, extract .cpp test files and return plausible test commands.
    """
    import re
    repo = instance.get('repo', '').lower()
    test_patch = instance.get('test_patch', '')
    diff_pat = r"diff --git a/.* b/(.*)"
    directives = re.findall(diff_pat, test_patch)
    # Remove non-test files for C++
    if 'catchorg/catch2' in repo or 'cpp' in repo or 'c++' in repo:
        # Heuristic: test files are in tests/ or end with _test.cpp, Test*.cpp, etc.
        cpp_test_files = [d for d in directives if (
            d.endswith('.cpp') and (
                '/test' in d or '/tests' in d or d.lower().startswith('test') or d.lower().endswith('_test.cpp') or d.lower().endswith('test.cpp')
            )
        )]
        # For Catch2, recommend ctest (after cmake build)
        if 'catchorg/catch2' in repo:
            return ['ctest --output-on-failure']
        # Otherwise, return plausible test binary run commands
        return [f'./build/tests/{os.path.splitext(os.path.basename(f))[0]}' for f in cpp_test_files] if cpp_test_files else ['ctest --output-on-failure']
    # Fallback to default (Python/JS/Java)
    # ... existing code for other languages ...
    return directives


def str2bool(v):
    """
    Minor helper function to convert string to boolean
    """
    if isinstance(v, bool):
        return v
    if v.lower() in ("yes", "true", "t", "y", "1"):
        return True
    elif v.lower() in ("no", "false", "f", "n", "0"):
        return False
    else:
        raise ArgumentTypeError("Boolean value expected.")
