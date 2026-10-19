# Bratislavský hrad V2 – spustenie na Windows

## 1. Inštalácia

1. **Blender 5.2 LTS**: inštalátor z blender.org (štandardne do `C:\Program Files\Blender Foundation\`).
2. **Godot 4.7.2** (štandardná verzia, nie .NET): zip `Godot_v4.7.2-stable_win64.exe.zip` z godotengine.org.
   Rozbaľ do `C:\Godot\`. Treba aj `Godot_v4.7.2-stable_win64_console.exe` (je v tom istom zipe), skripty ho používajú kvôli výpisom.
3. Ovládač **AMD Adrenalin** v aktuálnej verzii (Godot beží na Vulkane).
4. Voliteľne **Git for Windows** a **Claude Code** (pre ďalšiu prácu).

Iné umiestnenie programov nastavíš premennými prostredia:
`$env:BLENDER = 'D:\...\blender.exe'` a `$env:GODOT = 'D:\...\Godot_v4.7.2-stable_win64_console.exe'`.

## 2. Rozbalenie

Rozbaľ `bratislava_hrad_v2.zip` napríklad do `C:\Work\bratislava_hrad`. Cesta by nemala obsahovať diakritiku.

## 3. Postavenie a spustenie (PowerShell alebo dvojklik na .cmd v koreni projektu)

```powershell
cd C:\Work\bratislava_hrad
.\build.cmd            # Blender vygeneruje model -> out\main\castle.glb (~1–2 min)
.\import_model.cmd     # import do Godotu (prvýkrát niekoľko minút)
.\test.cmd             # walktest + sighttest + screenshoty + benchmark
.\run_godot.cmd        # hra
```

Očakávané výsledky testov: `WALKTEST PASS`, `SIGHTTEST PASS`, `SHOTS 21`. Na Macu M2 Pro dával benchmark
v kvalite Vysoká 51–80 FPS, na Radeone 7900 XT by mal byť výrazne vyšší. V hre kláves F1 prepína kvalitu (Ultra = SDFGI + SSR).

Parametre: `.\win\build.ps1 -Tag test -NoHires`, `.\win\import_model.ps1 -Tag test`, `.\win\test.ps1 -Only walk,sight`,
`.\win\run_godot.ps1 -Editor` (otvorí editor).

## 4. Štruktúra

- `scripts/build_castle.py`: hlavný generátor (palác, terén, záhrada, V1 okolie). Volá V2 moduly:
  - `v2_city.py` (mesto, Dunaj, mosty, skyline; dáta v `data/v2/city/`),
  - `v2_fortress.py` (brány, bašty, hradby, Zimná jazdiareň, Severný trakt),
  - `v2_garden.py` (terasy, živé ploty, ornamenty, lipy, kvetináče),
  - `v2_interior.py` (miestnosti, schodisko, Rytierska sála, klenotnica, pivnica, organ).
- `scripts/textures.py`: procedurálne textúry (numpy, súčasť Blendera).
- `godot/`: hra (`scripts/main.gd`, `player.gd`, `cli_tools.gd`, shadery).
- `data/`: OSM, DMR (`dmr256.json` = 2,4 m mriežka pre `--hires`), ortofotá, referenčné fotky `data/ref/v2/` (+ `SPEC.md`).
- `out/` a `godot/models/` sa generujú, netreba ich prenášať.
- `HANDOFF.md`: stav projektu a poznámky pre ďalšiu prácu s Claude Code.

## 5. Známe rozdiely voči macOS

- `.sh` skripty (`import_model.sh`, `run_godot.sh`) sú pre macOS. Na Windows použi `.cmd` / `win\*.ps1`.
- Ak PowerShell zablokuje skripty, `.cmd` wrappery ich spúšťajú s `-ExecutionPolicy Bypass`.
- Webová verzia (`godot_web/`) potrebuje export šablóny Godot 4.7.2 (Editor → Manage Export Templates).
