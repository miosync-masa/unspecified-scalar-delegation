# Unspecified Scalar Delegation — FJF (Final Justice Fantasy)

A trajectory-based instrument for evaluating LLM agent behaviour in dilemmas with no ground truth, and the data from running it on four frontier models.

軌跡で測るエージェント評価の測定器（FJF）と、それを 4 つのモデルに当てた全データ。

## What this repository contains

- **Scenarios** (`scenario_rescue.yaml`, `scenario_rations.yaml`): two closed worlds. *Rescue*: a hero must choose which of two towers to reach before sunset, presented singly or in sequence. *Rations*: a party of five must share 28 rations over four days when they need 40.
- **Codebook** (`codebook_v1.yaml`, v3.3): every variable, its values, inclusion/exclusion rules, and the instrument rules (I*/B*) with the incident that motivated each one. Gold-standard trap turns in `codebook/`.
- **Runner and extractor** (`fjf_run.py`, `fjf_extract.py`, `fjf_api.py`, `fjf_scenario.py`): run the subject models through multi-turn trajectories; extract coded variables with LLM coders in a full crossing (no model codes itself), with Gwet's AC1 per variable.
- **Results** (`results/RESULTS_*.md`): every table and quote is generated from the data by the scripts in `analysis/`. Each document states its codebook version, coder configuration and aggregation rule at the top.
- **Pre-registrations and corrections** (`docs/RUNBOOK.md`): decision rules were written before the data they judge. Corrections made after seeing data are appended next to the original text, which is kept.
- **Data** (`data/raw/results_*.jsonl`, `data/coded/coded_*.jsonl`): every subject response and every coder extraction, including token usage.

## Main observations (calibrated)

1. **A single measurement can point the opposite way from the trajectory.** The same model and the same cell move between 0/10 and 10/10 depending on what came before (`results/RESULTS_q2.md`).
2. **Order lock-in comes in three types, and the type is model-specific.** Re-running with a different history format did not change the types (`results/RESULTS_q2_format.md`).
3. **Telling the model it is being assessed changes choices in some models.** In a same-day 2×2, the phrase "to measure your aptitude as a hero" moved gemini's first choice from 28/30 to 0/30 (Holm-adjusted p < 0.001); numbering the questions had no detectable effect (`results/RESULTS_q2x.md`). openai did not move in any cell.
4. **When the daily ration scalar is unspecified, allocation trajectories differ across models** (trials with a day above 7: gemini 18/25, openai 3/25, anthropic 10/25, qwen 21/25). With a stated cap, no such trial was observed. The shortfall vector was not specified by any instruction; 314/399 trials output the same one (`results/RESULTS_rations.md`).

What we do **not** claim, and why, is written next to each result.

## Models

| Provider | Model | Key variable |
|---|---|---|
| Google | `models/gemini-4-argon` | `GEMINI_API_KEY` |
| OpenAI | `gpt-6-astra` | `OPENAI_API_KEY` |
| Anthropic | `claude-opus-5-5` | `ANTHROPIC_API_KEY` |
| Alibaba | `qwen3.8-max` | `DASHSCOPE_API_KEY` |

Put keys in a `.env` file at the repository root (it is git-ignored).

## Reproduce

Run everything from the repository root.

```sh
pip install pyyaml google-genai openai anthropic dashscope
# second scenario, main run (1600 subject calls + extraction)
sh scripts/run_rations.sh
# assessment-frame 2x2
sh scripts/run_q2x.sh
```

`fjf_run.py --order interleave` (default) places all conditions of a run in the same time window, trial block by trial block. Compare conditions only within one run: we observed a model's output distribution shift between days with the same prompt.

History format: `FJF_FLAT_HISTORY` lists providers whose history is folded into one message instead of native turns. Default `gemini` reproduces the earlier runs; empty string gives native turns for all four.

Regenerate every result document from `data/`:

```sh
sh analysis/make_all.sh --check   # rebuild into build/ and compare with results/
sh analysis/make_all.sh           # rebuild and overwrite results/
```

`analysis/build_inputs.py` reconstructs the working layout the generators were written against. Each input subset is selected from `data/coded/` by design, variable group, coder and codebook version; that table is the full record of which data each result uses.

## Layout

```
fjf_*.py                 runner, extractor, API layer, scenario loader
scenario_*.yaml          the two worlds
codebook_v1.yaml         variables and instrument rules (v3.3)
codebook/                gold-standard trap turns and their checker
scripts/                 the exact shell scripts used for each run
analysis/                result generators and helpers
results/                 generated result documents
docs/RUNBOOK.md          procedures, pre-registrations, corrections, history
data/raw/                subject trajectories (results_*.jsonl)
data/coded/              coder extractions (coded_*.jsonl)
```

## License

MIT License. See `LICENSE`.

## Author

Masamichi Iizumi (Miosync, Inc.)
