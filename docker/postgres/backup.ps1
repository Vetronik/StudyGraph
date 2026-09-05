param(
    [string]$OutputDirectory = "backups",
    [string]$DocumentDirectory = "data/documents"
)

$ErrorActionPreference = "Stop"

New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupPath = Join-Path $OutputDirectory "studygraph-$timestamp.sql"
$documentsBackupPath = Join-Path $OutputDirectory "studygraph-$timestamp-documents.zip"

Write-Host "Creating PostgreSQL backup at $backupPath"
docker compose exec -T postgres sh -c 'pg_dump --username "$POSTGRES_USER" --dbname "$POSTGRES_DB"' |
    Set-Content -Path $backupPath -Encoding utf8

if ($LASTEXITCODE -ne 0) {
    Remove-Item -LiteralPath $backupPath -Force -ErrorAction SilentlyContinue
    throw "PostgreSQL backup failed."
}

if (-not (Test-Path -LiteralPath $DocumentDirectory -PathType Container)) {
    Remove-Item -LiteralPath $backupPath -Force -ErrorAction SilentlyContinue
    throw "Document directory does not exist: $DocumentDirectory"
}

Write-Host "Creating document backup at $documentsBackupPath"
try {
    Compress-Archive -Path $DocumentDirectory -DestinationPath $documentsBackupPath -Force
}
catch {
    Remove-Item -LiteralPath $backupPath, $documentsBackupPath -Force -ErrorAction SilentlyContinue
    throw
}

Write-Host "Backup completed: $backupPath and $documentsBackupPath"
