# Pavement Knowledge MCP

Prepared by the Pavement Knowledge MCP team.

Pavement Knowledge MCP gives AI assistants evidence-based access to 584 FHWA pavement reports. It finds publications and retrieves relevant passages with source references. Your AI assistant uses that evidence to write its answer.

Retrieval runs locally and needs no answer-generation API key. Your AI assistant may use an online service separately.

## Download and run the complete package

Open **Releases** on this repository's main page. Under **Assets**, download `Pavement-Knowledge-MCP-0.4.1-offline.zip`. This ZIP includes the server code, the searchable FHWA report collection and index, the local search model, and the Python packages for offline installation.

Extract the ZIP into a short local path such as `C:\MCP`. In the extracted `Pavement-Knowledge-MCP` folder, follow **Get started** below. The checksum command verifies the contents of that complete package. The source code archives that GitHub generates automatically contain only the repository files.

## Package contents

| Folder | Contents |
|---|---|
| `server/` | MCP server, setup scripts, client configuration and software checks |
| `runtime/` | Prepared report text, search index and local search model |
| `wheelhouse/` | Python packages for offline installation |
| `evaluation/` | Answer comparisons, SME reviews and supporting evidence |

## Get started

Use **Windows x64, Python 3.11** and an AI client that supports a local MCP connection (STDIO). The client must be able to launch the server on the same computer or within the same sandbox. Other platforms have not been verified.

Keep the supplied folders together and the `runtime/` folder writable. Allow about 3.4 GB for the package, plus space for Python and installed dependencies. The report collection, index and search model are already prepared.

Open PowerShell in this package folder, then:

1. Check the delivered files before installation or first launch:

   ```powershell
   py -3.11 -I -B verify_bundle.py
   ```

2. Install from the included offline packages:

   ```powershell
   .\server\setup.ps1 -Wheelhouse .\wheelhouse
   ```

3. Check the local tools and save the results:

   ```powershell
   .\server\.venv\Scripts\python.exe -I -B server\evaluation\run_local.py --runtime .\runtime --output local-results.json
   ```

   This checks software operation without an AI client. Use a new results filename when repeating it.

4. Generate the connection settings, then enter them in your client's MCP configuration:

   ```powershell
   .\server\.venv\Scripts\python.exe -I -B server\configure_client.py
   ```

   This prints settings using your installation paths; it does not change client settings. Your client may use a different configuration format.

The first request may take tens of seconds while the local search model loads. For examples and troubleshooting, see the [server guide](server/README.md). For environments that restrict scripts or internet access, see [setup alternatives](server/SANDBOX_SETUP.md).

## Evaluation

Start with the [evaluation guide](evaluation/README.md) for answer comparisons, subject-matter expert (SME) reviews and source evidence. The existing `server/evaluation/` folder contains software test scripts, inputs and [recorded results](server/evaluation/REPORT.md).

The **Evaluation Report** is provided as a separate submission.

## Sources and use

The complete package includes the report list in `runtime/SOURCES.csv`. See the [source and software notices](NOTICE.md) and [use notice](USE_NOTICE.md). Check the supporting report pages before relying on technical conclusions: extracted passages may omit context, and answers can repeat source errors.

Runtime files may change during use, so verify checksums before the first launch.
