import os
import json
import argparse

def count_finished_status_and_cost(directory):
    # status.json 统计
    finished_count = 0
    total_status_files = 0

    # cost.json 统计
    total_tokens_sum = 0.0
    total_input_tokens_sum = 0.0
    total_output_tokens_sum = 0.0
    total_elapsed_seconds = 0.0
    total_cost_files = 0

    # meta.json 统计（如果需要）
    total_meta_files = 0

    for root, _, files in os.walk(directory):
        for file in files:
            path = os.path.join(root, file)

            if file == "status.json":
                total_status_files += 1
                try:
                    data = json.load(open(path, encoding="utf-8"))
                    if data.get("is_finish") is True:
                        finished_count += 1
                except Exception as e:
                    print(f"读取 {path} 出错: {e}")

            elif file == "cost.json":
                total_cost_files += 1
                try:
                    data = json.load(open(path, encoding="utf-8"))
                    # total_tokens
                    total_tokens_sum += float(data.get("total_tokens", 0))
                    # total_input_tokens
                    total_input_tokens_sum += float(data.get("total_input_tokens", 0))
                    # total_output_tokens
                    total_output_tokens_sum += float(data.get("total_output_tokens", 0))
                    # elapsed_seconds
                    total_elapsed_seconds += float(data.get("elapsed_seconds", 0))
                except Exception as e:
                    print(f"读取 {path} 出错: {e}")

            elif file == "meta.json":
                total_meta_files += 1

    # 输出结果
    print(f"Total 'status.json' files found: {total_status_files}")
    print(f"Files with 'is_finish = true': {finished_count}")
    print(f"Total 'meta.json' files found: {total_meta_files}")
    print(f"Total 'cost.json' files found: {total_cost_files}")

    if total_cost_files:
        avg_total = total_tokens_sum / total_cost_files
        avg_input = total_input_tokens_sum / total_cost_files
        avg_output = total_output_tokens_sum / total_cost_files
        avg_elapsed = total_elapsed_seconds / total_cost_files

        print(f"Sum of 'total_tokens': {total_tokens_sum}")
        print(f"Average 'total_tokens': {avg_total:.2f}")
        print(f"Sum of 'total_input_tokens': {total_input_tokens_sum}")
        print(f"Average 'total_input_tokens': {avg_input:.2f}")
        print(f"Sum of 'total_output_tokens': {total_output_tokens_sum}")
        print(f"Average 'total_output_tokens': {avg_output:.2f}")
        print(f"Sum of 'elapsed_seconds': {total_elapsed_seconds}")
        print(f"Average 'elapsed_seconds': {avg_elapsed:.2f}")
    else:
        print("No 'cost.json' files found, cannot compute averages.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="统计目录下 status.json、cost.json（含 total_tokens/input/output_tokens 和 elapsed_seconds）和 meta.json 文件情况。"
    )
    parser.add_argument("directory", help="目标目录路径")
    args = parser.parse_args()
    count_finished_status_and_cost(args.directory)
