#Requires -Version 7.0
# Protocol stdout belongs exclusively to the Python MCP server.
$ErrorActionPreference = 'Stop'
try {
    if (!$IsWindows) { throw 'Windows configuration required' }
    $configPath = $env:HORMUZ_KIMI_CONFIG
    if ([string]::IsNullOrWhiteSpace($configPath)) {
        $configPath = Join-Path $env:LOCALAPPDATA 'Hormuz/kimi-mcp.json'
    }
    $config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json -AsHashtable
    if ($config -isnot [System.Collections.IDictionary] -or
        @($config.Keys | Where-Object { $_ -cnotin @('python', 'workspace', 'database') }).Count) {
        throw 'Invalid runtime target'
    }
    foreach ($field in @('python', 'workspace')) {
        if ($config[$field] -isnot [string] -or
            ![IO.Path]::IsPathFullyQualified($config[$field])) { throw 'Invalid runtime target' }
    }
    if (!(Test-Path -LiteralPath $config.python -PathType Leaf) -or
        !(Test-Path -LiteralPath (Join-Path $config.workspace 'backend/mcp_server/__main__.py') -PathType Leaf)) {
        throw 'Invalid runtime target'
    }
    $db = $config.database
    $fields = @('user', 'credential', 'host', 'port', 'name')
    if ($db -isnot [System.Collections.IDictionary] -or
        @($db.Keys | Where-Object { $_ -cnotin $fields }).Count) { throw 'Invalid database metadata' }
    foreach ($field in $fields) {
        if ($db[$field] -isnot [string] -or [string]::IsNullOrWhiteSpace($db[$field])) {
            throw 'Invalid database metadata'
        }
    }
    if ($db.port -cnotmatch '^[0-9]{1,5}$' -or [int]$db.port -lt 1 -or [int]$db.port -gt 65535) {
        throw 'Invalid database port'
    }
    # A child-only environment, with inherited DB/MCP/SQL settings removed.
    $start = [Diagnostics.ProcessStartInfo]::new()
    $start.FileName = $config.python
    $start.WorkingDirectory = $config.workspace
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardInput = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    foreach ($arg in @('-m', 'backend.mcp_server', '--transport', 'stdio')) {
        $start.ArgumentList.Add($arg)
    }
    foreach ($key in @($start.Environment.Keys)) {
        if ($key -match '^(MCP_|DB_|AGENT_DB_|AGENT_QUERY_)') {
            [void]$start.Environment.Remove($key)
        }
    }
    $start.Environment['MCP_SQL_ENABLED'] = 'false'
    $start.Environment['MCP_DB_USER'] = $db.user
    $start.Environment['MCP_DB_PASSWORD_CREDENTIAL'] = $db.credential
    $start.Environment['MCP_DB_HOST'] = $db.host
    $start.Environment['MCP_DB_PORT'] = $db.port
    $start.Environment['MCP_DB_NAME'] = $db.name
    # Relay raw bytes, never PowerShell pipeline objects or line-oriented text.
    $child = [Diagnostics.Process]::Start($start)
    $inputCopy = [Console]::OpenStandardInput().CopyToAsync($child.StandardInput.BaseStream)
    $outputCopy = $child.StandardOutput.BaseStream.CopyToAsync([Console]::OpenStandardOutput())
    $errorCopy = $child.StandardError.BaseStream.CopyToAsync([Console]::OpenStandardError())
    while (!$child.HasExited -and !$inputCopy.IsCompleted) {
        [Threading.Thread]::Sleep(20)
    }
    if ($inputCopy.IsCompleted) { $child.StandardInput.Close() }
    $child.WaitForExit()
    [void]$outputCopy.GetAwaiter().GetResult()
    [void]$errorCopy.GetAwaiter().GetResult()
    exit $child.ExitCode
} catch {
    [Console]::Error.WriteLine('Hormuz MCP launch failed; check the local runtime configuration.')
    exit 1
}
