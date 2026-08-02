@echo off
chcp 65001 >nul
rem ============================================================
rem  run_rssbot.bat  —  タスクスケジューラから呼ぶラッパー
rem
rem  macOS の run_rssbot.sh に相当する Windows 版。
rem  Windows counterpart of run_rssbot.sh (called by Task Scheduler).
rem
rem  役割 / Purpose:
rem    - 実行ごとにタイムスタンプ付きのログへ出力する
rem    - スリープ復帰直後などネットワークが未準備のまま起動した場合に備え、
rem      投稿先へ疎通できるまで最大5分待ってから本体を起動する
rem
rem  パスは自分の位置から解決するので編集は不要です。
rem  登録は「自動実行を登録.bat」から行えます。
rem ============================================================
setlocal
cd /d "%~dp0"

if not exist "log" mkdir "log"

rem --- タイムスタンプ（ロケールに依存しない形で取得）/ Locale-independent timestamp ---
set "TS="
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"`) do set "TS=%%i"
if not defined TS set "TS=unknown"

set "LOG=log\launchd_run-%TS%.log"
set "ERR=log\launchd_err-%TS%.log"

rem --- 仮想環境の python を探す / Locate the venv interpreter ---
set "PY="
if exist "Scripts\python.exe" set "PY=Scripts\python.exe"
if not defined PY if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"

if not defined PY (
    echo [run_rssbot] 仮想環境が見つかりません。先に「はじめに設定する.bat」で初期設定してください。>> "%ERR%"
    exit /b 1
)

rem --- ネットワーク準備待ち（最大5分）/ Wait for network readiness (up to 5 min) ---
set /a WAITED=0
set /a MAX_WAIT=300
set /a INTERVAL=10

:netcheck
powershell -NoProfile -Command "try{$null = Invoke-WebRequest -Uri 'https://webexapis.com' -Method Head -TimeoutSec 8 -UseBasicParsing; exit 0}catch{exit 1}" >nul 2>&1
if not errorlevel 1 (
    echo [run_rssbot] network ready after %WAITED%s>> "%LOG%"
    goto :netready
)
if %WAITED% GEQ %MAX_WAIT% (
    echo [run_rssbot] WARN: network not confirmed after %MAX_WAIT%s; proceeding anyway>> "%LOG%"
    goto :netready
)
rem timeout は非対話セッションで失敗することがあるため ping で待つ
ping -n %INTERVAL% 127.0.0.1 >nul 2>&1
set /a WAITED=%WAITED%+%INTERVAL%
goto :netcheck

:netready
rem --weekend-catchup: 月曜の実行時だけ取得期間を72時間（金土日）へ自動拡張する。
rem 毎日実行する運用ならこのフラグは外してよい。
"%PY%" webex-news-rss-bot.py --weekend-catchup >> "%LOG%" 2>> "%ERR%"
exit /b %ERRORLEVEL%
