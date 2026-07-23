' run-hidden.vbs — VBScript launcher for Windows Scheduled Tasks
'
' Purpose: Execute a command with a hidden console window (window style 0).
'
' Usage:
'   wscript.exe //B //Nologo run-hidden.vbs <bash-exe> -lc "<command>"
'
' The script rebuilds a quoted command line from WScript.Arguments and runs it
' via WScript.Shell.Run with window style 0 (hidden).
'
' By contract, arguments never contain double quotes.

Dim shell, cmd, i, arg
Dim windowStyle, waitForExit

Set shell = CreateObject("WScript.Shell")

' Build command line from arguments
cmd = ""
For i = 0 To WScript.Arguments.Count - 1
    arg = WScript.Arguments(i)
    If i > 0 Then cmd = cmd & " "
    ' Arguments never contain quotes by contract; wrap in quotes for safety
    cmd = cmd & """" & arg & """"
Next

' Window style 0 = hidden; don't wait for process exit
windowStyle = 0
waitForExit = False

' Execute the command
shell.Run cmd, windowStyle, waitForExit
