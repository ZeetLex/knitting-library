param(
    [string]$OutputDirectory = 'app/backend/assets'
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    $helperPython = Join-Path $projectRoot '.venv-helper/Scripts/python.exe'
    if (-not (Test-Path -LiteralPath $helperPython)) {
        python -m venv .venv-helper
        if ($LASTEXITCODE -ne 0) { throw 'Could not create helper environment.' }
    }
    & $helperPython -m pip install -r tools/requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Could not install helper dependencies.' }
    & $helperPython -m PyInstaller --noconfirm --onefile --windowed --paths app/backend `
        --name KnittingLibrary-ChatGPT --distpath $OutputDirectory `
        --workpath data-test/helper-build --specpath data-test tools/chatgpt_connect.py
    if ($LASTEXITCODE -ne 0) { throw 'Could not build helper.' }
    $executable = Join-Path $OutputDirectory 'KnittingLibrary-ChatGPT.exe'
    (Get-FileHash -LiteralPath $executable -Algorithm SHA256).Hash.ToLower() + '  KnittingLibrary-ChatGPT.exe' |
        Set-Content -Encoding ascii -LiteralPath (Join-Path $OutputDirectory 'SHA256SUMS')
    Write-Output "Helper and checksum: $OutputDirectory"
} finally {
    Pop-Location
}
