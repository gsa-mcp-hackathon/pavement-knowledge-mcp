# Pavement Knowledge MCP evaluation

Prepared by the Pavement Knowledge MCP team. November 17, 2026.

The **Evaluation Report** is a separate submission. This folder contains its supporting records.

Our evaluation asks whether MCP gives an AI assistant access to pavement research evidence that users can check. The team and colleagues used MCP for many questions, with answers reviewed by pavement subject-matter experts (SMEs). Two answer comparisons are documented in detail; they are examples of this broader use.

## What the records show

| Evaluation | Finding | Supporting record |
|---|---|---|
| Final package verification, November 17 | Fresh offline installation passed; 25 software checks and 7 local tool checks passed. Operational files matched the original package. | [Verification record](software_verification_2026-11-17.md) |
| Installation and tool operation, October 21 | 25 software checks, 16 requests using actual reports and 7 checks after offline installation passed. Both installations passed dependency checks. | [Technical report](../server/evaluation/REPORT.md), [test inputs](../server/evaluation/cases.json), [saved results](../server/evaluation/results.json) |
| Heavy-load experiments | MCP supplied the requested report details and source locations. Scores: 5/8 without pavement MCP; 8/8 with it. | [Comparison and complete answers](superheavy_experiments_case/comparison_review.md) |
| Pavement sensor study | MCP added useful detail but repeated an apparent source-text error. Scores: 6/8 without pavement MCP; 7/8 with it. | [Comparison, correction and complete answers](tsdd_instrumentation_case/comparison_review.md) |
| Broader SME review | We found that MCP worked well across these questions. A second SME also reported successful installation and use with Claude and approved the answers reviewed. | [Team use and SME review](internal_sme_use_review.md), [Claude trial](claude_trial_review.md) |

## How the answers were reviewed

Each answer received 0 (not met or not demonstrated), 1 (partly met) or 2 (met for that question) on four criteria: correctness, completeness, support from cited sources, and clarity about limits or uncertainty. The maximum is 8. The scores describe performance on these questions, not overall accuracy.

AI assisted the assessments and source checks on November 10. The project-team pavement SME reviewed and approved the paired answers and assessments on November 12.

The same model and high reasoning setting were reportedly used in each pair. The intended prompts prohibited web access but allowed research-document tools. The assistant without pavement MCP could still use other documents, and complete run settings were not recorded. These are illustrative comparisons, not a fully controlled measure of MCP's effect.

## Reading the evidence

Each case folder contains the original answers, scores and review details, report text, selected page images and source checks. The TSDD folder also includes the intended prompt. Source checks were made after answer generation and are separate from the original tool runs. Case records include answer-file hashes. PDF page numbers count from the first PDF page and can differ from printed page numbers.

MCP makes supporting evidence accessible, but a technical error in a report can carry into an answer. The sensor case records one such correction. Software pass counts, answer scores and qualitative SME feedback measure different things and should be read separately.
