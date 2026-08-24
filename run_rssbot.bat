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

rem --- 日本時間ゲート / Japan-time gate ---
rem  配信内容（見出しの日付、記事の JST 表記、月曜だけ週末分をまとめる判定）はすべて
rem  日本時間が基準。ところがタスクスケジューラは「端末のローカル時刻」でしか予約できず、
rem  時差のある土地では JST の同じ時刻に当たるローカル時刻が夏時間で年に2通りになる。
rem  「自動実行を登録.bat」は両方を予約するので、本当に配信すべき回かをここで判定する。
rem    第1引数: 配信する時刻（日本時間の「時」。既定 9）
rem    第2引数: 配信する曜日（日本時間で 1=月 … 7=日 を並べた文字列。既定 12345）
set "TARGET_HOUR=%~1"
if not defined TARGET_HOUR set "TARGET_HOUR=9"
set "TARGET_DAYS=%~2"
if not defined TARGET_DAYS set "TARGET_DAYS=12345"
set "STAMP=log\.last_run_jst"
set "FORCE_FLAG=log\.force_run"
set "GATE_LOG=log\gate.log"

rem 日本時間の「日付・曜日(1=月…7=日)・時」をまとめて取得する
for /f "usebackq tokens=1-3" %%a in (`powershell -NoProfile -Command "$t=[TimeZoneInfo]::ConvertTimeFromUtc([DateTime]::UtcNow,[TimeZoneInfo]::FindSystemTimeZoneById('Tokyo Standard Time')); $d=@{Monday='1';Tuesday='2';Wednesday='3';Thursday='4';Friday='5';Saturday='6';Sunday='7'}[$t.DayOfWeek.ToString()]; '{0} {1} {2}' -f $t.ToString('yyyy-MM-dd'),$d,$t.Hour.ToString('00')"`) do (
    set "JST_DATE=%%a"
    set "JST_DAY=%%b"
    set "JST_HOUR=%%c"
)
if not defined JST_DATE (
    echo [run_rssbot] WARN: 日本時間を取得できませんでした。ゲートを通過します。>> "%GATE_LOG%"
    goto :gatepass
)

if exist "%FORCE_FLAG%" goto :gatepass
echo %TARGET_DAYS%| findstr /c:"%JST_DAY%" >nul
if errorlevel 1 (
    set "GATE_REASON=日本時間では配信しない曜日"
    goto :gateskip
)
set /a JST_H=1%JST_HOUR% - 100
if %JST_H% LSS %TARGET_HOUR% (
    set "GATE_REASON=日本時間ではまだ配信時刻の前"
    goto :gateskip
)
if not exist "%STAMP%" goto :gatepass
set "LAST="
set /p LAST=<"%STAMP%"
if "%LAST%"=="%JST_DATE%" (
    set "GATE_REASON=この日はすでに配信済み"
    goto :gateskip
)
goto :gatepass

:gateskip
echo %DATE% %TIME% skip: %GATE_REASON%（日本時間 %JST_DATE% %JST_HOUR%時）>> "%GATE_LOG%"
exit /b 0

:gatepass
if exist "%FORCE_FLAG%" del "%FORCE_FLAG%" >nul 2>&1
echo %JST_DATE%> "%STAMP%"

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
