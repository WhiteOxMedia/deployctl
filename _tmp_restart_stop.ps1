$procs = Get-CimInstance Win32_Process
$kill = @{}
foreach ($p in $procs) {
    if ($p.Name -match '^python' -and $p.CommandLine -match 'background_scanner\.py') {
        $kill[[int]$p.ProcessId] = $true
    }
}
foreach ($p in $procs) {
    if ($kill.ContainsKey([int]$p.ParentProcessId)) {
        $kill[[int]$p.ProcessId] = $true
    }
}
$n = 0
foreach ($k in $kill.Keys) {
    Stop-Process -Id $k -Force -ErrorAction SilentlyContinue
    $n++
}
Write-Output "swept $n scanner process(es)"
