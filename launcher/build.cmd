@echo off
rem Собирает morphbench.exe - окно запуска сервера, точку входа для Mod Organizer 2 -
rem штатным компилятором .NET Framework, который есть на любой Windows. Ничего ставить
rem не нужно. Результат кладётся рядом с mb.py; в git он не попадает (продукт сборки).
rem Значок берётся из morphbench.ico. Его рисует make-icon.py - он тоже продукт, и в git
rem лежит сценарий, а не двоичный файл: в истории от .ico видно только «файл изменился».
setlocal
rem Значок - продукт make-icon.py, в git его нет. Рисуем, если ещё не нарисован.
if not exist "%~dp0morphbench.ico" (
    python "%~dp0make-icon.py" || (echo не удалось нарисовать значок & exit /b 3)
)
set "CSC=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if not exist "%CSC%" set "CSC=%WINDIR%\Microsoft.NET\Framework\v4.0.30319\csc.exe"
if not exist "%CSC%" (
    echo не найден csc.exe из .NET Framework 4: %CSC%
    exit /b 2
)
"%CSC%" /nologo /optimize+ /codepage:65001 /target:winexe /platform:anycpu ^
    /r:System.Windows.Forms.dll /r:System.Drawing.dll /r:System.Web.Extensions.dll ^
    /win32manifest:"%~dp0morphbench.manifest" ^
    /win32icon:"%~dp0morphbench.ico" ^
    /out:"%~dp0..\morphbench.exe" "%~dp0morphbench.cs"
if errorlevel 1 exit /b %errorlevel%
echo собран: %~dp0..\morphbench.exe
endlocal
