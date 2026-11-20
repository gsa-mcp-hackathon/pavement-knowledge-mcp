# Setup in a restricted environment

Prepared by the Pavement Knowledge MCP team.

Use this guide when internet access or PowerShell scripts are restricted. For the usual setup, follow the [main README](../README.md).

## Requirements

- Windows x64 with Python 3.11 and the complete package.
- A client allowed to launch a local Python process and communicate over STDIO.
- The client and server in the same environment, with access to the configured paths.
- A writable `runtime/` folder alongside `server/`, containing the complete supplied collection, index and model cache.

The package includes Python dependencies in `wheelhouse/` for offline installation. No model download, report processing or hosted endpoint is needed. Other operating systems and managed-client policies require separate verification.

## Install offline

Verify the delivered files as described in the main README before installation or first launch. Run the following commands from the `server/` folder.

If PowerShell scripts are permitted:

```powershell
.\setup.ps1 -Wheelhouse ..\wheelhouse
```

If scripts are blocked but Python commands are permitted, use these commands in a fresh package folder with no existing `.venv`:

```powershell
py -3.11 -I -B -m venv .venv
.\.venv\Scripts\python.exe -I -B -m pip --isolated install --no-index --find-links ..\wheelhouse --require-hashes --only-binary=:all: -r requirements.txt
.\.venv\Scripts\python.exe -I -B -m pip --isolated check
```

These commands use the included packages and check their hashes. Follow the environment's normal permissions; no execution-policy change is required.

## Check and connect

Run the local software check:

```powershell
.\.venv\Scripts\python.exe -I -B evaluation\run_local.py --runtime ..\runtime --output sandbox-results.json
```

It checks the three tools and expected input errors, and saves requests, results and timings. It does not generate or score AI answers. Use a new output filename for each run. The default timeout is 240 seconds per call; `--timeout` changes it.

After the check passes, generate the connection settings:

```powershell
.\.venv\Scripts\python.exe -I -B configure_client.py
```

Enter these settings in the AI client running within the same environment. Paths inside a sandbox cannot be used directly by a client outside it.

See the [server guide](README.md) for questions and troubleshooting. Retain the package's [source notices](../NOTICE.md) and [use notice](../USE_NOTICE.md).
