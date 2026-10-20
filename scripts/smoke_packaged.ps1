$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$guiDir = Join-Path $root "dist\SuperCalc"
$cli = Join-Path $guiDir "SuperCalcCLI.exe"
if (-not (Test-Path -LiteralPath $cli)) {
    throw "Packaged CLI not found: $cli"
}

$json = & $cli eval "1/3 + 1/6" --json | ConvertFrom-Json
if ($json.value.display -ne "1/2" -or -not $json.value.exact) {
    throw "Packaged exact arithmetic acceptance failed"
}

$env:QT_QPA_PLATFORM = "offscreen"
$env:SUPERCALC_NO_RECOVERY = "1"
$env:SUPERCALC_SMOKE_SCREENSHOT = (Join-Path $root "artifacts\packaged-gui.png")
$env:SUPERCALC_SMOKE_STATUS = (Join-Path $root "artifacts\packaged-gui-status.txt")
$process = Start-Process -FilePath (Join-Path $guiDir "SuperCalc.exe") -ArgumentList "--smoke-test" -WindowStyle Hidden -PassThru
if (-not $process.WaitForExit(45000)) {
    Stop-Process -Id $process.Id -Force
    throw "GUI smoke test timed out"
}
if ($process.ExitCode -ne 0) {
    throw "GUI smoke test failed"
}
$status = Get-Content -LiteralPath $env:SUPERCALC_SMOKE_STATUS -Raw
if ($status -notmatch "1/2") {
    throw "GUI did not compute the expected result: $status"
}
Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
Write-Host "Packaged smoke test passed"

