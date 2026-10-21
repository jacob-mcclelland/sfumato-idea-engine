# Design log

Dated decisions from the three working versions of Sfumato, in order: prompt-only agent skills in March 2026, a runnable pipeline in September 2026, and this seed service published on 2026-09-23. These entries draw on commit messages and experiment notes, which record whether a decision came from me, the coordinating agent, or a control test. The numbers are from my own runs.

## 2026-03-09: Start as prompts

My premise was that chat models tend toward likely answers, so I paired them with a generator meant to diverge. The first version had six agent skills and a design note. They defined a staged pipeline: rewrite the problem as a finished end state, generate about fifty hypotheses in five themed batches, have a critic score and sort them into keep, refine, or discard, refine the middle group, and have an arbiter pick the top one to three. A failed reality check capped an idea's score, however novel it was.

In hindsight, the design note claimed more than anyone had measured. Its benchmark table and cost comparison were estimates, not runs.

## 2026-09-20: Find out why the March run was flat

In the one archived run, the critic discarded none of 55 hypotheses and gave 40 a novelty score of 8 or 9. I built a scorer for novelty, feasibility, and specificity, with flags for echoing the prompt and unexplained steps. I tested it on a control set with an ordering I considered clear. The control spread 4 to 10 times wider than the real pool, so the scorer could separate ideas, but it still placed the March pool in a narrow band. That pointed to generation rather than the critic.

- **The reality gate fires on contradiction, not immaturity.** "Depends on something that does not exist yet" describes many ambitious ideas before they are built.
- **The control found a formula bug.** An impossible idea ranked fourth of six because novelty carried it. The cap in the first design had not been implemented. Low feasibility now multiplies the total down.
- **My first diagnosis was wrong.** I blamed the problem rewrite for naming its own mechanisms. A controlled rerun the same day gave four times more spread from the same old prompt. My best reading is that the generator itself changed since March. I kept the new rewrite anyway. It states the destination and difficulty, leaves the mechanism open, and blocks a rewrite that leaks one. Mechanism leakage fell from 0.45 to 0.12.

## 2026-09-20: Compare generators before choosing one

I compared three generators on three problems, for 99 hypotheses. Pooled novelty was the same, but one generator produced more of the high novelty ideas: 7 of its 33 cleared my novelty cut, compared with 1 of 33 for each of the other two. Its results also varied three to five times more by domain. The pattern held under three definitions of novelty, including one with no definition. Each generator reached for different material: physical substrates, social and economic frames, or the problem's own domain.

Two scoring scales I built from my own reading failed to reproduce my ordering. That was an early sign that a score is no substitute for reading. I did not build a third scale.

## 2026-09-20: Move the pipeline into code

Six prompt-only skills meant an agent improvised the pipeline on every run. The March session recorded no tokens or costs, and its refine stage silently fell back on 8 of 12 hypotheses for six months without anyone noticing.

- **One session file per run** holds the problem, compiled prompt, generator and exact parameters, every hypothesis and score, and cost per stage. A stage completes only on success, so a crash reruns it rather than skipping it.
- **Quiet degradation is recorded.** Provider warnings are kept. The pipeline warns when no problem rewrite was composed and when the pool barely separates. My first run fired both warnings correctly.
- **The harvest stays manual.** It is a judgement task, and dismissing an odd idea can waste what came before it. I left out critic and refine stages until they earn a place.

This pipeline is the one I use every day through a skill in my own agent setup.

## 2026-09-20: Harvest ideas, do not assess them

I changed the harvest to say which mode the reader is in. A proposal read as a claim gets compared against the reasonable answer. The same text read as material to work through has nothing to prove. The reader translates it plainly, asks what would have to be true, separates impossible from merely unbuilt, then keeps the principle that transfers. A thread that leads nowhere still records where it led before it failed.

Both changes came from my catching two dismissals the agent could not see from the inside.

## 2026-09-21: Read the whole pool, not the top slice

On a pool where everything was already interesting, the scorer's top 15 of 55 were mostly generic, while candidates behind them supplied nearly every harvested principle. I had seen that shape before: the scorer separated interesting from dull across a large pool, but I did not trust its order within a good one. The harvest now reads every candidate.

The same day, a provider refused a whole class of problems at the topic level, whatever the wording. The pipeline already accepted hypotheses generated elsewhere, so that path carried the run.

## 2026-09-21: Ask whether seeds change a writer's output

I ran an early blind experiment, graded by model judges, with writing runs that used on-topic seeds, unrelated seeds, or no seeds. It did not measure how good the selected ideas were in use. It did prompt me to consider choosing between seeds instead of scoring them one at a time.

## 2026-09-22: Generate independently, select by contrast

- **One call per candidate.** In a batched list, later ideas can be constrained by earlier ones.
- **Choose, do not score.** The selector sees the pool as one multiple-choice question, with "none of these" as a real option, repeated over eight shuffled trials and asked in both option orders. After each pick it ranks the remaining candidates again, tells the selector what was already chosen, and asks for a different mechanism.
- **Cut points are starting heuristics, not validated thresholds.** Six wins out of eight make a core seed, and four or five make an optional one.

## 2026-09-22: Only "none of these" may end the sequence

When trial winners scatter across several real candidates, I treat the ranking as unresolved, not as proof that the pool is exhausted. That pass is marked unresolved and skipped, and selection continues. On one live run, this changed one delivered seed into three.

## 2026-09-22: An exclusion names only what cannot be changed

A technique that was tried and disappointed is a constraint, not an exclusion. One problem statement had seven technique bans that also banned methods the solution needed. Exclusions now cover physical impossibilities, fixed properties of existing material, and actions I cannot take.

## 2026-09-22: Tell the generator the situation

The generator has no tools and knows nothing about the user's situation, so it cannot use what the brief leaves out. A research step now finds what the request leaves implicit and writes a dated, sourced situation block for the generator and selector. It carries situation and constraints only, never existing proposals.

## 2026-09-22: Leave the tail alone

Selection drew from dense clusters and never surfaced the lowest ranked outliers. I read those outliers and judged them inventive but unusable, so I declined a separate pass to reach them.

## 2026-09-23: Close with credit, not one answer

The close asks for one primary idea plus alternates that genuinely do not merge, each with a reason. An idea credit ledger keeps one row per seed with idea value and immediate solution value scored separately, because a speculative idea can be valuable before it is workable. Seeds combine only when their causal mechanisms reinforce one another. A "park" decision keeps a seed alive as its own line.

## 2026-09-23: Publish a seed service, not an answer service

The public version accepts a brief and returns a packet of seeds with their support, stop decisions, hashes, usage, and cost estimates. The caller chooses the reasoning model, so the service holds no key for one. The divergent material stays visible instead of being compressed into one preferred answer. I built a small repository from the core rather than publishing the private tree, which held unrelated machinery, experiment logs, and assumptions about my own machine.

## 2026-10-03: Model judges measured the writer, not the ideas

I tried to assess selection with blind rounds in which model judges scored a writer's output with and without seeds, and model labellers grouped each pool by mechanism. Between the September and October rounds, the writer's own output improved by more than any seed effect, and the judges' scores moved with it. Those scores could not isolate the seeds. Grouping by mechanism can also merge ideas that share vocabulary but have different mechanisms. I had caught that kind of mistake by hand before.

I concluded these experiments were a lesson about grading, not a verdict on the engine. The September runs did not record the writer and judge versions, so a later comparison would need to record them and hold both constant. I judge seeds by using them. The close keeps each seed's ID on every note, so a kept idea traces back to its source seed.
