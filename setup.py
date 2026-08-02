#!/usr/bin/env python3
"""初期設定ウィザードのブートストラップ / Bootstrap for the rss-bot setup wizard.

仮想環境を作る前に動く必要があるため、**標準ライブラリだけ**で書いてある。
やること: 環境診断 → 仮想環境の作成 → 依存の導入 → ウィザード本体の起動。

実行 / Run:
    python3 setup.py            # 対話（ブラウザUI か CLI かを選ぶ）
    python3 setup.py --cli      # CLI 版で進める
    python3 setup.py --ui       # ブラウザUI版で進める
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

from wizard import core  # noqa: E402  sys.path を通してから読み込む必要がある

RULE = "=" * 60


def show_diagnostics() -> bool:
    """環境診断の結果を表示し、続行してよいかを返す。"""
    print(f"{RULE}\n rss-bot 初期設定ウィザード\n{RULE}\n")
    print("環境を確認しています...\n")
    checks = core.run_diagnostics()
    for check in checks:
        mark = "OK  " if check.ok else ("NG  " if check.fatal else "警告")
        print(f"  [{mark}] {check.name}: {check.detail}")
        if check.hint:
            print(f"         → {check.hint}")
    missing = core.missing_config_files()
    if missing:
        print("  [情報] 設定ファイルがまだありません: " + "、".join(missing))
        print("         ウィザードの中で、ひな形から自動的に作ります。")
    print()
    if any(c.fatal for c in checks):
        print("続行できない問題があります。上の指示に従ってから、もう一度実行してください。")
        return False
    if any(not c.ok for c in checks):
        answer = input("警告がありますが続けますか？ (y/N): ").strip().lower()
        return answer.startswith("y")
    return True


def ensure_environment(want_ui: bool) -> Path:
    """仮想環境と依存を整え、使う python のパスを返す。"""
    python_path = core.venv_python()
    if python_path is None:
        print("仮想環境が無いので作成します（1分ほどかかります）...")
        python_path = core.create_venv()
        print(f"  作成しました: {python_path}")

    missing = core.missing_packages(python_path)
    if missing:
        print(f"必要なパッケージを導入します: {', '.join(missing)}")
        print("（初回は数分かかることがあります）")
        core.install_requirements(python_path, include_ui=want_ui)
        print("  導入しました。")
    elif want_ui:
        core.install_requirements(python_path, include_ui=True)
    return python_path


def choose_mode(args: argparse.Namespace) -> str:
    """ブラウザUI と CLI のどちらで進めるかを決める。"""
    if args.ui:
        return "ui"
    if args.cli:
        return "cli"
    print("\nどちらで設定しますか？")
    print("  1. ブラウザで設定する（おすすめ・チェックボックスで選べます）")
    print("  2. このターミナルで設定する（追加のインストールが不要）")
    answer = input("番号 [1]: ").strip() or "1"
    return "cli" if answer == "2" else "ui"


def launch(mode: str, python_path: Path) -> int:
    """選ばれた方式でウィザード本体を起動する。"""
    if mode == "ui":
        print("\nブラウザでウィザードを開きます。止めるときは Control + C。\n")
        command = [str(python_path), "-m", "streamlit", "run", str(REPO_ROOT / "wizard" / "app.py")]
    else:
        command = [str(python_path), "-m", "wizard.cli"]
    try:
        return subprocess.run(command, cwd=str(REPO_ROOT), check=False).returncode
    except KeyboardInterrupt:
        print("\n中断しました。")
        return 130


def parse_args() -> argparse.Namespace:
    """コマンドライン引数を解釈する。"""
    parser = argparse.ArgumentParser(description="rss-bot の初期設定ウィザードを起動する")
    parser.add_argument("--cli", action="store_true", help="ターミナルで設定する")
    parser.add_argument("--ui", action="store_true", help="ブラウザで設定する")
    return parser.parse_args()


def main() -> int:
    """ブートストラップのエントリポイント。"""
    args = parse_args()
    if not show_diagnostics():
        return 1
    mode = choose_mode(args)
    try:
        python_path = ensure_environment(want_ui=(mode == "ui"))
    except (subprocess.CalledProcessError, OSError, RuntimeError) as exc:
        print(f"\n環境の準備に失敗しました: {exc}")
        print("ネットワーク接続と Python のインストール状態を確認してください。")
        return 1
    return launch(mode, python_path)


if __name__ == "__main__":
    sys.exit(main())
