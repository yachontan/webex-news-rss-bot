#!/bin/bash
# rss-bot を Documents フォルダ外（ホームディレクトリ直下）に同期・配置するスクリプト

TARGET_DIR="$HOME/rss-bot"
SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Deploying rss-bot from $SOURCE_DIR to $TARGET_DIR ..."
mkdir -p "$TARGET_DIR"

# コードや設定ファイルを rsync で同期 (仮想環境やログ、Git関係は除外)
rsync -av \
    --exclude 'bin' \
    --exclude 'lib' \
    --exclude 'include' \
    --exclude 'pyvenv.cfg' \
    --exclude '__pycache__' \
    --exclude '.git' \
    --exclude 'log' \
    "$SOURCE_DIR/" "$TARGET_DIR/"

# ログディレクトリの作成
mkdir -p "$TARGET_DIR/log"

# 同期先に仮想環境がない場合は作成し、依存ライブラリをインストール
if [ ! -d "$TARGET_DIR/bin" ]; then
    echo "Creating virtual environment in $TARGET_DIR..."
    python3 -m venv "$TARGET_DIR"
    "$TARGET_DIR/bin/pip" install -r "$TARGET_DIR/requirements.txt"
fi

# ラッパースクリプトを生成
# plist は StandardOutPath に動的なファイル名を指定できないため、
# ラッパー経由でタイムスタンプ付きログファイルにリダイレクトする。
WRAPPER_PATH="$TARGET_DIR/run_rssbot.sh"
cat << 'WRAPPER_EOF' > "$WRAPPER_PATH"
#!/bin/bash
# launchd から呼び出されるラッパースクリプト
# タイムスタンプ付きのログファイルに stdout/stderr をリダイレクトする

TARGET_DIR="$HOME/rss-bot"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
LOG_DIR="$TARGET_DIR/log"
LOG_FILE="$LOG_DIR/launchd_run-${TIMESTAMP}.log"
ERR_FILE="$LOG_DIR/launchd_err-${TIMESTAMP}.log"

cd "$TARGET_DIR"
"$TARGET_DIR/bin/python" "$TARGET_DIR/webex-news-rss-bot.py" >> "$LOG_FILE" 2>> "$ERR_FILE"
WRAPPER_EOF
chmod +x "$WRAPPER_PATH"
echo "Wrapper script generated: $WRAPPER_PATH"

# launchd 用の plist ファイルを作成・更新
PLIST_PATH="$HOME/Library/LaunchAgents/com.webex-news.rssbot.plist"
cat << EOF > "$PLIST_PATH"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.webex-news.rssbot</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>$TARGET_DIR/run_rssbot.sh</string>
    </array>
    <key>StartCalendarInterval</key>
    <array>
        <!-- 月曜日 (1) -->
        <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>1</integer></dict>
        <!-- 火曜日 (2) -->
        <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>1</integer></dict>
        <!-- 水曜日 (3) -->
        <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>1</integer></dict>
        <!-- 木曜日 (4) -->
        <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>1</integer></dict>
        <!-- 金曜日 (5) -->
        <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>1</integer></dict>
    </array>
    <key>WorkingDirectory</key>
    <string>$TARGET_DIR</string>
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
EOF

echo "Reloading launchd job..."
launchctl unload "$PLIST_PATH" 2>/dev/null
launchctl load "$PLIST_PATH"

echo "Deployment complete! The bot is now scheduled to run from $TARGET_DIR."
echo "Log files will be saved as: $TARGET_DIR/log/launchd_run-YYYYMMDD-HHMMSS.log"
echo "If you want to test it now, run: launchctl start com.webex-news.rssbot"
