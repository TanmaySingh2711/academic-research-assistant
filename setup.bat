@echo off
REM One-time setup on Windows: venv, Python libraries, Ollama model, setup check.
REM Usage: double-click setup.bat (or run it from a terminal in this folder).
REM Exit code: 0 = setup complete, 1 = something failed (used by CI).

cd /d "%~dp0"
set "RC=1"
echo ============================================
echo  Academic Research Assistant - Windows setup
echo ============================================
echo.

REM ---- 1. Find Python 3.10, 3.11 or 3.12 ----
set "PY="
py -3.12 -c "import sys" >nul 2>&1 && set "PY=py -3.12"
if not defined PY py -3.11 -c "import sys" >nul 2>&1 && set "PY=py -3.11"
if not defined PY py -3.10 -c "import sys" >nul 2>&1 && set "PY=py -3.10"
if not defined PY python -c "import sys; sys.exit(0 if (3, 10) <= sys.version_info[:2] <= (3, 12) else 1)" >nul 2>&1 && set "PY=python"
if not defined PY goto :no_python
echo [1/4] Using Python: %PY%

REM ---- 2. Create the virtual environment (only if it does not exist yet) ----
if exist "venv\Scripts\python.exe" (
    echo [2/4] Virtual environment already exists: venv
) else (
    echo [2/4] Creating virtual environment: venv
    %PY% -m venv venv
    if errorlevel 1 goto :venv_failed
)

REM ---- 3. Install the Python libraries ----
echo [3/4] Installing Python libraries. The first time this downloads about 1 GB, mostly PyTorch...
venv\Scripts\python.exe -m pip install --upgrade pip
venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto :pip_failed
REM Put all Python cache files of this project in .cache\pycache (see scripts\configure_venv.py)
venv\Scripts\python.exe scripts\configure_venv.py

REM ---- 4. Ollama and the llama3.2:3b model ----
set "OLLAMA="
where ollama >nul 2>&1 && set "OLLAMA=ollama"
if not defined OLLAMA if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "OLLAMA=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
if not defined OLLAMA goto :no_ollama
echo [4/4] Downloading the model llama3.2:3b, about 2 GB, skipped if already downloaded...
"%OLLAMA%" pull llama3.2:3b
if errorlevel 1 goto :pull_failed

echo.
echo Checking the setup...
venv\Scripts\python.exe scripts\verify_setup.py
if errorlevel 1 goto :check_failed
echo.
echo Setup complete. Start the app by double-clicking run_dashboard.bat
set "RC=0"
goto :end

:no_python
echo ERROR: Python 3.10, 3.11 or 3.12 was not found.
echo Install Python 3.12 from https://www.python.org/downloads/
echo During install, tick "Add python.exe to PATH". Then run setup.bat again.
goto :end

:venv_failed
echo ERROR: Could not create the virtual environment.
goto :end

:pip_failed
echo ERROR: Installing the Python libraries failed. Read the messages above.
echo Check your internet connection and run setup.bat again.
goto :end

:no_ollama
echo.
echo [4/4] Ollama is not installed.
echo Install it from https://ollama.com/download
echo Then run setup.bat again to download the llama3.2:3b model.
goto :end

:pull_failed
echo ERROR: Could not download llama3.2:3b.
echo Make sure the Ollama app is running, then run setup.bat again.
goto :end

:check_failed
echo ERROR: The setup check failed (a library or a search model is missing). Read the messages above.
echo Check your internet connection and run setup.bat again.
goto :end

:end
echo.
pause
exit /b %RC%
