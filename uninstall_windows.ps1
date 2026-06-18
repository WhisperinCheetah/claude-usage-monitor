# Remove the shortcuts created by install_windows.ps1.
$ErrorActionPreference = "SilentlyContinue"

$programs = [Environment]::GetFolderPath("Programs")
$startup  = [Environment]::GetFolderPath("Startup")

foreach ($dir in @($programs, $startup)) {
    $lnk = Join-Path $dir "Claude Usage Monitor.lnk"
    if (Test-Path $lnk) {
        Remove-Item $lnk
        Write-Host "Removed $lnk"
    }
}
Write-Host "Done."
