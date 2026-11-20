param(
    [string]$Python = 'py',
    [string]$Wheelhouse
)
$ErrorActionPreference = 'Stop'
$packageRoot = $PSScriptRoot
$environmentPath = Join-Path $packageRoot '.venv'
$environmentPython = Join-Path $environmentPath 'Scripts/python.exe'
$requirementsPath = Join-Path $packageRoot 'requirements.txt'

if (-not (Test-Path -LiteralPath $requirementsPath -PathType Leaf)) {
    throw 'The tested requirements.txt is missing. Obtain the complete package.'
}
if (Test-Path -LiteralPath $environmentPath) {
    throw 'This package already has a .venv. Use a fresh package folder for installation.'
}
$pythonArguments = @()
if ($Python -eq 'py') { $pythonArguments = @('-3.11') }
& $Python @pythonArguments -I -B -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3,11) and sys.maxsize > 2**32 else 1)'
if ($LASTEXITCODE -ne 0) { throw 'Use 64-bit Python 3.11 for this Windows package.' }
& $Python @pythonArguments -I -B -m venv $environmentPath
if ($LASTEXITCODE -ne 0) { throw 'Could not create the dedicated Python environment.' }

$installArguments = @('-I', '-B', '-m', 'pip', '--isolated', 'install',
    '--disable-pip-version-check', '--no-input', '--require-hashes',
    '--only-binary=:all:', '-r', $requirementsPath)
if ($Wheelhouse) {
    $wheelPath = (Resolve-Path -LiteralPath $Wheelhouse).Path
    $installArguments += @('--no-index', '--find-links', $wheelPath)
} else {
    $installArguments += @('--index-url', 'https://pypi.org/simple')
}
& $environmentPython @installArguments
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Review the pip error above.' }
& $environmentPython -I -B -m pip --isolated check
if ($LASTEXITCODE -ne 0) { throw 'Dependency consistency check failed.' }
Write-Host 'Installed. Use the included sibling runtime assets and run evaluation/run_local.py as described in README.md.'
