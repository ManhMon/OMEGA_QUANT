@echo off
echo Searching for python.exe...
where python
if %ERRORLEVEL% NEQ 0 (
    dir /s /b C:\python.exe 2>nul
    dir /s /b "C:\Users\%USERNAME%\AppData\Local\Programs\Python\python.exe" 2>nul
    dir /s /b "C:\Program Files\Python*\python.exe" 2>nul
    dir /s /b "C:\Program Files (x86)\Python*\python.exe" 2>nul
)
