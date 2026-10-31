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

# Neura LARA 5 — simulation records

Archived model interactions and measured simulation results for the LARA 5 seminar
project. [Source code and current documentation](https://github.com/carlo2004/Simulation-Neura-LARA-5)
remain on GitHub. Raw development records are not automatically a supervised
training dataset or a held-out benchmark.

## Historical migration

The sealed selection references GitHub commit
`40790e3addb62b5d9e1a9544b67bc4145a3e2f1c`. It covers 491 original paths under
`experiments/archive/` and `examples/experiments/archive/`. The 240 byte-identical
duplicate paths are explicitly mapped to 251 canonical files, preserving every
original name. Canonical file bytes total 33,596,782, including the comparison GIF.

| Record | Meaning |
|---|---|
| `legacy/<migration-id>/migration.json` | Exact source revision, selection, file sizes, SHA-256 and Git blob hashes, duplicate-path mappings |
| `legacy/<migration-id>/experiments/archive/…` | Original records and binary archives, unchanged |
| `legacy/<migration-id>/verification.json` | Written only after every canonical file was downloaded again from the recorded data commit and verified |

Pin the full Hub commit and migration ID when citing these records. A migration
without a verification record has not completed the post-upload check. The
migration tool preserves any existing dataset card and never deletes GitHub data.

## Interpretation

These are historical development attempts with differing prompts, APIs and model
profiles. Failures remain visible. Model-provided code was not repaired after the
fact. Physical success is determined by the simulator evaluator, not by a model's
claim to be finished. Stability samples within an episode are not independent
trials. The model receives exact simulator observations rather than camera-derived
perception. No fine-tuning improvement is claimed.

Before training, freeze case-level train/development/test groups and create a
separate reviewed dataset export with provenance and filtering rules. Adapters or
model checkpoints belong in a separate Hub model repository linked to that export.
No blanket dataset license is assigned by this migration; redistribution and
model-specific conditions require a separate review for a curated training release.

[Migration tool and Colab notebook](https://github.com/carlo2004/Simulation-Neura-LARA-5/tree/feature/archive-migration)
