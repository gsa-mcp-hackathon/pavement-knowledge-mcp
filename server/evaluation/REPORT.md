# Installation and local tool evaluation

Prepared by the Pavement Knowledge MCP team. Tests recorded October 21, 2026.

We checked whether Pavement Knowledge MCP could be installed in a fresh software environment and return report details and evidence through its local tools. These checks cover software operation, not AI answer accuracy. The [test inputs](cases.json) and [saved results](results.json) support this report. See the separate [November 17 verification record](../../evaluation/software_verification_2026-11-17.md) for the final package checks.

## What we tested

We tested two fresh installations on one Windows x64 computer using Python 3.11.14 and server version 0.4.1. One installed the required packages from the internet; the other used the supplied setup script and prepared offline packages. Each had its own software environment, with all 113 required package versions and no dependency conflicts. Existing installed packages were not copied into either environment.

Both installations used the same existing Python installation and prepared report collection, search index and model. This tested fresh installation of the MCP software; it did not test rebuilding the collection or installation on a second computer.

## Results

| Check | Result | What passing means |
|---|---|---|
| Software rules and error handling | 25/25 passed | Requests, error responses, excerpt limits and local MCP communication behaved as expected. |
| Requests using actual reports | 16/16 passed | Report details, evidence and expected error responses matched the saved reference results. |
| Tools after offline installation | 7/7 passed | Search, report details, three evidence requests and two invalid requests returned the expected results. |
| Required software packages | Both installations passed | The required versions were installed with no dependency conflicts. |

We also checked a copy in a different folder, using the previously installed environment and the copied code and runtime assets. All 584 catalog records and 16 report-test responses matched the earlier results. The 25 software checks and seven local tool checks also passed there.

In one run, retrieval became ready in about 39 seconds. Successful evidence requests then took about 0.10-1.60 seconds. These times exclude writing an AI answer and do not establish a speed improvement. The first request can include model-loading time; allow for this when connecting a client.

## Repeat the checks

Follow the [server guide](../README.md) or [restricted-environment setup guide](../SANDBOX_SETUP.md), then run these commands from the **server folder**:

```powershell
.\.venv\Scripts\python.exe -I -B tests\test_mcp_foundation.py
.\.venv\Scripts\python.exe -I -B tests\test_mcp_tools.py
.\.venv\Scripts\python.exe -I -B tests\test_mcp_evidence.py
.\.venv\Scripts\python.exe -I -B evaluation\run_local.py --runtime ..\runtime --output local-results.json
```

The first three commands use simulated inputs and do not need the report collection. The last command uses the supplied collection, index and model to check the tools and save requests, responses and timings. Use a new output filename for each run; the script refuses to overwrite existing results and reports failed checks.

Verify the delivered checksums before installation or first launch. Runtime files may change during use. Use a separate copy when checking a package intended for delivery.

## Safeguards and limits

The server checks requests, limits returned text, blocks automatic model downloads during use and ignores answer-generation service settings. Retrieval runs locally; these tests need no AI client or answer-generation API key. Tests restricted outside network access, with a limited local-connection exception needed for Windows operation. These checks do not amount to a full security audit.

A question outside the subject area still returned passages. The assistant must check relevance, context and whether the evidence supports its answer. Returned passages may be incomplete, and an overview does not guarantee full report coverage. Review final answers separately and identify any external sources used.

These tests do not establish performance on Linux, macOS, other Python versions or every managed environment. They did not test a fresh AI-client connection or a corpus rebuild. Source and software terms are described in the [source notices](../../NOTICE.md) and [use notice](../../USE_NOTICE.md).
