---
title: Sfumato Idea Engine
emoji: 🌫️
colorFrom: purple
colorTo: blue
sdk: gradio
sdk_version: 6.28.0
app_file: app.py
pinned: false
---

# Sfumato Idea Engine

Sfumato generates independent idea seeds for a problem, compares them to select distinct directions, and returns support for each choice. In my own use, I have observed that the selected seeds have different underlying mechanisms. The packet includes the support for each pick so the selection can be inspected. A reasoning model or a person can work through the seeds. Sfumato does not choose a final answer.

I designed the project and directed the AI coding agents that built it. This repository contains a Gradio API and the sfumato agent skill. The software is released under the MIT License. Keep the copyright and license notices with redistributed copies.

## How it works

Each candidate is generated in its own call. The selection step compares candidates, includes a real "none of these" option, and asks for a different mechanism after each pick. Each pass uses eight trials in both option orders. Option masses are averaged across the two orders. Win counts use the first order, and order flips are reported.

With eight trials, a seed is marked core at six or more wins and optional at four or five. Less stable selections can be skipped and the next pass can continue. Selection stops when "none of these" wins at least half the trials or has at least as much mean option mass as the top candidate. These cut points and stop rules are starting heuristics, not validated thresholds.

I treat the comparison values as ranking scores, not as calibrated odds.

## API

The named Gradio endpoint is /generate_seed_packet. Its fields are:

- problem_brief: the situation, objective, constraints, success condition, and exclusions. Leave the mechanism open.
- candidate_count: 33 or 100.
- max_selected_seeds: a requested cap from 1 to 5. The pipeline can return fewer if an unstable selection is skipped near the pass limit.
- trials_per_pass: fixed at 8 for this release.
- word_range: defaults to [100, 180] and must satisfy 50 <= minimum < maximum <= 250. Candidate output is capped at 256 tokens, so a request near 250 words can be cut off.
- client_run_id: an optional caller label.

The packet returns the brief (trimmed of leading and trailing whitespace), selected seeds, support counts and option mass, stopping and skip decisions, candidate hashes, and token usage.

## Configure provider keys

For a local run, set MERCURY_API_KEY and TYPESAFE_API_KEY in your environment. For a hosted Space, add them as Space Secrets. Do not put provider keys in source files or request fields. Each deployment uses its own provider keys and is responsible for its own provider usage.

## Run locally

Install the requirements, set both provider keys, and start the app:

    python -m pip install -r requirements.txt
    $env:MERCURY_API_KEY = "..."
    $env:TYPESAFE_API_KEY = "..."
    python app.py

## Create your own private Space

Authenticate to your own account, then run the deployment script:

    hf auth login
    python deploy_private.py

The script creates a private Gradio Space named sfumato-idea-engine in the logged-in account and uploads the four runtime files. If that Space already exists, the script stops without uploading. Add your provider keys as Space Secrets in its Settings. The deployment script does not read or upload those keys.

## Limits

As of October 2026, I had not verified an end-to-end run of this hosted endpoint against the providers. My daily use of the method is through a local pipeline. If a provider fails partway through a request, the current prototype returns an error and does not persist a resumable run.

## How I work

I learned this way of working in graduate school. As a linguist, I was paired with computer science students. I brought the broad view and many of the ideas, and knew enough computer science to show what needed doing and which tools fit. My partners wrote most of the code. We argued it back and forth until it worked.

I still work that way. My computer science partners are now AI agents, Claude Code and Codex. I use Sfumato every day as a skill in my own work. The agents write most of the code. I own the design, the decisions, and what counts as done. [DESIGN-LOG.md](DESIGN-LOG.md) records those decisions in date order.

## How it evolved

Sfumato is the third version of an idea I started in March 2026. My premise is that a chat model tends toward likely, reasonable answers, so I pair it with a generator for unusual ideas, a selection step, and a reasoning model or person to harvest what is useful.

**First version, March 2026: prompts only.** Six agent skills described a pipeline: rewrite the problem, generate about fifty hypotheses in themed batches, score and sort them, refine the middle group, and pick the best one to three. In the one archived run, the critic discarded none of 55 hypotheses, the refine stage fell back on 8 of 12, and no token counts or costs were recorded. My design notes included a benchmark table that nobody had measured.

**Second version, September 2026: a runnable pipeline.** Generation, scoring, and bookkeeping moved into code, with records for parameters, scores, and cost, plus warnings for quiet degradation. A control set with a known ordering showed that the scorer could separate ideas, but it placed the March pool in a narrow band. I first blamed the problem rewrite. A controlled rerun using the same old prompt produced four times more spread. My best reading is that the generator itself had changed since March. I kept the new rewrite because it cut mechanism leakage (the brief hinting at a solution) from 0.45 to 0.12.

The harvest stayed manual. I rewrote it to work each odd idea through instead of grading it. The reader translates it plainly, asks what would have to be true, separates impossible from merely unbuilt, then keeps the principle that transfers.

**Third version, this repository, September 2026: a seed service.** Each candidate comes from a separate call because ideas in a batched list can constrain the ones that follow. Absolute scores gave way to repeated comparisons with a real "none of these" option. After each pick, the next pass asks for a different mechanism. The caller chooses the reasoning model.

**What I learned about grading.** In October, model judges scored a writer's output with and without seeds, and model labellers grouped candidate pools by mechanism. The writer's output changed between rounds, so those scores could not isolate the seeds. A model can also mistake shared wording for a shared mechanism. I concluded that these experiments graded the wrong thing, not that the engine failed. I judge seeds by using them, and each kept idea carries the ID of the seed it came from. See [DESIGN-LOG.md](DESIGN-LOG.md) for the dated decisions.
