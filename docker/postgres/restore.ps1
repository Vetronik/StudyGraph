param(
    [Parameter(Mandatory = $true)]
    [string]$BackupPath,
    [switch]$ConfirmRestore
)

$ErrorActionPreference = "Stop"

if (-not $ConfirmRestore) {
    throw "Restore is destructive. Re-run with -ConfirmRestore after verifying the target database."
}

$resolvedBackupPath = (Resolve-Path -LiteralPath $BackupPath -ErrorAction Stop).Path
Write-Host "Restoring PostgreSQL backup from $resolvedBackupPath"

Get-Content -LiteralPath $resolvedBackupPath -Raw |
    docker compose exec -T postgres sh -c 'psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB"'

if ($LASTEXITCODE -ne 0) {
    throw "PostgreSQL restore failed."
}

Write-Host "Restore completed."
