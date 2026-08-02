@echo off
chcp 65001 >nul
rem ============================================================
rem  起動_スペースID確認UI.bat  —  Windows 用ランチャー
rem
rem  エクスプローラーでダブルクリックすると、Webex スペースID 確認ツールを
rem  ブラウザで開きます。初回は必要なパッケージを自動でインストールします。
rem  Double-click in Explorer to launch the Webex space-ID browser UI.
rem
rem  止めるときは、このウィンドウで Ctrl + C。
rem ============================================================
setlocal
cd /d "%~dp0"

echo === Webex スペースID 確認ツール ===
echo.

rem --- 仮想環境の python を探す / Locate the venv interpreter ---
set "PY="
if exist "Scripts\python.exe" set "PY=Scripts\python.exe"
if not defined PY if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"

if not defined PY (
    echo   [NG] 仮想環境が見つかりません。
    echo.
    echo   先に「はじめに設定する.bat」をダブルクリックして初期設定を済ませてください。
    echo   （手動で作る場合: python -m venv venv ^&^& venv\Scripts\python -m pip install -r requirements.txt）
    echo.
    pause
    exit /b 1
)

rem --- 初回のみ UI 用パッケージを導入 / Install UI deps on first run ---
"%PY%" -c "import streamlit" >nul 2>&1
if errorlevel 1 (
    echo 初回起動のため、UI に必要なパッケージを入れます（数分かかることがあります）...
    echo.
    "%PY%" -m pip install -r requirements-ui.txt
    if errorlevel 1 (
        echo.
        echo   [NG] パッケージのインストールに失敗しました。ネットワーク接続を確認してください。
        pause
        exit /b 1
    )
    echo.
    echo   準備ができました。
    echo.
)

echo ブラウザで UI を開きます。止めるときは Ctrl + C を押してください。
echo.
"%PY%" -m streamlit run check_rooms_ui.py

echo.
echo ------------------------------------------------------------
echo  終了しました。このウィンドウは閉じて構いません。
echo ------------------------------------------------------------
pause
