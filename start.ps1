# ================================================================
# Agentic AI Enterprise Assistant — Full Startup Script
# ================================================================
# Run from the project root:  .\start.ps1
# Requires: Docker Desktop running, uv installed, node/npm installed
# ================================================================

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot

Write-Host ""
Write-Host "===========================================================" -ForegroundColor Cyan
Write-Host "  Agentic AI Enterprise Assistant — Startup" -ForegroundColor Cyan
Write-Host "===========================================================" -ForegroundColor Cyan
Write-Host ""

# ── 1. Check Docker is running ────────────────────────────────────────────────
Write-Host "[1/5] Checking Docker..." -ForegroundColor Yellow
try {
    docker info > $null 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Docker not ready" }
    Write-Host "  ✓ Docker is running" -ForegroundColor Green
} catch {
    Write-Host "  ✗ Docker Desktop is not running!" -ForegroundColor Red
    Write-Host "    Please start Docker Desktop and re-run this script." -ForegroundColor Red
    exit 1
}

# ── 2. Start Postgres + Redis ─────────────────────────────────────────────────
Write-Host "[2/5] Starting Postgres + Redis..." -ForegroundColor Yellow
Set-Location $ProjectRoot
docker compose up -d
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ✗ Failed to start Docker services" -ForegroundColor Red
    exit 1
}
Write-Host "  ✓ Postgres and Redis started" -ForegroundColor Green

# Wait for Postgres to be healthy
Write-Host "  Waiting for Postgres to be ready..."
$retries = 20
do {
    Start-Sleep -Seconds 2
    $health = docker inspect --format="{{.State.Health.Status}}" agentic_ai_postgres 2>$null
    $retries--
} while ($health -ne "healthy" -and $retries -gt 0)

if ($health -eq "healthy") {
    Write-Host "  ✓ Postgres is healthy" -ForegroundColor Green
} else {
    Write-Host "  ⚠ Postgres health check timed out, continuing anyway..." -ForegroundColor Yellow
}

# ── 3. Run Alembic migrations ─────────────────────────────────────────────────
Write-Host "[3/5] Running database migrations..." -ForegroundColor Yellow
Set-Location "$ProjectRoot\backend"
uv run alembic upgrade head
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ✗ Migration failed! Check your DATABASE_URL in .env" -ForegroundColor Red
    exit 1
}
Write-Host "  ✓ Database schema is up to date" -ForegroundColor Green

# ── 4. Start backend ──────────────────────────────────────────────────────────
Write-Host "[4/5] Starting FastAPI backend on port 8000..." -ForegroundColor Yellow
$backendJob = Start-Process powershell -ArgumentList @(
    "-NoProfile",
    "-Command",
    "Set-Location '$ProjectRoot\backend'; uv run uvicorn app.main:app --reload --port 8000 --host 0.0.0.0"
) -PassThru
Write-Host "  ✓ Backend starting (PID: $($backendJob.Id))" -ForegroundColor Green

Start-Sleep -Seconds 3

# ── 5. Start frontend ─────────────────────────────────────────────────────────
Write-Host "[5/5] Starting Next.js frontend on port 3000..." -ForegroundColor Yellow
$frontendJob = Start-Process powershell -ArgumentList @(
    "-NoProfile",
    "-Command",
    "Set-Location '$ProjectRoot\frontend'; npm run dev"
) -PassThru
Write-Host "  ✓ Frontend starting (PID: $($frontendJob.Id))" -ForegroundColor Green

Write-Host ""
Write-Host "===========================================================" -ForegroundColor Cyan
Write-Host "  All services started!" -ForegroundColor Green
Write-Host ""
Write-Host "  Frontend  →  http://localhost:3000" -ForegroundColor White
Write-Host "  Backend   →  http://localhost:8000" -ForegroundColor White
Write-Host "  API Docs  →  http://localhost:8000/api/docs" -ForegroundColor White
Write-Host ""
Write-Host "  Press Ctrl+C to stop watching logs." -ForegroundColor Gray
Write-Host "===========================================================" -ForegroundColor Cyan
Write-Host ""

# Keep script alive
try { Wait-Process -Id $backendJob.Id } catch {}
