[CmdletBinding()]
param(
    [string]$Image = 'postgres:17@sha256:f4c66b820c6f974249089d3d16d86a3698eae11e8746eb6644b2271031e91232',
    [string]$Python = '',
    [switch]$KeepContainer
)

$ErrorActionPreference = 'Stop'
$verifier = Join-Path $PSScriptRoot 'verify_query_analytics_executor.ps1'
& $verifier `
    -Image $Image `
    -Python $Python `
    -Stage 'SQL-05' `
    -AdditionalTestTarget 'backend/tests/test_query_analytics_integration.py' `
    -KeepContainer:$KeepContainer
if ($LASTEXITCODE -ne 0) {
    throw 'SQL-05 PostgreSQL integration verifier failed.'
}
