# Interpretation notes for the 10-model run

Interpretation of the recorded 10-model benchmark. Overall scores and coverage are in [report.md](report.md).

## What the comparison measures

The score measures the configured application pipeline—classifier, generator, validation/repair and critic—not SQL generation alone. Models run at the recorded request settings (including low reasoning effort where configured), with an 8,192 completion-token ceiling. Do not extrapolate to different reasoning settings, prompts or retrieval context.

The first full launch used 60 concurrent case workers, up to six per model. After 912 completed cases, the run was restarted at 120 workers, up to 12 per model; interrupted cases remain resumable and earlier call usage stays in the checkpoint. After 1,847 completed cases, the final three models resumed with up to 96 workers, capped at 32 per model. The first case per model came from a lower-concurrency pilot and is reused rather than called again. Latency is therefore a measure of this experiment's changing end-to-end workload, not isolated inference speed. Cheap early failures also lower average latency and cost; compare correctness alongside these metrics and examine correct-case latency. Report the concurrency change with the results rather than treating all timings as one controlled load level.

## Classifier contract failures dominate one model

GPT-5.4 mini completed all 200 cases with 165 errors saying `The classifier returned an invalid decision. Please try again.` The classifier requires a JSON object containing `valid` as a boolean and a nonempty string `explanation`. These are interface/structured-response failures before SQL generation, distinct from the classifier deliberately rejecting a question.

The runner has different errors for unreadable JSON and length truncation, so these particular failures reached the classifier's shape/type checks. The raw response content is not recorded: the log cannot establish which required field was absent or mistyped. Do not describe this as 165 incorrect SQL queries or claim a specific malformed payload.

A separate diagnostic subsequently returned the expected classifier contract. The recorded failure pattern is therefore intermittent, not proof that this model cannot produce the required format. Preserve the original 165 failures in the benchmark score. The diagnostic is outside `cases.jsonl`; its estimated cost of **$0.00061125** must be disclosed separately if reporting total experiment spending, rather than silently included in or omitted from a claimed all-in figure.

## Generator and critic disagree about LIMIT

`app/agent.py` instructs the generator to add a sensible LIMIT to detail listings. The critic receives `generation_messages[1:]`, excluding that generator system instruction, and checks whether the SQL completely answers the user's question. Several models retain LIMIT 100 or 1000 while the critic repeatedly asks for its removal, exhausting all three critique rounds.

Concrete saved examples: `s01_q01` for GPT-6 Luna, GPT-6.2 Sol and GPT-6.2 Astra; `s01_q07` and `s02_q01` for GPT-6.2 Sol. Their final SQL passes fixture execution while the final critic rejects the unrequested cap.

All 200 reference outputs have at most **36 rows**; none has 100 or more. Consequently, an added LIMIT 100 cannot expose omissions on an otherwise correct result in these fixtures. Execution agreement is insufficient to prove complete answers on larger databases. A critic rejection in these cases is a legitimate general-data concern, not automatically a false alarm. The repeated revisions also affect latency and cost without changing the local execution score.

## Representative failure modes already observed

| Model / case | Failure | Interpretation |
| --- | --- | --- |
| GPT-4.1 and GPT-4.1 mini, `s05_q01` | Filtered `status = 'in-transit'`; fixture stores `'in_transit'` | Missing value grounding: the provided CREATE TABLE has a plain TEXT status column and no enumeration. The question uses “in-transit.” The model never sees seed rows. |
| GPT-5 mini, `s01_q04` | Used `printf('%.2f', ...)` for revenue | Revenue is formatted as TEXT instead of the numeric reference value. The strict typed result comparison fails it; this is different from incorrect aggregation. |
| GPT-4.1 mini, `s01_q09` | Filtered completed orders in a LEFT JOIN but summed item amounts without conditioning on a matched completed order | A real SQL semantics error: non-completed item revenue can remain in the sum. The critic approved it. |
| GPT-5.4 mini, `s07_q02` | Negated ledger `amount` when asked for its signed amount | Changed already signed values rather than returning the stored sign. Critic approved. |
| GPT-4o mini, `s03_q06` | Tested for no enrollments rather than no completed enrollments | Omitted the status condition and answered a different question. Critic approved. |
| GPT-4o mini, `s02_q09` | Chose two salary values globally after per-department ranking | Lost the requirement to choose the top two distinct levels separately for every department. |
| GPT-5 nano, `s02_q08` | Recursive step selected the next manager ID but retained the current employee name | Misaligned ID/name values across recursion levels. Critic approved. |

These are examples, not a frequency ranking. Final failure counts should come from the completed checkpoint. Some stored critique findings miss the actual SQL defect, so approval/critique statistics should remain separate from reference-result accuracy.

Independent local replay confirmed the GPT-5 mini example has all 13 expected rows and exactly matching numeric values after converting the revenue strings to numbers. It also confirmed the GPT-4.1 status-token mismatch returns zero rows instead of two, and the GPT-4.1 mini LEFT JOIN error returns three winners instead of the four reference rows. These diagnostic replays used isolated in-memory fixtures and did not change the official scores.

## Why the two highest scores missed cases

GPT-6.2 Sol's sole failed case, `s05_q08`, requested clarification about timestamp format and timezone offsets before choosing the latest shipment event. GPT-6.2 Astra's two failed cases, `s07_q09` and `s07_q10`, requested clarification about whether ledger amounts were already signed. None of these three cases ended with incorrect executable SQL: all ended without SQL. The benchmark expects an immediate query and therefore counts clarification as a failure. This one-case difference does not establish that Sol has stronger general reasoning than Astra.

## Follow-up work supported by this run

1. Align generator/critic policy for completeness and pagination; expose the same relevant application rules to both agents.
2. Add classifier JSON Schema enforcement or a bounded repair of malformed classifier responses, then benchmark the changed pipeline separately.
3. Supply permitted categorical values or representative value metadata when natural-language terms must map to exact stored tokens.
4. Strengthen test fixtures with larger outputs and alternative data distributions, and clarify whether numeric formatting as text is acceptable.
5. Add a generator-only or no-critic ablation before concluding that the critic improves accuracy; this run measures the combined system only.

Do not modify the active run or retroactively rewrite its scoring rules. Any of these changes requires a separate configuration/source fingerprint and a new comparison.
