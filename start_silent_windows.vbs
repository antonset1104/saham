' VBScript untuk menjalankan start_saham_windows.bat di latar belakang secara tersembunyi (tanpa jendela hitam CMD)
Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
WshShell.Run "cmd /c start_saham_windows.bat", 0, False
Set WshShell = Nothing
