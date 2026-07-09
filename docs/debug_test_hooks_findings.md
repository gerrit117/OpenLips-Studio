# Debug/Test Hooks Findings

Stand: 2026-07-06

Dieses Dokument fasst bereinigte Findings aus `private/Lips/` zusammen. Die privaten Gamefiles wurden nicht kopiert oder gedumpt. Ausfuehrliche lokale Scan-Artefakte liegen unter `private/outputs/debug_test_hooks/` und bleiben privat.

## Methodik

- Geprueft: alle Script-Dateien unter `private/Lips/` mit `.lua` und `.luaB` im Script-Bereich.
- Fuer `.lua` wurden Funktionskontext, Trefferbegriffe und Zeilennummern ausgewertet.
- Fuer `.luaB` wurden nur druckbare Strings gescannt. Diese Treffer sind Indizien, aber ohne Decompile kein sicherer Kontrollflussnachweis.
- `private/Lips/` und `private/outputs/` sind ueber `.gitignore` abgedeckt.

Private Scan-Zusammenfassung:

- Script-Dateien gescannt: 202
- Dateien mit Treffern: 187
- Besonders relevante Begriffe: `chart`, `button`, `load`, `lyric`, `SELECT`, `input`, `marker`, `test`, `Debug`, `pitch`, `offset`, `DebugSettings`, `DebugMenu`, `AppSetting`, `bEnableInGameDebugCommands`

## Gesicherte Fakten

### DebugSettings und Aktivierung

`private/Lips/lps/Script/Settings.lua` definiert `DebugSettings` und setzt `bEnableInGameDebugCommands` im Script initial auf `true`.

`DebugSettings:InitializeDebugSettings()` deaktiviert Debug-Features aber, wenn `LPS_LUA_RELEASE == 1` gesetzt ist. Dazu gehoert auch `bEnableInGameDebugCommands = false`.

Relevante Stellen:

- `private/Lips/lps/Script/Settings.lua:1` - `DebugSettings`
- `private/Lips/lps/Script/Settings.lua:39` - `InitializeDebugSettings`
- `private/Lips/lps/Script/Main.lua:28` - Initialisierung beim App-Launch

Folgerung: Debug-Kommandos sind scriptseitig vorhanden, aber in Release-Konfigurationen wahrscheinlich abgeschaltet. Ein reines `AppSetting.ixb`-Flag als Aktivierung wurde im Script-Corpus nicht belastbar gefunden.

### Globales Debug-Menue

`private/Lips/lps/Script/Main.lua` definiert `lpsDebugMenu` als Ableitung von `BasicDebugMenu`.

Das Menue wird ueber `App:eIX_BUTTONID_RUP()` getoggelt, wenn `SELECT` gehalten wird und `DebugSettings.bEnableInGameDebugCommands` aktiv ist.

Relevante Stellen:

- `private/Lips/lps/Script/Main.lua:38` - `lpsDebugMenu`
- `private/Lips/lps/Script/Main.lua:43` - Aufbau der Controls
- `private/Lips/lps/Script/Main.lua:88` - `SELECT + RUP` toggelt `ixDebugMenuAgent:new("lpsDebugMenu")`

Menuepunkte mit direktem Chart-/Lyric-/Marker-Bezug:

| Menuepunkt | Ziel | Bedeutung |
| --- | --- | --- |
| `Show lyrics under markers` | `AppSetting.showMarkerLyrics` | Lyrics werden zusaetzlich an/unter Markern angezeigt |
| `hitMarkerGroupValue` | `AppSetting.hitMarkerGroupValue` | Debug-/Tuning-Wert fuer Hit-Marker-Gruppen |
| `phraseMarkerGroupValue` | `AppSetting.phraseMarkerGroupValue` | Debug-/Tuning-Wert fuer Phrase-Marker-Gruppen |
| `screamMarkerGroupValue` | `AppSetting.screamMarkerGroupValue` | Debug-/Tuning-Wert fuer Scream-Marker-Gruppen |
| `groupBonusThreshold` | `AppSetting.groupBonusThreshold` | Schwelle fuer Gruppenbonus |
| `Master Offset` | `_ChartPlayer.m_MusicStartDelay` | Laufzeitverstellung des Musikstarts, wenn ein Chart aktiv ist |
| `Display led on screen` | `AppSetting.showLEDs` | LED-Debuganzeige |
| `Show pitch line` | `AppSetting.showPitchLine` | Pitch-Line/Debug-Renderer-Pfad |

Bei aktivem Chart werden zusaetzlich Mikrofon-/InputDevice-Parameter angeboten, u.a. LED-Aktivierung, Delay, Gain, Volume und Reverb-Parameter.

### Controller-Kombinationen

| Kontext | Kombination | Wirkung | Quelle |
| --- | --- | --- | --- |
| Global/App | `SELECT + RUP` | toggelt `lpsDebugMenu` | `private/Lips/lps/Script/Main.lua:88` |
| In-game Playing Normal | `SELECT + RUP` | toggelt `inputDevice:SetDebugMode(...)` | `private/Lips/lps/Script/Main.lua:649` |
| In-game Playing Normal | `SELECT + RLEFT` | toggelt `EnableDebugText` und Debug-Display | `private/Lips/lps/Script/Main.lua:710` |
| In-game Playing Normal | `SELECT + RDOWN` | aktiviert Excite Mode und `ForceShake()` fuer Spieler | `private/Lips/lps/Script/Main.lua:683` |
| In-game Coop, im RDOWN-Handler | `SELECT + RRIGHT` | aktiviert Excite Mode fuer beide Grader | `private/Lips/lps/Script/Main.lua:683` |
| Lobby Entrance2 | `L3` | `DebugDumpGameContentDB()` | `private/Lips/lps/Script/Menu/EntranceMenu2.lua:600` |
| Lobby Entrance2 | `R3` | nur noch kommentierte DLC/Disc-Swap-Testhooks | `private/Lips/lps/Script/Menu/EntranceMenu2.lua:589` |
| Play Options | Fokus auf `MasterOffset`, `RDOWN` | Master-Offset-Menue betreten oder Offset anwenden/resetten | `private/Lips/lps/Script/Menu/PlayOptionsMenu.lua:606` |
| MasterOffset-Menue | `LLEFT` / `LRIGHT` | Offset scrollen | `private/Lips/lps/Script/Menu/PlayOptionsMenu.lua:643` |

Hinweis: `SELECT + RUP` existiert global und in-game. Welche Handler-Kette im laufenden Spiel zuerst greift, muss runtime-seitig geprueft werden.

### In-Game Debugtext fuer Chart/Pitch/Marker/Timing

`OutputChartPlayerState()` erzeugt einen umfangreichen Debugtext, wenn `EnableDebugText` und `DebugSettings.bEnableInGameDebugCommands` aktiv sind.

Der Text umfasst:

- Chartless-/Chart-Zustand, Envelope, Tone und Monitoring Volume
- InputDevice-Werte pro Spieler: Envelope, Tone, Volume, Volume-Threshold
- Pitch-Distanz zum Marker
- Pitch-Perfect-Multiplier
- Hit-Combo und Vibrato-Combo
- Mikrofon-Callback-Intervalle
- Berechnungsdetails fuer Medals: Pitch, Rhythm, Stability, Technique, Performance, Party
- Markerzaehler wie Hit Marker, Phrase Marker, Page Counts

Relevante Stellen:

- `private/Lips/lps/Script/LpsUtilities.lua:1268` - `OutputChartPlayerState`
- `private/Lips/lps/Script/LpsUtilities.lua:1424` - `ExciteGestureDebugDisplay`

Das ist der wichtigste gefundene Script-Hook, um eigene Chart-/Pitch-/Timing-Daten im Spiel zu validieren.

### Chart-, Lyric- und Marker-Anzeigehooks

`AppSetting.showMarkerLyrics` wird in `LyricRenderer` ausgewertet. Wenn aktiv und nicht chartless, werden Lyrics zusaetzlich in Markernaehe erzeugt.

Relevante Stelle:

- `private/Lips/lps/Script/Chart/LyricRenderer.lua:137` - `FinishNewLyricPage`

`AppSetting.showPitchLine` beeinflusst in `_LoadChart()` die Rendererwahl: statt normalem `lpsChartRenderer` wird `lpsChartDebugRenderer` verwendet.

Relevante Stellen:

- `private/Lips/lps/Script/LpsUtilities.lua:338` - `_LoadChart`
- `private/Lips/lps/Script/LpsUtilities.lua:439` - Debug-Renderer fuer Spieler 1
- `private/Lips/lps/Script/LpsUtilities.lua:449` - Debug-Renderer fuer Spieler 2

`ChartRenderer` enthaelt die normalen Spawn-Pfade fuer Phrase-, Hit-, Scream-, Call-and-Response-Marker und Pitch-Lines. Diese Funktionen sind keine Debughooks, aber sie zeigen die Script-Semantik der angezeigten Markerarten.

Relevante Datei:

- `private/Lips/lps/Script/Chart/ChartRenderer.lua`

### Chart laden, initialisieren und neu aufbauen

Die zentralen Script-Pfade fuer Chart-Aufbau und Wiedergabe liegen in `LpsUtilities.lua`.

Wichtige Funktionen:

| Funktion | Zweck |
| --- | --- |
| `CreateChart()` | initialisiert Chart-Erzeugung und ruft `_SetupChart(...)` |
| `_GetChart(songPath, pMusicIndex)` | holt ChartPlayer ueber Songpfad oder MusicIndex |
| `_LoadChart()` | erstellt Renderer, Grader, InputDevices und initialisiert `_ChartPlayer` |
| `_SetupChart()` | verbindet `_GetChart()` und `_LoadChart()` |
| `_LoadMusic()` | `LoadMusicFromSequence()` |
| `_LoadMovie()` | `LoadMovieFromSequence()` |
| `PlayChart()` | startet Chart/Musik |
| `UpdateChartSettings()` | setzt Master Offset, Movie Delay, AudioFX und Vocal Reduction |
| `CleanupChart()` | stoppt und raeumt Chart auf |

Relevante Stellen:

- `private/Lips/lps/Script/LpsUtilities.lua:130` - `CreateChart`
- `private/Lips/lps/Script/LpsUtilities.lua:324` - `_GetChart`
- `private/Lips/lps/Script/LpsUtilities.lua:338` - `_LoadChart`
- `private/Lips/lps/Script/LpsUtilities.lua:560` - `_SetupChart`
- `private/Lips/lps/Script/LpsUtilities.lua:574` - `_LoadMusic`
- `private/Lips/lps/Script/LpsUtilities.lua:606` - `_LoadMovie`
- `private/Lips/lps/Script/LpsUtilities.lua:632` - `PlayChart`
- `private/Lips/lps/Script/LpsUtilities.lua:1008` - `UpdateChartSettings`
- `private/Lips/lps/Script/LpsUtilities.lua:1030` - `CleanupChart`

Es wurde kein direkter Lua-Hook gefunden, der eine bereits geladene `.X360`/IXB-Datei nach Dateiaenderung im laufenden Song einfach neu liest. Realistisch ist ein Destroy/Cleanup/Create-Pfad oder der ChartPreview-Pfad.

### ChartPreview/Test-Initialisierung

`private/Lips/lps/Script/ChartPreview.lua` enthaelt Preview-Funktionen fuer Chart-Tests:

- `CreateChartPreview(pChart, bLoadMovie)`
- `LoadChartPreview()`
- `PlayChartPreview(startOffset, Endoffset)`
- `StartChartPreview()`
- `StopChartPreview()`
- `CleanupChartPreview()`
- `DestroyChartPreview()`

Diese Funktionen sind starke Kandidaten fuer Tool-/Editor- oder interne Preview-Kontexte. Sie sind nuetzlich, um den erwarteten Lifecycle fuer kontrolliertes Laden/Stoppen/Neustarten von Charts zu verstehen.

### Master Offset

Es gibt zwei relevante Master-Offset-Pfade:

- Laufzeit-Debugmenue: `Master Offset` bindet direkt an `_ChartPlayer.m_MusicStartDelay`.
- PlayOptions-Menue: `PlayOptionsProperties[7]` ist `MasterOffset` mit Slider und Reset.

`UpdateChartSettings()` setzt den Offset aktiv auf ChartPlayer und Movie:

- `_ChartPlayer:SetMusicStartDelay(GameSessionSetting:GetMasterOffset())`
- `_ChartPlayer:SetMovieStartDelay(GameSessionSetting:GetMasterOffset())`

Relevante Stellen:

- `private/Lips/lps/Script/Menu/PlayOptionsMenu.lua:205` - `MasterOffset`
- `private/Lips/lps/Script/Menu/PlayOptionsMenu.lua:643` - MasterOffset-State
- `private/Lips/lps/Script/LpsUtilities.lua:1008` - Anwendung auf Chart/Movie

### Tests und Assertions

`EnableTests()` laedt `Script/Test/LpsTests`.

`LpsTests.lua` bietet u.a.:

- Text-/Lyric-Extents-Tests
- `TogglePitchArrow()`
- `TestMeshLine(...)`
- `TestMiniGameApi()`
- `TestAssert(...)` und `TestAssertDelta(...)` mit `Assert2`
- einen grossen auskommentierten `TestRenderArea`-Block zur manuellen Verschiebung von Chart- und Marker-Positionen

Relevante Stellen:

- `private/Lips/lps/Script/LpsUtilities.lua:1052` - `EnableTests`
- `private/Lips/lps/Script/Test/LpsTests.lua`

Der Testbereich ist eher Entwickler-/API-Testcode als automatischer Songdatei-Validator. Er ist trotzdem wertvoll, weil er zeigt, welche ChartRenderer-, ChartGrader- und InputDevice-APIs scriptseitig erreichbar sind.

### Logging, Dumping und Validation

Gefundene Hilfen:

- `Report(...)` wird breit fuer Laufzeitdiagnose genutzt.
- `GameFramework:SetDebugDisplayMessage(...)` zeigt Debug-Overlays.
- `Assert2` wird in Testfunktionen verwendet.
- `DebugDumpGameContentDB()` enumeriert mehrere GameContent-Klassen und reported Felder.
- `OutputChartPlayerState()` zeigt Score-/Marker-/Pitch-/Mic-Diagnose.

Relevante Stellen:

- `private/Lips/lps/Script/LpsUtilities.lua:1135` - `DebugDumpGameContentDB`
- `private/Lips/lps/Script/Menu/EntranceMenu2.lua:600` - Aufruf via `L3`
- `private/Lips/lps/Script/LpsUtilities.lua:1268` - In-game Debugtext

### Recording-Debugmenue

`RecordingMenu.lua` enthaelt Debugfunktionen zum Anzeigen und Speichern von Mic-Recording-Slots. Der lokale Schalter `ALLOW_DEBUG_RECORDING_MENU` steht aber auf `false`, dadurch sind die Funktionen scriptseitig deaktiviert.

Relevante Stellen:

- `private/Lips/lps/Script/Menu/RecordingMenu.lua:1` - `ALLOW_DEBUG_RECORDING_MENU = false`
- `private/Lips/lps/Script/Menu/RecordingMenu.lua:10` - `DebugToggleRecordingMenu`
- `private/Lips/lps/Script/Menu/RecordingMenu.lua:23` - `DebugSaveRecordingFromMenu`

### SequenceTrackConfig und Semantik

`SequenceTrackConfig.lua` definiert die Default-Sequenzen und Tracknamen, die fuer Chart-/Lyric-Autorenschaft wichtig sind:

- `Time`
- `Conductor`
- `Audio`
- `Lyric`
- `Melody`
- `Group`
- `Section`
- `Led`
- `CallAndResponse`
- `Movie`
- `AudioEffect`

Zusatztracks enthalten u.a. `AudioEffectParam` fuer Mic-, BGM- und Reverb-/XAPO-Pfade.

Relevante Stellen:

- `private/Lips/lps/Script/SequenceTrackConfig.lua:7` - Default-Sequenzen
- `private/Lips/lps/Script/SequenceTrackConfig.lua:26` - Default-Tracks

Das ist kein Debughook, aber eine wichtige Semantikquelle fuer eigene Chart-/Lyric-Dateien und Validatoren.

## Starke Indizien

### AppSetting ist runtime-/scriptseitiger Zustand

`AppSetting` wird in Debugmenues, ChartPreview und Renderer-Pfaden genutzt. Im Script-Corpus wurde kein belastbarer Fund gemacht, dass ein `AppSetting.ixb` allein Debugbefehle dauerhaft aktiviert.

Starkes Indiz: `AppSetting.showMarkerLyrics`, `showPitchLine` und `showLEDs` sind Laufzeit-Schalter, die ueber Debugmenue oder Preview gesetzt werden koennen.

### LS2 enthaelt aehnliche Debughooks

`private/Lips/Ls2/Script/LuaBinaryScriptsFile.luaB` und einzelne `.luaB`-Dateien enthalten Strings wie `DebugSettings`, `bEnableInGameDebugCommands`, `DebugMenu`, `BasicDebugMenu`, `lpsDebugMenu`, `Chart`, `Lyric` und `Marker`.

Da es sich um Binary-Lua/String-Scan handelt, ist das nur ein Indiz. Der erste Lips-Scriptbereich `private/Lips/lps/Script/` liefert die belastbaren Quellen.

### Visualizer-Gesten koennen debug-injiziert werden

`VirtualMusicVideo.lua` registriert Debug-Input-Funktionen, die bei aktivem Chart und aktiven Debugkommandos Gesten ausloesen. Die Buttons `RUP`, `RDOWN`, `RLEFT`, `RRIGHT` werden auf farbige Gesture-Events gemappt.

Relevante Stellen:

- `private/Lips/lps/Script/MiniGames/Visualizer/VirtualMusicVideo/VirtualMusicVideo.lua`

Das hilft eher fuer Gesture-/Quick-Action-Verhalten als fuer Kern-IXB-Struktur.

## Hypothesen

- Ein nicht-release Lua-/Buildzustand oder ein Patch an `LPS_LUA_RELEASE`/`DebugSettings` waere noetig, um Debugkommandos in einer Retail-Umgebung zu aktivieren. Das wurde nicht getestet.
- `lpsChartDebugRenderer` ist wahrscheinlich der beste sichtbare Einstieg, um Pitch-Line-/Marker-Rendering fuer eigene Charts zu kontrollieren. Die genaue visuelle Ausgabe muss runtime-seitig geprueft werden.
- `ChartPreview.lua` koennte in einem internen Tool-Kontext gedacht sein und muss nicht vollstaendig im Retail-Flow erreichbar sein.
- Der doppelte `SELECT + RUP`-Pfad kann je nach State-Routing entweder das globale Debugmenue oder den InputDevice-DebugMode treffen. Das ist ohne Runtime-Test offen.

## Risiken und Grenzen

- Keine `.luaB`-Decompilation: Binary-Lua-Ergebnisse sind nur String-Indizien.
- Keine Runtime-Ausfuehrung im Spiel: Controller-Routing und Release-Flags sind aus Scripts abgeleitet.
- Kein Beweis fuer eine hot-reload-freundliche Songdatei-Pipeline im Retail-Flow.
- Debughooks helfen beim Validieren von Chart-/Lyric-/Timing-Verhalten, ersetzen aber keinen strukturellen IXB/X360-Writer-Test.

## Konkreter Plan ohne Trial-and-Error

1. Runtime-Checkliste bauen, aber privat halten:
   - Ist `LPS_LUA_RELEASE` in der genutzten Umgebung aktiv?
   - Reagiert `SELECT + RUP` auf `lpsDebugMenu`?
   - Reagiert `SELECT + RLEFT` auf `OutputChartPlayerState()`?
   - Wirkt `Show pitch line` sichtbar auf `lpsChartDebugRenderer`?

2. Eigene Chart-/Lyric-Samples mit bestehenden Readern validieren:
   - Tracknamen gegen `SequenceTrackConfig.lua` pruefen.
   - Lyric-/Melody-/Group-/Section-Trennung pruefen.
   - Markerarten gegen Renderer-/Grader-Anzeigen abgleichen.

3. Template-preserving Writer mit Debughooks testen:
   - Erst nur Lyric-/Timing-Minimaledits.
   - Dann Melody-/Pitch-Minimaledits.
   - In jedem Lauf `OutputChartPlayerState()` und sichtbare Marker-/Pitch-Line-Ausgabe vergleichen.

4. Ghidra nur fuer konkrete offene Fragen nutzen:
   - Was macht `inputDevice:SetDebugMode()` nativ genau?
   - Wo wird `lpsChartDebugRenderer` gebunden?
   - Welche Native-APIs liegen hinter `GetChartPlayer...`, `LoadMusicFromSequence()` und `Initialize()`?

## Nicht tun

- Keine privaten Scripts oder Gamefiles ins Repo kopieren.
- Keine grossen Rohdaten oder Quelltextauszuege in Docs dumpen.
- Nicht versuchen, Debugflags blind in Gamefiles zu patchen.
- Nicht aus `.luaB`-Strings allein Formatregeln ableiten.
- Kein Writer-from-scratch auf Basis dieser Hooks bauen. Die Hooks sind Validierungs- und Diagnosehilfe, keine Dateiformat-Spezifikation.
