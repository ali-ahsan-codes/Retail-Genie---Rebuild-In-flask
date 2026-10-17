' Retail Genie Silent Launcher
' Executes the PowerShell deployment script without showing a console window.

Set objFSO = CreateObject("Scripting.FileSystemObject")
strPath = objFSO.GetParentFolderName(WScript.ScriptFullName)
Set objShell = CreateObject("WScript.Shell")

' Build the command to run PowerShell hidden with Bypass policy
strCommand = "powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & strPath & "\install-and-start.ps1"""

' Run the command (0 = hide window, False = don't wait for completion)
objShell.Run strCommand, 0, False
