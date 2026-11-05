# Runs the private HQ server.
$ErrorActionPreference = 'Stop'
& python -I -B (Join-Path $PSScriptRoot 'run-server.py')
exit $LASTEXITCODE
