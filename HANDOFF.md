# Handoff – stav V5 (19. 10. 2026, ~05:30)

Pre Claude Code: prečítaj tento súbor, `SETUP_WINDOWS.md` (ak si na Windows) a `data/ref/v2/SPEC.md`.

## Stav

- V1–V5 sú na GitHube (`main`), web ukážka na `gh-pages` (hrad v `index.pck`, mesto v `city_0.pck`). Git/web len na výslovnú žiadosť.
- Cieľ používateľa: **pešia prechádzka** hrad → schody → Staré Mesto → Dunaj (z výšky očí). Rozsah: hrad, okolie, centrum, nábrežie – ďalej nie.
- Build: `Blender -b -P scripts/build_castle.py -- --tag main --hires` (~1,5 min) → `./import_model.sh out/main/castle.glb`. ~2,70 mil. polygónov (v2_city ≤950 tis.).
- Testy (Godot): `--walktest` (hrad, interiér, záhrada, 4 zostupy do mesta, Dóm→Hlavné nám.→Michalská, Dóm→nábrežie, hrad→Dunaj) PASS,
  `--sighttest` (16 miest) PASS, `--shots`, `--earthshots <dir>` (kamery z Google Earth referencií), `--bench` (High ~47–67 FPS na M2 Pro).
- V hre: 0–9 miesta na hrade, **Shift+1…6** miesta v meste (Hlavné nám., Michalská brána, Dóm, nábrežie, Hviezdoslavovo nám., Zámocké schody).

## V5 (opravy chýb a verné pamiatky)

- Pamiatky podľa fotiek (`data/ref/landmarks/`, Wikimedia Commons, ATTRIBUTION.md) v novom `scripts/v2_landmarks.py`:
  Most SNP (A-pylón, UFO, 2 roviny lán, oceľová mostovka, lávky pod ňou), Dóm sv. Martina (veža s korunou 84,8 m, kaplnka s medenou kupolou),
  Michalská brána, Stará radnica, SND, Primaciálny palác, Reduta, Klarisky. Každý builder v try/except (`V2 LANDMARK FAILED` v logu).
- Autá a ľudia: CC0 modely (Quaternius/KayKit, `data/assets/cc0/`, LICENSE.md) → `scripts/prep_props.py` (Blender, statické pózy, reálne rozmery)
  → `godot/models/props/`. Godot `scripts/street_life.gd` ich inštancuje (MultiMesh po 100 m bunkách): autá z `out/street_cars.json` (build),
  ľudia popri trasách. Kolízie áut sú neviditeľné kvádre v builde.
- Mosty končia na zemi, rieka bez „múru“ pod mostom (terén v koryte pod hladinou), zábradlia so stĺpikmi len pri zráze, priechody len pre OSM
  `building_passage`/`covered`, lampy/lavičky/stromy mimo chodníkov a vozoviek, Svätopluk podľa fotiek, farby fasád podľa Earth.
- Nástroje: `--routeshots <dir> --around` (pohľady do 4 strán), audity `scripts/audit_heights.py`, `out/<tag>/rails.json`;
  `scripts/earth_views.py` opravené výšky kamier 9 nízkych Earth pohľadov.

## V4 (kvalita, bez rozširovania rozsahu)

- Terén a výšky hrad → Podhradie: fasády sedia na teréne (zasypané 2363 → 334), domy na svahu majú podlažia od hornej ulice a sokel max. 3 m.
  Zámocké schody sú jedno schodisko medzi dvoma múrmi z lomového kameňa a dole napájajú Beblavého v rovine.
  Na južnom svahu sú terasy pri oporných múroch a na Mikulášskej súvislá dláždená cesta.
- Domy v Podhradí: červené valbové strechy, vikiere, omietnuté komíny, 6-tabuľkové okná, dvere so schodmi, garáže ako garáže.
- Rampa mosta SNP: súvislý profil, ≥6,5–7 m nad chodníkom, svetlý betón.
- Nástroje: `scripts/audit_heights.py` (výšky budov a ciest), `--routeshots <dir>` (zábery z výšky očí každých 35 m po trasách), Earth zábery `ph_*` (Podhradie).
- Reviews: 10× Codex, 5× Fable.

## Dáta pribudnuté vo V3

- `data/dmr_centre.json`: DMR 300×300 (~5 m) pre centrum a nábrežie (druhá vrstva terénu, `Terrain.covers()`).
- `data/ref/earth/`: 38 referenčných záberov z Google Earth Web (`ge_*` letecké, `gs_*` nízke uličné), kamery v `scripts/earth_views.py`.
  Iba na porovnanie (licencia Google), nie na extrakciu geometrie.
- `scripts/walk_routes.py`: pešie trasy po OSM sieti → `out/<tag>/city_routes.json`; zostupy z hradu: `data/ref/fortress/descents_waypoints.json`.

## Moduly

- `v2_city.py`: mesto, chodecká zóna (kolízie `*-col`), ulice, dlažba, výklady, stromy, pamiatky (Dóm, Stará radnica, SND, Michalská brána…), Dunaj.
- `v2_fortress.py` + `v2_garden.py`: brány, bašty, terasy, cesty a schody v areáli, záhrada, Námestie A. Dubčeka.
- `v2_interior.py`: interiér paláca.

## Pravidlá práce

- Slovensky, stručne; konvenčné commity bez AI atribúcie; necommitovať bez žiadosti.
- Kvalitu overovať screenshotmi z Godotu oproti fotkám/Earth z rovnakého uhla; po každej zmene build → import → walktest/sighttest.

## Známe slabiny

- Socha Svätopluka schematická; niektoré okolité múry a svahy majú zubaté okraje dlažba/tráva (`build_ground_detail`, bunky 0,75 m).
- Fasády Starého Mesta sú procedurálne (bez zapustených okien); niektoré budovy majú pri zemi orezaný rad okien.
- Zubaté okraje dlažby (4 m bunky) na Mudroňovej a pri predmostí SNP – jemnejšie delenie stojí ~+215 tis. polygónov.
- Vydrica je jeden objem, nie terasy; Earth tam má stavenisko.
- Autá sú krabice.
- Earth páry `gs_*`/`ph_*`: kamera v Godote je nižšie ako v Earth (Earth URL `a` je výška cieľa), porovnanie výšok z nich je orientačné.
