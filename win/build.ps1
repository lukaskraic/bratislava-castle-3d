# Generate the castle in Blender -> out\<Tag>\castle.glb (+ castle.blend, probes.json)
# Usage: .\win\build.ps1              (V2 main build, hi-res terrain)
#        .\win\build.ps1 -Tag test -NoHires
param([string]$Tag = 'main', [switch]$NoHires, [switch]$Web)
. "$PSScriptRoot\common.ps1"
$blender = Find-Blender
$a = @('-b', '-P', "$Root\scripts\build_castle.py", '--', '--tag', $Tag)
if (-not $NoHires) { $a += '--hires' }
if ($Web) { $a += '--web' }
New-Item -ItemType Directory -Force "$Root\out\$Tag" | Out-Null
$log = "$Root\out\$Tag\build.log"
Write-Host "Blender: $blender"
$t0 = Get-Date
& $blender @a *> $log
$bad = Select-String -Path $log -Pattern 'Traceback|MODULE FAILED' -SimpleMatch:$false
Select-String -Path $log -Pattern 'objects \d+ polys' | ForEach-Object { $_.Line }
if ($bad) { $bad | ForEach-Object { $_.Line }; throw "Build failed, see $log" }
Write-Host ("Build OK in {0:N0} s -> out\{1}\castle.glb" -f ((Get-Date) - $t0).TotalSeconds, $Tag)
