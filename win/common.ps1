# Shared helpers: locate Blender / Godot on Windows. Override with $env:BLENDER / $env:GODOT.
# 'Continue': Windows PowerShell 5.1 turns any stderr line of a native exe (Blender warnings) into an error,
# which with 'Stop' aborts the build; failures are detected from the logs / exit codes instead
$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent $PSScriptRoot

function Find-Blender {
    if ($env:BLENDER -and (Test-Path $env:BLENDER)) { return $env:BLENDER }
    $c = Get-ChildItem 'C:\Program Files\Blender Foundation\Blender*\blender.exe' -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending | Select-Object -First 1
    if ($c) { return $c.FullName }
    $p = Get-Command blender.exe -ErrorAction SilentlyContinue
    if ($p) { return $p.Source }
    throw 'Blender not found. Install Blender 5.2 LTS or set $env:BLENDER to blender.exe'
}

function Find-Godot {
    # the *_console.exe build prints to the terminal (needed for tests); the plain exe is GUI-only
    if ($env:GODOT -and (Test-Path $env:GODOT)) { return $env:GODOT }
    $roots = @("$env:LOCALAPPDATA\Microsoft\WinGet\Packages", 'C:\Godot', "$env:USERPROFILE\Godot",
               "$env:USERPROFILE\Downloads", 'C:\Program Files\Godot', "$Root\tools")
    foreach ($r in $roots) {
        if (-not (Test-Path $r)) { continue }
        $c = Get-ChildItem $r -Recurse -Filter 'Godot_v4.7*_win64_console.exe' -ErrorAction SilentlyContinue |
            Sort-Object FullName -Descending | Select-Object -First 1
        if ($c) { return $c.FullName }
    }
    $p = Get-Command godot.exe -ErrorAction SilentlyContinue
    if ($p) { return $p.Source }
    throw 'Godot 4.7.2 not found. Unzip it to C:\Godot or set $env:GODOT to Godot_v4.7.2-stable_win64_console.exe'
}
