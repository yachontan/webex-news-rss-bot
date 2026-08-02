#!/bin/bash
# ============================================================
# 起動_スペースID確認UI.command
#
# Finder でダブルクリックすると、Webex スペースID 確認ツール（check_rooms_ui.py）を
# ブラウザで開くランチャー。初回は必要なパッケージを自動でインストールする。
# Double-click in Finder to launch the Webex space-ID browser UI.
#
# 実行権限が外れてダブルクリックできない場合 / If it won't open:
#   chmod +x "起動_スペースID確認UI.command"
#
# 置き場所について / Location:
#   このUIは手動起動なので TCC 配下でも動くが、定時実行（launchd）を使うなら
#   リポジトリごと ~/Developer/rss-bot のような TCC 保護対象外へ置くこと。
# ============================================================

cd "$(dirname "$0")" || exit 1

# --- 終了時にウィンドウを即閉じさせない（エラーを読めるように）---
finish() {
    echo
    echo "------------------------------------------------------------"
    echo "終了しました。このウィンドウは閉じて構いません。"
    echo "（UI を止めるには、このウィンドウで Control + C）"
    echo "------------------------------------------------------------"
}
trap finish EXIT

echo "=== Webex スペースID 確認ツール ==="
echo

# --- Python の場所を決める / Locate the venv interpreter ---
if [ -x "./bin/python" ]; then
    PY="./bin/python"
elif [ -x "./venv/bin/python" ]; then
    PY="./venv/bin/python"
else
    echo "❌ 仮想環境が見つかりません。"
    echo
    echo "  ターミナルで次を実行してから、もう一度このアイコンをダブルクリックしてください:"
    echo "    cd \"$(pwd)\""
    echo "    python3 -m venv ."
    echo "    ./bin/python -m pip install -r requirements.txt"
    echo
    read -r -p "Enter キーで閉じます..."
    exit 1
fi

# --- 初回のみ UI 用パッケージを導入 / Install UI deps on first run ---
if ! "$PY" -c "import streamlit" >/dev/null 2>&1; then
    echo "初回起動のため、UI に必要なパッケージを入れます（数分かかることがあります）..."
    echo
    if ! "$PY" -m pip install -r requirements-ui.txt; then
        echo
        echo "❌ パッケージのインストールに失敗しました。ネットワーク接続を確認してください。"
        read -r -p "Enter キーで閉じます..."
        exit 1
    fi
    echo
    echo "✅ 準備ができました。"
    echo
fi

# --- 起動 / Launch（ブラウザが自動で開く。止めるときは Control + C）---
echo "ブラウザで UI を開きます。止めるときは Control + C を押してください。"
echo
exec "$PY" -m streamlit run check_rooms_ui.py
