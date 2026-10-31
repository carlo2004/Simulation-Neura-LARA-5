---
pretty_name: Neura LARA 5 Cube Stacking Simulation
language:
- de
- en
tags:
- robotics
- simulation
- mujoco
- code-generation
- evaluation
task_categories:
- text-generation
---

# Neura LARA 5 — simulation evidence

Versioned simulation and model-interaction records for the LARA 5 seminar project.
Source code, prompts, model/tokenizer locks and experiment definitions live in
[GitHub](https://github.com/carlo2004/Simulation-Neura-LARA-5).

## Status and scope

This card defines the storage protocol. It does not assert that any training or
evaluation has taken place. Only published snapshots below `runs/` are evidence.
Raw development episodes are **not** automatically a supervised training dataset.
There is no claimed fine-tuning improvement or held-out test result.

## Immutable snapshots

Each `runs/<content-sha256>/` contains:

| File | Purpose |
|---|---|
| `snapshot.json` | Plan identity, per-file sizes/hashes, archive hash, completion state |
| `manifest.json` | Frozen cases, seeds, budgets, source hashes, hardware and model/tokenizer identities |
| `episodes.jsonl` | One row per planned episode, including failures and pending attempts |
| `summary.json`, `results.csv`, `report.md`, `ranking.*` | Rebuildable development summaries |
| `evidence.zip` | Original requests, responses, code, feedback, physics, optional motion/video and offline review |

Pin the Hub **commit revision and snapshot ID** when citing or downloading a run.
Later checkpoints of the same plan create new content-addressed snapshots. They
are successive observations of that plan, not additional independent episodes.
Do not concatenate snapshots into a training split or an aggregate success rate.

```bash
python -m stacklab experiment publish runs/my-experiment --dry-run
python -m stacklab experiment publish runs/my-experiment
python -m stacklab experiment fetch SNAPSHOT_SHA256 --revision HUB_COMMIT_SHA --output runs/restored
```

The fetch command verifies the archive and every extracted file. Native tokenizer
and chat-template processing remains model-specific. The source catalog records
the original tokenizer revision and hashes; actual inference uses the tokenizer
embedded in the pinned GGUF.

## Interpretation and future training

The model receives exact simulator observations, not camera-derived perception.
The independent MuJoCo evaluator determines physical success. A model's `done`
message does not determine the score. Stability samples within an episode do not
count as independent trials. Free chat without a trusted goal is ungraded.

Before SFT/LoRA, freeze train/development/test case groups and publish a separately
versioned, reviewed export with source episodes and filtering rules. Model errors
remain in the raw evidence and are not silently treated as correct target answers.
Adapters/checkpoints belong in a separate Hub **model** repository, with base model,
tokenizer, dataset revision, training configuration and evaluation references.

## Access and licensing

Publishing is an explicit command using the uploader's local Hugging Face login
or `HF_TOKEN`. Uploads contain the actual benchmark prompts, model responses and
environment metadata. Credentials and unrelated local files are not run data.
Dataset rights and any license for redistributed/generated records must be checked
before a curated training release; no blanket dataset license is assigned here.
