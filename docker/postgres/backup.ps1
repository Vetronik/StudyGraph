param(
    [string]$OutputDirectory = "backups"
)

$ErrorActionPreference = "Stop"

New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupPath = Join-Path $OutputDirectory "studygraph-$timestamp.sql"

Write-Host "Creating PostgreSQL backup at $backupPath"
docker compose exec -T postgres sh -c 'pg_dump --username "$POSTGRES_USER" --dbname "$POSTGRES_DB"' |
    Set-Content -Path $backupPath -Encoding utf8

if ($LASTEXITCODE -ne 0) {
    Remove-Item -LiteralPath $backupPath -Force -ErrorAction SilentlyContinue
    throw "PostgreSQL backup failed."
}

Write-Host "Backup completed: $backupPath"
