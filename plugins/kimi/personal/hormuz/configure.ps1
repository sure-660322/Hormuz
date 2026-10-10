#Requires -Version 7.0
param(
    [Parameter(Mandatory)][string]$Workspace,
    [Parameter(Mandatory)][string]$DbUser,
    [Parameter(Mandatory)][string]$DbCredential,
    [Parameter(Mandatory)][string]$DbName,
    [string]$DbHost = '127.0.0.1',
    [ValidateRange(1, 65535)][int]$DbPort = 5432,
    [switch]$Force
)
$ErrorActionPreference = 'Stop'
$workspacePath = (Resolve-Path -LiteralPath $Workspace).Path
$pythonPath = Join-Path $workspacePath 'backend\.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $pythonPath -PathType Leaf) -or
    !(Test-Path -LiteralPath (Join-Path $workspacePath 'backend\mcp_server\__main__.py') -PathType Leaf)) {
    throw 'Workspace must contain the MCP module and its installed virtual environment.'
}
if ([string]::IsNullOrWhiteSpace($DbUser) -or [string]::IsNullOrWhiteSpace($DbCredential) -or
    [string]::IsNullOrWhiteSpace($DbName) -or [string]::IsNullOrWhiteSpace($DbHost)) {
    throw 'Database metadata and an existing named Windows credential are required.'
}
$configDirectory = Join-Path $env:LOCALAPPDATA 'Hormuz'
$configPath = Join-Path $configDirectory 'kimi-mcp.json'
if ((Test-Path -LiteralPath $configPath) -and !$Force) {
    throw 'Existing local runtime configuration preserved; use -Force only after reviewing it.'
}
$config = @{
    python = $pythonPath
    workspace = $workspacePath
    database = @{ user = $DbUser; credential = $DbCredential; host = $DbHost;
                  port = [string]$DbPort; name = $DbName }
}
New-Item -ItemType Directory -Force -Path $configDirectory | Out-Null
$config | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $configPath -Encoding utf8
Write-Output 'Configured Hormuz MCP locally. No password stored; SQL tools disabled.'
