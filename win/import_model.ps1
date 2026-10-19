# Copy a build into the Godot project and run the headless import.
# Usage: .\win\import_model.ps1            (imports out\main\castle.glb)
#        .\win\import_model.ps1 -Tag test
param([string]$Tag = 'main')
. "$PSScriptRoot\common.ps1"
$godot = Find-Godot
$src = "$Root\out\$Tag\castle.glb"
if (-not (Test-Path $src)) { throw "Missing $src - run .\win\build.ps1 first" }
New-Item -ItemType Directory -Force "$Root\godot\models" | Out-Null
Copy-Item $src "$Root\godot\models\castle.glb" -Force
# walk/shot tools read out\probes.json: keep it in sync with the imported build
if (Test-Path "$Root\out\$Tag\probes.json") { Copy-Item "$Root\out\$Tag\probes.json" "$Root\out\probes.json" -Force }
# auto-LOD strips thin joinery (window frames, mouldings) at mid distance -> keep full detail
$imp = "$Root\godot\models\castle.glb.import"
if (Test-Path $imp) {
    (Get-Content $imp) -replace '^meshes/generate_lods=true', 'meshes/generate_lods=false' | Set-Content $imp
}
Write-Host "Godot: $godot"
$out = & $godot --headless --path "$Root\godot" --import 2>&1
# first import creates the .import file with LODs on -> fix it and import once more
if (Test-Path $imp) {
    $txt = Get-Content $imp
    if ($txt -match '^meshes/generate_lods=true') {
        $txt -replace '^meshes/generate_lods=true', 'meshes/generate_lods=false' | Set-Content $imp
        $out = & $godot --headless --path "$Root\godot" --import 2>&1
    }
}
$err = $out | Select-String -Pattern 'ERROR'
if ($err) { $err | Select-Object -First 10 | ForEach-Object { $_.Line } } else { Write-Host 'Import OK' }
