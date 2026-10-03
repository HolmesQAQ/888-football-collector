param([switch]$CheckOnly, [switch]$NoBrowser, [switch]$Web, [switch]$PortableOnly)
$ErrorActionPreference = 'Stop'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONUTF8 = '1'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Set-Location -LiteralPath $PSScriptRoot
function Test-Python([string]$Executable) {
    if (-not (Test-Path -LiteralPath $Executable)) { return $false }
    try {
        & $Executable -c 'import sys,sqlite3,ssl; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>$null
        return ($LASTEXITCODE -eq 0)
    } catch { return $false }
}
try {
    $appFile = Join-Path $PSScriptRoot 'console.py'
    if ($Web -or $NoBrowser) { $appFile = Join-Path $PSScriptRoot 'app.py' }
    if (-not (Test-Path -LiteralPath $appFile)) { throw 'Program files missing. Extract the entire ZIP first.' }
    $config = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'python-runtime.json') -Raw | ConvertFrom-Json
    $arch = $env:PROCESSOR_ARCHITECTURE
    if ($env:PROCESSOR_ARCHITEW6432) { $arch = $env:PROCESSOR_ARCHITEW6432 }
    $suffix = switch ($arch.ToUpperInvariant()) { 'AMD64' {'amd64'} 'ARM64' {'arm64'} 'X86' {'win32'} default { throw 'Unsupported Windows architecture.' } }
    $runtimeRoot = Join-Path $PSScriptRoot '.runtime'
    $runtimeDir = Join-Path $runtimeRoot ('python-' + $config.version + '-' + $suffix)
    $selectedPython = Join-Path $runtimeDir 'python.exe'
    if (-not (Test-Python $selectedPython)) {
        $selectedPython = $null
        if (-not $PortableOnly) {
            $candidates = @((Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'))
            $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
            if ($pythonCommand -and $pythonCommand.Source -notlike '*\WindowsApps\*') { $candidates += $pythonCommand.Source }
            foreach ($candidate in $candidates) {
                if (Test-Python $candidate) { $selectedPython = $candidate; break }
            }
        }
    }
    if (-not $selectedPython) {
        Write-Host 'First run: downloading a private Python runtime from python.org. No administrator rights needed.'
        $spec = $config.archives.$suffix
        if (([Uri]$spec.url).Scheme -ne 'https' -or ([Uri]$spec.url).Host -ne 'www.python.org') { throw 'Invalid runtime download host.' }
        New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
        $zipFile = Join-Path $runtimeRoot ('download-' + [guid]::NewGuid().ToString('N') + '.zip')
        $staging = Join-Path $runtimeRoot ('install-' + [guid]::NewGuid().ToString('N'))
        $allowed = [IO.Path]::GetFullPath($runtimeRoot) + [IO.Path]::DirectorySeparatorChar
        foreach ($target in @($runtimeDir, $staging, $zipFile)) {
            if (-not ([IO.Path]::GetFullPath($target)).StartsWith($allowed,[StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid runtime path.' }
        }
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $ProgressPreference = 'SilentlyContinue'
        try {
            Invoke-WebRequest -UseBasicParsing -Uri $spec.url -OutFile $zipFile -TimeoutSec 120
            $hasher = [Security.Cryptography.SHA256]::Create()
            $stream = [IO.File]::OpenRead($zipFile)
            try { $actualHash = [BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-','') }
            finally { $stream.Dispose(); $hasher.Dispose() }
            if ($actualHash -ne $spec.sha256) { throw 'Python download SHA-256 mismatch. Nothing was installed; retry later.' }
            Add-Type -AssemblyName System.IO.Compression.FileSystem
            [IO.Compression.ZipFile]::ExtractToDirectory($zipFile, $staging)
            if (-not (Test-Python (Join-Path $staging 'python.exe'))) { throw 'Downloaded runtime failed its sqlite3/ssl self-test.' }
            if (Test-Path -LiteralPath $runtimeDir) {
                $resolved = [IO.Path]::GetFullPath($runtimeDir)
                $allowed = [IO.Path]::GetFullPath($runtimeRoot) + [IO.Path]::DirectorySeparatorChar
                if (-not $resolved.StartsWith($allowed,[StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid runtime target.' }
                Move-Item -LiteralPath $resolved -Destination ($resolved + '.old-' + [guid]::NewGuid().ToString('N'))
            }
            Move-Item -LiteralPath $staging -Destination $runtimeDir
        } finally {
            if (Test-Path -LiteralPath $zipFile) { Remove-Item -LiteralPath $zipFile }
        }
        $selectedPython = Join-Path $runtimeDir 'python.exe'
    }
    Write-Host ('Python: ' + $selectedPython)
    if ($CheckOnly) {
        & $selectedPython -c 'import sqlite3,ssl,sys; print(sys.version.split()[0])'
        exit $LASTEXITCODE
    }
    $launchArgs = @()
    if ($NoBrowser) { $launchArgs += '--no-browser' }
    & $selectedPython -c 'import sys,runpy; root,script=sys.argv[1:3]; sys.path.insert(0,root); sys.argv=[script]+sys.argv[3:]; runpy.run_path(script,run_name=__name__)' $PSScriptRoot $appFile @launchArgs
    exit $LASTEXITCODE
} catch {
    Write-Host ('Startup failed: ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host 'Check network access to https://www.python.org, extract all files to a writable folder, then retry start.bat.'
    exit 1
}
