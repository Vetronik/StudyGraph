param(
    [Parameter(Mandatory = $true)]
    [string]$BackupPath,
    [string]$DocumentsArchivePath,
    [string]$DocumentDirectory = "data/documents",
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

if ($DocumentsArchivePath) {
    $resolvedDocumentsArchivePath = (Resolve-Path -LiteralPath $DocumentsArchivePath -ErrorAction Stop).Path
    New-Item -ItemType Directory -Force -Path $DocumentDirectory | Out-Null
    Write-Host "Restoring document files from $resolvedDocumentsArchivePath"
    Expand-Archive -LiteralPath $resolvedDocumentsArchivePath -DestinationPath (Split-Path -Parent $DocumentDirectory) -Force
}

Write-Host "Restore completed."
