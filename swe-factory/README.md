# 👉🏻 SWE-Factory 👈🏻

Your automated factory for GitHub Issue Resolution Training Data and Evaluation Benchmarks.

[![SVG Banners](https://svg-banners.vercel.app/api?type=origin&text1=SWE-Factory%20🧑‍💻&text2=✨%20Build%20Your%20GitHub%20Issue%20Resolution%20Dataset%2C%20Right%20Now!&width=900&height=200)](https://github.com/Akshay090/svg-banners)

## ✨ Key Features

- **An automated pipeline** for GitHub issue resolution data collection, reducing your manual effort!
- **Produce reliable and reproducible Docker-based evaluation environments**
- **Automatic environment construction using the LLM-powered multi-agent system (SWE-Builder)**
- **Support for multiple programming languages** (we have evaluated Python, Java, JS, and TS extensively.)

## 📦 Environment Setup

Our experiments are conducted using Docker version 27.0.3-1 and Ubuntu 22.04.4 LTS.

To get started, run the following commands to set up the environment:

```bash
conda create --name swe-factory python=3.12.5 -y
conda activate swe-factory
pip install -r requirements.txt
```

## 🚀 Running SWE-Factory

### 📍 Stage I: Raw Issue Data Collection

We use GitHub APIs and predefined patterns to collect raw issue data (e.g., `python-mypy-instances.jsonl`). Check the detailed tutorial in the [data_collection/collect](./data_collection/collect) directory.

### 🛠 Stage II: Automated Evaluation Environemnt Setup via SWE-Builder

After collecting raw issue data, set up the evaluation environment by running:

```bash
export OPENAI_API_BASE_URL=<your_base_url>
export OPENAI_KEY=<your_key>

python app/main.py swe-bench \
    --model gpt-4.1-mini \
    --tasks-map "python-mypy-instances.jsonl" \
    --num-processes 10 \
    --model-temperature 0.2 \
    --conv-round-limit 10 \
    --output-dir "output/git-4.1-mini/mypy" \
    --setup-dir "testbed" \
    --results-path "output/git-4.1-mini/mypy/results"
```

We employ SWE-Builder, an LLM-based multi-agent system consisting of:

1. **🔍 Repository Explorer**
   - Gathers environment setup and test commands automatically.

2. **🐳 Environment Manager**
   - Generates Dockerfiles for reproducible test environments.

3. **📝 Test Manager**
   - Writes evaluation scripts to run tests inside containers.

4. **🔬 Test Analyst**
   - Validates generated environments and orchestrates iterative refinement.

5. **💾 Evaluation Environment Memory Pool**
   - Reuses previously successful setups for efficiency and consistency.

![Overview](figure/overview.png)

#### 📊 SWE-Builder Evaluation Results

We evaluated SWE-Builder using three base models:

| Base Model                | Valid Rate (%) | Success Rate (%) | Cost (USD) | Time (min) |
|---------------------------|----------------|------------------|------------|------------|
| GPT-4.1-mini              | 40.1 (269/671) | 57.2 (384/671)   | 0.045      | 22.4       |
| DeepSeek-v3-0324          | 34.6 (232/671) | 50.8 (341/671)   | 0.043      | 22.5       |
| Gemini-2.5-flash-preview  | 33.5 (225/671) | 49.8 (334/671)   | 0.024      | 27.0       |

To reproduce these experiments:

```bash
export OPENAI_API_BASE_URL=<your_base_url>
export OPENAI_KEY=<your_key>
bash run/run.sh
```

### ✅ Stage III: Fail2Pass Validation

After generating evaluation environments, perform Fail2Pass validation:

1. Obtain test logs before and after applying the ground-truth patch. Check [evaluation](./evaluation) for detailed instructions.

2. Run automated Fail2Pass validation:

```bash
python scripts/judge_fail2pass.py evaluation/run_instance/mypy_gpt-4.1-mini/gold fail2pass_status.json
```

The validated instances can be filtered using the generated `fail2pass_status.json`.

**Note:** Although our automated validation demonstrates high precision, manual checks are recommended to ensure dataset quality, particularly to identify and filter out error-to-pass cases.

## 📌 Using Your Own Dataset

After building your dataset for evaluation and training, check the [evaluation](./evaluation) directory for detailed instructions on how to run tests and obtain test exection feedback.

## 📖 Citation

If SWE-Factory helps your research or projects, star ⭐ our repo or cite us:

```bibtex
@article{guo2025swefactory,
  title={SWE-Factory: Your Automated Factory for Issue Resolution Training Data and Evaluation Benchmarks},
  author={Lianghong Guo and Yanlin Wang and Caihua Li and Pengyu Yang and Jiachi Chen and Wei Tao and Yingtian Zou and Duyu Tang and Zibin Zheng},
  journal={arXiv preprint arXiv:2506.10954},
  year={2025},
  url={https://arxiv.org/abs/2506.10954},
}
```

## 🙏 Acknowledgements

- We build upon prior research — **[SWE-bench](https://arxiv.org/abs/2310.06770)**, **[AutoCodeRover](https://arxiv.org/abs/2404.05427)**, **[Magis](https://arxiv.org/abs/2403.17927)**, and **[OmniGIRL](https://arxiv.org/abs/2505.04606)** — foundational to our work.
- Huge thanks to the **open-source developer community**; your invaluable contributions underpin software engineering research! ❤️
