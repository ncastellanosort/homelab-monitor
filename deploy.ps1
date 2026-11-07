<#
.SYNOPSIS
  Sube el monitor al ESP32 en una sola sesion de mpremote (Windows).

.EXAMPLE
  .\deploy.ps1 -Port COM3
  .\deploy.ps1 -Port COM3 -Mpy
  .\deploy.ps1 -DryRun

.NOTES
  -Port    COM3, ... (por defecto: auto)
  -Mpy     precompila los modulos con mpy-cross (menos RAM al importar)
  -DryRun  muestra el comando de mpremote sin ejecutarlo
  Variables opcionales: $env:MPREMOTE, $env:MPY_CROSS (rutas a los ejecutables).
  Si la placa no responde (monitor bloqueando el REPL o watchdog reiniciando),
  haz safe-boot: pulsa EN/RST, suelta, y pulsa BOOT antes de 3 s. Luego repite.
#>
param(
    [string]$Port = "auto",
    [switch]$Mpy,
    [switch]$DryRun
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$mpremote = if ($env:MPREMOTE) { $env:MPREMOTE } else { "mpremote" }
$mpyCross = if ($env:MPY_CROSS) { $env:MPY_CROSS } else { "mpy-cross" }

# Borra en la placa todos los modulos (.py salvo boot/main, y .mpy): un .py
# viejo tendria prioridad sobre un .mpy nuevo. El .env no se toca.
$clean = "import os;[os.remove(f) for f in os.listdir() if f.endswith('.mpy') or (f.endswith('.py') and f not in ('boot.py','main.py'))]"

$files = @()
$sources = Get-ChildItem -Path src -Filter *.py | Sort-Object Name
if ($Mpy) {
    if (Test-Path build) { Remove-Item -Recurse -Force build }
    New-Item -ItemType Directory -Force build | Out-Null
    foreach ($f in $sources) {
        if ($f.Name -in @("boot.py", "main.py")) {
            $files += "src/$($f.Name)"   # MicroPython solo ejecuta los .py
        } else {
            $out = "build/$($f.BaseName).mpy"
            & $mpyCross -o $out "src/$($f.Name)"
            if ($LASTEXITCODE -ne 0) { throw "mpy-cross fallo con $($f.Name)" }
            $files += $out
        }
    }
} else {
    $files = $sources | ForEach-Object { "src/$($_.Name)" }
}

$cmdArgs = @("connect", $Port, "exec", $clean, "+", "cp") + $files + @(":")
if (Test-Path .env) {
    $cmdArgs += @("+", "cp", ".env", ":.env")
} else {
    Write-Warning "No hay .env; se conserva el que ya tenga la placa (copy .env.example .env)."
}
$cmdArgs += @("+", "reset")

if ($DryRun) {
    $quoted = $cmdArgs | ForEach-Object { if ($_ -match '[\s;''"()\[\]]') { "`"$_`"" } else { $_ } }
    Write-Output ("$mpremote " + ($quoted -join " "))
    exit 0
}

Write-Output "Subiendo $($files.Count) archivos a $Port ..."
& $mpremote @cmdArgs
if ($LASTEXITCODE -ne 0) { throw "mpremote fallo (codigo $LASTEXITCODE). Prueba safe-boot y repite." }
Write-Output "Listo. La placa se ha reiniciado; ver salida con: $mpremote connect $Port"
