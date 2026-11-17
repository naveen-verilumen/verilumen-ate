# Verilumen - ATE Release Build Script
# Reads single source of truth version, builds Windows installer and differential update blockmaps.
$ErrorActionPreference = "Stop"

$Root = $PSScriptRoot
$DesktopDir = Join-Path $Root "desktop"
$PackageJsonPath = Join-Path $DesktopDir "package.json"

if (-not (Test-Path $PackageJsonPath)) {
    throw "Cannot find package.json at $PackageJsonPath"
}

$pkg = Get-Content $PackageJsonPath -Raw | ConvertFrom-Json
$version = $pkg.version
$productName = $pkg.productName

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  BUILDING RELEASE: $productName v$version" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# 1. Sync version.json and frontend src/version.json
$VersionJsonPath = Join-Path $Root "version.json"
$FrontendVerPath = Join-Path $Root "tools\ate_frontend\src\version.json"
$verData = [ordered]@{
    version = $version
    appName = $productName
    releaseName = "Verilumen-ATE-Setup-$version.exe"
}
$verData | ConvertTo-Json -Depth 4 | Set-Content $VersionJsonPath -Encoding utf8
$verData | ConvertTo-Json -Depth 4 | Set-Content $FrontendVerPath -Encoding utf8

# 2. Check for signing certificates in environment
if (-not $env:VL_REUSE_PYTHON) {
    $env:VL_REUSE_PYTHON = "1"
}

if ($env:CSC_LINK) {
    Write-Host "[Code Signing] Certificate found in CSC_LINK. Build will be signed." -ForegroundColor Green
} else {
    Write-Host "[Code Signing] No CSC_LINK set. Proceeding with unsigned build." -ForegroundColor Yellow
}

# 3. Run build-windows.ps1
Push-Location $DesktopDir
try {
    Write-Host "Running Electron + NSIS packaging pipeline..." -ForegroundColor Cyan
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $DesktopDir "scripts\build-windows.ps1")
} finally {
    Pop-Location
}

# 4. Validate output files
$DistDir = Join-Path $DesktopDir "dist"
$Installer = Join-Path $DistDir "Verilumen-ATE-Setup-$version.exe"
$Blockmap = Join-Path $DistDir "Verilumen-ATE-Setup-$version.exe.blockmap"
$LatestYml = Join-Path $DistDir "latest.yml"

Write-Host "============================================================" -ForegroundColor Green
Write-Host "  RELEASE BUILD COMPLETED SUCCESSFULLY" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green

if (Test-Path $Installer) {
    $sizeMb = [math]::Round((Get-Item $Installer).Length / 1MB, 2)
    Write-Host "  Installer:       $Installer ($sizeMb MB)" -ForegroundColor Green
} else {
    Write-Warning "  Installer not found at expected path: $Installer"
}

if (Test-Path $Blockmap) {
    $bmKb = [math]::Round((Get-Item $Blockmap).Length / 1KB, 2)
    Write-Host "  Delta Blockmap:  $Blockmap ($bmKb KB)" -ForegroundColor Green
}

if (Test-Path $LatestYml) {
    Write-Host "  Release Metadata: $LatestYml" -ForegroundColor Green
}

Write-Host "`nReady for distribution or publishing to GitHub Releases." -ForegroundColor Cyan
