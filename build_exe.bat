@echo off
echo =========================================
echo Building Twitch Pear Song Requests to EXE
echo =========================================
echo.

echo Installing PyInstaller...
pip install pyinstaller
if %errorlevel% neq 0 (
    echo Error installing PyInstaller. Make sure Python/pip is installed and in your PATH.
    pause
    exit /b %errorlevel%
)

echo.
echo Running PyInstaller...
:: --noconfirm: overwrite existing build directories
:: --onedir: create a 1-folder bundle containing the executable
:: --windowed: do not provide a console window for standard i/o
:: --add-data "SOURCE;DEST": bundle the SVG file so it's available in the final exe
pyinstaller --noconfirm --onedir --windowed --add-data "app/ui/checkmark.svg;app/ui" --name "TwitchPearSongRequests" main.py

if %errorlevel% neq 0 (
    echo.
    echo PyInstaller failed with an error.
    pause
    exit /b %errorlevel%
)

echo.
echo =========================================
echo Build Complete!
echo You can find the built program in the "dist\TwitchPearSongRequests" folder.
echo =========================================
pause
