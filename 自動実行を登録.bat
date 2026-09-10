@echo off
chcp 65001 >nul
rem ============================================================
rem  自動実行を登録.bat  —  Windows タスクスケジューラへの登録ツール
rem
rem  ダブルクリックすると、毎朝の自動配信を登録・解除・確認できます。
rem  Registers/removes the daily delivery task in Windows Task Scheduler.
rem
rem  時刻は「日本時間」です / Times are Japan time (JST):
rem    配信内容（見出しの日付、記事の JST 表記、月曜の週末まとめ）はすべて日本時間が
rem    基準です。一方スケジューラはローカル時刻でしか予約できないため、ここでは
rem    「30分ごとに様子を見にいく」タスクを登録し、実際に配信するかどうかは
rem    run_rssbot.bat が日本時間とネットワークの疎通を見て決めます。繋がっていなければ
rem    見送って30分後にやり直します。こうすると PC のタイムゾーンや
rem    夏時間が何であっても、日本時間の平日 09:01 に配信されます。
rem    配信しない回は何もせずすぐ終了し、理由が log\gate.log に残ります。
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
echo   1. 登録する（日本時間の平日 09:01 に毎朝配信）
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
call :purge
echo.
echo 30分ごとに様子を見にいくタスクを登録します...
schtasks /Create /TN "%TASKNAME%" /TR "\"%TARGET%\" %GATE_ARGS%" /SC MINUTE /MO 30 /ST 00:01 /F
if errorlevel 1 (
    echo.
    echo   [NG] 登録に失敗しました。上のメッセージを確認してください。
    goto :done
)
echo.
echo   [OK] 登録しました。タスク名: %TASKNAME%
echo        実際に配信するのは、日本時間で平日 09:01 を過ぎた最初の1回だけです。
echo        それ以外の回は何もせずすぐ終了し、理由が log\gate.log に残ります。
echo        PC がスリープ中は起動しません。必要なら「電源とスリープ」の設定や
echo        タスクのプロパティで「スリープを解除して実行する」を有効にしてください。
goto :done

:remove
echo.
call :purge
echo   [OK] 解除しました（登録が無かった場合も同じ表示になります）。
goto :done

:status
echo.
set /a SEEN=0
for %%i in ("%TASKNAME%" "%TASKNAME% 2" "%TASKNAME% 3" "%TASKNAME% 4") do call :showone %%i
if %SEEN%==0 echo   このタスクはまだ登録されていません。
goto :done

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

:purge
rem 古い版が作った連番タスクも含めて、いったん全部消す
for %%i in ("%TASKNAME%" "%TASKNAME% 2" "%TASKNAME% 3" "%TASKNAME% 4") do (
    schtasks /Delete /TN %%i /F >nul 2>&1
)
goto :eof

:showone
schtasks /Query /TN %1 /FO LIST >nul 2>&1
if errorlevel 1 goto :eof
set /a SEEN+=1
schtasks /Query /TN %1 /FO LIST
goto :eof

:done
echo.
echo ------------------------------------------------------------
echo  終了しました。このウィンドウは閉じて構いません。
echo ------------------------------------------------------------
pause
