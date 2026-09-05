[CmdletBinding()]
param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [double]$WarningLimitGB = 9.0,
    [double]$HardLimitGB = 10.0
)

$resolvedRoot = (Resolve-Path -LiteralPath $ProjectRoot -ErrorAction Stop).Path
$files = Get-ChildItem -LiteralPath $resolvedRoot -Recurse -File -Force -ErrorAction SilentlyContinue
$totalBytes = ($files | Measure-Object -Property Length -Sum).Sum
if ($null -eq $totalBytes) { $totalBytes = 0 }

$totalGB = [math]::Round($totalBytes / 1GB, 4)
$largest = $files | Sort-Object Length -Descending | Select-Object -First 10 FullName, Length

Write-Host "NDirty total project size: $totalGB GB ($totalBytes bytes)"
Write-Host "Largest files:"
$largest | Format-Table -AutoSize

if ($totalBytes -ge ($HardLimitGB * 1GB)) {
    Write-Error "Project exceeds the hard $HardLimitGB GB limit."
    exit 2
}

if ($totalBytes -ge ($WarningLimitGB * 1GB)) {
    Write-Error "Project exceeds the $WarningLimitGB GB release-warning limit."
    exit 1
}

exit 0
