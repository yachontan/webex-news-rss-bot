#!/usr/bin/env python3
"""配信前のネットワーク疎通確認 / Pre-flight connectivity check for rss-bot.

無線が切れている・DNS が返らない状態で本体を走らせると、フィードは取れても
投稿先や要約APIの名前解決に失敗し、全チャンネルが空振りする（実際に発生）。
そこで配信の前に、DNS が引けて期待どおりの HTTP 応答が返ることを確かめる。

確認先の URL はこのコードに直書きせず、urls.yml の `healthcheck:` に置く。

実行 / Run:
    ./bin/python check_network.py           # 1回だけ確認する
    ./bin/python check_network.py --quiet   # 結果を出さず終了コードだけ返す

終了コード / Exit status:
    0 = すべて疎通できた
    1 = 疎通できなかった（呼び出し側は配信を見送り、次の再試行に任せる）
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
URLS_FILE = REPO_ROOT / "urls.yml"

DEFAULT_TIMEOUT = 10


def load_targets(path: Path = URLS_FILE) -> tuple[list[dict], int]:
    """urls.yml の healthcheck: から確認先と待ち時間を読む。

    確認先が書かれていなければ空を返す。呼び出し側はそれを「確認できることが無い」
    とみなして通す。設定漏れで配信そのものが止まってしまうのを避けるため。
    """
    import yaml

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        print(f"  [WARN] urls.yml を読めません: {exc}")
        return [], DEFAULT_TIMEOUT

    feeds = data.get("feeds") if isinstance(data, dict) else data
    for item in feeds or []:
        if isinstance(item, dict) and item.get("healthcheck"):
            block = item["healthcheck"] or {}
            targets = [t for t in (block.get("urls") or []) if t]
            if targets:
                return targets, int(block.get("timeout") or DEFAULT_TIMEOUT)
    return [], DEFAULT_TIMEOUT


def _host_of(url: str) -> str:
    """URL からホスト名だけを取り出す。"""
    from urllib.parse import urlparse

    return urlparse(url).hostname or ""


def check_dns(host: str) -> tuple[bool, str]:
    """名前解決できるかを確かめる。"""
    try:
        return True, socket.getaddrinfo(host, 443)[0][4][0]
    except (socket.gaierror, OSError, IndexError) as exc:
        return False, f"名前解決できません: {exc}"


def check_http(url: str, expect: list[int], timeout: int) -> tuple[bool, str]:
    """期待した HTTP 応答が返るかを確かめる。"""
    import requests

    verify = os.getenv("SSL_VERIFY", "false").strip().lower() == "true"
    if not verify:
        # 検証を切るのは本体(SSL_VERIFY)に合わせた意図的な設定。毎回の警告は出さない。
        import urllib3

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    try:
        code = requests.get(url, timeout=timeout, verify=verify,
                            headers={"User-Agent": "rss-bot/1.0"}).status_code
    except requests.exceptions.RequestException as exc:
        return False, f"接続できません: {exc}"
    if code in expect:
        return True, f"HTTP {code}"
    return False, f"HTTP {code}（期待: {'/'.join(str(c) for c in expect)}）"


def probe(target: dict, timeout: int) -> tuple[bool, str]:
    """1件の確認先について、DNS と HTTP を順に確かめる。"""
    url = str(target.get("url") or "").strip()
    if not url:
        return False, "url が空です"
    expect = [int(c) for c in (target.get("expect") or [200])]

    host = _host_of(url)
    ok, detail = check_dns(host)
    if not ok:
        return False, detail
    ok, http_detail = check_http(url, expect, timeout)
    return ok, f"DNS {detail} / {http_detail}"


def main() -> int:
    """すべての確認先を順に見て、1つでも駄目なら 1 を返す。"""
    parser = argparse.ArgumentParser(description="rss-bot 配信前のネットワーク疎通確認")
    parser.add_argument("--quiet", action="store_true", help="結果を表示しない")
    args = parser.parse_args()

    targets, timeout = load_targets()
    if not targets:
        if not args.quiet:
            print("  [疎通確認] urls.yml に healthcheck: がないため確認を省略します。"
                  "（urls.yml.example を参考に追記すると、配信前に疎通を確かめます）")
        return 0

    failures = []
    for target in targets:
        ok, detail = probe(target, timeout)
        if not ok:
            failures.append(str(target.get("url")))
        if not args.quiet:
            mark = "OK" if ok else "NG"
            print(f"  [疎通確認/{mark}] {target.get('url')} → {detail}")

    if failures and not args.quiet:
        print(f"  [疎通確認] {len(failures)} 件に到達できませんでした。配信を見送ります。")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
