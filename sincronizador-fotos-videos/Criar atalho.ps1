$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$pythonExe = Join-Path $projectRoot '.venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Instale o ambiente Python conforme o README.' }
$desktopFolder = [Environment]::GetFolderPath('Desktop')
$shortcutPath = Join-Path $desktopFolder 'FujiTimeline.lnk'
if (Test-Path -LiteralPath $shortcutPath) {
    $shortcutPath = Join-Path $desktopFolder ('FujiTimeline-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.lnk')
}
$shellObject = New-Object -ComObject WScript.Shell
$shortcut = $shellObject.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $pythonExe
$shortcut.Arguments = '-m fujitimeline.gui'
$shortcut.WorkingDirectory = $projectRoot
$shortcut.IconLocation = (Join-Path $projectRoot 'src\fujitimeline\assets\fujitimeline.ico')
$shortcut.Description = 'FujiTimeline - fotos e videos em sincronia'
$shortcut.Save()
Write-Output $shortcutPath
