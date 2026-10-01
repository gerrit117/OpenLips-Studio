param(
    [Parameter(Mandatory=$true)][int]$XeniaPid,
    [Parameter(Mandatory=$true)][string]$Out,
    [ValidateRange(1,3600)][int]$Seconds = 180,
    [ValidateSet('original','observe','coalesce')][string]$Variant = 'original'
)

$ErrorActionPreference = 'Stop'
$process = Get-Process -Id $XeniaPid
if ($process.ProcessName -notlike 'xenia*') { throw 'PID is not a Xenia process' }
$started = $process.StartTime
$stream = [System.IO.File]::Open($Out, 'CreateNew', 'Write', 'Read')
$writer = [System.IO.StreamWriter]::new($stream)
$clock = [System.Diagnostics.Stopwatch]::StartNew()
$lastCpu = $process.TotalProcessorTime.TotalSeconds
$lastTime = 0.0
try {
    for ($i = 0; $i -lt $Seconds; $i++) {
        Start-Sleep -Seconds 1
        $process = Get-Process -Id $XeniaPid -ErrorAction SilentlyContinue
        if (-not $process -or $process.StartTime -ne $started) { break }
        $now = $clock.Elapsed.TotalSeconds
        $cpu = $process.TotalProcessorTime.TotalSeconds
        $row = [ordered]@{
            utc = [DateTime]::UtcNow.ToString('o')
            elapsed_seconds = $now
            variant = $Variant
            pid = $XeniaPid
            cpu_core_percent = 100 * ($cpu - $lastCpu) / ($now - $lastTime)
            working_set_bytes = $process.WorkingSet64
            private_bytes = $process.PrivateMemorySize64
            handles = $process.HandleCount
            threads = $process.Threads.Count
        }
        $writer.WriteLine(($row | ConvertTo-Json -Compress))
        $writer.Flush()
        $lastCpu = $cpu
        $lastTime = $now
    }
} finally {
    $writer.Dispose()
    $stream.Dispose()
}
