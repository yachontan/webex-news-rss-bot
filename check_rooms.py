#!/usr/bin/env python3
"""
check_rooms.py
--------------
Webex スペース（ルーム）情報の取得ツール。
Fetches Webex space (room) info: list all, or find a space by name.

使い方 / Usage:
  # 全スペース一覧（対話的にトークン入力）
  python check_rooms.py

  # 名前で絞り込み（.env の設定用 Room ID を表示）
  python check_rooms.py --find "Cisco Security Advisories"

  # トークンを引数/環境変数で渡す（対話プロンプトを省略）
  python check_rooms.py --token xxxxx --find "Cisco Security Advisories"
  WEBEX_BOT_TOKEN=xxxxx python check_rooms.py --find "Cisco Security Advisories"
"""

import argparse
import getpass
import os
import sys
from pathlib import Path

import requests

# 単体実行（python check_rooms.py）でもリポジトリ直下を読めるようにする
sys.path.insert(0, str(Path(__file__).resolve().parent))
from endpoints import get_endpoint  # noqa: E402  sys.path を通してから読み込む


def list_rooms(token: str, max_rooms: int = 1000) -> list[dict]:
    """
    トークンに紐づく Webex ルーム一覧を取得して返します。
    Returns the list of Webex rooms accessible with the given token.

    失敗時は例外を送出します（呼び出し側で処理）。
    """
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(
        get_endpoint("webex", "rooms"), headers=headers,
        params={"max": max_rooms}, timeout=15
    )
    response.raise_for_status()
    return response.json().get("items", [])


def find_rooms_by_title(rooms: list[dict], query: str) -> list[dict]:
    """
    ルーム一覧からタイトルに query を含むものを返します（大文字小文字を区別しない）。
    Returns rooms whose title contains query (case-insensitive substring match).
    """
    q = query.strip().lower()
    return [r for r in rooms if q in (r.get("title") or "").lower()]


def get_room_id_by_title(token: str, title: str, exact: bool = False) -> str | None:
    """
    指定タイトルのスペースの Room ID を1件返します。見つからなければ None。
    Returns the Room ID of the space matching `title` (None if not found).

    exact=True の場合は完全一致、False の場合は部分一致（先頭ヒットを返す）。
    複数ヒット時は先頭を返すため、曖昧な場合は list_rooms で確認すること。
    """
    rooms = list_rooms(token)
    if exact:
        for r in rooms:
            if (r.get("title") or "") == title:
                return r.get("id")
        return None
    matches = find_rooms_by_title(rooms, title)
    return matches[0].get("id") if matches else None


def _resolve_token(cli_token: str | None) -> str:
    """--token 引数 → 環境変数 WEBEX_BOT_TOKEN → 対話入力 の順でトークンを解決する。"""
    if cli_token:
        return cli_token.strip()
    env_token = os.environ.get("WEBEX_BOT_TOKEN", "").strip()
    if env_token:
        print("（環境変数 WEBEX_BOT_TOKEN を使用します）")
        return env_token
    print("Webex Developer Portal から取得したパーソナルアクセストークン、または Bot トークンを入力してください。")
    print("（※セキュリティのため、入力した文字は画面に表示されません）\n")
    return getpass.getpass("Token: ").strip()


def _print_room(room: dict) -> None:
    print(f"■ ルーム名: {room.get('title')}")
    print(f"  Room ID : {room.get('id')}")
    print("-" * 50)


def main() -> None:
    parser = argparse.ArgumentParser(description="Webex スペース情報の取得ツール")
    parser.add_argument("--find", metavar="TEXT",
                        help="この文字列をタイトルに含むスペースだけを表示（部分一致・大文字小文字問わず）")
    parser.add_argument("--token", metavar="TOKEN",
                        help="Webex トークン（省略時は WEBEX_BOT_TOKEN 環境変数、それも無ければ対話入力）")
    parser.add_argument("--exact", action="store_true",
                        help="--find を完全一致で判定する")
    args = parser.parse_args()

    print("=== Webex スペース情報 確認ツール ===")
    token = _resolve_token(args.token)
    if not token:
        print("エラー: トークンが入力されませんでした。")
        sys.exit(1)

    print("\nWebex API に接続してスペース一覧を取得しています...")
    try:
        rooms = list_rooms(token)
    except requests.exceptions.RequestException as e:
        status = getattr(e.response, "status_code", "N/A")
        body = getattr(e.response, "text", str(e))
        print(f"\n❌ 取得失敗 (ステータスコード: {status})")
        print("トークンが無効、または期限切れの可能性があります。")
        print(f"詳細: {body}")
        sys.exit(1)

    if args.find:
        if args.exact:
            matches = [r for r in rooms if (r.get("title") or "") == args.find]
        else:
            matches = find_rooms_by_title(rooms, args.find)
        print(f"\n✅ 「{args.find}」にマッチするスペース: {len(matches)} 件\n")
        print("-" * 50)
        for room in matches:
            _print_room(room)
        if len(matches) == 1:
            print(f"\n※ .env に設定する場合の例:")
            print(f"  WEBEX_SPACE_ID_CISCO_ADVISORY={matches[0].get('id')}")
        elif len(matches) == 0:
            print("\n※ 見つかりませんでした。Bot がそのスペースのメンバーになっているか確認してください。")
            print("  （Bot を新スペースに追加していないと一覧に出ません）")
        else:
            print("\n※ 複数ヒットしました。--exact でスペース名を完全一致指定してください。")
        return

    print(f"\n✅ トークンは有効です！ {len(rooms)} 件のスペースが見つかりました。\n")
    print("-" * 50)
    for room in rooms:
        _print_room(room)
    print("\n※ 確認できた Room ID を .env の WEBEX_SPACE_ID_xxx に設定してください。")


if __name__ == "__main__":
    main()
