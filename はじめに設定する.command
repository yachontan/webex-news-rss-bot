#!/bin/bash
# ============================================================
# はじめに設定する.command  —  macOS 用セットアップウィザード
#
# Finder でダブルクリックすると、初期設定ウィザードが開きます。
# Double-click in Finder to launch the setup wizard (macOS).
#
# ダブルクリックできない場合 / If it won't open:
#   chmod +x "はじめに設定する.command"
#
# 置き場所について / Location:
#   定時実行（launchd）を使うなら、このリポジトリを ~/Documents ・ ~/Desktop ・
#   ~/Downloads ・ iCloud Drive の**外**（例: ~/Developer/rss-bot）へ置いてください。
#   ウィザードの最初のステップでも自動判定します。
# ============================================================

cd "$(dirname "$0")" || exit 1

finish() {
    echo
    echo "------------------------------------------------------------"
    echo "ウィザードを終了しました。このウィンドウは閉じて構いません。"
    echo "------------------------------------------------------------"
}
trap finish EXIT

# --- Python を探す / Locate Python 3 ---
PY=""
for candidate in python3 python3.13 python3.12 python3.11 python3.10; do
    if command -v "$candidate" >/dev/null 2>&1; then
        PY="$candidate"
        break
    fi
done

if [ -z "$PY" ]; then
    echo "❌ Python 3 が見つかりません。"
    echo
    echo "  次のいずれかで入れてから、もう一度ダブルクリックしてください:"
    echo "    ・https://www.python.org/downloads/ からインストール"
    echo "    ・ターミナルで: xcode-select --install"
    echo
    read -r -p "Enter キーで閉じます..."
    exit 1
fi

exec "$PY" setup.py
