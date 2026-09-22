[CmdletBinding()]
param(
    [string]$Image = 'postgres:17@sha256:f4c66b820c6f974249089d3d16d86a3698eae11e8746eb6644b2271031e91232',
    [string]$Python = '',
    [switch]$RunRealModel,
    [string]$SecretsEnvPath = '',
    [switch]$KeepContainer
)

$ErrorActionPreference = 'Stop'
$verifier = Join-Path $PSScriptRoot 'verify_query_analytics_executor.ps1'
$modelVariables = @('DEEPSEEK_API_KEY', 'DEEPSEEK_BASE_URL', 'DEEPSEEK_MODEL', 'SQL06_TEST_REAL_MODEL')
$saved = @{}

function Import-ModelEnvironment([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Secrets env file not found: $Path"
    }
    $allowed = @('DEEPSEEK_API_KEY', 'DEEPSEEK_BASE_URL', 'DEEPSEEK_MODEL')
    foreach ($line in Get-Content -LiteralPath $Path) {
        if ($line -notmatch '^\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$') { continue }
        $name = $Matches[1]
        if ($name -notin $allowed) { continue }
        $value = $Matches[2].Trim()
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or
            ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        [Environment]::SetEnvironmentVariable($name, $value, 'Process')
    }
    if (-not $env:DEEPSEEK_API_KEY) {
        throw 'DEEPSEEK_API_KEY is missing; cannot run real-model SQL-06 checks.'
    }
}

try {
    foreach ($name in $modelVariables) {
        $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
    }
    if ($RunRealModel) {
        if (-not $SecretsEnvPath) {
            throw '-RunRealModel requires -SecretsEnvPath; credentials are never copied into the worktree.'
        }
        Import-ModelEnvironment $SecretsEnvPath
        $env:SQL06_TEST_REAL_MODEL = '1'
    }
    else {
        $env:SQL06_TEST_REAL_MODEL = '0'
    }

    & $verifier `
        -Image $Image `
        -Python $Python `
        -Stage 'SQL-06' `
        -AdditionalTestTarget @(
            'backend/tests/test_query_analytics_integration.py',
            'backend/tests/test_query_analytics_sql06.py'
        ) `
        -KeepContainer:$KeepContainer
    if ($LASTEXITCODE -ne 0) {
        throw 'SQL-06 PostgreSQL acceptance verifier failed.'
    }
}
finally {
    foreach ($name in $modelVariables) {
        [Environment]::SetEnvironmentVariable($name, $saved[$name], 'Process')
    }
}
