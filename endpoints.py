"""外部APIの宛先を endpoints.yml から読む / Loads API endpoints from endpoints.yml.

URL をコードに直書きしないための共有ローダ。本体（webex-news-rss-bot.py）、
check_rooms.py、ウィザード（wizard/core.py）の3か所から使う。

このモジュールは**標準ライブラリだけで import できる**。PyYAML は関数内で遅延 import する
（setup.py が仮想環境を作る前に wizard/core.py 経由で読み込むため、ここで PyYAML を
requires にすると初期セットアップが動かなくなる）。
"""

from __future__ import annotations

from pathlib import Path

ENDPOINTS_FILE = Path(__file__).resolve().parent / "endpoints.yml"

_CACHE: dict | None = None


def load_endpoints(path: Path | None = None) -> dict:
    """endpoints.yml を読み込んで返す。2回目以降はキャッシュを返す。"""
    global _CACHE  # noqa: E06  読み込み結果を1度だけ保持するためのキャッシュ

    if _CACHE is not None and path is None:
        return _CACHE

    import yaml

    target = path or ENDPOINTS_FILE
    try:
        text = target.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(
            f"{target.name} を読めません（{exc}）。リポジトリ直下に endpoints.yml が"
            "あるか確認してください（git で管理されているファイルです）。") from exc
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise RuntimeError(f"{target.name} の解析に失敗しました: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"{target.name} の形式が正しくありません（マップである必要があります）")

    if path is None:
        _CACHE = data
    return data


def get_endpoint(*keys: str) -> str:
    """endpoints.yml から URL を1つ取り出す。

    例 / Example:
        get_endpoint("webex", "messages")  ->  "https://webexapis.com/v1/messages"

    見つからない場合は RuntimeError を送出する。空文字を返すと、投稿失敗の原因が
    「トークン」なのか「宛先が空」なのか分からなくなるため、その場で止める。
    """
    node: object = load_endpoints()
    for depth, key in enumerate(keys):
        if not isinstance(node, dict) or key not in node:
            path = " → ".join(keys[:depth + 1])
            raise RuntimeError(
                f"endpoints.yml に '{path}' がありません。"
                f"{ENDPOINTS_FILE.name} を確認してください。")
        node = node[key]
    url = str(node or "").strip()
    if not url:
        raise RuntimeError(
            f"endpoints.yml の '{' → '.join(keys)}' が空です。"
            f"{ENDPOINTS_FILE.name} を確認してください。")
    return url
