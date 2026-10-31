@echo off
setlocal enabledelayedexpansion

:: Find mysql.exe
set MYSQL_PATH=
for %%i in (mysql.exe) do set MYSQL_PATH=%%~$PATH:i
if not defined MYSQL_PATH (
    if exist "C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe" set MYSQL_PATH=C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe
    if exist "C:\Program Files\MySQL\MySQL Server 5.7\bin\mysql.exe" set MYSQL_PATH=C:\Program Files\MySQL\MySQL Server 5.7\bin\mysql.exe
)
if not defined MYSQL_PATH (
    echo Cannot find mysql.exe. Ensure MySQL is installed and in PATH.
    pause
    exit /b 1
)

:: Read DATABASE_URL from .env
if not exist .env (
    echo .env file not found!
    pause
    exit /b 1
)

for /f "usebackq tokens=*" %%i in (`type .env ^| findstr /i "DATABASE_URL"`) do set DB_LINE=%%i
set DB_LINE=%DB_LINE:DATABASE_URL==%
set DB_LINE=%DB_LINE: =%

:: Remove the scheme
set DB_LINE=%DB_LINE:mysql+pymysql://=%

:: Now DB_LINE is user:pass@host:port/db
:: Split at @
for /f "tokens=1,2 delims=@" %%a in ("%DB_LINE%") do (
    set USER_PASS=%%a
    set HOST_PORT_DB=%%b
)

:: Split USER_PASS at :
for /f "tokens=1,2 delims=:" %%a in ("%USER_PASS%") do (
    set MYSQL_USER=%%a
    set MYSQL_PASS=%%b
)

:: URL-decode password: replace %40 with @
set MYSQL_PASS=%MYSQL_PASS:%%40=@%

:: Split HOST_PORT_DB at : to separate host and port/db
for /f "tokens=1,2 delims=:" %%a in ("%HOST_PORT_DB%") do (
    set MYSQL_HOST=%%a
    set PORT_DB=%%b
)

:: Split PORT_DB at / to separate port and db
for /f "tokens=1,2 delims=/" %%a in ("%PORT_DB%") do (
    set MYSQL_PORT=%%a
    set MYSQL_DB=%%b
)

:: If any variable is empty, set defaults
if "%MYSQL_HOST%"=="" set MYSQL_HOST=localhost
if "%MYSQL_PORT%"=="" set MYSQL_PORT=3306
if "%MYSQL_DB%"=="" set MYSQL_DB=gyropulse

echo Using:
echo   Host: %MYSQL_HOST%
echo   Port: %MYSQL_PORT%
echo   User: %MYSQL_USER%
echo   Database: %MYSQL_DB%

:: Test connection
echo Testing connection...
"%MYSQL_PATH%" -h %MYSQL_HOST% -P %MYSQL_PORT% -u %MYSQL_USER% -p%MYSQL_PASS% -e "SELECT 1" >nul 2>&1
if %errorlevel% neq 0 (
    echo Connection failed. Please check your credentials.
    pause
    exit /b 1
)

:: Drop and recreate database
echo Dropping and recreating database %MYSQL_DB%...
"%MYSQL_PATH%" -h %MYSQL_HOST% -P %MYSQL_PORT% -u %MYSQL_USER% -p%MYSQL_PASS% -e "DROP DATABASE IF EXISTS %MYSQL_DB%; CREATE DATABASE %MYSQL_DB% CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
if %errorlevel% neq 0 (
    echo Failed to drop/recreate database.
    pause
    exit /b 1
)

:: Run the schema
echo Creating tables...
"%MYSQL_PATH%" -h %MYSQL_HOST% -P %MYSQL_PORT% -u %MYSQL_USER% -p%MYSQL_PASS% %MYSQL_DB% < "%~dp0schema.sql"

if %errorlevel% equ 0 (
    echo Database and tables created successfully.
    echo.
    echo The default admin user (admin/admin123) will be created on next server start.
    echo Role API keys will be generated automatically.
) else (
    echo Error creating tables.
)
pause