# Large song library performance

Initial read-only investigation, 2026-10-01. Optional game-side research,
separate from the standalone builder. The user reports severe lag with about
600 installed DLC songs. This configuration has not been reproduced here;
an experimental source-level batching candidate is now prepared, but no
runtime performance fix is proven or installed.

## Evidence

One OG disc database (40 rows), two emulator profile database files and the
OG backup's loose menu Lua were inspected. Loose source is not proof of the
exact packed code executed by every retail build; see
[Lua runtime limits](lua_runtime_capabilities.md). No original files changed.

| Finding | Source anchor | Confidence |
|---|---|---|
| Active-menu install event performs synchronous full selection and list refresh | Menu/PlayMenu2.lua:1999, OnMusicIndexInstalled | High source evidence; live frequency unmeasured |
| XMP enumeration completion invokes the same handler | PlayMenu2.lua:2036; registration :330 | High; not a proven DLC-enumeration completion event |
| Inactive-menu branch already defers using a dirty flag | OnMusicIndexInstalled | High source evidence |
| Selection completion refreshes entrance song cloud too | PlayMenu2.lua:2046, EntranceMenu2.lua:1069 | High source evidence; cost unmeasured |
| Menu uses 7x5 visible buffer; entrance uses 10x4 | PlayMenu2.lua:10, EntranceMenu2.lua:14 | High source evidence; native caches may be larger |
| MAX_SONGS=1000 is used in a commented-out density formula | PlayMenu2.lua:14 and :2567 | Not evidence of an active capacity limit |
| Original disc MusicDB has no indexes; query scans and sorts | Read-only SQLite schema/query plan | High for this file/PC planner; low causal confidence |

Strongest testable hypothesis: repeated complete rebuilds during DLC
enumeration. If one callback fires per song while the menu is active and each
rebuild visits the growing list, work could grow approximately quadratically.
Event batching and native caching must be measured. This may explain
enumeration stalls, not continuous lag after enumeration finishes.

Cover cache churn, preview switching, native index construction, STFS mounts,
storage latency and background network retries remain separate suspects.
Do not disable online features or shrink buffers without evidence. The visible
buffers do not support assuming all 600 covers are rendered simultaneously.

## Read-only diagnostics

`tools/analyze_catalog_scaling.py` opens databases with mode=ro and query_only.
It reports unsupported schemas/unreadable files without repair. Benchmarks
use only synthetic metadata in an in-memory PC database.

The 40-row original MusicDB has no indexes. Its installed-song selection uses
SCAN Music and a temporary sorting B-tree on desktop SQLite 3.50.4. The initial
600-row synthetic run took about 0.43 ms per query, or 0.40 ms with a title/artist
index. Repeats vary. This is not Xbox timing and excludes native objects, covers,
I/O and rendering; the synthetic row schema is smaller. Indexes alone are not
established as a remedy for severe lag.

The older local profile MusicDB returns "database disk image is malformed" to
desktop SQLite; no repair attempted. It is not the user's 600-song Xbox database,
so this does not explain that observation. Its capture state/runtime format
needs separate checking. The second profile database is readable but uses
MusicData/PreviewData/StageData/DLCData and other tables, not the OG Music table.
An OG query/index patch must not be applied blindly to this later schema.
Private reports are under private/outputs/catalog-scaling*; no profile data is
published.

## Next Experiment

Compare 40/200/600/1000 valid entries with identical executable/title update,
storage and profile state. Measure cold/warm menu load, enumeration completion,
frame-time median/p95/p99 and scroll latency during and after enumeration.
Bounded logs must count/timestamp selections, index/list rebuilds, jacket
loads/releases, preview switches and STFS opens. Logging itself can cause lag.

Only if repeated rebuilds are measured: coalesce install events into a dirty
flag, refresh once at enumeration completion, and allow bounded periodic updates
while enumeration continues. Preserve focused stable ID, filters, playlists,
install/update notifications and device removal. Verify the packed retail
execution path before editing loose Lua. Test index tuning, cover caching and
preview debounce separately.

## Optional Patch Distribution

A proven optimization should be an opt-in standalone patcher, not a song-export
side effect. Require supported input hashes/builds, back up the user's own files,
emit patched copies, verify change boundaries and offer rollback. Publish patch
code and findings only, never original XEX, packed scripts, songs, SDK binaries
or profile databases. Signing and hardware acceptance remain separate issues.

## Prepared A/B experiment

`tools/prepare_catalog_refresh_test.py` accepts only the SHA-256 verified OG
backup PlayMenu2.lua. It emits a new private directory containing the original,
an observation-only copy, a batching copy and hashes. It does not install,
repack PackedScript.X360, modify the XEX or touch any game directory.

```powershell
py tools/prepare_catalog_refresh_test.py prepare "<own PlayMenu2.lua>" --out private/outputs/catalog-refresh-test
py tools/prepare_catalog_refresh_test.py rollback private/outputs/catalog-refresh-test "<test copy PlayMenu2.lua>"
```

The appended hooks retain original callbacks. Observe calls the installation
handler normally. Coalesce batches only active, non-challenge-menu installation
notifications, with a fixed deadline of 30 existing EvalState updates from the
first queued event, not 30 seconds. Continuous notifications cannot postpone
that deadline indefinitely. Menu exit flushes a pending notification. Original
inactive/challenge behavior remains. No rows, covers or database indexes are
removed. Last sender is retained; the inspected handler does not read it.
Tests use synthetic callbacks under Lua 5.1 (optional test dependency Lupa).
Runtime menu transitions, selection stability and actual callback scheduling
remain unverified.

Correction to the initial hypothesis: the registered OnSongEnumerationFinished
comes from GetXmpManager(), not a proven DLC-completion notification. This
experiment therefore does not use it as a batching-completion gate.

**Activation blocker:** retail startup reads PackedScript.X360 rather than
loose Lua. Merely copying these files will not constitute a working patch.
Before claiming an optimized comparison, inject/load the hook via a verified
active Lua boundary or a separately validated packed-script modification.
The log must contain `OPENLIPS_CATALOG ... reason=hook_active`. No such native
hook or repacker is implemented by this preparation tool. Do not change the
release flag blindly. A missing activation message invalidates the A/B result.

For the first run, leave every game file unchanged. The independent process
sampler works without any Lua patch:

```powershell
./tools/measure_xenia_catalog.ps1 -XeniaPid <pid> -Out private/outputs/catalog-original.jsonl -Variant original -Seconds 180
```

CPU percentage measures one-core equivalents (can exceed 100%), not FPS or
guest GPU load. It records host CPU, working/private memory, handles and threads
once per second, stops on process exit/PID reuse, and refuses output overwrite.
Keep a separate copy of the matching Xenia log and use analyze_xenia_log.py for
content calls, XMP signals and crashes. Logs may omit I/O events unless tracing
is enabled: absence of log messages does not establish absence of I/O.

Baseline protocol: same 600 DLC, profile, executable, storage, emulator config,
and navigation route; record boot-to-menu and enumeration settling, then 60
seconds idle and 60 seconds scrolling. Record cold and warm runs separately.
Observe frame pacing with emulator/profiler data separately; this sampler cannot
produce p95/p99 frame times. Compare host CPU and memory, content/error activity,
and menu response before choosing additional native probes. Observation hooks
are a second baseline only after active loading is proven. Then test batching
with identical conditions and check all songs remain reachable, disc swaps,
challenge mode, menu leave/re-entry and selection persistence. If repeated
refreshes are not measured, do not present batching as the cause or fix.

Preparation validation (2026-10-01): 266 tests passed, three skipped, eleven
subtests passed, with the isolated optional Lupa test runtime. Nine new tests
cover refusal, copy preservation, rollback and Lua 5.1 behavior. A 600-event
synthetic burst produces 600 original handler calls in observe versus one in
coalesce after 30 menu ticks; continuous input flushes every 30 ticks. This is
callback batching evidence, not a measured game-speed improvement. Original
and both privately generated complete source copies compile with Lua 5.1;
the process sampler passes PowerShell syntax validation but has not yet been
validated against the planned 600-DLC game run.
