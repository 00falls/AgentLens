param(
    [ValidateSet('start', 'stop', 'status')][string]$Action = 'start',
    [ValidatePattern('^[D-Z]$')][string]$Drive = 'L'
)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path $PSScriptRoot -Parent
# PostgreSQL initdb fails with non-ASCII installation paths on this Windows host.
# A subst drive keeps binaries and data in this project while presenting an ASCII path.
if (Test-Path "$Drive`:\") {
    # subst's console output uses a legacy encoding; query the Unicode mapping directly.
    if (-not ('AgentLens.DriveMapping' -as [type])) {
        Add-Type -Namespace AgentLens -Name DriveMapping -MemberDefinition @'
        [System.Runtime.InteropServices.DllImport("kernel32.dll", CharSet = System.Runtime.InteropServices.CharSet.Unicode)]
        public static extern uint QueryDosDevice(string name, System.Text.StringBuilder target, int size);
'@
    }
    $taskTarget = [Text.StringBuilder]::new(32768)
    $taskMappingResult = [AgentLens.DriveMapping]::QueryDosDevice("$Drive`:", $taskTarget, $taskTarget.Capacity)
    if ($taskMappingResult -eq 0 -or $taskTarget.ToString() -ine "\??\$taskRoot") {
        throw "$Drive`: is already in use; choose another drive with -Drive."
    }
} else {
    & subst.exe "$Drive`:" $taskRoot
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the project drive mapping' }
}
$taskRoot = "$Drive`:\"
$taskPgBin = Join-Path $taskRoot '.tools\pgsql\bin'
$taskPgData = Join-Path $taskRoot 'data\postgres'
$taskPgLog = Join-Path $taskRoot 'data\postgres.log'

if (-not (Test-Path -LiteralPath (Join-Path $taskPgBin 'pg_ctl.exe'))) {
    throw 'Extract the EDB PostgreSQL 17.11 bin/lib/share directories into .tools/pgsql first.'
}
if ($Action -eq 'start') {
    New-Item -ItemType Directory -Force -Path (Join-Path $taskRoot 'data') | Out-Null
    if (-not (Test-Path -LiteralPath (Join-Path $taskPgData 'PG_VERSION'))) {
        $taskPwFile = Join-Path $taskRoot '.tools\postgres-dev-password.txt'
        [IO.File]::WriteAllText($taskPwFile, 'agentlens-local', [Text.UTF8Encoding]::new($false))
        try {
            & (Join-Path $taskPgBin 'initdb.exe') -D $taskPgData --username=agentlens `
                --encoding=UTF8 --locale=C --auth=scram-sha-256 --pwfile=$taskPwFile
            if ($LASTEXITCODE -ne 0) { throw 'initdb failed' }
        } finally {
            Remove-Item -LiteralPath $taskPwFile
        }
    }
    & (Join-Path $taskPgBin 'pg_ctl.exe') -D $taskPgData status
    if ($LASTEXITCODE -ne 0) {
        & (Join-Path $taskPgBin 'pg_ctl.exe') -D $taskPgData -l $taskPgLog `
            -o '-h 127.0.0.1 -p 5432' -w start
        if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL start failed; inspect data/postgres.log' }
    }
} elseif ($Action -eq 'stop') {
    & (Join-Path $taskPgBin 'pg_ctl.exe') -D $taskPgData -m fast -w stop
} else {
    & (Join-Path $taskPgBin 'pg_ctl.exe') -D $taskPgData status
}
