# stop.ps1 — dừng toàn bộ Derma trên Windows.
$root = $PSScriptRoot
foreach ($p in 3040,3051,3052,3053,3054,3055,3010) {
    $c = Get-NetTCPConnection -LocalPort $p -ErrorAction SilentlyContinue
    if ($c) {
        taskkill /PID $c.OwningProcess /F 2>$null | Out-Null
        Write-Host "killed port $p" -ForegroundColor Yellow
    }
}
docker compose -f (Join-Path $root "deploy\docker-compose.yml") down
Write-Host "infra stopped" -ForegroundColor Green