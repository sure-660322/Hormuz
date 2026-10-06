# 启动本地瓦片服务（OSM 底图，端口 8080）
# 前置条件：tiles/ 目录已有瓦片（scripts/download_tiles.py 产物）

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)   # 仓库根目录
$nginxDir = Join-Path $root 'local-archive/nginx-1.30.5'
$nginx = Join-Path $nginxDir 'nginx.exe'
$conf = Join-Path $PSScriptRoot 'nginx.conf'

if (-not (Test-Path $nginx)) { throw "nginx 不存在: $nginx（见 deploy/tiles/README）" }
if (-not (Test-Path (Join-Path $root 'tiles'))) { Write-Host "警告: tiles/ 目录不存在，先运行 scripts/download_tiles.py" -ForegroundColor Yellow }

Start-Process -FilePath $nginx -ArgumentList '-p', "`"$nginxDir`"", '-c', "`"$conf`"" -WindowStyle Hidden
Start-Sleep -Milliseconds 800
try {
    $r = Invoke-WebRequest -Uri 'http://localhost:8080/health' -UseBasicParsing -TimeoutSec 5
    Write-Host "tile server: $($r.Content) @ http://localhost:8080/tiles/{z}/{x}/{y}.png"
} catch {
    Write-Host "启动后健康检查失败: $_" -ForegroundColor Red
    exit 1
}
