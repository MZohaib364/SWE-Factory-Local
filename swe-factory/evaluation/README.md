# Evaluation Framework

This directory provides the evaluation framework for the GitHub issue resolution task.

## Fail2Pass Validation

Ensure your dataset contains both a Dockerfile and an evaluation script. Then, run the following command to generate Fail2Pass test logs. The logs will be saved under `run_instances/mypy_fail2pass_check/gold`. When performing Fail2Pass validation, set the `predictions_path` to `gold` and use the `--is_judge_fail2pass` flag.
After running this command, you can find two test log files: "test_output_after_apply.txt" and "test_output_prev_apply.txt".
```bash
python run_evaluation.py \
  --dataset_name "output/git-4.1-mini/mypy/results/results.json" \
  --predictions_path "gold" \
  --max_workers 5 \
  --run_id "mypy_fail2pass_check" \
  --output_path "run_instances" \
  --timeout 3600 \
  --is_judge_fail2pass
```

## Evaluation

Once you have a validated GitHub issue resolution dataset (including Dockerfile and evaluation script), you can run the evaluation using the following command:

```bash
python run_evaluation.py \
  --dataset_name "mypy_valid.json" \
  --predictions_path "predictions.json" \
  --max_workers 5 \
  --run_id "mypy_evaluation" \
  --output_path "run_instances" \
  --timeout 3600 \
```