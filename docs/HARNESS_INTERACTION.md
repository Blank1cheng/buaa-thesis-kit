# Harness Interaction Protocol

The harness is the control loop for BUAA thesis normalization. It reports which artifact was validated, which gates passed or failed, and the next single failure to fix. A text gate passing is not the same thing as a complete thesis pass.

## Commands

`/status`

Return the current gate board, current phase, candidate path, candidate SHA, commit, and next failure.

`/triage`

Return the top five prioritized failure queue items. Each item must include `id`, `gate`, `region`, `evidence_text`, `expected`, `suggested_fix`, and `can_fix_now`.

`/fix H-xxx`

Fix exactly one failure id. Do not opportunistically fix unrelated issues. Do not loosen validators to make a failure pass.

`/evidence H-xxx`

Return the selected failure plus candidate SHA, report paths, artifact paths, and available screenshots from the evidence packet.

`/reject <description>`

Record the current artifact as a bad fixture, add or update a harness rule for the rejected behavior, and prove the artifact fails before attempting a fix.

## Loop

1. Run the pipeline or harness.
2. Run `python scripts/harness_doctor.py --out output/harness`.
3. Use `/status` to identify the current phase and next failure.
4. Use `/triage` or `/evidence H-xxx` to inspect evidence.
5. Use `/fix H-xxx` for exactly one failure.
6. Re-run tests, pipeline, doctor, and compare the new failure queue.

## Non-goals In Truncated Mode

When `--sample-mode truncated` is active, missing later chapters, references, figures, or equations are not sufficient by themselves to fail the current workflow. The harness may report them as future review items, but the next fix should stay focused on the highest-priority failure id.
