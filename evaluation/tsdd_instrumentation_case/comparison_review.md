# Pavement sensor installation and measurement alignment

Pavement Knowledge MCP team. Assessment: November 10, 2026. Project-team pavement SME approval: November 12, 2026.

## Question and finding

The task used FHWA-HRT-15-074 to explain how pavement sensors were installed and their measurements aligned with moving traffic-speed deflection devices (TSDDs), including limitations and recommendations for a new experiment.

Both answers offered useful guidance. The answer without pavement MCP used related papers and a report-derived summary. MCP added details about all four installed test cells, the trigger arrangement, clock matching, averaging and measurement limitations. It also repeated an apparent error in the report's explanation of speed. Access to the report improved detail, while SME review identified a correction needed before reuse.

## Scores

The [shared method](../README.md#how-the-answers-were-reviewed) describes the 0–2 scale, review process and comparison limits.

| Criterion | Without pavement MCP | With pavement MCP | Reason |
|---|---:|---:|---|
| Correctness | 2 | 1 | MCP repeated an incorrect speed relationship, relevant to measurement alignment. |
| Completeness | 1 | 2 | MCP added the fourth installed cell, full trigger arrangement, clock matching and more limitations. |
| Support from cited sources | 1 | 2 | The baseline used related sources; the main MCP claims were checked directly in the requested report. Citation refinements appear below. |
| Limits and uncertainty | 2 | 2 | Both distinguish reported work from recommendations. MCP does not invent an acquisition sampling rate or shared hardware clock. |
| Total | 6/8 | 7/8 | Scores apply to this question, not overall accuracy. |

The AI-assisted assessment was reviewed and approved by the project-team SME. The speed error affected the correctness score.

## Correction before reuse

**Speed = axle spacing / elapsed time between the corresponding front- and rear-axle response peaks.** This assumes sufficiently steady speed and comparable response lags; trigger-to-response lag needs separate consideration.

The MCP answer reverses this relationship. The source report also describes time divided by distance on PDF page 73 (printed 53). Visual inspection confirmed the wording, so this is an apparent source-text error, not just a text-extraction problem. The study's calculation files were not checked; this finding does not establish that its numerical calculations were wrong. The original answer is preserved unchanged.

## Source checks and citation refinements

Source: [FHWA-HRT-15-074](https://www.fhwa.dot.gov/publications/research/infrastructure/pavements/15074/15074.pdf). Locations below use PDF pages; printed numbers are 20 lower in these sections.

| Topic | Review finding and location |
|---|---|
| Test cells and sensors | Three flexible cells and concrete cell 72 were instrumented, each with four geophones and an accelerometer. The concrete cell was excluded from accuracy analysis because its signals were unsuitable. PDF 63–65, 78 and 267. |
| Calibration and installation | Sensor types, housings, calibration, grooves, partial grout, FWD check and final grout are supported. Core-depth wording varies slightly between Chapter 5 and Appendix C. PDF 63–69 and 267–268. |
| Sensor layout | Centerline sensors and 6-inch lateral offsets are supported. Figures also show 1-foot longitudinal spacing, omitted by both answers. PDF 64–65, Figure 24; PDF 143, Figure 140. |
| Position triggers | Three infrared triggers at −132/0/+132 feet, upstream acquisition start and two cameras are supported. The baseline's term “laser trigger” also appears in Chapter 7; verify hardware for a new specification. PDF 70–71 and 143. |
| Clock matching | The TSDDs did not share the project's GPS timing system. Computer clocks were used for record matching; this does not establish shared hardware timing. PDF 71. |
| Speed and signal processing | Peak separation and axle spacing support time-to-distance conversion, subject to the correction above. Filtering, integration and the −7 to +10-foot analysis window are documented. PDF 72–77. |
| Lag, averaging and offsets | Lag correction, 1–2-inch uncertainty, cell 19 trigger obstruction, device offsets, 32/50-foot averaging and replicates are supported. PDF 76 and 78–83. |
| Matching and analysis limits | The clearest nearest-GPS matching statement is on PDF 91, beyond the nearby citation in the answer. That page also supports the approximately ±7% analysis uncertainty and lack of raw TSDD data; this is not an overall device-accuracy score. |
| Excluded measurements | Missing ground affected 15 of 64 accelerometer passes; double integration adds uncertainty. Concrete and far-offset reference signals were too small for some comparisons. PDF 71, 77–78 and 82. |
| Texture and moisture | Texture is addressed on PDF 91/102. The moisture-study scheduling limitation is on PDF 126, outside the answer's cited PDF 52–101 range. |
| Missing acquisition details | The passages did not verify the embedded-sensor sampling rate or a shared hardware-clock protocol. A TSD device frequency elsewhere is not a substitute for the embedded system's rate. PDF 71. |

Visual review covered PDF pages 65, 67, 70, 73 and 143. Other checks used extracted report text and saved retrieval results. The related papers were identifiable, but all exact article-page references in the baseline were not fully verified.

Neither answer is a complete experiment specification. Sampling, calibration, positioning uncertainty, repeated runs and acceptance criteria need definition. Proposed shared timing, radar, laser measurement and automated tracking are recommendations, not verified features of the original setup. Useful recommendations in the baseline should not be attributed uniquely to MCP.

## Complete evidence

- [Original answer without pavement MCP](answer_without_mcp.txt)
- [Original answer with pavement MCP](answer_with_mcp.txt)
- [Intended prompt](prompt.txt)
- [Case details, scores, SME approval and answer hashes](case_record.json)
- [Post-answer source checks](source_audit_tool_results.json)
- [Report text extracts](report_pages.json); selected page images are included in this folder.

The original answers are preserved unchanged. This review records the source checks and correction.
