# Dashboard launcher (called by run_dashboard.bat):
# starts the server on port 5000 right away, centers this window, opens the browser
# as soon as the server answers, and Esc stops everything.

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$Host.UI.RawUI.WindowTitle = "Academic Research Assistant"

$port = 5000
$url = "http://127.0.0.1:$port"  # the same as http://localhost:5000
$python = Join-Path $root "venv\Scripts\python.exe"

function Exit-AfterKey($code) {
    Write-Host ""
    Write-Host "Press any key to close this window."
    [void][Console]::ReadKey($true)
    exit $code
}

function Test-Port($number) {
    # True if something is listening on 127.0.0.1:$number (connection refused returns at once)
    $client = New-Object System.Net.Sockets.TcpClient
    try { $client.Connect("127.0.0.1", $number); return $true } catch { return $false } finally { $client.Close() }
}

# Returns the process of THIS project's server if it is the one using the port, else $null.
# Our server is "python -m flask --app app run" or "python app.py", started from this project's venv.
function Get-OurServer($number) {
    $listener = Get-NetTCPConnection -LocalPort $number -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $listener) { return $null }
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)"
    # The venv's python.exe starts the real Python as a child, so also look at the parent
    $parent = Get-CimInstance Win32_Process -Filter "ProcessId = $($process.ParentProcessId)" -ErrorAction SilentlyContinue
    foreach ($p in @($parent, $process)) {
        if ($p -and $p.ExecutablePath -and $p.ExecutablePath.StartsWith((Join-Path $root "venv"), "OrdinalIgnoreCase") `
                -and $p.CommandLine -match "flask --app app run|app\.py") {
            return $p
        }
    }
    return $null
}

Write-Host "=============================================="
Write-Host " Academic Research Assistant"
Write-Host "=============================================="

if (-not (Test-Path $python)) {
    Write-Host "The virtual environment was not found. Run setup.bat first."
    Exit-AfterKey 1
}

# ---------- 1. Make sure port 5000 is free ----------
if (Test-Port $port) {
    $old = Get-OurServer $port
    if ($old) {
        # An older run of this dashboard is still open: restart it, so the newest code runs
        Write-Host "Restarting the dashboard that was already running..."
        taskkill /PID $old.ProcessId /T /F 2>&1 | Out-Null
        $wait = [Diagnostics.Stopwatch]::StartNew()
        while ((Test-Port $port) -and $wait.Elapsed.TotalSeconds -lt 5) { Start-Sleep -Milliseconds 100 }
    }
    if (Test-Port $port) {
        $listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
        $name = if ($listener) { (Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue).ProcessName } else { "unknown" }
        Write-Host "Port $port is used by another program ($name). Close it, then start the dashboard again."
        Exit-AfterKey 1
    }
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

# ---------- 3. Start the server right away (fast mode) ----------
# - flask run without debug: the app starts once (debug mode starts it twice)
# - the embedding model loads in the background after the page opens (see app.py)
# - Hugging Face offline mode when the model is already downloaded: no online checks
$env:PYTHONIOENCODING = "utf-8"
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"
$hfHub = if ($env:HF_HOME) { Join-Path $env:HF_HOME "hub" } else { Join-Path $HOME ".cache\huggingface\hub" }
if (Test-Path (Join-Path $hfHub "models--sentence-transformers--all-MiniLM-L6-v2")) { $env:HF_HUB_OFFLINE = "1" }

Write-Host "Starting the server..."
Write-Host "Dashboard: $url  (also http://localhost:$port)"
Write-Host "Press Esc to stop the server and close this window."
Write-Host ""
$server = Start-Process -FilePath $python -ArgumentList "-m flask --app app run --host 127.0.0.1 --port $port" -NoNewWindow -PassThru

# ---------- 4. Center this window (while the server starts) ----------
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

# ---------- 5. Wait: open the browser when ready, warm up the LLM, stop on Esc ----------
[Console]::TreatControlCAsInput = $true  # Ctrl+C is handled like Esc, so nothing is left running
Add-Type -AssemblyName System.Net.Http
$http = New-Object System.Net.Http.HttpClient
$http.Timeout = [TimeSpan]::FromMinutes(5)

$browserOpened = $false
$llmWarmed = $false
$stopRequested = $false

while (-not $server.HasExited) {
    if (-not $browserOpened -and (Test-Port $port)) {
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

# ---------- 6. Stop everything ----------
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
