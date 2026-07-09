# Local Lua Debug Patch Proposal

Stand: 2026-07-06

Ziel: minimale, lokale Test-Patches fuer private Gamefiles unter `private/Lips/`. Keine Binaerdateien anfassen, keine Gamefiles committen.

## Sauberste Patchstelle

Datei:

- `private/Lips/lps/Script/Main.lua`

Funktion:

- `App:Launch()`

Patchstelle:

- direkt nach `DebugSettings:InitializeDebugSettings()`
- aktuell Zeile `28`

Warum diese Stelle:

- `Settings.lua` darf seine Release-Defaults normal setzen.
- Der Patch ist ein klarer lokaler Override nach der Initialisierung.
- Nur eine lesbare Lua-Datei muss angepasst werden.
- Kein Eingriff in `.luaB`, `.X360`, Executable oder andere Binaerdaten.
- Rollback ist trivial: eingefuegte Zeilen wieder entfernen.

## Patch 1: nur sichtbarer Debug-Indikator

Das ist der kleinste sinnvolle Test. Er aktiviert noch keine Controller-Debugkommandos.

Alte Stelle:

```lua
	DebugSettings:InitializeDebugSettings()
	if DebugSettings.SkipStates then
```

Neue Stelle:

```lua
	DebugSettings:InitializeDebugSettings()

	-- LOCAL DEBUG TEST ONLY: visible marker that Lua override is active.
	DebugSettings.bVersionText = true

	if DebugSettings.SkipStates then
```

Erwarteter sichtbarer Effekt:

- Wenn der relevante Lobby-/Play-Initialisierungspfad erreicht wird, ruft `Main.lua` spaeter bei aktivem `DebugSettings.bVersionText` `ShowVersionText()` statt `HideVersionText()` auf.
- Relevanter Check: `private/Lips/lps/Script/Main.lua:2242`
- Keine In-Game-Debugcommands werden dadurch aktiviert.
- Keine Chart-/Lyric-Dateien werden veraendert.

Rollback:

- Die drei eingefuegten Zeilen nach `DebugSettings:InitializeDebugSettings()` entfernen.

## Patch 1b: sichtbare Chart-Debugflags, weiterhin ohne Debugcommands

Optionaler naechster Sichtbarkeitstest. Nur nutzen, wenn Patch 1 sichtbar greift.

Alte Stelle:

```lua
	DebugSettings:InitializeDebugSettings()
	if DebugSettings.SkipStates then
```

Neue Stelle:

```lua
	DebugSettings:InitializeDebugSettings()

	-- LOCAL DEBUG TEST ONLY: visible flags, no controller debug commands yet.
	DebugSettings.bVersionText = true
	if AppSetting ~= nil then
		AppSetting.showPitchLine = true
		AppSetting.showMarkerLyrics = true
		AppSetting.showLEDs = true
	end

	if DebugSettings.SkipStates then
```

Erwarteter sichtbarer Effekt:

- `bVersionText`: Versionstext wird angezeigt, sobald der spaetere Initialisierungspfad `ShowVersionText()` erreicht.
- `AppSetting.showPitchLine`: `_LoadChart()` waehlt `lpsChartDebugRenderer` statt `lpsChartRenderer`.
- `AppSetting.showMarkerLyrics`: `LyricRenderer` erzeugt Lyrics zusaetzlich im Markerbereich.
- `AppSetting.showLEDs`: `_LoadChart()` erzeugt LED-Indikatoren auf dem Screen.

Relevante Quellen:

- `private/Lips/lps/Script/Main.lua:2242` - Versionstext
- `private/Lips/lps/Script/LpsUtilities.lua:439` - Pitch-Line/Debug-Renderer Spieler 1
- `private/Lips/lps/Script/LpsUtilities.lua:449` - Pitch-Line/Debug-Renderer Spieler 2
- `private/Lips/lps/Script/LpsUtilities.lua:539` - LED-Indikatoren
- `private/Lips/lps/Script/Chart/LyricRenderer.lua:139` - Marker-Lyrics

Rollback:

- Den gesamten eingefuegten lokalen Debugblock nach `DebugSettings:InitializeDebugSettings()` entfernen.

Risiko:

- `AppSetting` ist an anderen Stellen als globaler Runtime-Zustand genutzt. Der `nil`-Guard verhindert einen direkten Lua-Fehler, falls es an dieser Stelle noch nicht existiert.
- Falls `AppSetting` spaeter neu initialisiert wird, koennen diese Flags wieder verloren gehen. Dann waere der naechste saubere Testpunkt der Chart-Aufbau in `_LoadChart()`, aber das waere bereits weniger minimal.

## Patch 2: optional Debugcommands nach Initialize aktivieren

Erst testen, nachdem Patch 1 oder 1b sichtbar funktioniert.

Alte Stelle:

```lua
	DebugSettings:InitializeDebugSettings()
	if DebugSettings.SkipStates then
```

Neue Stelle:

```lua
	DebugSettings:InitializeDebugSettings()

	-- LOCAL DEBUG TEST ONLY: visible flags.
	DebugSettings.bVersionText = true

	-- LOCAL DEBUG TEST ONLY: enable controller debug commands after release init.
	DebugSettings.bEnableInGameDebugCommands = true

	if DebugSettings.SkipStates then
```

Erwarteter sichtbarer Effekt:

- `SELECT + RUP` kann das `lpsDebugMenu` toggeln.
- In-game kann `SELECT + RLEFT` den Debugtext fuer Chart/Pitch/Marker/Timing toggeln.
- In-game kann `SELECT + RUP` den InputDevice-DebugMode toggeln.
- In-game koennen weitere vorhandene Debugkombinationen aktiv werden.

Relevante Quellen:

- `private/Lips/lps/Script/Main.lua:88` - globales `SELECT + RUP` Debugmenue
- `private/Lips/lps/Script/Main.lua:661` - in-game `SELECT + RUP` InputDevice-DebugMode
- `private/Lips/lps/Script/Main.lua:720` - in-game `SELECT + RLEFT` Debugtext
- `private/Lips/lps/Script/LpsUtilities.lua:1268` - `OutputChartPlayerState()`

Rollback:

- Nur die Zeile `DebugSettings.bEnableInGameDebugCommands = true` entfernen, wenn sichtbare Flags bleiben sollen.
- Oder den kompletten lokalen Debugblock nach `DebugSettings:InitializeDebugSettings()` entfernen.

## Nicht empfohlene Minimalpatches

### `Settings.lua` direkt im Release-Block aendern

Beispiel:

```lua
DebugSettings.bEnableInGameDebugCommands = false
```

zu:

```lua
DebugSettings.bEnableInGameDebugCommands = true
```

Das funktioniert wahrscheinlich, ist aber weniger sauber als der Override nach `InitializeDebugSettings()`, weil es Release-Policy und lokalen Test-Override vermischt.

### Binaerdateien oder `.luaB` patchen

Nicht tun. Fuer den Test reichen die lesbaren Lua-Dateien unter `private/Lips/lps/Script/`.

## Empfohlene Reihenfolge

1. Nur Patch 1 anwenden.
2. Starten und pruefen, ob Versionstext sichtbar wird.
3. Wenn ja, Patch 1b testen, um Pitch-Line/Marker-Lyrics/LEDs sichtbar zu machen.
4. Erst danach Patch 2 aktivieren.
5. Debugmenue mit `SELECT + RUP` pruefen.
6. In einem Song `SELECT + RLEFT` pruefen und schauen, ob der Chart-/Pitch-/Marker-Debugtext erscheint.

## Vollstaendiger Rollback

In `private/Lips/lps/Script/Main.lua` den Bereich direkt nach `DebugSettings:InitializeDebugSettings()` wieder auf den Originalzustand bringen:

```lua
	DebugSettings:InitializeDebugSettings()
	if DebugSettings.SkipStates then
```

Danach sind die lokalen Debug-Overrides entfernt.
