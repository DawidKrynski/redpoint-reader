# End-to-end test on a real Windows desktop session: Notepad text is selected, the global
# shortcut is pressed, Redpoint must show it and the clipboard must be restored afterwards.
#   tools\e2e_windows.ps1 -Exe path\to\Redpoint.exe -Out out-dir
param([string]$Exe, [string]$Out)
$ErrorActionPreference = 'Continue'
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
$py = Join-Path (Split-Path $PSScriptRoot -Parent) '.venv\Scripts\python.exe'
$press = Join-Path $PSScriptRoot 'press_keys.py'
New-Item -ItemType Directory $Out -Force | Out-Null
$result = [ordered]@{}

function Shot($name) {
  $b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
  $bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size)
  $bmp.Save((Join-Path $Out "$name.png"), [System.Drawing.Imaging.ImageFormat]::Png)
  $g.Dispose(); $bmp.Dispose()
}
function Press($combo) { & $py $press $combo; Start-Sleep -Milliseconds 300 }

# fresh config with a known shortcut
$cfgDir = Join-Path $env:APPDATA 'Redpoint'
Remove-Item $cfgDir -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory $cfgDir | Out-Null
[IO.File]::WriteAllText((Join-Path $cfgDir 'config.json'), '{"hotkey": "ctrl+alt+r", "welcome_shown": true, "wpm": 150}')
$env:REDPOINT_LOG = Join-Path $Out 'redpoint.log'
Remove-Item $env:REDPOINT_LOG -ErrorAction SilentlyContinue

Set-Clipboard -Value 'ORIGINAL CLIPBOARD'
$app = Start-Process $Exe -ArgumentList '--background' -PassThru
Start-Sleep -Seconds 4
$result.app_running = -not $app.HasExited

$txt = Join-Path $Out 'sample.txt'
'Zażółć gęślą jaźń. Redpoint reads this sentence from Notepad on Windows.' | Set-Content $txt -Encoding UTF8
$np = Start-Process notepad.exe -ArgumentList $txt -PassThru
Start-Sleep -Seconds 3
(New-Object -ComObject WScript.Shell).AppActivate('sample') | Out-Null
Start-Sleep -Milliseconds 500
Press 'ctrl+a'
Press 'ctrl+alt+r'
Start-Sleep -Milliseconds 1500
Shot 'reading'
Start-Sleep -Seconds 1
Shot 'reading-later'
$result.clipboard_after = (Get-Clipboard -Raw)
$result.clipboard_restored = ($result.clipboard_after -eq 'ORIGINAL CLIPBOARD')
Press 'escape'
Start-Sleep -Milliseconds 500

# second run: nothing selected -> clipboard fallback
Press 'ctrl+alt+r'
Start-Sleep -Milliseconds 800
Shot 'clipboard-fallback'
Press 'escape'

$result.log = (Get-Content $env:REDPOINT_LOG -ErrorAction SilentlyContinue) -join "`n"
$result.read_selection = $result.log -match 'text from selection: \d+ chars .Za'
$result.fallback = $result.log -match 'text from clipboard: \d+ chars .ORIGINAL'
& $Exe --quit
Start-Sleep -Seconds 2
$result.app_quit = $app.HasExited
Stop-Process -Id $np.Id -Force -ErrorAction SilentlyContinue
$result.ok = $result.app_running -and $result.read_selection -and $result.clipboard_restored -and $result.app_quit
$result | ConvertTo-Json | Set-Content (Join-Path $Out 'e2e.json') -Encoding UTF8
$result | ConvertTo-Json
