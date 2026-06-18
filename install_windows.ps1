# Install Start Menu + Startup shortcuts for the Claude usage monitor (Windows).
# Run in PowerShell:  powershell -ExecutionPolicy Bypass -File .\install_windows.ps1
$ErrorActionPreference = "Stop"

$Repo = $PSScriptRoot
$run  = Join-Path $Repo "run.py"

# Prefer pythonw.exe so no console window appears; fall back to python.exe.
$pyw = Get-Command pythonw.exe -ErrorAction SilentlyContinue
$exe = if ($pyw) { $pyw.Source } else { (Get-Command python.exe).Source }

$shell    = New-Object -ComObject WScript.Shell
$programs = [Environment]::GetFolderPath("Programs")   # Start Menu\Programs
$startup  = [Environment]::GetFolderPath("Startup")    # launch at login

foreach ($dir in @($programs, $startup)) {
    $lnk = Join-Path $dir "Claude Usage Monitor.lnk"
    $s = $shell.CreateShortcut($lnk)
    $s.TargetPath       = $exe
    $s.Arguments        = "`"$run`""
    $s.WorkingDirectory = $Repo
    $s.Description      = "Claude usage monitor"
    $s.Save()
    Write-Host "Created $lnk"
}

Write-Host "Done. 'Claude Usage Monitor' is in the Start Menu and starts at login."
Write-Host "Remove with: .\uninstall_windows.ps1"
