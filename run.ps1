# run.ps1 — khởi động toàn bộ Derma trên Windows (PowerShell).
# Chạy: .\run.ps1   (cần cho phép script: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned)
param(
    [switch]$InfraOnly,
    [switch]$NoFrontend
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

function Start-Svc($name, $dir, $cmd) {
    $full = Join-Path $root $dir
    Start-Process powershell -ArgumentList "-NoExit","-Command","cd '$full'; $cmd" -WindowStyle Normal
    Write-Host "started $name" -ForegroundColor Green
}

# 1. Hạ tầng
docker compose -f (Join-Path $root "deploy\docker-compose.yml") up -d
if ($LASTEXITCODE -ne 0) { throw "infra failed" }

# 2. Tạo DB
& "C:\Program Files\Git\bin\bash.exe" (Join-Path $root "scripts\init-service-databases.sh")
if ($LASTEXITCODE -ne 0) { throw "services-db failed" }

# 3. Migration knowledge
Push-Location (Join-Path $root "knowledge_service")
uv run alembic upgrade head
Pop-Location
if ($LASTEXITCODE -ne 0) { throw "knowledge-migrate failed" }

if ($InfraOnly) { return }

# 4. Các service (mỗi cái một cửa sổ)
Start-Svc "gateway"        "gateway_service"        ".\mvnw spring-boot:run"
Start-Svc "identity"       "identity_service"       ".\mvnw spring-boot:run"
Start-Svc "consultation"   "consultation_service"   ".\mvnw spring-boot:run"
Start-Svc "clinical"       "clinical_service"       ".\mvnw spring-boot:run"
Start-Svc "knowledge"      "knowledge_service"      "uv run python -m app.main"
Start-Svc "knowledge-worker" "knowledge_service"    "uv run python -u -m app.workers.document_ingest_worker"
Start-Svc "ai"             "ai_service"            "uv run python -m app.main"

if (-not $NoFrontend) {
    Start-Svc "frontend" "fe" "pnpm dev"
}

Write-Host ""
Write-Host "Frontend: http://localhost:3010  (gateway :3040)" -ForegroundColor Cyan
Write-Host "Tài khoản mẫu: user-1 / doctor-1 / admin-1, mật khẩu 123456" -ForegroundColor Cyan