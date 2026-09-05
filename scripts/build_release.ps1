[CmdletBinding()]
param(
    [string]$Python = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $projectRoot

& $Python -m PyInstaller --noconfirm --windowed --name NDirty --paths src `
    --add-data "models;models" `
    --collect-all rapidocr `
    --collect-all onnxruntime `
    --collect-all cv2 `
    src\ndirty\__main__.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 构建失败。" }

$release = Join-Path $projectRoot "dist\NDirty"
# RapidOCR is configured to use the explicitly bundled models\ocr directory.
# Its package-default model cache is redundant and must not inflate the release.
$redundantRapidOcrModels = Join-Path $release "_internal\rapidocr\models"
if (Test-Path -LiteralPath $redundantRapidOcrModels) {
    Remove-Item -LiteralPath $redundantRapidOcrModels -Recurse -Force
}
Copy-Item -LiteralPath "docs\用户指南.md" -Destination (Join-Path $release "用户指南.md") -Force
Copy-Item -LiteralPath "THIRD_PARTY_NOTICES.md" -Destination (Join-Path $release "THIRD_PARTY_NOTICES.md") -Force
Copy-Item -LiteralPath "版本信息.txt" -Destination (Join-Path $release "版本信息.txt") -Force

$hashFile = Join-Path $release "SHA256SUMS.txt"
Get-ChildItem -LiteralPath $release -Recurse -File |
    Where-Object { $_.Name -ne "SHA256SUMS.txt" } |
    Sort-Object FullName |
    ForEach-Object {
        $relative = $_.FullName.Substring($release.Length).TrimStart('\')
        "$((Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLower())  $relative"
    } | Set-Content -LiteralPath $hashFile -Encoding utf8

& (Join-Path $projectRoot "scripts\check_size.ps1") -ProjectRoot $release
Write-Host "发行包已生成：$release"
