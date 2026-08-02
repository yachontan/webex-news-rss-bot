@echo off
chcp 65001 >nul
rem ============================================================
rem  はじめに設定する.bat  —  Windows 用セットアップウィザード
rem
rem  エクスプローラーでダブルクリックすると、初期設定ウィザードが開きます。
rem  Double-click in Explorer to launch the setup wizard (Windows).
rem
rem  置き場所について / Location:
rem    定時実行（タスクスケジューラ）を使うなら、OneDrive 同期フォルダーの外
rem    （例: C:\tools\rss-bot）へ置いてください。ウィザードの最初のステップでも
rem    自動判定します。
rem ============================================================
setlocal
cd /d "%~dp0"

rem --- Python を探す / Locate Python 3 ---
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
    where python >nul 2>&1 && set "PY=python"
)

if not defined PY (
    echo.
    echo   [NG] Python 3 が見つかりません。
    echo.
    echo   https://www.python.org/downloads/windows/ からインストールし、
    echo   インストーラーの "Add python.exe to PATH" にチェックを入れてください。
    echo   その後、もう一度このファイルをダブルクリックしてください。
    echo.
    pause
    exit /b 1
)

%PY% setup.py
set "RC=%ERRORLEVEL%"

echo.
echo ------------------------------------------------------------
echo  ウィザードを終了しました。このウィンドウは閉じて構いません。
echo ------------------------------------------------------------
pause
exit /b %RC%
