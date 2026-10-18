# Buduje "dist\AOWcloud Clipper.exe" (jeden plik, bez konsoli).
# Uruchom w PowerShell z folderu projektu:  .\build.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    $py = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $py) { $py = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" }
    & $py -m venv .venv
}
$venvPy = ".venv\Scripts\python.exe"
& $venvPy -m pip install --quiet --upgrade pip
& $venvPy -m pip install --quiet -r requirements.txt

& $venvPy tools\make_icon.py

& $venvPy -m PyInstaller --noconfirm --clean --onefile --windowed `
    --name "AOWcloud Clipper" `
    --icon assets\icon.ico `
    --add-data "clipper\ui\res;clipper\ui\res" `
    --exclude-module tkinter `
    --exclude-module PySide6.QtWebEngineCore `
    --exclude-module PySide6.QtQml `
    --exclude-module PySide6.QtQuick `
    --exclude-module PySide6.Qt3DCore `
    main.py

Write-Host ""
Write-Host "Gotowe: $PSScriptRoot\dist\AOWcloud Clipper.exe"
