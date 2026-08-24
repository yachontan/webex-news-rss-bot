@echo off
chcp 65001 >nul
rem ============================================================
rem  自動実行を登録.bat  —  Windows タスクスケジューラへの登録ツール
rem
rem  ダブルクリックすると、毎朝の自動配信を登録・解除・確認できます。
rem  Registers/removes the daily delivery task in Windows Task Scheduler.
rem
rem  時刻は「日本時間」で考えます / Times are Japan time (JST):
rem    配信内容（見出しの日付、記事の JST 表記、月曜の週末まとめ）はすべて日本時間が
rem    基準です。タスクスケジューラはローカル時刻でしか予約できないため、日本時間の
rem    09:01 に当たるローカル時刻を計算して登録します。夏時間のある地域では候補が
rem    2通りになるので両方を登録し、run_rssbot.bat 側が正しい回だけを実行します。
rem    日本国内の PC なら、そのまま平日 09:01 のタスクが1つできます。
rem
rem  管理者権限は不要です（ログインユーザーのタスクとして登録します）。
rem  No administrator rights required.
rem
rem  置き場所の注意 / Location:
rem    OneDrive 同期フォルダーの配下だと、タスクからの実行が失敗することが
rem    あります。C:\tools\rss-bot のような同期対象外へ置いてください。
rem ============================================================
setlocal
cd /d "%~dp0"

set "TASKNAME=rss-bot daily"
set "TARGET=%~dp0run_rssbot.bat"
rem run_rssbot.bat へ渡す日本時間のゲート条件（配信する時 / 曜日 1=月…7=日）
set "GATE_ARGS=9 12345"

echo ============================================================
echo  rss-bot 自動実行の設定（Windows タスクスケジューラ）
echo ============================================================
echo.
echo  対象: %TARGET%
echo.
echo   1. 登録する（日本時間の平日 09:01 に毎朝実行）
echo   2. 解除する
echo   3. 今の状態を確認する
echo   4. 今すぐ1回実行する（動作確認）
echo   5. 何もしないで閉じる
echo.

set "CHOICE="
set /p "CHOICE=番号を入力して Enter [1]: "
if not defined CHOICE set "CHOICE=1"

if "%CHOICE%"=="1" goto :register
if "%CHOICE%"=="2" goto :remove
if "%CHOICE%"=="3" goto :status
if "%CHOICE%"=="4" goto :runnow
goto :done

:register
if not exist "%TARGET%" (
    echo.
    echo   [NG] run_rssbot.bat が見つかりません。リポジトリが壊れていないか確認してください。
    goto :done
)
echo.
echo 日本時間の平日 09:01 に当たるローカル時刻を計算しています...
call :purge
set /a IDX=0
for /f "usebackq tokens=1,2" %%a in (`powershell -NoProfile -Command "$jst=[TimeZoneInfo]::FindSystemTimeZoneById('Tokyo Standard Time'); $base=[DateTime]::SpecifyKind([DateTime]::Today.AddHours(9).AddMinutes(1),'Unspecified'); $map=@{}; 0..365 | ForEach-Object { $d=$base.AddDays($_); if([int]$d.DayOfWeek -ge 1 -and [int]$d.DayOfWeek -le 5){ $l=[TimeZoneInfo]::ConvertTime($d,$jst,[TimeZoneInfo]::Local); $t=$l.ToString('HH:mm'); if(-not $map[$t]){$map[$t]=@{}}; $map[$t][$l.DayOfWeek.ToString().Substring(0,3).ToUpper()]=1 } }; $map.Keys | Sort-Object | ForEach-Object { '{0} {1}' -f $_,(($map[$_].Keys | Sort-Object) -join ',') }"`) do call :addtask "%%a" "%%b"
if %IDX%==0 (
    echo   [NG] ローカル時刻を計算できませんでした。PowerShell が使えるか確認してください。
    goto :done
)
echo.
echo   [OK] %IDX% 件のタスクを登録しました（日本時間の平日 09:01 に配信します）。
echo        PC がスリープ中は起動しません。必要なら「電源とスリープ」の設定や
echo        タスクのプロパティで「スリープを解除して実行する」を有効にしてください。
goto :done

:addtask
rem %1 = ローカル時刻 HH:MM / %2 = ローカル曜日 MON,TUE,...
set /a IDX+=1
set "TN=%TASKNAME%"
if not %IDX%==1 set "TN=%TASKNAME% %IDX%"
schtasks /Create /TN "%TN%" /TR "\"%TARGET%\" %GATE_ARGS%" /SC WEEKLY /D %~2 /ST %~1 /F >nul
if errorlevel 1 (
    echo   [NG] %TN% の登録に失敗しました（%~2 %~1）。
) else (
    echo   [OK] %TN%: %~2 の %~1（ローカル時刻）
)
goto :eof

:purge
rem 前回の登録が残っていると時刻が重複するため、いったん全部消す
for %%i in ("%TASKNAME%" "%TASKNAME% 2" "%TASKNAME% 3" "%TASKNAME% 4") do (
    schtasks /Delete /TN %%i /F >nul 2>&1
)
goto :eof

:remove
echo.
set /a GONE=0
for %%i in ("%TASKNAME%" "%TASKNAME% 2" "%TASKNAME% 3" "%TASKNAME% 4") do call :delone %%i
if %GONE%==0 (
    echo   [NG] 解除できませんでした（登録されていない可能性があります）。
) else (
    echo   [OK] %GONE% 件を解除しました。
)
goto :done

:delone
schtasks /Delete /TN %1 /F >nul 2>&1
if not errorlevel 1 set /a GONE+=1
goto :eof

:status
echo.
set /a SEEN=0
for %%i in ("%TASKNAME%" "%TASKNAME% 2" "%TASKNAME% 3" "%TASKNAME% 4") do call :showone %%i
if %SEEN%==0 echo   このタスクはまだ登録されていません。
goto :done

:showone
schtasks /Query /TN %1 /FO LIST >nul 2>&1
if errorlevel 1 goto :eof
set /a SEEN+=1
schtasks /Query /TN %1 /FO LIST
goto :eof

:runnow
echo.
echo 今すぐ実行します（結果は log\ フォルダに出ます）...
if not exist "log" mkdir "log"
rem 日本時間ゲートを1回だけ素通りさせる通行証を置く
echo force>"log\.force_run"
schtasks /Run /TN "%TASKNAME%"
if errorlevel 1 (
    echo   [NG] 実行できませんでした。先に「1. 登録する」を行ってください。
    del "log\.force_run" >nul 2>&1
) else (
    echo   [OK] 実行を開始しました。log フォルダの launchd_run-*.log を確認してください。
)
goto :done

:done
echo.
echo ------------------------------------------------------------
echo  終了しました。このウィンドウは閉じて構いません。
echo ------------------------------------------------------------
pause
