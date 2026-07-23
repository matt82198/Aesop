' run-hidden.vbs — VBScript launcher for Windows Scheduled Tasks
'
' Purpose: Execute a command with a hidden console window (window style 0) and
' propagate its exit code.
'
' Usage:
'   wscript.exe //B //Nologo run-hidden.vbs <bash-exe> -lc "<command>"
'
' The script rebuilds a quoted command line from WScript.Arguments and runs it
' via WScript.Shell.Run with window style 0 (hidden). CRITICAL: The task
' instance lives as long as the child process (shell.Run waits), so that
' - MultipleInstances IgnoreNew can prevent concurrent runs
' - ExecutionTimeLimit can kill hung processes
' - LastTaskResult reflects the actual child exit code (not always 0)
'
' By contract, arguments never contain double quotes.

Dim shell, cmd, i, arg
Dim windowStyle, rc

Set shell = CreateObject("WScript.Shell")

' Build command line from arguments
cmd = ""
For i = 0 To WScript.Arguments.Count - 1
    arg = WScript.Arguments(i)
    If i > 0 Then cmd = cmd & " "
    ' Arguments never contain quotes by contract; wrap in quotes for safety
    cmd = cmd & """" & arg & """"
Next

' Window style 0 = hidden; wait for process exit (True = wait)
windowStyle = 0

' Execute the command and wait for it to complete, capturing exit code
rc = shell.Run(cmd, windowStyle, True)

' Exit with the child process's exit code
WScript.Quit rc
