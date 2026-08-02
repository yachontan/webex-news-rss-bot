@echo off
chcp 65001 >nul
rem ============================================================
rem  自動実行を登録.bat  —  Windows タスクスケジューラへの登録ツール
rem
rem  ダブルクリックすると、毎朝の自動配信を登録・解除・確認できます。
rem  Registers/removes the daily delivery task in Windows Task Scheduler.
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

echo ============================================================
echo  rss-bot 自動実行の設定（Windows タスクスケジューラ）
echo ============================================================
echo.
echo  対象: %TARGET%
echo.
echo   1. 登録する（平日 09:01 に毎朝実行）
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
echo 平日 09:01 に実行するタスクを登録します...
schtasks /Create /TN "%TASKNAME%" /TR "\"%TARGET%\"" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 09:01 /F
if errorlevel 1 (
    echo.
    echo   [NG] 登録に失敗しました。上のメッセージを確認してください。
    goto :done
)
echo.
echo   [OK] 登録しました。タスク名: %TASKNAME%
echo        PC がスリープ中は起動しません。必要なら「電源とスリープ」の設定や
echo        タスクのプロパティで「スリープを解除して実行する」を有効にしてください。
goto :done

:remove
echo.
schtasks /Delete /TN "%TASKNAME%" /F
if errorlevel 1 (
    echo   [NG] 解除に失敗しました（登録されていない可能性があります）。
) else (
    echo   [OK] 解除しました。
)
goto :done

:status
echo.
schtasks /Query /TN "%TASKNAME%" /V /FO LIST
if errorlevel 1 echo   このタスクはまだ登録されていません。
goto :done

:runnow
echo.
echo 今すぐ実行します（結果は log\ フォルダに出ます）...
schtasks /Run /TN "%TASKNAME%"
if errorlevel 1 (
    echo   [NG] 実行できませんでした。先に「1. 登録する」を行ってください。
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
