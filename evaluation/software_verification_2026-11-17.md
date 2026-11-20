# Final package verification

Pavement Knowledge MCP team. November 17, 2026.

We checked a separate copy of the final package on Windows x64 with Python 3.11.14. A fresh software environment was installed using the supplied setup script and offline packages. The existing Python installation and prepared report collection, index and model were reused.

| Check | Result |
|---|---|
| Offline installation | Completed; all 113 pinned dependency versions matched and the dependency check passed. |
| Software checks | 25 of 25 passed. |
| Local MCP tools | 7 of 7 passed, including search, report details, evidence retrieval and expected input errors. |
| Client configuration helper | Generated the correct paths for the test installation. |
| Operational files | Matched the original package. Tests used unchanged code in a separate copy. |

These checks confirm installation, local server startup and tool operation in the tested environment. They do not measure AI answer accuracy or establish compatibility with other operating systems. The original package and release files were unchanged by testing.

See the [verification summary](software_verification_2026-11-17.json), [complete tool results](portable_results_2026-11-17.json) and [test inputs](../server/evaluation/cases.json). The [server evaluation](../server/evaluation/REPORT.md) explains how to repeat the software checks. Answer comparisons and SME reviews are listed in the [evaluation guide](README.md).
