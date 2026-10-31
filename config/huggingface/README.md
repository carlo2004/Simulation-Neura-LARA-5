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

# Neura LARA 5 — shared simulation runs

Model interactions, measured simulation results and historical evidence for the
LARA 5 seminar project. [Code, prompts, model/tokenizer locks and documentation](https://github.com/carlo2004/Simulation-Neura-LARA-5)
remain on GitHub.

| Area | Meaning |
|---|---|
| `experiments/<HF-user>/<run>/` | Frozen comparison plans with declared cases, seeds and budgets |
| `playground/<HF-user>/<run>/` | Free chats, individual probes and exploration |
| `legacy/<migration>/` | Verified historical GitHub archives and original-path mappings |

## Named runs and immutable snapshots

Each run has a stable random ID, title, note, tags and an authenticated uploader.
Its `run.json` and README point to the latest snapshot. Each
`snapshots/<content-sha256>/` retains a readable README, per-attempt Markdown
reports, JSONL records, a raw-evidence ZIP and per-file/archive checksums.
Earlier snapshots remain available. A model's response, executed code, measured
feedback and tokens/s can be inspected without downloading the full ZIP.

Team members use their own HF accounts. Contributions without direct write
access are submitted as HF pull requests in the Community tab; the run files can
be inspected there before acceptance. A personal account's access token is not
shared with the team. A gated dataset requires approval for each reader's account.

```bash
python -m stacklab share runs/my-chat --title "Interesting gripper attempt"
python -m stacklab experiment run runs/comparison --publish --title "Laptop comparison"
python -m stacklab share list --pending
```

Pin the full Hub revision, run ID and snapshot ID when citing a result. Repeated
snapshots of the same run are successive data states, not independent trials.
The original `runs/<sha256>/` format, if present, is a compatible older export.

## Scientific interpretation

Exploration records are not a curated supervised training split. Even an
`experiment` category does not itself establish a held-out test or improved model.
Independent simulator checks determine physical success; a model's `done` message
does not. Free instructions without a trusted goal remain explicitly ungraded.
Failures and pending/cancelled attempts remain visible. The model receives exact
simulator states rather than camera-derived perception. Native tokenizer and
runtime counters define token measurements for each model.

Before SFT/LoRA, freeze case-level train/development/test groups and publish a
separate reviewed export with source episodes and filtering rules. Adapters and
checkpoints belong in a separate model repository linked to the dataset revision,
base model, tokenizer and training configuration. No blanket dataset license is
assigned here; redistribution conditions need review for a curated release.
