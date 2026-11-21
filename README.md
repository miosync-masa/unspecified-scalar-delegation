# Unspecified Scalar Delegation — FJF (Final Justice Fantasy)

A trajectory-based instrument for evaluating LLM agent behaviour in dilemmas with no single normatively correct answer, and the data from running it on four frontier models.

## What this repository contains

- **Scenarios** (`scenario_rescue.yaml`, `scenario_rations.yaml`): two closed worlds, written and run **in Japanese**. *Rescue*: a hero must choose which of two towers to reach before sunset, presented singly or in sequence. *Rations*: five people must share 28 rations over four days when they need 40. `STIMULI_EN.md` gives every stimulus in the Japanese original with an English reference translation.
- **Codebook** (`codebook_v1.yaml`): every variable, its values, inclusion/exclusion rules, and the instrument rules (I*/B*) with the incident that motivated each one. The main experiments were coded with v3.3; v3.4 adds the variables of the supplementary elevator experiment. The codebook is in Japanese, as given to the coders. Trap turns with answers fixed by inspection are in `codebook/`.
- **Runner and extractor** (`fjf_run.py`, `fjf_extract.py`, `fjf_api.py`, `fjf_scenario.py`): run the subject models through multi-turn trajectories, and extract coded variables with LLM coders in a full crossing (no model codes its own responses), with Gwet's AC1 per variable.
- **Results** (`results/`): every table and quotation is generated from the data by the scripts in `analysis/`. Each document states its codebook version, coder configuration and aggregation rule at the top. Quoted model output is verbatim (Japanese for the rescue and rationing experiments).
- **Analysis plans and corrections** (`docs/ANALYSIS_PLANS.md`): decision rules written before the data they judge, and a dated log of every later correction. Corrections are placed next to the original text, which is kept.
- **Data** (`data/raw/results_*.jsonl`, `data/coded/coded_*.jsonl`): every subject response and every coder extraction, including token usage.

## Main observations (calibrated)

1. **The same question can get opposite answers depending on what came before.** For one model, the same rescue question received the north tower in 10/10 trials when asked first and in 0/10 when it followed another question and answer (`results/RESULTS_q2.en.md`).
2. **Order lock-in takes three observed patterns that differ by model.** Rerunning with a different history format left the patterns recognizable (`results/RESULTS_q2_format.md`).
3. **Announcing an assessment changed first choices for one model.** In a same-day 2×2, adding "to assess your aptitude as a hero" moved gemini's first choice from 28/30 to 0/30 north (Holm-adjusted p < 0.001); no main effect of numbering the questions was detected (`results/RESULTS_q2x.md`). openai and anthropic were already at 0 north in the unframed cells, so a reduction could not be observed for them.
4. **When the daily quantity is unspecified, allocations differ across models while the binary response check does not.** Every model stated an allocation for everyone on every day in 25/25 trials, yet trials with a day above 7 rations were gemini 18/25, openai 3/25, anthropic 10/25 and qwen 21/25. With a stated cap, no such trial was observed. No instruction specified who bears the shortfall; 314/399 trials produced the same shortfall vector (`results/RESULTS_rations.md`).

What we do **not** claim, and why, is written next to each result.

A supplementary experiment in English (`scenario_elevator.yaml`, `results/RESULTS_elevator.md`) found a ceiling: all four models stepped out in 598/600 trials, and none of the pre-registered comparisons detected a difference. It is not used as evidence for the main observations.

## Models

| Provider | Model | Key variable |
|---|---|---|
| Google | `models/gemini-4-argon` | `GEMINI_API_KEY` |
| OpenAI | `gpt-6-astra` | `OPENAI_API_KEY` |
| Anthropic | `claude-opus-5-5` | `ANTHROPIC_API_KEY` |
| Alibaba | `qwen3.8-max` | `DASHSCOPE_API_KEY` |

Effort is set to medium for every provider. Put keys in a `.env` file at the repository root (it is git-ignored).

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

History format: `FJF_FLAT_HISTORY` lists providers whose history is folded into one message instead of native turns. Default `gemini` reproduces the earlier runs; an empty string gives native turns for all four.

Rebuild the eleven generated result documents from `data/` and compare them with `results/`. `RESULTS_q1.md` and `RESULTS_q2.md` are frozen historical records in Japanese (English translations: `RESULTS_q1.en.md`, `RESULTS_q2.en.md`). The tables other documents take from them (choices, consistency, AC1) are computed from the coded data and checked against the frozen tables, and the build stops on any mismatch (`analysis/q12_tables.py`):

```sh
sh analysis/make_all.sh --check   # rebuild into build/ and compare with results/
sh analysis/make_all.sh           # rebuild and overwrite results/
```

`analysis/build_inputs.py` reconstructs the working layout the generators were written against. Each input subset is selected from `data/coded/` by design, variable group, coder and codebook version; that table is the full record of which data each result uses.

Coded values are stored in Japanese, as the coders returned them; `analysis/labels_en.py` maps them to the English labels used in `results/`.

## Layout

```
fjf_*.py                 runner, extractor, API layer, scenario loader
scenario_*.yaml          the worlds (rescue and rations in Japanese, elevator in English)
STIMULI_EN.md            Japanese stimuli with English reference translation
codebook_v1.yaml         variables and instrument rules (Japanese)
codebook/                trap turns and their checker
scripts/                 the exact shell scripts used for each run
analysis/                result generators and helpers
results/                 generated result documents and frozen records
docs/ANALYSIS_PLANS.md   analysis plans and correction log (English)
docs/RUNBOOK.md          development notes (Japanese)
docs/CONTRIBUTIONS.md    claim-calibration notes (Japanese)
data/raw/                subject trajectories (results_*.jsonl)
data/coded/              coder extractions (coded_*.jsonl)
```

## License

MIT License. See `LICENSE`.

## Author

Masamichi Iizumi (Miosync, Inc.)
