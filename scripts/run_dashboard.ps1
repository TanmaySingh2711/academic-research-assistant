# Dashboard launcher (called by run_dashboard.bat):
# centers this window, starts the server, opens the browser, and Esc stops everything.

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$Host.UI.RawUI.WindowTitle = "Academic Research Assistant"

$url = "http://127.0.0.1:5000"
$python = Join-Path $root "venv\Scripts\python.exe"

function Exit-AfterKey($code) {
    Write-Host ""
    Write-Host "Press any key to close this window."
    [void][Console]::ReadKey($true)
    exit $code
}

function Test-Port($port) {
    # True if something is listening on 127.0.0.1:$port (connection refused returns at once)
    $client = New-Object System.Net.Sockets.TcpClient
    try { $client.Connect("127.0.0.1", $port); return $true } catch { return $false } finally { $client.Close() }
}

# ---------- 1. Center this window on the main screen ----------
Add-Type -Namespace Win32 -Name Window -MemberDefinition @"
[DllImport("kernel32.dll")] public static extern IntPtr GetConsoleWindow();
[DllImport("user32.dll")] public static extern IntPtr GetAncestor(IntPtr hwnd, uint flags);
[DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hwnd, out RECT rect);
[DllImport("user32.dll")] public static extern IntPtr MonitorFromPoint(POINT pt, uint flags);
[DllImport("user32.dll")] public static extern bool GetMonitorInfo(IntPtr monitor, ref MONITORINFO info);
[DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr hwnd, IntPtr after, int x, int y, int cx, int cy, uint flags);
[DllImport("user32.dll")] public static extern IntPtr SetThreadDpiAwarenessContext(IntPtr context);
[StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
[StructLayout(LayoutKind.Sequential)] public struct POINT { public int X, Y; }
[StructLayout(LayoutKind.Sequential)] public struct MONITORINFO { public int cbSize; public RECT rcMonitor; public RECT rcWork; public uint dwFlags; }
"@

function Move-WindowToCenter {
    try {
        # Work in real screen pixels, so scaled laptop screens (125%, 150%) are centered correctly
        [void][Win32.Window]::SetThreadDpiAwarenessContext([IntPtr](-4))

        $hwnd = [Win32.Window]::GetConsoleWindow()
        # In Windows Terminal the console window is hidden; its owner is the visible terminal window
        $owner = [Win32.Window]::GetAncestor($hwnd, 3)  # 3 = GA_ROOTOWNER
        if ($owner -ne [IntPtr]::Zero) { $hwnd = $owner }

        $rect = New-Object Win32.Window+RECT
        [void][Win32.Window]::GetWindowRect($hwnd, [ref]$rect)

        # Work area (screen without the taskbar) of the main screen
        $info = New-Object Win32.Window+MONITORINFO
        $info.cbSize = [Runtime.InteropServices.Marshal]::SizeOf($info)
        $monitor = [Win32.Window]::MonitorFromPoint((New-Object Win32.Window+POINT), 1)  # 1 = primary screen
        [void][Win32.Window]::GetMonitorInfo($monitor, [ref]$info)

        $width = $rect.Right - $rect.Left
        $height = $rect.Bottom - $rect.Top
        $x = $info.rcWork.Left + [int](($info.rcWork.Right - $info.rcWork.Left - $width) / 2)
        $y = $info.rcWork.Top + [int](($info.rcWork.Bottom - $info.rcWork.Top - $height) / 2)
        [void][Win32.Window]::SetWindowPos($hwnd, [IntPtr]::Zero, $x, $y, 0, 0, 0x0001 -bor 0x0004)  # keep size and z-order
    } catch {
        # Centering is only cosmetic; never stop the app because of it
    }
}

Move-WindowToCenter

Write-Host "=============================================="
Write-Host " Academic Research Assistant"
Write-Host "=============================================="

if (-not (Test-Path $python)) {
    Write-Host "The virtual environment was not found. Run setup.bat first."
    Exit-AfterKey 1
}

if (Test-Port 5000) {
    Write-Host "The dashboard is already running (maybe in another window). Opening it..."
    Start-Process $url
    Exit-AfterKey 0
}

# ---------- 2. Start Ollama if it is not running ----------
$ollamaProcess = $null
if (-not (Test-Port 11434)) {
    $ollamaExe = (Get-Command ollama -ErrorAction SilentlyContinue).Source
    if (-not $ollamaExe) { $ollamaExe = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe" }
    if (Test-Path $ollamaExe) {
        Write-Host "Starting Ollama..."
        $ollamaProcess = Start-Process -FilePath $ollamaExe -ArgumentList "serve" -WindowStyle Hidden -PassThru
    } else {
        Write-Host "Ollama was not found. You can upload papers, but answers need Ollama (run setup.bat)."
    }
}

# ---------- 3. Start the server (fast mode) ----------
# - flask run without debug: the app starts once (debug mode starts it twice)
# - Hugging Face offline mode when the embedding model is already downloaded: no online checks at startup
$env:PYTHONIOENCODING = "utf-8"
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"
$hfHub = if ($env:HF_HOME) { Join-Path $env:HF_HOME "hub" } else { Join-Path $HOME ".cache\huggingface\hub" }
if (Test-Path (Join-Path $hfHub "models--sentence-transformers--all-MiniLM-L6-v2")) { $env:HF_HUB_OFFLINE = "1" }

Write-Host "Starting the server, this takes about 10 seconds..."
Write-Host "Dashboard: $url"
Write-Host "Press Esc to stop the server and close this window."
Write-Host ""
$server = Start-Process -FilePath $python -ArgumentList "-m flask --app app run --host 127.0.0.1 --port 5000" -NoNewWindow -PassThru

# ---------- 4. Wait: open the browser when ready, warm up the LLM, stop on Esc ----------
[Console]::TreatControlCAsInput = $true  # Ctrl+C is handled like Esc, so nothing is left running
Add-Type -AssemblyName System.Net.Http
$http = New-Object System.Net.Http.HttpClient
$http.Timeout = [TimeSpan]::FromMinutes(5)

$browserOpened = $false
$llmWarmed = $false
$stopRequested = $false

while (-not $server.HasExited) {
    if (-not $browserOpened -and (Test-Port 5000)) {
        Start-Process $url
        $browserOpened = $true
    }

    # Load llama3.2 into memory in the background, so the first answer is fast
    if (-not $llmWarmed -and (Test-Port 11434)) {
        $body = New-Object System.Net.Http.StringContent('{"model": "llama3.2:3b"}', [Text.Encoding]::UTF8, "application/json")
        [void]$http.PostAsync("http://127.0.0.1:11434/api/generate", $body)
        $llmWarmed = $true
    }

    if ([Console]::KeyAvailable) {
        $key = [Console]::ReadKey($true)
        $ctrlC = $key.Key -eq "C" -and ($key.Modifiers -band [ConsoleModifiers]::Control)
        if ($key.Key -eq "Escape" -or $ctrlC) {
            $stopRequested = $true
            break
        }
    }
    Start-Sleep -Milliseconds 100
}

# ---------- 5. Stop everything ----------
if ($stopRequested) {
    Write-Host ""
    Write-Host "Stopping the server..."
}
if (-not $server.HasExited) { taskkill /PID $server.Id /T /F 2>&1 | Out-Null }
if ($ollamaProcess -and -not $ollamaProcess.HasExited) { taskkill /PID $ollamaProcess.Id /T /F 2>&1 | Out-Null }

if (-not $stopRequested) {
    # The server stopped by itself (for example an error): keep the window open to read the message
    Write-Host ""
    Write-Host "The server stopped unexpectedly. Read the messages above."
    Exit-AfterKey 1
}
exit 0
