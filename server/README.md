# Pavement Knowledge MCP: server guide

Prepared by the Pavement Knowledge MCP team.

Start with the [main README](../README.md) for installation and connection steps. This guide explains the tools, assistant guidance and common setup issues.

## Tools

| Tool | Purpose |
|---|---|
| `search_publications` | Find reports by topic, title or report number and obtain their document IDs |
| `get_publication` | Get report details for a known document ID |
| `retrieve_evidence` | Retrieve passages across the collection, from one report, or for a report overview |

Results include report details, available source links and PDF page ranges. The AI assistant writes the answer using those passages. Selected passages may not cover every part of a report.

## Installation options

The supplied packages target Windows x64 with Python 3.11. From this `server/` folder, run:

```powershell
.\setup.ps1 -Wheelhouse ..\wheelhouse
```

The installer creates a dedicated `.venv` environment, checks package hashes and checks that dependencies are consistent. It will not overwrite an existing `.venv`; use a fresh package folder for a new installation.

The default Python command is `py -3.11`. To choose another Python 3.11 installation, add `-Python "C:\Python311\python.exe"`, replacing the path with your own. Omit `-Wheelhouse` to install from PyPI when internet access is allowed. See [setup alternatives](SANDBOX_SETUP.md) if PowerShell scripts are restricted.

Keep the supplied `server/`, `runtime/` and `wheelhouse/` folders together. The complete matching report collection, index and local model are included; startup does not download or rebuild them. The `runtime/` folder must remain writable.

## Connect the AI client

From this folder, print the connection settings:

```powershell
.\.venv\Scripts\python.exe -I -B configure_client.py
```

Enter the output in your client's supported MCP configuration format. It supplies the Python executable, launcher arguments and runtime/model-cache paths. The [example configuration](examples/stdio-config.json) shows the structure; its paths are placeholders.

The client launches the server locally over STDIO. A hosted URL is not required. The client must run where the configured files are accessible and be permitted to start the Python process. Your client's AI service and charges are separate from this MCP.

The local model and index load at startup. Allow extra time for the first request. The server writes `local retrieval ready` to its diagnostic log when loading succeeds. Running the launcher manually leaves it waiting for MCP messages.

## Companion guidance

Where your client supports skills, we recommend installing the included [pavement-research folder](skills/pavement-research/) through its supported mechanism. This guidance helps the assistant find reports, assess evidence and cite sources. Confirm that it is available in the conversation. The MCP also works without the skill.

## Try a question

After completing the software check in the main README, confirm that your client lists the three tools above. Client-specific prefixes may appear in their names.

> Using only the connected pavement corpus, explain how FWD and TSD measurements differ and when each is useful. Cite the retrieved reports and available page references. Identify details the passages do not establish. Do not search the web.

Check that the client retrieves evidence and includes source references in its answer.

For a report overview, first find the report with `search_publications`. Use the returned `doc_id` with `retrieve_evidence`, set `mode` to `report_overview`, and omit `query`. Follow up on missing topics with a question scoped to the same report.

## Troubleshooting

| Issue | What to check |
|---|---|
| Server does not appear | Check the generated Python and launcher paths, local STDIO support and refreshed client session. |
| First request takes longer | Allow time for the local model and index to load; inspect the server's diagnostic log. |
| `CORPUS_UNAVAILABLE` | Check that the complete `runtime/` folder is present and accessible. |
| `SERVICE_UNAVAILABLE` | Check installed dependencies, the local model cache and startup diagnostics, then restart. |
| `INVALID_ARGUMENT` | Check the document ID, request mode, query and limits against the tool definition. |
| Evidence is weak or irrelevant | Narrow the question or select a report. An empty result does not prove that the topic is absent from the collection. |

## Evidence and evaluation

PDF page ranges locate passages and may differ from printed page numbers. Check the original reports for figures, tables and surrounding context. A citation does not guarantee technical correctness; source errors can carry into answers. Identify recommendations separately from documented findings and label any external sources used.

The [evaluation guide](../evaluation/README.md) links answer comparisons and SME reviews. The [software evaluation](evaluation/REPORT.md) documents installation and tool checks, with [test inputs](evaluation/cases.json) and [saved results](evaluation/results.json). Software checks do not measure answer accuracy.

The **Evaluation Report** is a separate submission. Retain the [source notices](../NOTICE.md) and [use notice](../USE_NOTICE.md).
