from __future__ import annotations

import docker
import json
import resource
import traceback
import os
from argparse import ArgumentParser
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from tqdm import tqdm
from docker import DockerClient
# from constants import (
#     # APPLY_PATCH_FAIL,
#     # APPLY_PATCH_PASS,
#     INSTANCE_IMAGE_BUILD_DIR,
#     RUN_INSTANCE_LOG_DIR,
# )
import re
from docker_utils import (
    remove_image,
    copy_to_container,
    exec_run_with_timeout,
    cleanup_container,
    list_images,
    should_remove,
    clean_images,
)
from docker_build import (
    build_container,
    build_setup_container,
    build_env_images,
    close_logger,
    setup_logger,
)
# from grading import get_pred_report
from test_spec import make_test_spec, TestSpec
from utils import load_omnigirl_dataset, str2bool

APPLY_PATCH_FAIL = ">>>>> Patch Apply Failed"
APPLY_PATCH_PASS = ">>>>> Patch Apply Passed"

class EvaluationError(Exception):
    def __init__(self, instance_id, message, logger):
        super().__init__(message)
        self.instance_id = instance_id
        self.log_file = logger.log_file
        self.logger = logger

    def __str__(self):
        log_msg = traceback.format_exc()
        self.logger.info(log_msg)
        return (
            f"{self.instance_id}: {super().__str__()}\n"
            f"Check ({self.log_file}) for more information."
        )

def run_instance_fail_to_pass(
        test_spec: TestSpec,
        pred: dict,
        rm_image: bool,
        force_rebuild: bool,
        client: docker.DockerClient,
        run_id: str,
        output_path: str,
        timeout: int|None = None,
        
    ):

    run_instance_setup(test_spec,pred,False,force_rebuild,client,run_id,output_path,"not_apply_patch",timeout)
    run_instance_setup(test_spec,pred,rm_image,False,client,run_id,output_path,"apply_patch",timeout)

def get_pred_report(
    test_spec: TestSpec,
    prediction: dict[str, str],
    test_output_path: str
) -> dict[str, Any]:

    report_map = {}

    instance_id = prediction["instance_id"]
    if instance_id not in report_map:
        report_map[instance_id] = {
            "patch_is_None": False,
            "patch_exists": False,
            "patch_successfully_applied": False,
            "resolved": False,
        }

    # Check if the model patch exists
    if prediction["model_patch"] is None:
        report_map[instance_id]["patch_is_None"] = True
        return report_map
    report_map[instance_id]["patch_exists"] = True

    test_output_path = Path(test_output_path)
    test_output_content = ""
    run_instance_log_content = ""

    if test_output_path.exists():
        with open(test_output_path, "r", encoding="utf-8") as f:
            test_output_content = f.read()
    else:
        print(f"[WARN] Test output file not found: {test_output_path}")

    run_instance_log_path = test_output_path.parent / "run_instance_after_apply.log"
    if run_instance_log_path.exists():
        with open(run_instance_log_path, "r", encoding="utf-8") as f:
            run_instance_log_content  = f.read()
    else:
        print(f"[WARN] Run instance log file not found: {run_instance_log_path}")

    if run_instance_log_content:
        if APPLY_PATCH_PASS in run_instance_log_content:
            report_map[instance_id]["patch_successfully_applied"] = True
        elif APPLY_PATCH_FAIL in run_instance_log_content:
            report_map[instance_id]["patch_successfully_applied"] = False
        else:
            print(f"[WARN] No patch status found in run instance log for {instance_id}")
    else:
        print(f"[WARN] Empty run instance log content for {instance_id}")

    
    EXIT_CODE_RE = re.compile(r"echo OMNIGRIL_EXIT_CODE=(\d)")

    if test_output_content:
        match = EXIT_CODE_RE.search(test_output_content)
        if match:
            exit_code = match.group(1)
            if exit_code == "0":
                report_map[instance_id]["resolved"] = True
        else:
            print(f"[WARN] No exit code found in test output for {instance_id}")
    else:
        print(f"[WARN] Empty test output content for {instance_id}")
    
    
    return report_map

def run_instance_setup(
        test_spec: TestSpec,
        pred: dict,
        rm_image: bool,
        force_rebuild: bool,
        client: docker.DockerClient,
        run_id: str,
        output_path: str,
        mode: str,
        timeout: int|None = None,
        
    ):
    """
    Run a single instance with the given prediction.

    Args:
        test_spec (TestSpec): TestSpec instance
        pred (dict): Prediction w/ model_name_or_path, model_patch, instance_id
        rm_image (bool): Whether to remove the image after running
        force_rebuild (bool): Whether to force rebuild the image
        client (docker.DockerClient): Docker client
        run_id (str): Run ID
        timeout (int): Timeout for running tests
    """
    # Set up logging directory

    instance_id = test_spec.instance_id
    model_name_or_path = pred.get("model_name_or_path", "None").replace("/", "__")
    log_dir = Path(output_path) / run_id / model_name_or_path / instance_id
    log_dir.mkdir(parents=True, exist_ok=True)

    # Link the image build dir in the log dir
    build_dir = Path(output_path) / test_spec.instance_image_key.replace(":", "__")
    # image_build_link = log_dir / "image_build_dir"
    # if not image_build_link.exists():
    #     try:
    #         # link the image build dir in the log dir
    #         image_build_link.symlink_to(build_dir, target_is_directory=True)
    #     except:
    #         # some error, idk why
    #         pass
    # report_path = log_dir / "report.json"
    # if report_path.exists():
    #     return instance_id, json.loads(report_path.read_text())
    # logger = setup_logger(instance_id, log_file)
    run_instance_log_name = "run_instance_prev_apply.log" if mode == "not_apply_patch" else "run_instance_after_apply.log"
    log_file = log_dir / run_instance_log_name

    # Set up report file + logger
    report_path = log_dir / "report.json"
    if report_path.exists():
        return instance_id, json.loads(report_path.read_text())
    logger = setup_logger(instance_id, log_file)

    # Run the instance
    container = None
    try:
        # Build + start instance container (instance image should already be built)
        container = build_setup_container(test_spec, client, run_id, logger, rm_image, log_dir, force_rebuild)
        container.start()
     
        logger.info(f"Container for {instance_id} started: {container.id}")
        
        # Copy model prediction as patch file to container
        patch_file = Path(log_dir / "patch.diff")
        patch_file.write_text(test_spec.patch or "")
        logger.info(
            f"Intermediate patch for {instance_id} written to {patch_file}, now applying to container..."
        )
        copy_to_container(container, patch_file, Path("/tmp/patch.diff"))
        if mode  != 'not_apply_patch':
            # Attempt to apply patch to container
            val = container.exec_run(
                "git apply --allow-empty -v /tmp/patch.diff",
                workdir="/testbed",
                user="root",
            )
            if val.exit_code != 0:
                logger.info(f"Failed to apply patch to container, trying again...")
                
                # try "patch --batch --fuzz=5 -p1 -i {patch_path}" to try again
                val = container.exec_run(
                    "patch --batch --fuzz=5 -p1 -i /tmp/patch.diff",
                    workdir="/testbed",
                    user="root",
                )
                if val.exit_code != 0:
                    logger.info(f"{APPLY_PATCH_FAIL}:\n{val.output.decode('utf-8')}")
                    raise EvaluationError(
                        instance_id,
                        f"{APPLY_PATCH_FAIL}:\n{val.output.decode('utf-8')}",
                        logger,
                    )
                else:
                    logger.info(f"{APPLY_PATCH_PASS}:\n{val.output.decode('utf-8')}")
            else:
                logger.info(f"{APPLY_PATCH_PASS}:\n{val.output.decode('utf-8')}")


        eval_file = Path(log_dir / "eval.sh")
        eval_file.write_text(test_spec.eval_script)
        logger.info(
            f"Eval script for {instance_id} written to {eval_file}, now applying to container..."
        )
        copy_to_container(container, eval_file, Path("/eval.sh"))

        # Run eval script, write output to logs
        result = exec_run_with_timeout(container, "/bin/bash /eval.sh", timeout=timeout)
        test_output = result.decode("utf-8")
        test_output_name = "test_output_prev_apply.txt" if mode == "not_apply_patch" else "test_output_after_apply.txt"
        test_output_path = log_dir / test_output_name
        with open(test_output_path, "w") as f:
            f.write(test_output)
        logger.info(f"Test output for {instance_id} written to {test_output_path}")

        if mode  != 'not_apply_patch':
            logger.info(f"Grading answer for {instance_id}...")
            report = get_pred_report(
                test_spec=test_spec,
                prediction=pred,
                test_output_path=str(test_output_path)
            )
            logger.info(
                f"report: {report}\n"
                f"Result for {instance_id}: resolved: {report[instance_id]['resolved']}"
            )

            # Write report to report.json
            with open(report_path, "w") as f:
                f.write(json.dumps(report, indent=4))
        else:
            report = None
            
        return instance_id, report
    except EvaluationError as e:
        error_msg = (f"EvaluationError {instance_id}: {e}\n"
                     f"{traceback.format_exc()}\n"
                     f"Check ({logger.log_file}) for more information.")
        logger.info(error_msg)
        print(error_msg)
    except Exception as e:
        error_msg = (f"Error in evaluating model for {instance_id}: {e}\n"
                     f"{traceback.format_exc()}\n"
                     f"Check ({logger.log_file}) for more information.")
        logger.info(error_msg)
        print(error_msg)
    finally:
        # Remove instance container + image, close logger
        cleanup_container(client, container, logger)
        if rm_image:
            remove_image(client, test_spec.instance_image_key, logger)
        close_logger(logger)

def run_instance(
        test_spec: TestSpec,
        pred: dict,
        rm_image: bool,
        force_rebuild: bool,
        client: docker.DockerClient,
        run_id: str,
        output_path: str,
        timeout: int|None = None,
        
    ):
    """
    Run a single instance with the given prediction.

    Args:
        test_spec (TestSpec): TestSpec instance
        pred (dict): Prediction w/ model_name_or_path, model_patch, instance_id
        rm_image (bool): Whether to remove the image after running
        force_rebuild (bool): Whether to force rebuild the image
        client (docker.DockerClient): Docker client
        run_id (str): Run ID
        timeout (int): Timeout for running tests
    """
    # Set up logging directory

    instance_id = test_spec.instance_id
    model_name_or_path = pred.get("model_name_or_path", "None").replace("/", "__")
    log_dir = output_path / run_id / model_name_or_path / instance_id
    log_dir.mkdir(parents=True, exist_ok=True)

    # Link the image build dir in the log dir
    build_dir = output_path / test_spec.instance_image_key.replace(":", "__")
    # image_build_link = log_dir / "image_build_dir"
    # if not image_build_link.exists():
    #     try:
    #         # link the image build dir in the log dir
    #         image_build_link.symlink_to(build_dir, target_is_directory=True)
    #     except:
    #         # some error, idk why
    #         pass
    log_file = log_dir / "run_instance.log"

    # Set up report file + logger
    report_path = log_dir / "report.json"
    if report_path.exists():
        return instance_id, json.loads(report_path.read_text())
    logger = setup_logger(instance_id, log_file)

    # Run the instance
    container = None
    try:
        # Build + start instance container (instance image should already be built)
        container = build_setup_container(test_spec, client, run_id, logger, rm_image, output_path, force_rebuild)
        container.start()
        # if 'redis' in run_id:
        #     client = DockerClient()
        #     network = client.networks.get("redis-py_default")
        #     network.connect(container)
        logger.info(f"Container for {instance_id} started: {container.id}")
        
        # Copy model prediction as patch file to container
        patch_file = Path(log_dir / "patch.diff")
        patch_file.write_text(test_spec.patch or "")
        logger.info(
            f"Intermediate patch for {instance_id} written to {patch_file}, now applying to container..."
        )
        copy_to_container(container, patch_file, Path("/tmp/patch.diff"))
        if pred["model_patch"] != 'none':
            # Attempt to apply patch to container
            val = container.exec_run(
                "git apply --allow-empty -v /tmp/patch.diff",
                workdir="/testbed",
                user="root",
            )
            if val.exit_code != 0:
                logger.info(f"Failed to apply patch to container, trying again...")
                
                # try "patch --batch --fuzz=5 -p1 -i {patch_path}" to try again
                val = container.exec_run(
                    "patch --batch --fuzz=5 -p1 -i /tmp/patch.diff",
                    workdir="/testbed",
                    user="root",
                )
                if val.exit_code != 0:
                    logger.info(f"{APPLY_PATCH_FAIL}:\n{val.output.decode('utf-8')}")
                    raise EvaluationError(
                        instance_id,
                        f"{APPLY_PATCH_FAIL}:\n{val.output.decode('utf-8')}",
                        logger,
                    )
                else:
                    logger.info(f"{APPLY_PATCH_PASS}:\n{val.output.decode('utf-8')}")
            else:
                logger.info(f"{APPLY_PATCH_PASS}:\n{val.output.decode('utf-8')}")

        # Get git diff before running eval script
        git_diff_output_before = (
            container.exec_run("git diff", workdir="/testbed").output.decode("utf-8").strip()
        )
        logger.info(f"Git diff before:\n{git_diff_output_before}")

        eval_file = Path(log_dir / "eval.sh")
        eval_file.write_text(test_spec.eval_script)
        logger.info(
            f"Eval script for {instance_id} written to {patch_file}, now applying to container..."
        )
        copy_to_container(container, test_spec.eval_script, Path("/eval.sh"))

        # Run eval script, write output to logs
        result = exec_run_with_timeout(container, "/bin/bash /eval.sh", timeout=timeout)
        test_output = result.decode("utf-8")
        test_output_path = log_dir / "test_output.txt"
        with open(test_output_path, "w") as f:
            f.write(test_output)
        logger.info(f"Test output for {instance_id} written to {test_output_path}")

        # # Get git diff after running eval script
        # git_diff_output_after = (
        #     container.exec_run("git diff", workdir="/testbed").output.decode("utf-8").strip()
        # )

        # Check if git diff changed after running eval script
        # logger.info(f"Git diff after:\n{git_diff_output_after}")
        # if git_diff_output_after != git_diff_output_before:
        #     logger.info(f"Git diff changed after running eval script")

        # Get report from test output
        logger.info(f"Grading answer for {instance_id}...")
        report = get_pred_report(
            test_spec=test_spec,
            prediction=pred,
            log_path=test_output_path,
            include_tests_status=True,
        )
        logger.info(
            f"report: {report}\n"
            f"Result for {instance_id}: resolved: {report[instance_id]['resolved']}"
        )

        # Write report to report.json
        with open(report_path, "w") as f:
            f.write(json.dumps(report, indent=4))
        report = None
        return instance_id, report
    except EvaluationError as e:
        error_msg = (f"EvaluationError {instance_id}: {e}\n"
                     f"{traceback.format_exc()}\n"
                     f"Check ({logger.log_file}) for more information.")
        logger.info(error_msg)
        print(error_msg)
    except Exception as e:
        error_msg = (f"Error in evaluating model for {instance_id}: {e}\n"
                     f"{traceback.format_exc()}\n"
                     f"Check ({logger.log_file}) for more information.")
        logger.info(error_msg)
        print(error_msg)
    finally:
        # Remove instance container + image, close logger
        cleanup_container(client, container, logger)
        if rm_image:
            remove_image(client, test_spec.instance_image_key, logger)
        close_logger(logger)

def run_instances(
        predictions: dict,
        instances: list,
        cache_level: str,
        clean: bool,
        force_rebuild: bool,
        max_workers: int,
        run_id: str,
        output_path: str,
        timeout: int,
        is_judge_fail2pass: bool,
       
    ):
    """
    Run all instances for the given predictions in parallel.

    Args:
        predictions (dict): Predictions dict generated by the model
        instances (list): List of instances
        cache_level (str): Cache level
        clean (bool): Clean images above cache level
        force_rebuild (bool): Force rebuild images
        max_workers (int): Maximum number of workers
        run_id (str): Run ID
        timeout (int): Timeout for running tests
    """
    client = docker.from_env()
    # test_specs = list(map(make_test_spec, instances, predictions))
    test_specs = [make_test_spec(instance, predictions[instance['instance_id']]) for instance in instances]

    # input()
    test_specs = [test_spec for test_spec in test_specs if test_spec != None]
    # print number of existing instance images
    instance_image_ids = {x.instance_image_key for x in test_specs}
    existing_images = {
        tag for i in client.images.list(all=True)
        for tag in i.tags if tag in instance_image_ids
    }
    if not force_rebuild and len(existing_images):
        print(f"Found {len(existing_images)} existing instance images. Will reuse them.")

    # run instances in parallel
    print(f"Running {len(instances)} instances...")
    if is_judge_fail2pass:
            
        with tqdm(total=len(instances), smoothing=0) as pbar:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Create a future for running each instance
                futures = {
                    executor.submit(
                        run_instance_fail_to_pass,
                        test_spec,
                        predictions[test_spec.instance_id],
                        # should_remove(
                        #     test_spec.instance_image_key,
                        #     cache_level,
                        #     clean,
                        #     existing_images,
                        # ),
                        True,
                        force_rebuild,
                        client,
                        run_id,
                        output_path,
                        timeout,
                    ): None
                    for test_spec in test_specs
                }
                # Wait for each future to complete
                for future in as_completed(futures):
                    pbar.update(1)
                    try:
                        # Update progress bar, check if instance ran successfully
                        future.result()
                    except Exception as e:
                        traceback.print_exc()
                        continue
    else:
        with tqdm(total=len(instances), smoothing=0) as pbar:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Create a future for running each instance
                futures = {
                    executor.submit(
                        run_instance_setup,
                        test_spec,
                        predictions[test_spec.instance_id],
                        # should_remove(
                        #     test_spec.instance_image_key,
                        #     cache_level,
                        #     clean,
                        #     existing_images,
                        # ),
                        True,
                        force_rebuild,
                        client,
                        run_id,
                        output_path,
                        "apply_patch",
                        timeout,
                    ): None
                    for test_spec in test_specs
                }
                # Wait for each future to complete
                for future in as_completed(futures):
                    pbar.update(1)
                    try:
                        # Update progress bar, check if instance ran successfully
                        future.result()
                    except Exception as e:
                        traceback.print_exc()
                        continue
    print("All instances run.")


def get_dataset_from_preds(
        dataset_name: str,
        split: str,
        instance_ids: list,
        predictions: dict,
        run_id: str,
        version_spec: str,
        output_path: str,
        exclude_completed: bool = True
    ):
    """
    Return only instances that have predictions and are in the dataset.
    If instance_ids is provided, only return instances with those IDs.
    If exclude_completed is True, only return instances that have not been run yet.
    """
    # load dataset
    dataset = load_omnigirl_dataset(dataset_name, split)

    if version_spec == 'all':
        dataset_ids = {i["instance_id"] for i in dataset}
    else:
        dataset_ids = {i["instance_id"] for i in dataset if i['version'] == version_spec}
    if instance_ids:
        # check that all instance IDs are in the dataset
        instance_ids = set(instance_ids)
        if instance_ids - dataset_ids:
            raise ValueError(
                (
                    "Some instance IDs not found in dataset!"
                    f"\nMissing IDs:\n{' '.join(instance_ids - dataset_ids)}"
                )
            )
        # check that all instance IDs have predictions
        missing_preds = instance_ids - set(predictions.keys())
        if missing_preds:
            print(f"Warning: Missing predictions for {len(missing_preds)} instance IDs.")
    
    # check that all prediction IDs are in the dataset
    prediction_ids = set(predictions.keys())
   
    # if prediction_ids - dataset_ids:
    #     raise ValueError(
    #         (
    #             "Some prediction IDs not found in dataset!"
    #             f"\nMissing IDs:\n{' '.join(prediction_ids - dataset_ids)}"
    #         )
    #     )
    if prediction_ids - dataset_ids:
        predictions = {k: v for k, v in predictions.items() if k in dataset_ids}
        print(f"Warning: {len(prediction_ids - dataset_ids)} prediction IDs not found in dataset.")
        # raise ValueError(
        #     (
        #         "Some prediction IDs not found in dataset!"
        #         f"\nMissing IDs:\n{' '.join(prediction_ids - dataset_ids)}"
        #     )
        # )

    if instance_ids:
        # filter dataset to just the instance IDs
        dataset = [i for i in dataset if i["instance_id"] in instance_ids]

    # check which instance IDs have already been run
    completed_ids = set()
    for instance in dataset:
        if instance["instance_id"] not in prediction_ids:
            # skip instances without predictions
            continue
        prediction = predictions[instance["instance_id"]]
        prev_apply_file = (
            Path(output_path)
            / run_id
            / prediction["model_name_or_path"].replace("/", "__")
            / prediction["instance_id"]
            / "test_output_prev_apply.txt"
        )
        after_apply_file = (
            Path(output_path)
            / run_id
            / prediction["model_name_or_path"].replace("/", "__")
            / prediction["instance_id"]
            / "test_output_after_apply.txt"
        )
        if prev_apply_file.exists() and after_apply_file.exists():
            completed_ids.add(instance["instance_id"])

    if completed_ids and exclude_completed:
        # filter dataset to only instances that have not been run
        print(f"{len(completed_ids)} instances already run, skipping...")
        dataset = [i for i in dataset if i["instance_id"] not in completed_ids]

    # empty_patch_ids = {k for k, v in predictions.items() if v["model_patch"] == "" or v["model_patch"] is None}
    empty_setup_ids = {
        k for k, v in predictions.items()
        if (v.get("model_patch") == "" or v.get("model_patch") is None) 
    }

    # filter dataset to only instances with predictions
    dataset = [i for i in dataset if i["instance_id"] in prediction_ids and i["instance_id"] not in empty_setup_ids]
    return dataset


def make_run_report(
        predictions: dict,
        full_dataset: list,
        client: docker.DockerClient,
        run_id: str,
        reports_dir: str,
        output_path: str
    ):
    """
    Make a final evaluation and run report of the instances that have been run.
    Also reports on images and containers that may still running!

    Args:
        predictions (dict): Predictions dict generated by the model
        full_dataset (list): List of all instances
        client (docker.DockerClient): Docker client
        run_id (str): Run ID
    """
    
    # instantiate sets to store IDs of different outcomes
    completed_ids = set()
    resolved_ids = set()
    error_ids = set()
    unstopped_containers = set()
    unremoved_images = set()
    unresolved_ids = set()
    incomplete_ids = set()
    # get instances with empty patches
    empty_patch_ids = set()

    # iterate through dataset and check if the instance has been run
    for instance in full_dataset:
        instance_id = instance["instance_id"]
        if instance_id not in predictions:
            # skip instances without 
            incomplete_ids.add(instance_id+"_version-"+str(instance['version']))
            continue
        prediction = predictions[instance_id]
        if prediction.get("model_patch", None) in ["", None]:
            empty_patch_ids.add(instance_id+"_version-"+str(instance['version']))
            continue
        log_dir = Path(output_path) / run_id / prediction["model_name_or_path"].replace("/", "__") / instance_id
        report_file = log_dir / "report.json"
        # report_file = (
        #     RUN_INSTANCE_LOG_DIR
        #     / run_id
        #     / prediction["model_name_or_path"].replace("/", "__")
        #     / prediction["instance_id"]
        #     / "report.json"
        # )
        if report_file.exists():
            # If report file exists, then the instance has been run
            completed_ids.add(instance_id+"_version-"+str(instance['version']))
            report = json.loads(report_file.read_text())
            if report[instance_id]["resolved"]:
                # Record if the instance was resolved
                resolved_ids.add(instance_id+"_version-"+str(instance['version']))
            else:
                unresolved_ids.add(instance_id+"_version-"+str(instance['version']))
        else:
            # Otherwise, the instance was not run successfully
            error_ids.add(instance_id+"_version-"+str(instance['version']))

    # get remaining images and containers
    images = list_images(client)
    # test_specs = [make_test_spec(instance, predictions[instance['instance_id']]) for instance in full_dataset]
    test_specs = [
    make_test_spec(instance, predictions[instance['instance_id']])
    for instance in full_dataset
    if instance['instance_id'] in predictions]
    # test_specs = list(map(make_test_spec, full_dataset))
    # test_specs = [test_spec for test_spec in test_specs if test_spec != None]
    for spec in test_specs:
        image_name = spec.instance_image_key
        if image_name in images:
            unremoved_images.add(image_name)
    containers = client.containers.list(all=True)
    for container in containers:
        if run_id in container.name:
            unstopped_containers.add(container.name)

    # print final report
    print(f"Total instances: {len(full_dataset)}")
    print(f"Instances submitted: {len(predictions)}")
    print(f"Instances completed: {len(completed_ids)}")
    print(f"Instances incomplete: {len(incomplete_ids)}")
    print(f"Instances resolved: {len(resolved_ids)}")
    print(f"Instances unresolved: {len(unresolved_ids)}")
    print(f"Instances with empty patches: {len(empty_patch_ids)}")
    print(f"Instances with errors: {len(error_ids)}")
    print(f"Unstopped containers: {len(unstopped_containers)}")
    print(f"Unremoved images: {len(unremoved_images)}")

    # write report to file
    report = {
        "total_instances": len(full_dataset),
        "submitted_instances": len(predictions),
        "completed_instances": len(completed_ids),
        "resolved_instances": len(resolved_ids),
        "unresolved_instances": len(unresolved_ids),
        "empty_patch_instances": len(empty_patch_ids),
        "error_instances": len(error_ids),
        "unstopped_instances": len(unstopped_containers),
        "completed_ids": list(sorted(completed_ids)),
        "incomplete_ids": list(sorted(incomplete_ids)),
        "empty_patch_ids": list(sorted(empty_patch_ids)),
        "submitted_ids": list(sorted(predictions.keys())),
        "resolved_ids": list(sorted(resolved_ids)),
        "unresolved_ids": list(sorted(unresolved_ids)),
        "error_ids": list(sorted(error_ids)),
        "unstopped_containers": list(sorted(unstopped_containers)),
        "unremoved_images": list(sorted(unremoved_images)),
    }
    report_file = Path(
        list(predictions.values())[0]["model_name_or_path"].replace("/", "__")
        + f".{run_id}"
        + ".json"
    )
    reports_dir = Path(reports_dir) 
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_file = reports_dir / report_file
    with open(report_file, "w") as f:
        print(json.dumps(report, indent=4), file=f)
    print(f"Report written to {report_file}")


def get_gold_predictions(dataset_name: str, split: str,version_spec: str,instance_ids):
    """
    Get gold predictions for the given dataset and split.
    """
    dataset = load_omnigirl_dataset(dataset_name, split)
    if instance_ids:
        # filter dataset to just the instance IDs
        dataset = [i for i in dataset if i["instance_id"] in instance_ids]
    if version_spec =='all':
        return [
            {
                "instance_id": datum["instance_id"],
                "model_patch": datum["patch"],
                "model_name_or_path": "gold",
            } for datum in dataset
        ]
    else:
        return [
            {
                "instance_id": datum["instance_id"],
                "model_patch": datum["patch"],
                "model_name_or_path": "gold",
            } for datum in dataset if datum['version'] == version_spec
        ]

def get_none_predictions(dataset_name: str, split: str,version_spec: str,instance_ids):
    """
    Get gold predictions for the given dataset and split.
    """

    dataset = load_omnigirl_dataset(dataset_name, split)
    if instance_ids:
        # filter dataset to just the instance IDs
        dataset = [i for i in dataset if i["instance_id"] in instance_ids]
    if version_spec =='all':
        return [
            {
                "instance_id": datum["instance_id"],
                "model_patch": "none",
                "model_name_or_path": "gold",
            } for datum in dataset
        ]
    else:
        return [
            {
                "instance_id": datum["instance_id"],
                "model_patch": "none",
                "model_name_or_path": "gold",
            } for datum in dataset if datum['version'] == version_spec
        ]


def main(
        dataset_name: str,
        split: str,
        instance_ids: list,
        predictions_path: str,
        max_workers: int,
        force_rebuild: bool,
        is_judge_fail2pass: bool,
        cache_level: str,
        clean: bool,
        open_file_limit: int,
        run_id: str,
        output_path:str,
        timeout: int,
        version_spec: str,
        reports_dir: str,
        
    ):
    """
    Run evaluation harness for the given dataset and predictions.
    """
    # set open file limit
    assert len(run_id) > 0, "Run ID must be provided"
    resource.setrlimit(resource.RLIMIT_NOFILE, (open_file_limit, open_file_limit))
    client = docker.from_env()



    if predictions_path == 'gold':
        print("Using gold predictions - ignoring predictions_path")
        predictions = get_gold_predictions(dataset_name, split,version_spec,instance_ids)
    elif predictions_path.endswith(".json"):
        # Handle .json file
        print(f"Reading predictions from single .json file: {predictions_path}")
        try:
            with open(predictions_path, "r", encoding='utf-8') as f:
                predictions = json.load(f)
            print("Successfully loaded predictions from .json file.")
        except Exception as e:
            raise RuntimeError(f"An error occurred while reading {predictions_path}: {e}")

    elif predictions_path.endswith(".jsonl"):
        # Handle .jsonl file
        print(f"Reading predictions from .jsonl file: {predictions_path}")
        predictions = []
        try:
            with open(predictions_path, "r", encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line: continue
                    try:
                        predictions.append(json.loads(line))
                    except json.JSONDecodeError:
                        print(f"Warning: Could not decode JSON on line {line_num} in {predictions_path}. Skipping line.")
                print(f"Successfully loaded {len(predictions)} entries from .jsonl file.")
        except Exception as e:
            raise RuntimeError(f"An error occurred while reading {predictions_path}: {e}")
    else:
        raise ValueError(f"Predictions path must be a directory, \"gold\", .json, or .jsonl, but got '{predictions_path}'")

    predictions = {pred["instance_id"]: pred for pred in predictions}
    print(f"collect {len(predictions)} predictions")
    # get dataset from predictions
    dataset = get_dataset_from_preds(dataset_name, split, instance_ids, predictions, run_id,version_spec,output_path)
    full_dataset = load_omnigirl_dataset(dataset_name, split)
    existing_images = list_images(client)
    print(f"Running {len(dataset)} unevaluated instances...")
    if not dataset:
        print("No instances to run.")
    else:
        # build environment images + run instances
        # build_env_images(client, dataset, force_rebuild, max_workers)
        run_instances(predictions, dataset, cache_level, clean, force_rebuild, max_workers, run_id, output_path, timeout, is_judge_fail2pass)

    # clean images + make final report
    clean_images(client, existing_images, cache_level, clean)
    make_run_report(predictions, full_dataset, client, run_id, reports_dir,output_path)


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("--dataset_name", default="princeton-nlp/SWE-bench_Lite", type=str, help="Name of dataset or path to JSON file.")
    parser.add_argument("--split", type=str, default="test", help="Split of the dataset")
    parser.add_argument("--instance_ids", nargs="+", type=str, help="Instance IDs to run (space separated)")
    parser.add_argument("--predictions_path", type=str, help="Path to predictions file - if 'gold', uses gold predictions", required=True)
    # parser.add_argument("--setup_predictions_path", type=str, help="Path to predictions file - if 'gold', uses gold predictions", required=True)
    parser.add_argument("--max_workers", type=int, default=4, help="Maximum number of workers (should be <= 75%% of CPU cores)")
    parser.add_argument("--open_file_limit", type=int, default=4096, help="Open file limit")
    parser.add_argument(
        "--timeout", type=int, default=1_800, help="Timeout (in seconds) for running tests for each instance"
        )
    parser.add_argument(
        "--force_rebuild", type=str2bool, default=False, help="Force rebuild of all images"
    )
    parser.add_argument(
        "--is_judge_fail2pass",
        action="store_true",
        default=False,
        help="Force rebuild of all images"
    )

    parser.add_argument(
        "--cache_level",
        type=str,
        choices=["none", "base", "env", "instance"],
        help="Cache level - remove images above this level",
        default="env",
    )
    # if clean is true then we remove all images that are above the cache level
    # if clean is false, we only remove images above the cache level if they don't already exist
    parser.add_argument(
        "--clean", type=str2bool, default=False, help="Clean images above cache level"
    )
    parser.add_argument("--run_id", type=str, required=True, help="Run ID - identifies the run")
    parser.add_argument("--output_path", type=str, required=True, help="Run ID - identifies the run")
    parser.add_argument(
        "--version_spec", type=str, default="all", help="version for specficcation"
        )
    parser.add_argument(
        "--reports_dir", type=str, default="reports", help="directory for saving reports"
        )
    
    args = parser.parse_args()

    main(**vars(args))
