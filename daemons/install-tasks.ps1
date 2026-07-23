param(
    [string]$BashExe = 'C:\Program Files\Git\bin\bash.exe',
    [string]$WatchdogCommand = '',
    [string]$MonitorCommand = '',
    [int]$WatchdogIntervalMinutes = 5,
    [int]$MonitorIntervalMinutes = 20,
    [string]$TaskPrefix = 'Aesop',
    [switch]$Uninstall,
    [switch]$DryRun
)

# Enable strict error handling
$ErrorActionPreference = 'Stop'

function ConvertTo-PosixPath {
    param([string]$WindowsPath)
    # Convert C:\foo\bar to /c/foo/bar
    # Rejects UNC paths (\\server\share) — error out instead of mangling
    if ($WindowsPath -match '^\\\\') {
        Write-Error "UNC paths are unsupported (got: $WindowsPath). Pass -WatchdogCommand explicitly with a valid path."
        exit 1
    }
    $posixPath = $WindowsPath -replace '\\', '/'
    $posixPath = $posixPath -replace '^([A-Za-z]):', '/$1'
    return $posixPath
}

function Get-WorktreeRoot {
    # Derive worktree root from $PSScriptRoot (daemons/)
    # $PSScriptRoot is C:\...\aesop\daemons
    # Parent is C:\...\aesop
    $daemonsDir = $PSScriptRoot
    $aesopRoot = Split-Path -Parent $daemonsDir
    return $aesopRoot
}

function Register-DaemonTask {
    param(
        [string]$TaskName,
        [string]$Command,
        [int]$IntervalMinutes,
        [string]$RunHiddenVbs,
        [string]$BashExe
    )

    # Build the action: wscript.exe //B //Nologo "path\to\run-hidden.vbs" "<bash>" -lc "<command>"
    $action = New-ScheduledTaskAction `
        -Execute 'wscript.exe' `
        -Argument "//B //Nologo ""$RunHiddenVbs"" ""$BashExe"" -lc ""$Command"""

    # Build the trigger: Once, starting in 1 minute, repeating every N minutes for 10 years
    $startTime = (Get-Date).AddMinutes(1)
    $trigger = New-ScheduledTaskTrigger `
        -Once `
        -At $startTime `
        -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
        -RepetitionDuration (New-TimeSpan -Days 3650)

    # Build the settings: Hidden, IgnoreNew for multiple instances, 1-hour timeout
    $settings = New-ScheduledTaskSettingsSet `
        -Hidden `
        -MultipleInstances IgnoreNew `
        -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
        -StartWhenAvailable

    if ($DryRun) {
        # Print DryRun output
        Write-Host "DRYRUN: $TaskName -> wscript.exe //B //Nologo ""$RunHiddenVbs"" ""$BashExe"" -lc ""$Command"" (interval=$IntervalMinutes`m, Hidden=True)"
    }
    else {
        # Register the task (force overwrite if exists)
        try {
            Register-ScheduledTask `
                -TaskName $TaskName `
                -Action $action `
                -Trigger $trigger `
                -Settings $settings `
                -Force `
                -ErrorAction Stop | Out-Null
            Write-Host "Registered task: $TaskName (interval=$IntervalMinutes minutes)"
        }
        catch {
            Write-Error "Failed to register task $TaskName : $_"
            exit 1
        }
    }
}

function Unregister-DaemonTask {
    param([string]$TaskName)

    try {
        $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if ($task) {
            Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
            Write-Host "Unregistered task: $TaskName"
            return $true
        }
        else {
            Write-Host "Task not found: $TaskName (already unregistered or never existed)"
            return $true
        }
    }
    catch {
        Write-Error "Failed to unregister $TaskName : $_"
        return $false
    }
}

function Main {
    # Resolve paths
    $aesopRoot = Get-WorktreeRoot
    $runHiddenVbs = Join-Path $PSScriptRoot 'run-hidden.vbs'

    # VALIDATION: Check for double quotes in commands (contract violation)
    # This check runs early and always, before any operations
    if ($WatchdogCommand -like '*"*') {
        Write-Error "WatchdogCommand contains double quotes, which are not allowed (vbs launcher contract violation)."
        exit 1
    }
    if ($MonitorCommand -like '*"*') {
        Write-Error "MonitorCommand contains double quotes, which are not allowed (vbs launcher contract violation)."
        exit 1
    }

    # PATH VALIDATION: Only enforce file existence checks if not in DryRun mode
    # In DryRun, downgrade to warnings so preview works on machines without Git Bash
    if (-not $DryRun) {
        if (-not (Test-Path $runHiddenVbs)) {
            Write-Error "run-hidden.vbs not found at: $runHiddenVbs"
            exit 1
        }
        if (-not (Test-Path $BashExe)) {
            Write-Error "bash.exe not found at: $BashExe"
            exit 1
        }
    }
    else {
        if (-not (Test-Path $runHiddenVbs)) {
            Write-Warning "run-hidden.vbs not found at: $runHiddenVbs (DryRun mode)"
        }
        if (-not (Test-Path $BashExe)) {
            Write-Warning "bash.exe not found at: $BashExe (DryRun mode)"
        }
    }

    # Handle Uninstall mode
    if ($Uninstall) {
        $watchdog_ok = Unregister-DaemonTask -TaskName "${TaskPrefix}WatchdogDaemon"
        $monitor_ok = Unregister-DaemonTask -TaskName "${TaskPrefix}RefinementMonitor"
        if (-not $watchdog_ok -or -not $monitor_ok) {
            exit 1
        }
        exit 0
    }

    # Derive default commands if not provided
    if (-not $WatchdogCommand) {
        $posixRoot = ConvertTo-PosixPath $aesopRoot

        # P2: Detect apostrophe in derived path (breaks bash syntax if not escaped)
        if ($posixRoot -like "*'*") {
            Write-Error "Repository path contains apostrophe, which would break the derived command: $posixRoot`nPass -WatchdogCommand explicitly."
            exit 1
        }

        $WatchdogCommand = "bash '$posixRoot/daemons/run-watchdog.sh' --once >> '$posixRoot/state/cron-watchdog.log' 2>&1"
    }

    # Register watchdog task
    $watchdogTaskName = "${TaskPrefix}WatchdogDaemon"
    Register-DaemonTask `
        -TaskName $watchdogTaskName `
        -Command $WatchdogCommand `
        -IntervalMinutes $WatchdogIntervalMinutes `
        -RunHiddenVbs $runHiddenVbs `
        -BashExe $BashExe

    # Register monitor task if command provided
    if ($MonitorCommand) {
        $monitorTaskName = "${TaskPrefix}RefinementMonitor"
        Register-DaemonTask `
            -TaskName $monitorTaskName `
            -Command $MonitorCommand `
            -IntervalMinutes $MonitorIntervalMinutes `
            -RunHiddenVbs $runHiddenVbs `
            -BashExe $BashExe
    }

    exit 0
}

Main
