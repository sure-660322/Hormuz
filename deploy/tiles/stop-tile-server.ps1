# 停止本地瓦片服务

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$nginxDir = Join-Path $root 'local-archive/nginx-1.30.5'
$nginx = Join-Path $nginxDir 'nginx.exe'
$conf = Join-Path $PSScriptRoot 'nginx.conf'

& $nginx -p $nginxDir -c $conf -s stop
Write-Host 'tile server stopped'
