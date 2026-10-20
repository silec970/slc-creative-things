$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $root

Write-Host "1/6 Install locked dependencies"
uv sync --extra dev --locked --index-url https://pypi.org/simple

Write-Host "2/6 Static checks"
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src

Write-Host "3/6 Unit, integration, GUI and acceptance tests"
New-Item -ItemType Directory -Force -Path (Join-Path $root "artifacts") | Out-Null
uv run pytest --junitxml (Join-Path $root "artifacts\test-results.xml")

Write-Host "4/6 Generate icon and build artifacts"
uv run python scripts\make_icon.py
$guiDist = Join-Path $root "dist\SuperCalc"
$cliExe = Join-Path $root "dist\SuperCalcCLI.exe"
if (Test-Path -LiteralPath $guiDist) {
    $resolvedDist = (Resolve-Path (Join-Path $root "dist")).Path
    if (-not $guiDist.StartsWith($resolvedDist, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to clean a path outside dist"
    }
    Remove-Item -LiteralPath $guiDist -Recurse -Force
}
if (Test-Path -LiteralPath $cliExe) {
    Remove-Item -LiteralPath $cliExe -Force
}
uv run pyinstaller packaging\SuperCalc.spec --noconfirm --clean
uv run pyinstaller packaging\SuperCalcCLI.spec --noconfirm --clean
Copy-Item -LiteralPath $cliExe -Destination (Join-Path $guiDist "SuperCalcCLI.exe") -Force
Copy-Item -LiteralPath (Join-Path $root "README.md") -Destination $guiDist -Force
Copy-Item -LiteralPath (Join-Path $root "LICENSE") -Destination $guiDist -Force
Copy-Item -LiteralPath (Join-Path $root "THIRD_PARTY_NOTICES.md") -Destination $guiDist -Force
$guiDocs = Join-Path $guiDist "docs"
$guiExamples = Join-Path $guiDist "examples"
New-Item -ItemType Directory -Force -Path $guiDocs | Out-Null
New-Item -ItemType Directory -Force -Path $guiExamples | Out-Null
Copy-Item -Path (Join-Path $root "docs\*") -Destination $guiDocs -Recurse -Force
Copy-Item -Path (Join-Path $root "examples\*") -Destination $guiExamples -Recurse -Force

Write-Host "5/6 Packaged smoke tests"
$packagedCli = Join-Path $guiDist "SuperCalcCLI.exe"
$evalOutput = & $packagedCli eval "1/3 + 1/6" --json
if ($LASTEXITCODE -ne 0) { throw "CLI smoke test failed" }
$evalJson = $evalOutput | ConvertFrom-Json
if ($evalJson.value.display -ne "1/2") { throw "CLI exact arithmetic smoke test failed" }

$env:QT_QPA_PLATFORM = "offscreen"
$env:SUPERCALC_NO_RECOVERY = "1"
$env:SUPERCALC_SMOKE_SCREENSHOT = (Join-Path $root "artifacts\packaged-gui.png")
$env:SUPERCALC_SMOKE_STATUS = (Join-Path $root "artifacts\packaged-gui-status.txt")
$guiProcess = Start-Process -FilePath (Join-Path $guiDist "SuperCalc.exe") -ArgumentList "--smoke-test" -WindowStyle Hidden -PassThru
if (-not $guiProcess.WaitForExit(45000)) {
    Stop-Process -Id $guiProcess.Id -Force
    throw "GUI smoke test timed out"
}
if ($guiProcess.ExitCode -ne 0) { throw "GUI smoke test failed with exit code $($guiProcess.ExitCode)" }
$guiStatus = Get-Content -LiteralPath $env:SUPERCALC_SMOKE_STATUS -Raw
if ($guiStatus -notmatch "1/2") { throw "GUI did not compute the expected result: $guiStatus" }

$env:SUPERCALC_GUI_INPROCESS = "1"
$env:SUPERCALC_SMOKE_STATUS = (Join-Path $root "artifacts\packaged-gui-fallback-status.txt")
$fallbackProcess = Start-Process -FilePath (Join-Path $guiDist "SuperCalc.exe") -ArgumentList "--smoke-test" -WindowStyle Hidden -PassThru
if (-not $fallbackProcess.WaitForExit(45000)) {
    Stop-Process -Id $fallbackProcess.Id -Force
    throw "GUI compatibility-mode smoke test timed out"
}
if ($fallbackProcess.ExitCode -ne 0) { throw "GUI compatibility-mode smoke test failed" }
$fallbackStatus = Get-Content -LiteralPath $env:SUPERCALC_SMOKE_STATUS -Raw
if ($fallbackStatus -notmatch "1/2") {
    throw "GUI compatibility mode did not compute the expected result: $fallbackStatus"
}
Remove-Item Env:SUPERCALC_GUI_INPROCESS -ErrorAction SilentlyContinue
Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
Remove-Item Env:SUPERCALC_SMOKE_SCREENSHOT -ErrorAction SilentlyContinue
Remove-Item Env:SUPERCALC_SMOKE_STATUS -ErrorAction SilentlyContinue

Write-Host "6/6 Create portable ZIP and optional installer"
$zipPath = Join-Path $root "dist\SuperCalc-0.1.0-win64.zip"
if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
Compress-Archive -Path (Join-Path $guiDist "*") -DestinationPath $zipPath -CompressionLevel Optimal

$iscc = Get-Command iscc.exe -ErrorAction SilentlyContinue
if ($null -ne $iscc) {
    & $iscc.Source (Join-Path $root "packaging\SuperCalc.iss")
}

Get-FileHash -Algorithm SHA256 -LiteralPath $zipPath | Format-List
Write-Host "Build complete: $zipPath"

