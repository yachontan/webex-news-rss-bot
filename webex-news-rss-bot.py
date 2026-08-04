#!/usr/bin/env python3
"""
webex-news-rss-bot.py
-------------------
Collects today's RSS news by category keyword and sends notifications via Webex Bot.
カテゴリキーワードに基づいて当日のRSSニュースを収集し、Webex Bot経由で通知します。

設定ファイル:
  - urls.yml     : 収集するRSSフィード（天気APIと名前付きグループもここ）
  - channels.yml : 配信先チャンネル（どのスペースへどのカテゴリを送るか）
  - categories.yml : カテゴリのキーワード

動作モード / Operation Modes:
  - マルチチャンネルモード: channels.yml がある場合。各チャンネルに個別配信。
  - シングルボットモード : channels: が無い場合。--category 引数で制御。
"""

import feedparser
import datetime
import requests
import json
import os
import sys
import time
import argparse
import yaml
import random
import re
import unicodedata

from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

from dotenv import load_dotenv

from endpoints import get_endpoint  # 外部APIの宛先は endpoints.yml から読む

# --- 環境変数の読み込み / Load environment variables ---
# override=True: シェル側に空文字などで既存セットされていても .env の値で上書きする。
# これがないと、たとえば shell 環境に ANTHROPIC_API_KEY='' があるだけで
# .env の API キーが無視されて Claude 要約が無効化される。
_BASE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_BASE, ".env"), override=True)


WEBEX_BOT_TOKEN = os.getenv("WEBEX_BOT_TOKEN", "")
WEBEX_SPACE_ID  = os.getenv("WEBEX_SPACE_ID", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
# 実際に使うキーは LLM_PROVIDER に応じて llm_api_key() で解決する
ANTHROPIC_MODEL   = os.getenv("ANTHROPIC_MODEL", "claude-3-haiku-20240307")
# 再ランク（stratified_pick の置き換え）専用モデル。要約用の ANTHROPIC_MODEL とは別枠。
ANTHROPIC_RERANK_MODEL = os.getenv("ANTHROPIC_RERANK_MODEL", "claude-haiku-4-5-20251001")
SSL_VERIFY        = os.getenv("SSL_VERIFY", "True").strip().lower() != "false"

# SSL検証を無効にする場合、警告を非表示にします
if not SSL_VERIFY:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- ファイルパス定数 / File path constants ---

CATEGORIES_FILE = os.path.join(_BASE, "categories.yml")
# 設定は用途ごとに分ける（編集しやすさのため）。
#   urls.yml     : 収集するRSSフィード（feeds:）
#   channels.yml : 配信先チャンネル（channels:）
# Config is split by purpose: urls.yml (feeds) and channels.yml (channels).
# 1チャンネルに1回で投稿する記事数の上限。channels.yml の max_items で変えられる。
# これを超えた分は LLM 再ランク（失敗時は stratified_pick）で絞り込む。
# 既定引数から参照するため、関数定義より前に置く必要がある。
MAX_ITEMS_DEFAULT = 15
MAX_ITEMS_LIMIT = 50      # 多すぎると1通が長大になり Webex 側で分割される

URLS_FILE       = os.path.join(_BASE, "urls.yml")
CHANNELS_FILE   = os.path.join(_BASE, "channels.yml")
# 旧構成（1ファイルにまとめていた頃）。両方が無い場合の後方互換として読む。
LEGACY_CONFIG_FILE = os.path.join(_BASE, "config.yml")
MORNING_MESSAGES_FILE = os.path.join(_BASE, "morning_messages.txt")

# ===========================================================
# 設定ファイル読み込み / Config loaders
# ===========================================================

def load_random_morning_message(path: str = MORNING_MESSAGES_FILE) -> str:
    """
    morning_messages.txt からランダムに1行のメッセージを読み込みます。
    Loads a random morning message from morning_messages.txt.
    """
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
        if lines:
            return random.choice(lines)
    except Exception as e:
        print(f"  [WARN] 朝メッセージファイルの読み込みに失敗しました: {e}")
    return ""

def _load_yaml(path: str, label: str):
    """YAML を読み込んで返す内部関数（解析エラーは停止）。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except yaml.YAMLError as e:
        print(f"[ERROR] {label} の解析に失敗しました: {e}")
        sys.exit(1)


def _read_feeds(path: str = URLS_FILE) -> list:
    """収集するフィードの一覧を返す内部関数。

    受け付ける形式 / Accepted forms:
      - urls.yml が `feeds:` を持つマップ（現行）
      - urls.yml がトップレベルのリスト（v1.x の書き方）
      - urls.yml が無い場合は config.yml の `feeds:`（旧1ファイル構成）
    """
    source, label = path, "urls.yml"
    if not os.path.exists(source):
        if os.path.exists(LEGACY_CONFIG_FILE):
            source, label = LEGACY_CONFIG_FILE, "config.yml"
        else:
            print(f"[ERROR] フィード設定ファイルが見つかりません: {path}")
            print("       urls.yml.example をコピーして urls.yml を作成してください。")
            sys.exit(1)

    data = _load_yaml(source, label)
    if isinstance(data, list):
        return data                      # v1.x のリスト形式
    if isinstance(data, dict) and isinstance(data.get("feeds"), list):
        return data["feeds"]
    print(f"[ERROR] {label} に 'feeds:' がありません（リスト形式で記述してください）。")
    sys.exit(1)


def load_urls(path: str = URLS_FILE) -> list[str]:
    """
    urls.yml から収集対象の全RSSフィードURLを平坦なリストで読み込みます。
    Loads all RSS feed URLs (flattened) from urls.yml.

    urls.yml の feeds: の各要素は次のどちらでもよい:
      - 文字列                         : 通常のフィードURL
      - {group: <名前>, urls: [<URL>...]} : 名前付きグループ（channels.yml の
        source_groups から参照される。URL の正本は urls.yml に一本化する用途）
    どちらの形式でも、ここでは収集対象として全URLを平坦化して返す。
    """
    data = _read_feeds(path)
    urls: list[str] = []
    for item in data:
        if not item:
            continue
        if isinstance(item, dict):
            # グループ形式: {group: name, urls: [...]}
            for u in (item.get("urls") or []):
                if u:
                    urls.append(str(u).strip())
        else:
            urls.append(str(item).strip())
    # 重複排除（順序保持）
    return list(dict.fromkeys(urls))


def load_url_groups(path: str = URLS_FILE) -> dict[str, list[str]]:
    """
    urls.yml 内の名前付きグループを {グループ名: [URL, ...]} で返します。
    Returns named URL groups defined in urls.yml as {group_name: [urls]}.

    channels.yml の source_groups からフィードを URL 直書きせずに参照するために使う。
    """
    data = _read_feeds(path)
    groups: dict[str, list[str]] = {}
    for item in data:
        if isinstance(item, dict) and item.get("group"):
            name = str(item["group"]).strip()
            urls = [str(u).strip() for u in (item.get("urls") or []) if u]
            if name:
                groups.setdefault(name, []).extend(urls)
    return groups


def load_advisory_config(path: str = URLS_FILE) -> str:
    """
    urls.yml から CVRF API の URL 雛形を読み込みます。
    Loads the CVRF URL template from urls.yml.

    形式 / Format（推奨）: Advisory を集めるグループに直接書く。
        - group: Cisco-Security-Advisories
          urls:
            - https://sec.cloudapps.cisco.com/security/center/psirtrss20/CiscoSecurityAdvisory.xml
          cvrf_url: https://.../CiscoSecurityAdvisory/{adv_id}/cvrf/{adv_id}_cvrf.xml

    「どこから集めるか」と「その記事に CVSS をどう付けるか」は同じ Advisory の話なので、
    1つのエントリにまとめる。旧形式（独立した `- cisco_advisory:` エントリ）も読む。

    `{adv_id}` が Advisory ID に置き換わる。URL の正本は urls.yml に集約し、
    Python コードには直書きしない。未定義の場合は空文字を返す
    （その場合 CVSS バッジの付与をスキップする）。
    """
    def _valid(template: str, where: str) -> str:
        template = (template or "").strip()
        if template and "{adv_id}" not in template:
            print(f"  [WARN] urls.yml {where}: cvrf_url に {{adv_id}} が含まれていません")
            return ""
        return template

    fallback = ""
    for item in _read_feeds(path):
        if not isinstance(item, dict):
            continue
        if item.get("group"):
            found = _valid(item.get("cvrf_url"), f"group: {item['group']}")
            if found:
                return found
        elif item.get("cisco_advisory"):
            # 旧形式。グループ側に書かれていればそちらを優先する
            fallback = fallback or _valid(
                (item["cisco_advisory"] or {}).get("cvrf_url"), "cisco_advisory")
    return fallback


def load_weather_config(path: str = URLS_FILE) -> dict | None:
    """
    urls.yml 内の weather エントリ（天気API設定）を読み込みます。
    Loads the weather API config from the `weather` entry in urls.yml.

    形式 / Format:
        - weather:
            api_url: https://api.open-meteo.com/v1/forecast
            locations:
              - { label: 東京, lat: 35.6895, lon: 139.6917 }

    URL・地点の正本は urls.yml に集約し、Python コードには直書きしない。
    未定義・不完全な場合は None を返す（デイリーダイジェストは天気ブロックを省略）。
    weather エントリは urls / group キーを持たないため RSS 収集からは無視される。
    """
    data = _read_feeds(path)
    for item in data:
        if not (isinstance(item, dict) and item.get("weather")):
            continue
        w = item["weather"] or {}
        api_url = str(w.get("api_url") or "").strip()
        locations: list[tuple[str, float, float]] = []
        for loc in (w.get("locations") or []):
            if not isinstance(loc, dict):
                continue
            label = str(loc.get("label") or "").strip()
            lat, lon = loc.get("lat"), loc.get("lon")
            if label and lat is not None and lon is not None:
                try:
                    locations.append((label, float(lat), float(lon)))
                except (TypeError, ValueError):
                    print(f"  [WARN] urls.yml weather: 地点 '{label}' の lat/lon が不正です")
        if api_url and locations:
            return {"api_url": api_url, "locations": locations}
        print("  [WARN] urls.yml の weather 設定が不完全です（api_url / locations を確認）")
        return None
    return None


REGIONS_FILE = os.path.join(_BASE, "regions.yml")


def load_regions_config(path: str = REGIONS_FILE) -> dict | None:
    """
    regions.yml から時事ダイジェストの地域バランス設定を読み込みます。
    Loads region-balance config (quota + keywords) for the current-affairs digest.

    形式 / Format:
        quota: { japan: 7, us: 3, other: 5 }
        keywords:
          us:    [アメリカ, 米国, ...]
          other: [中国, 韓国, ...]

    キーワード・クオータの正本は regions.yml に集約し、Python には直書きしない。
    ファイルが無い・不完全な場合は None を返す（呼び出し側で従来の日本ニュース枠へ
    フォールバックする＝後方互換）。
    """
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        print(f"  [WARN] regions.yml の解析に失敗しました: {e}")
        return None
    if not isinstance(data, dict):
        print("  [WARN] regions.yml の形式が正しくありません（マップ形式で記述してください）")
        return None

    quota_raw = data.get("quota") or {}
    kw_raw = data.get("keywords") or {}

    def _int(v, default):
        try:
            return max(0, int(v))
        except (TypeError, ValueError):
            return default

    quota = {
        "japan": _int(quota_raw.get("japan"), 7),
        "us":    _int(quota_raw.get("us"), 3),
        "other": _int(quota_raw.get("other"), 5),
    }
    us_kws    = [str(k).strip() for k in (kw_raw.get("us") or []) if str(k).strip()]
    other_kws = [str(k).strip() for k in (kw_raw.get("other") or []) if str(k).strip()]

    if not us_kws and not other_kws:
        print("  [WARN] regions.yml に keywords（us/other）がありません → 地域バランスを無効化")
        return None
    return {"quota": quota, "us_keywords": us_kws, "other_keywords": other_kws}

# ===========================================================
# LLM (Claude) 要約処理 / LLM (Claude) Summarization
# ===========================================================

# ===========================================================
# LLM プロバイダ / LLM providers
# ===========================================================
# 要約と再ランクは、Claude・OpenAI・Gemini のいずれでも動く。
# どれを使うかは .env の LLM_PROVIDER で決める（未指定なら anthropic）。

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic").strip().lower() or "anthropic"

# エンドポイントURLは endpoints.yml に集約する（コードに直書きしない）。
# 取得は endpoints.get_endpoint("llm", <プロバイダ名>)。
LLM_KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
}


def llm_api_key(provider: str = "") -> str:
    """使用中のプロバイダに対応する API キーを .env から取得します。"""
    name = LLM_KEY_ENV.get(provider or LLM_PROVIDER, "ANTHROPIC_API_KEY")
    return os.getenv(name, "").strip()


def call_llm(prompt: str, api_key: str, model: str, max_tokens: int = 140,
             provider: str = "") -> str:
    """LLM に1回問い合わせて、返ってきた本文を返します。

    プロバイダごとに URL・ヘッダ・本文の形が違うだけで、やることは同じ。
    呼び出し側はプロバイダを意識しなくてよい。
    """
    name = (provider or LLM_PROVIDER).lower()
    if name == "openai":
        url = get_endpoint("llm", "openai")
        headers = {"Authorization": f"Bearer {api_key}", "content-type": "application/json"}
        payload = {"model": model, "max_completion_tokens": max_tokens,
                   "messages": [{"role": "user", "content": prompt}]}
    elif name == "gemini":
        # gemini だけ、エンドポイントの後ろにモデル名と動詞を付けて呼ぶ
        url = f"{get_endpoint('llm', 'gemini')}/{model}:generateContent"
        headers = {"x-goog-api-key": api_key, "content-type": "application/json"}
        payload = {"contents": [{"parts": [{"text": prompt}]}],
                   "generationConfig": {"maxOutputTokens": max_tokens}}
    else:
        url = get_endpoint("llm", "anthropic")
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01",
                   "content-type": "application/json"}
        payload = {"model": model, "max_tokens": max_tokens,
                   "messages": [{"role": "user", "content": prompt}]}

    response = requests.post(url, headers=headers, json=payload, timeout=30, verify=SSL_VERIFY)
    response.raise_for_status()
    data = response.json()
    if name == "openai":
        return (data["choices"][0]["message"]["content"] or "").strip()
    if name == "gemini":
        parts = data["candidates"][0]["content"]["parts"]
        return "".join(part.get("text", "") for part in parts).strip()
    return data["content"][0]["text"].strip()


def summarize_with_claude(title: str, summary: str, api_key: str, model: str = "claude-3-haiku-20240307", is_advisory: bool = False) -> str:
    """
    Claude API を使用して記事を要約します。

    is_advisory=True（Cisco Security Advisory）の場合は、深刻度に見合う影響
    （攻撃前提・想定被害）を簡潔にまとめる専用プロンプトを使う。
    ※ CVSS の数値はプロンプトで問い合わせない（課金削減）。深刻度はモデルが本文から
      推測し、数値自体はタイトル行のバッジ（CVRF 由来の実値）で表示する。
    """
    if not api_key:
        return summary

    # 圧縮プロンプト: 主要制約を最短で記述（約45トークン）
    # - ラベル/前置き禁止: タイトル：/概要：等を防止
    # - 情報不足要求禁止: 「本文を提供してください」等を防止
    # - 英文は翻訳: 英語RSSを日本語化
    if is_advisory:
        # Cisco Security Advisory 専用: 深刻度に見合う影響を簡潔に。
        # CVSS の数値は問い合わせない（別途バッジ表示。echo が出ても後段で除去）。
        prompt = (
            "日本語110字以内1〜2文で要約のみ出力。"
            "ラベル/前置き/改行/情報不足要求は禁止。"
            "深刻度に見合う影響（攻撃前提・想定被害）を簡潔に。英文は翻訳。\n\n"
            f"T: {title}\nS: {summary}"
        )
    else:
        prompt = (
            "日本語110字以内1〜2文で要約のみ出力。"
            "ラベル/前置き/改行/情報不足要求は禁止。"
            "提供情報のみで完結、英文は翻訳。\n\n"
            f"T: {title}\nS: {summary}"
        )

    try:
        return call_llm(prompt, api_key, model, max_tokens=140)
    except Exception as e:
        print(f"    [WARN] 要約に失敗しました（{LLM_PROVIDER}）: {e}。元の概要を使用します。")
        return summary

def summarize_entries_in_place(entries: list[dict], api_key: str, cache: dict, model: str = "claude-3-haiku-20240307") -> None:
    """
    送信対象の記事リストの各エントリの summary を Claude で要約して上書きします。
    """
    if not api_key:
        return
    
    to_summarize = [e for e in entries if e.get("summary")]
    if not to_summarize:
        return
        
    print(f"    --- Claudeによる要約処理を開始 (対象: {len(to_summarize)} 件) ---")
    for entry in to_summarize:
        link = entry["link"]
        if link in cache:
            entry["summary"] = cache[link]
            continue
            
        raw_sum = entry["summary"].strip()
        is_short = len(raw_sum) <= 100
        is_complete = not (raw_sum.endswith("...") or raw_sum.endswith("…") or "続き" in raw_sum or "more" in raw_sum.lower())
        is_clean = not any(entity in raw_sum for entity in ["&nbsp;", "&gt;", "&lt;", "&quot;", "&amp;"])
        # ひらがな/カタカナ/漢字を1文字も含まなければ「英文(または非日本語)」と判定。
        # この場合は短くてもClaudeに渡して日本語へ翻訳要約させる。
        is_japanese = bool(re.search(r'[ぁ-んァ-ヶー一-龯]', raw_sum))

        if is_short and is_complete and is_clean and is_japanese:
            # 日本語かつ既に十分に短く綺麗な文章の場合は、APIコールをせずそのまま採用して節約
            print(f"      [SKIP-API] 概要が既に短く綺麗な日本語です: {entry['title'][:25]}...")
            cache[link] = raw_sum
            continue

        action = "翻訳・要約中" if not is_japanese else "要約中"
        print(f"      {action} (モデル: {model}): {entry['title'][:25]}...")
        is_advisory = "/CiscoSecurityAdvisory/" in (entry.get("link") or "")
        new_summary = summarize_with_claude(
            entry["title"], entry["summary"], api_key, model=model, is_advisory=is_advisory
        )
        # CVSS 付きエントリは、LLM が概要から CVSS を拾って要約に混ぜることがあるため除去する
        # （プロンプトでは CVSS を問い合わせない。数値はタイトル行のバッジで表示。二重表示防止）。
        if entry.get("cvss"):
            new_summary = _strip_cvss_mentions(new_summary)
        cache[link] = new_summary
        entry["summary"] = new_summary
        time.sleep(0.5)  # レート制限対策
    print("    --- 要約完了 ---")


# ===========================================================
# Cisco Security Advisory の CVSS スコア取得 / CVSS enrichment
# ===========================================================
#
# CVSS スコアは RSS の本文には含まれず、各 advisory の詳細ページ（URL 先）にある。
# LLM に渡すのは RSS のタイトル＋概要だけなので、プロンプトだけでは正確な CVSS を
# 出せない（捏造になる）。そこで Cisco が公開している構造化データ（advisory ごとの
# CVRF XML）から実スコアを取得して表示する。
#
#   CVRF URL 例:
#     https://sec.cloudapps.cisco.com/security/center/contentxml/
#       CiscoSecurityAdvisory/<advisory-id>/cvrf/<advisory-id>_cvrf.xml
#   スコアは <BaseScoreV3>9.1</BaseScoreV3>（CVSS v3）。複数 CVE があれば複数出現する。

_CVSS_CACHE: dict[str, tuple[str, str]] = {}
_ADVISORY_LINK_RE = re.compile(r'/CiscoSecurityAdvisory/([A-Za-z0-9][A-Za-z0-9\-_]+)')
_BASESCORE_V3_RE = re.compile(r'<BaseScoreV3>\s*([0-9]+(?:\.[0-9])?)\s*</BaseScoreV3>')
_BASESCORE_V2_RE = re.compile(r'<BaseScore>\s*([0-9]+(?:\.[0-9])?)\s*</BaseScore>')


# 要約文に紛れ込む CVSS 表記（LLM の echo や生 RSS 由来）を除去するための正規表現。
# 例: "**CVSS: 7.8**" / "CVSS 7.5〜9.1（複数該当）" / "CVSS：5.5" など。
# CVSS の数値はタイトル行のバッジで表示するため、要約文からは取り除いて二重表示を防ぐ。
_CVSS_MENTION_RE = re.compile(
    r'\s*(?:\*\*)?\s*CVSS\s*(?:Base\s*Score)?\s*[:：]?\s*'
    r'[0-9]+(?:\.[0-9])?(?:\s*[〜～~]\s*[0-9]+(?:\.[0-9])?)?'
    r'\s*(?:（複数該当）)?\s*(?:\*\*)?',
    re.IGNORECASE,
)


def _strip_cvss_mentions(text: str) -> str:
    """要約文中の CVSS 表記を除去し、余分な空白を整える（数値はバッジで別途表示）。"""
    if not text:
        return text
    cleaned = _CVSS_MENTION_RE.sub(" ", text)
    return re.sub(r"\s+", " ", cleaned).strip()


def _advisory_id_from_link(link: str) -> str | None:
    """Cisco Security Advisory の URL から advisory ID を取り出す。該当しなければ None。"""
    if not link or "/CiscoSecurityAdvisory/" not in link:
        return None
    m = _ADVISORY_LINK_RE.search(link)
    return m.group(1) if m else None


def _format_cvss(scores: list[float]) -> str:
    """
    CVSS スコアのリストを表示文字列に整形する。
      - 0件           : "" （表示しない）
      - 1種類         : "9.1"
      - 複数種類      : "7.5〜9.1（複数該当）"  （最小〜最大）
    """
    uniq = sorted(set(scores))
    if not uniq:
        return ""
    if len(uniq) == 1:
        return f"{uniq[0]:.1f}"
    return f"{uniq[0]:.1f}〜{uniq[-1]:.1f}（複数該当）"


def _cvss_color(score: float) -> str:
    """
    CVSS Base Score を、標準的な CVSS v3.x 深刻度バンドに沿って危険度カラーに割り当てる。
      - 9.0〜10.0 : Critical → 🔴
      - 7.0〜 8.9 : High     → 🟠
      - 0.1〜 6.9 : Medium / Low → 🟡
    複数スコアがある場合は最大値（最悪ケース）で色を決める想定で呼び出す。
    """
    if score >= 9.0:
        return "🔴"
    if score >= 7.0:
        return "🟠"
    return "🟡"


def fetch_cisco_cvss(link: str, cvrf_url_template: str) -> tuple[str, str]:
    """
    Cisco Security Advisory の CVRF から CVSS Base Score を取得し、
    (表示文字列, 危険度カラー絵文字) を返す。

    cvrf_url_template は urls.yml の cisco_advisory エントリ由来（`{adv_id}` を含む）。
    advisory でない・取得失敗・スコア無しの場合は ("", "") を返す（表示しない）。
    色は複数スコア時は最大値（最悪ケース）で決定する。
    """
    adv_id = _advisory_id_from_link(link)
    if not adv_id:
        return "", ""
    if adv_id in _CVSS_CACHE:
        return _CVSS_CACHE[adv_id]

    cvrf_url = cvrf_url_template.format(adv_id=adv_id)
    result: tuple[str, str] = ("", "")
    try:
        resp = requests.get(
            cvrf_url,
            headers={"User-Agent": "rss-bot/1.0 (+RSS aggregator; feed reader)"},
            timeout=15,
            verify=SSL_VERIFY,
        )
        if resp.status_code == 200:
            scores = [float(x) for x in _BASESCORE_V3_RE.findall(resp.text)]
            if not scores:  # v3 が無ければ v2 にフォールバック
                scores = [float(x) for x in _BASESCORE_V2_RE.findall(resp.text)]
            if scores:
                result = (_format_cvss(scores), _cvss_color(max(scores)))
    except Exception as e:
        print(f"    [WARN] CVSS 取得失敗（{adv_id}）: {e}")
        result = ("", "")

    _CVSS_CACHE[adv_id] = result
    return result


def enrich_cisco_cvss_in_place(entries: list[dict], cvrf_url_template: str) -> None:
    """
    Cisco Security Advisory のエントリに CVSS スコア（entry["cvss"]）を付与する。
    advisory でないエントリは何もしない（ネットワーク取得も行わない）。

    cvrf_url_template が空（urls.yml に cisco_advisory エントリが無い）の場合は
    取得をスキップする。URL をコードに直書きしないための仕様。
    """
    targets = [e for e in entries if "/CiscoSecurityAdvisory/" in (e.get("link") or "")]
    if not targets:
        return
    if not cvrf_url_template:
        print(f"    [WARN] urls.yml に cisco_advisory エントリが無いため "
              f"CVSS 取得をスキップします（対象 {len(targets)} 件）")
        return
    print(f"    --- CVSS 取得処理を開始 (対象: {len(targets)} 件) ---")
    for e in targets:
        cvss, color = fetch_cisco_cvss(e.get("link", ""), cvrf_url_template)
        if cvss:
            e["cvss"] = cvss
            e["cvss_color"] = color
            # 生 RSS 本文に CVSS 表記が含まれる場合に備え、この時点でも除去しておく
            # （要約が無効=APIキー未設定でもバッジと二重表示にならないように）。
            e["summary"] = _strip_cvss_mentions(e.get("summary", ""))
            print(f"      {color} CVSS {cvss}: {e['title'][:30]}...")
    print("    --- CVSS 取得完了 ---")

# ===========================================================
# 天気取得（Open-Meteo）/ Weather (Open-Meteo, key-less & free)
# ===========================================================
# 対象地点・API URL は urls.yml の weather エントリに集約する（コードに直書きしない）。
# 読み込みは load_weather_config()。以下は天気コード→表示の変換ロジックのみを持つ。

# WMO weather_code → (絵文字, 日本語ラベル)
# https://open-meteo.com/en/docs（WW コード表）
WMO_WEATHER = {
    0:  ("☀️", "快晴"),
    1:  ("🌤", "晴れ"),
    2:  ("⛅", "晴れ時々くもり"),
    3:  ("☁️", "くもり"),
    45: ("🌫", "霧"),
    48: ("🌫", "霧氷"),
    51: ("🌦", "弱い霧雨"),
    53: ("🌦", "霧雨"),
    55: ("🌦", "強い霧雨"),
    56: ("🌧", "着氷性の霧雨"),
    57: ("🌧", "着氷性の霧雨"),
    61: ("🌦", "小雨"),
    63: ("🌧", "雨"),
    65: ("🌧", "強い雨"),
    66: ("🌧", "着氷性の雨"),
    67: ("🌧", "着氷性の雨"),
    71: ("🌨", "小雪"),
    73: ("❄️", "雪"),
    75: ("❄️", "大雪"),
    77: ("🌨", "細氷"),
    80: ("🌦", "にわか雨"),
    81: ("🌧", "にわか雨"),
    82: ("⛈", "激しいにわか雨"),
    85: ("🌨", "にわか雪"),
    86: ("❄️", "強いにわか雪"),
    95: ("⛈", "雷雨"),
    96: ("⛈", "雹を伴う雷雨"),
    99: ("⛈", "雹を伴う雷雨"),
}


def _wmo_label(code) -> tuple[str, str]:
    """weather_code を (絵文字, 日本語ラベル) に変換。未知コードは汎用表示。"""
    try:
        return WMO_WEATHER.get(int(code), ("🌡", "不明"))
    except (TypeError, ValueError):
        return ("🌡", "不明")


def fetch_weather(api_url: str, label: str, lat: float, lon: float) -> dict | None:
    """
    Open-Meteo から指定地点の「今日・明日」の予報を取得する。
    api_url は urls.yml の weather 設定から渡す（コードに直書きしない）。
    取得失敗時は None を返す（呼び出し側でその地点だけスキップ）。
    Fetches today's & tomorrow's forecast for one location; returns None on failure.
    """
    params = {
        "latitude":  lat,
        "longitude": lon,
        "current":   "temperature_2m,relative_humidity_2m,weather_code",
        "daily":     ("weather_code,temperature_2m_max,temperature_2m_min,"
                      "precipitation_probability_max,relative_humidity_2m_mean"),
        "timezone":  "Asia/Tokyo",
        "forecast_days": 2,
    }
    try:
        resp = requests.get(api_url, params=params, timeout=15, verify=SSL_VERIFY)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"    [WARN] 天気取得失敗（{label}）: {e}")
        return None

    daily = data.get("daily") or {}
    codes = daily.get("weather_code") or []
    tmax  = daily.get("temperature_2m_max") or []
    tmin  = daily.get("temperature_2m_min") or []
    pop   = daily.get("precipitation_probability_max") or []
    hum   = daily.get("relative_humidity_2m_mean") or []

    def _day(i: int) -> dict | None:
        if i >= len(codes):
            return None
        return {
            "code": codes[i],
            "tmax": tmax[i] if i < len(tmax) else None,
            "tmin": tmin[i] if i < len(tmin) else None,
            "pop":  pop[i]  if i < len(pop)  else None,
            "hum":  hum[i]  if i < len(hum)  else None,
        }

    current = data.get("current") or {}
    return {
        "label":           label,
        "current_temp":    current.get("temperature_2m"),
        "current_humidity": current.get("relative_humidity_2m"),
        "today":           _day(0),
        "tomorrow":        _day(1),
    }


def _format_day(day: dict | None) -> str:
    """1日分の予報を「⛅くもり 28°/24° ☔40%」形式に整形。"""
    if not day:
        return "—"
    emoji, name = _wmo_label(day.get("code"))
    tmax, tmin, pop = day.get("tmax"), day.get("tmin"), day.get("pop")
    if tmax is not None and tmin is not None:
        temp = f" {round(tmax)}°/{round(tmin)}°"
    elif tmax is not None:
        temp = f" {round(tmax)}°"
    else:
        temp = ""
    pop_str = f" ☔{round(pop)}%" if pop is not None else ""
    hum = day.get("hum")
    hum_str = f" 💧{round(hum)}%" if hum is not None else ""
    return f"{emoji}{name}{temp}{pop_str}{hum_str}"


def _display_width(text: str) -> int:
    """等幅フォントでの表示幅を数える（全角=2、半角=1）。

    Webex はコードブロック内を等幅で表示するため、桁を揃えるには
    文字数ではなく**表示幅**で数える必要がある。日本語の地名（全角）と
    絵文字はどちらも2桁分を占める。
    """
    width = 0
    for ch in text:
        code = ord(ch)
        if ch == "️":
            # 異体字セレクタ。直前の記号を絵文字表示（2桁）へ格上げする印で、
            # それ自体は字形を持たない。格上げ分の +1 をここで足す。
            width += 1
        elif unicodedata.combining(ch):
            width += 0
        elif unicodedata.east_asian_width(ch) in ("W", "F"):
            width += 2      # 全角（日本語など）と、絵文字の多く
        elif 0x1F300 <= code <= 0x1FAFF:
            width += 2      # east_asian_width が判定できない絵文字
        else:
            width += 1
    return width


def _pad(text: str, width: int) -> str:
    """表示幅が width になるよう右側を空白で埋める（超過時はそのまま返す）。"""
    return text + " " * max(0, width - _display_width(text))


def _day_cell(day: dict | None) -> str:
    """表の1マス分。「🌦 26/22° ☔90% 💧74%」形式。"""
    if not day:
        return "—"
    emoji, _ = _wmo_label(day.get("code"))
    tmax, tmin = day.get("tmax"), day.get("tmin")
    if tmax is not None and tmin is not None:
        temp = f"{round(tmax)}/{round(tmin)}°"
    elif tmax is not None:
        temp = f"{round(tmax)}°"
    else:
        temp = "—"
    pop, hum = day.get("pop"), day.get("hum")
    pop_str = f" ☔{round(pop):>3}%" if pop is not None else ""
    hum_str = f" 💧{round(hum):>3}%" if hum is not None else ""
    return f"{emoji} {temp}{pop_str}{hum_str}"


def format_weather_table(results: list[dict]) -> str:
    """天気を等幅の表に整形する。

    Webex は Markdown の表に対応していないため、コードブロック内で桁を揃えて
    「表に見えるもの」を作る（公式に案内されている回避策）。
    """
    results = [r for r in results if r]
    if not results:
        return ""

    rows = []
    for r in results:
        temp = r.get("current_temp")
        hum = r.get("current_humidity")
        now = "—"
        if temp is not None:
            now = f"{round(temp)}°"
            if hum is not None:
                now += f" {round(hum)}%"
        rows.append([str(r["label"]), now,
                     _day_cell(r.get("today")), _day_cell(r.get("tomorrow"))])

    header = ["地点", "現在", "今日", "明日"]
    widths = [max(_display_width(row[i]) for row in [header, *rows]) for i in range(4)]
    sep = "─" * (sum(widths) + 6)

    lines = ["🌤 **今日・明日の天気**", "```"]
    lines.append("  ".join(_pad(header[i], widths[i]) for i in range(4)).rstrip())
    lines.append(sep)
    for row in rows:
        lines.append("  ".join(_pad(row[i], widths[i]) for i in range(4)).rstrip())
    lines.append("```")
    lines.append("　気温は最高/最低、☔は降水確率、💧は平均湿度です。")
    return "\n".join(lines)


def format_weather_block(results: list[dict]) -> str:
    """天気結果リストを Markdown の箇条書きに整形する。全滅（空）なら空文字を返す。"""
    results = [r for r in results if r]
    if not results:
        return ""
    lines = ["🌤 **今日・明日の天気**"]
    for r in results:
        cur = ""
        if r.get("current_temp") is not None:
            cur = f"（現在 {round(r['current_temp'])}°"
            if r.get("current_humidity") is not None:
                cur += f"・湿度 {round(r['current_humidity'])}%"
            cur += "）"
        lines.append(
            f"- **{r['label']}**{cur}\n"
            f"　　今日: {_format_day(r.get('today'))}　／　明日: {_format_day(r.get('tomorrow'))}"
        )
    return "\n".join(lines)


def format_weather(results: list[dict], style: str = "table") -> str:
    """設定に応じて表形式・箇条書きのどちらかで天気を整形する。"""
    if str(style).strip().lower() == "list":
        return format_weather_block(results)
    return format_weather_table(results)


# ===========================================================
# 日本語ニュース判定・最低件数保証 / Japanese news helpers
# ===========================================================

_JP_CHAR_RE = re.compile(r"[぀-ゟ゠-ヿ]")  # ひらがな(U+3040–309F) + カタカナ(U+30A0–30FF)


def is_japanese_text(text: str) -> bool:
    """
    タイトル等に日本語（ひらがな/カタカナ）が含まれれば True。
    漢字のみ（中国語の可能性）は False とし、日本語記事だけを拾う。
    """
    return bool(_JP_CHAR_RE.search(text or ""))


def pick_japanese(pool: list[dict], exclude_links: set[str], minimum: int) -> list[dict]:
    """
    pool から日本語記事を新着順に最大 minimum 件返す（exclude_links に含む link は除外）。
    ダイジェストの日本ニュース枠と、一般チャンネルの最低件数補充の両方で再利用する。
    """
    if minimum <= 0:
        return []
    candidates = [
        e for e in pool
        if is_japanese_text(e.get("title", "")) and (e.get("link") or "") not in exclude_links
    ]
    candidates.sort(key=lambda x: x["published"], reverse=True)
    return candidates[:minimum]


def classify_region(entry: dict, us_keywords: list[str], other_keywords: list[str]) -> str:
    """
    記事（タイトル＋概要）を地域分類する: "us" / "other" / "japan"。
    US を優先評価し（上限管理のため）、次に米国以外の外国、いずれも無ければ国内。
    既存の _keyword_in_text を再利用（ASCII 短語は語境界、日本語は部分一致）。
    """
    text = f"{entry.get('title', '')} {entry.get('summary', '')}".lower()
    for kw in us_keywords:
        if _keyword_in_text(kw.lower(), text):
            return "us"
    for kw in other_keywords:
        if _keyword_in_text(kw.lower(), text):
            return "other"
    return "japan"


def select_by_region_quota(
    pool: list[dict],
    us_keywords: list[str],
    other_keywords: list[str],
    quota: dict,
) -> dict:
    """
    pool を地域分類し、quota（japan/us/other）に従って各地域を新着順に選ぶ。
    合計が目標（japan+us+other）に満たない分は、japan→other の順に残り候補で補充する。
    US は quota["us"] を上限として超えて補充しない。
    返り値: {"japan": [...], "us": [...], "other": [...]}（各新着順）。
    """
    buckets: dict[str, list[dict]] = {"japan": [], "us": [], "other": []}
    for e in pool:
        buckets[classify_region(e, us_keywords, other_keywords)].append(e)
    for b in buckets.values():
        b.sort(key=lambda x: x["published"], reverse=True)

    total_target = quota["japan"] + quota["us"] + quota["other"]
    selected = {r: list(buckets[r][:quota[r]]) for r in ("japan", "us", "other")}

    def _count() -> int:
        return sum(len(v) for v in selected.values())

    # 不足分の補充（US は上限厳守のため対象外。日本優先）。
    for region in ("japan", "other"):
        if _count() >= total_target:
            break
        for e in buckets[region][quota[region]:]:
            if _count() >= total_target:
                break
            selected[region].append(e)
    return selected


_CAT_ENV_VAR_RE = re.compile(r'\$\{([A-Za-z_][A-Za-z0-9_]*)\}')


def _expand_keyword_env(value: str) -> str | None:
    """
    キーワード文字列内の ${VAR} を環境変数（.env）で展開する。
    - 環境変数が定義されていれば、その値で置換した文字列を返す。
    - 未定義または空文字なら警告を出して None を返す（呼び出し側でスキップ）。
    - ${VAR} を含まない通常キーワードはそのまま返す。

    例: "!${MYFAB_KEYWORD}" + MYFAB_KEYWORD="abc"  → "!abc"

    用途: 公開リポジトリの categories.yml にプロプライエタリな会社名・ブランド名を
    直接書きたくない場合、placeholder を .env で実値に解決できる。
    """
    if '${' not in value:
        return value  # 変数なし、そのまま
    missing = []
    def _repl(m):
        name = m.group(1)
        val = os.environ.get(name)
        if val is None or val == "":
            missing.append(name)
            return ""
        return val
    expanded = _CAT_ENV_VAR_RE.sub(_repl, value)
    if missing:
        print(f"  [WARN] categories.yml: 環境変数 {missing} が未定義のためキーワード '{value}' をスキップ")
        return None
    return expanded


def _load_categories_yaml(path: str) -> dict[str, list[str]]:
    """単一YAMLファイルからカテゴリ定義を読み込み、${VAR} を展開する内部関数。"""
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        return {}
    result: dict[str, list[str]] = {}
    for cat, keywords in data.items():
        if not keywords:
            continue
        # カテゴリ名（キー）の ${VAR} も展開する
        cat_name = str(cat)
        if '${' in cat_name:
            resolved_cat = _expand_keyword_env(cat_name)
            if not resolved_cat:
                continue
            cat_name = resolved_cat
        expanded_kws: list[str] = []
        for kw in keywords:
            kw_str = str(kw)
            resolved = _expand_keyword_env(kw_str)
            if resolved:
                expanded_kws.append(resolved)
        if expanded_kws:
            result[cat_name] = expanded_kws
    return result


def load_categories(path: str = CATEGORIES_FILE) -> dict[str, list[str]]:
    """
    categories.yml からカテゴリキーワード定義を読み込みます。
    キーワード値に ${VAR} が含まれる場合、環境変数（.env）で展開します。

    同ディレクトリに categories-private.yml が存在する場合は、
    そのファイルもロードして既存カテゴリに **追加マージ** します。
    機密キーワード（社名・パートナー名等）を git 管理外に分離する用途。

    Loads category keyword definitions; supports:
      - ${VAR} env-var interpolation
      - Auto-merge from categories-private.yml if present (gitignored overlay)
    """
    if not os.path.exists(path):
        print(f"[ERROR] カテゴリ設定ファイルが見つかりません: {path}")
        sys.exit(1)
    try:
        result = _load_categories_yaml(path)
    except yaml.YAMLError as e:
        print(f"[ERROR] categories.yml の解析に失敗しました: {e}")
        sys.exit(1)

    # 非公開オーバーレイをマージ（存在すれば）
    private_path = os.path.join(os.path.dirname(path), "categories-private.yml")
    if os.path.exists(private_path):
        try:
            private = _load_categories_yaml(private_path)
            merged_cats = []
            new_cats = []
            for cat, kws in private.items():
                if cat in result:
                    result[cat].extend(kws)
                    merged_cats.append(f"{cat}(+{len(kws)})")
                else:
                    result[cat] = kws
                    new_cats.append(f"{cat}({len(kws)})")
            if merged_cats or new_cats:
                print(f"  [INFO] categories-private.yml をマージ: 既存追加={merged_cats}, 新規={new_cats}")
        except yaml.YAMLError as e:
            print(f"  [WARN] categories-private.yml の解析失敗、スキップ: {e}")
    return result


def resolve_categories_from_name(name: str, category_keywords: dict[str, list[str]]) -> list[str]:
    """
    チャンネル名から categories.yml のカテゴリ名を解決します（categories: 省略時に使用）。
    Resolves the category name from a channel name (used when `categories:` is omitted).

    **完全一致のみ**。name が categories.yml のカテゴリ名そのものである場合だけ採用する。
    Exact match only — the channel name must equal a category name in categories.yml.
      例: "セキュリティ"     → ["セキュリティ"]
          "セキュリティニュース" → []  （呼び出し側でスキップし、categories: の明示を促す）

    部分一致を採らないのは、name の一部が偶然カテゴリ名と重なったときに
    意図しないカテゴリが配信される事故を避けるため。
    """
    n = (name or "").strip()
    return [n] if n and n in category_keywords else []


def load_channels(path: str = CHANNELS_FILE) -> list[dict]:
    """
    channels.yml の channels: セクションからマルチチャンネル設定を読み込みます。
    ファイルが無い、または channels: が無い場合は空リスト＝シングルボットモード。
    Loads multi-channel configs from the `channels:` section of channels.yml.
    Returns [] if the file or the section is absent (single-bot mode).

    channels.yml が無い場合は、旧1ファイル構成の config.yml も読む（後方互換）。
    """
    source = path
    if not os.path.exists(source):
        if os.path.exists(LEGACY_CONFIG_FILE):
            source = LEGACY_CONFIG_FILE
        else:
            return []
    try:
        data = _load_yaml(source, os.path.basename(source))
        if not isinstance(data, dict) or "channels" not in data:
            return []  # channels: が無い = シングルボットモード
        channels = data.get("channels") or []
        # 環境変数の展開と必須フィールドの検証 / Expand env vars and validate required fields
        for i, ch in enumerate(channels):
            # チャンネル表示名 (name) も ${VAR} を展開する
            # 例: "${MYFAB_KEYWORD}ニュース" + MYFAB_KEYWORD=abc → "abcニュース"
            # 用途: 公開リポジトリにチャンネル名（=会社名）を露出させない
            if "name" in ch and isinstance(ch["name"], str) and '$' in ch["name"]:
                resolved_name = os.path.expandvars(ch["name"])
                if '$' in resolved_name:
                    print(f"  [WARN] channels.yml channel[{i}]: name '{ch['name']}' に未定義の環境変数があります")
                else:
                    ch["name"] = resolved_name
            # webex_space_id / webex_bot_token の ${VAR} を .env から展開する。
            # 未定義で ${VAR} がそのまま残る場合は「未設定」とみなして空文字にし、
            # 実行時にそのチャンネルだけスキップできるようにする（トークンを後から
            # 用意する運用に対応。例: 新設した Cisco Security Advisories チャンネル）。
            if "webex_space_id" in ch and isinstance(ch["webex_space_id"], str):
                expanded = os.path.expandvars(ch["webex_space_id"])
                if "${" in expanded:
                    print(f"  [WARN] channels.yml channel[{i}] ({ch.get('name','?')}): webex_space_id の環境変数が未解決です → このチャンネルはスキップされます")
                    expanded = ""
                    ch["_skip_reason"] = "webex_space_id 未設定（環境変数が未解決）"
                ch["webex_space_id"] = expanded
            if "webex_bot_token" in ch and isinstance(ch["webex_bot_token"], str):
                expanded_tok = os.path.expandvars(ch["webex_bot_token"])
                if "${" in expanded_tok:
                    expanded_tok = ""
                ch["webex_bot_token"] = expanded_tok
            # categories リスト内の ${VAR} も .env から展開する
            # 例: ["${MYFAB_KEYWORD}"] + .env MYFAB_KEYWORD=my-fab → ["my-fab"]
            # 用途: カテゴリ名を公開リポジトリに露出させたくない場合
            if "categories" in ch and isinstance(ch["categories"], list):
                expanded_cats = []
                for cat in ch["categories"]:
                    cat_str = str(cat)
                    if '$' in cat_str:
                        resolved = os.path.expandvars(cat_str)
                        # 未展開の ${VAR} が残っていれば警告
                        if '$' in resolved:
                            print(f"  [WARN] channels.yml channel[{i}] ({ch.get('name','?')}): categories の '{cat_str}' に未定義の環境変数があります")
                            continue
                        expanded_cats.append(resolved)
                    else:
                        expanded_cats.append(cat_str)
                ch["categories"] = expanded_cats

            # categories を書かなかったチャンネルは、name をそのままカテゴリ名として使う。
            # 例: `- name: セキュリティ` だけで categories: [セキュリティ] と同じ意味になる。
            # （name はこれまでどおり投稿見出し・ダイジェスト・defers_to の識別子でもある）
            # categories: [] と明示した場合は「全カテゴリ / source_groups 専用」の意味なので対象外。
            # name が categories.yml に無い名前だと全記事が通ってしまうため、
            # 実際の採用可否は main 側でカテゴリ定義と突き合わせて判定する。
            if "categories" not in ch:
                ch["categories"] = [str(ch.get("name", "")).strip()]
                ch["_categories_from_name"] = True

            # webex_space_id キー自体が無い場合のみ設定ミスとして停止する。
            # キーはあるが環境変数が未解決（_skip_reason 付き）の場合は、
            # 停止せず実行時にそのチャンネルだけスキップする。
            if "webex_space_id" not in ch:
                print(f"[ERROR] channels.yml の channel[{i}] ({ch.get('name', '?')}) に webex_space_id がありません。")
                sys.exit(1)
        return channels
    except yaml.YAMLError as e:
        print(f"[ERROR] channels.yml の解析に失敗しました: {e}")
        sys.exit(1)


# ===========================================================
# RSS フィード取得 / RSS collection
# ===========================================================

def _parse_entry(entry, source_feed: str = "") -> dict | None:
    """feedparser のエントリを辞書に変換します。日時情報がない場合は None を返します。

    source_feed には、このエントリを取得した RSS フィードの URL を記録する。
    後段のソースベース振り分け（channels.yml の source_feeds）で、記事本文のキーワードで
    はなく「どのフィード由来か」でチャンネルを決めるために使う。
    """
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        published_dt = datetime.datetime(*entry.published_parsed[:6], tzinfo=datetime.timezone.utc)
    elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
        published_dt = datetime.datetime(*entry.updated_parsed[:6], tzinfo=datetime.timezone.utc)
    else:
        return None
    summary = getattr(entry, "summary", "") or ""
    summary_clean = re.sub(r'<[^>]+>', '', summary).replace('\n', ' ').strip()
    if len(summary_clean) > 250:
        summary_clean = summary_clean[:250] + "..."

    return {
        "title":    entry.get("title", "(No title)"),
        "link":     entry.get("link", ""),
        "published": published_dt,
        "summary":  summary_clean,
        "tags":     [t.get("term", "") for t in getattr(entry, "tags", [])],
        "fallback": False,
        "source_feed": source_feed,
    }


def get_recent_rss_entries(
    feed_url: str,
    hours_ago: int = 24,
    fallback_items: int = 0,
) -> list[dict]:
    """
    指定されたRSSフィードから、過去指定時間以内のエントリを取得します。
    hours_ago 以内の記事が0件だった場合、fallback_items > 0 なら最新N件を追加します。
    """
    entries: list[dict] = []
    all_parsed: list[dict] = []
    time_threshold = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours_ago)

    # requests を使って取得
    # 注: ブラウザ風UA（Mozilla/Chrome等）は CISA / community.cisco.com など
    # bot対策のあるサイトで403になるため、フィードリーダ系UAを使用する。
    headers = {
        "User-Agent": "rss-bot/1.0 (+RSS aggregator; feed reader)"
    }

    response = None
    try:
        response = requests.get(feed_url, headers=headers, timeout=15, verify=SSL_VERIFY)
        response.raise_for_status()
    except requests.exceptions.SSLError as e:
        # 証明書チェーン解決失敗 (anthropic.com / huggingface.co 等で発生する Mac Python の既知問題)
        # → verify=False で1度だけリトライ。警告は表示するが、フィード取得は継続する。
        if SSL_VERIFY:
            print(f"  [WARN] SSL証明書検証に失敗。verify=Falseで再試行: {feed_url}")
            try:
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                response = requests.get(feed_url, headers=headers, timeout=15, verify=False)
                response.raise_for_status()
            except Exception as e2:
                print(f"  [ERROR] SSL fallback も失敗: {feed_url} → {e2}")
                return entries
        else:
            print(f"  [ERROR] SSLエラー: {feed_url} → {e}")
            return entries
    except requests.exceptions.RequestException as e:
        print(f"  [ERROR] ネットワーク接続エラー: {feed_url} → {e}")
        return entries

    try:
        # 取得したXML/テキストを feedparser に渡す
        feed = feedparser.parse(response.content)

        if feed.bozo and feed.entries == []:
            print(f"  [WARN] フィード解析エラー: {feed_url} → {feed.bozo_exception}")
            return entries

        for entry in feed.entries:
            parsed = _parse_entry(entry, source_feed=feed_url)
            if parsed is None:
                continue
            all_parsed.append(parsed)
            if parsed["published"] >= time_threshold:
                entries.append(parsed)
    except Exception as e:
        print(f"  [ERROR] フィード処理エラー: {feed_url} → {e}")
        return entries

    return entries


def collect_all_entries(rss_urls: list[str], hours_ago: int, fallback_items: int) -> list[dict]:
    """全RSSフィードから記事を収集し、重複排除を行います。 / Collect entries from all RSS feeds and deduplicate.

    取得はホスト別にグループ化し、ThreadPoolExecutor でホスト単位のワーカーを
    並列実行する（max_workers=12）。各ワーカーは自ホストの URL を直列処理し、
    リクエスト間に time.sleep(1.0) を挟む（同一ホストへの礼儀）。
    """
    # ホスト別にグループ化 / Group URLs by host (netloc)
    host_groups: dict[str, list[str]] = {}
    for url in rss_urls:
        host = urlparse(url).netloc
        host_groups.setdefault(host, []).append(url)

    def _fetch_host(urls: list[str]) -> list[dict]:
        """1ホスト分の URL を直列取得する（別スレッドで実行）。"""
        results: list[dict] = []
        for i, url in enumerate(urls):
            # フォールバックをやめるため、get_recent_rss_entries には fallback_items=0 を渡します
            entries = get_recent_rss_entries(url, hours_ago=hours_ago, fallback_items=0)
            # スレッド間のログのインターリーブを防ぐため、URL と件数を1回の print で出力
            print(f"  取得: {url} → {len(entries)} 件")
            results.extend(entries)
            if i < len(urls) - 1:
                time.sleep(1.0)  # 同一ホストへの連続リクエスト間隔を維持
        return results

    all_entries: list[dict] = []
    with ThreadPoolExecutor(max_workers=12) as executor:
        for host_results in executor.map(_fetch_host, host_groups.values()):
            all_entries.extend(host_results)

    print(f"  [INFO] 収集完了: {len(all_entries)} 件（重複排除前 / {len(host_groups)} ホスト）")

    # 重複排除 / Deduplicate
    # 日本語ニュースは SequenceMatcher（文字単位）だけでは類似度が低く出る傾向があるため、
    # 「漢字bigram Jaccard」「漢字bigram Overlap係数」を併用するハイブリッド判定を採用する。
    #
    # 例: 「中国山西省の炭鉱で爆発事故 82人死亡(国営メディア)」 と
    #     「中国炭鉱のガス爆発、死者82人に(CNN)」
    #     → SequenceMatcher は 0.50 程度（文字並びが揺らぐと低くなる）
    #     → 漢字bigram Jaccard 0.25 / Overlap 0.50 で同一事件を判定できる
    #
    # 重複判定の4段階:
    #   1) SequenceMatcher >= 0.85                       → タイトルがほぼ同一（言語問わず確実）
    #   2) 漢字bigram Jaccard >= 0.20                    → 日本語の同一事件クラスタリング
    #   3) 漢字bigram Overlap >= 0.50 かつ共通bigram>=5 → 長短タイトル対称性問題に対応
    #   4) SequenceMatcher >= 0.55 かつ summary類似 >= 0.55 → リライト記事
    #
    # 残すべき記事: 公開日時が新しい方を優先（同時刻なら情報量の多い方）
    import difflib
    SEQ_HIGH = 0.85
    KANJI_JACCARD_MIN = 0.20
    KANJI_OVERLAP_MIN = 0.50
    KANJI_INTER_MIN = 5
    SEQ_MID = 0.55
    SUMMARY_MID = 0.55
    # 英語タイトル向け word Jaccard（漢字bigramと対称の判定軸）
    WORD_JACCARD_MIN = 0.5
    WORD_MIN_TOKENS = 4

    # 英語トークンから除外する高頻度語（内容語のみで類似度を測るため）
    STOPWORDS = {
        "the", "and", "for", "with", "from", "that", "this", "are", "was", "has",
        "have", "its", "their", "after", "over", "into", "new", "how", "why", "what",
        "when", "will", "says", "said", "can", "could", "more", "than", "been", "were",
        "not", "but", "you", "your", "off", "out", "about", "against", "between",
        "during", "under", "amid", "per", "via", "vs", "amp",
    }

    _KANJI_RE = re.compile(r'[一-龯]')
    # 媒体名サフィックス/プレフィックス除去: "(共同通信)" / " - 朝日新聞" / "【速報】"
    _MEDIA_RE = re.compile(
        r'\s*[\(（][^)）]{1,15}[\)）]\s*$'   # 末尾の (媒体名)
        r'|\s*[-—–]\s*[^-—–]{1,15}$'        # 末尾の " - 媒体名"
        r'|^[【\[][^】\]]{1,10}[】\]]\s*'    # 先頭の 【速報】
    )

    def _normalize_title(title: str) -> str:
        prev = None
        norm = title
        # 複数回適用（"(共同通信)" の後に "【速報】" が残るケースなど）
        while prev != norm:
            prev = norm
            norm = _MEDIA_RE.sub('', norm).strip()
        return norm

    def _kanji_bigrams(text: str) -> set:
        kanji_only = ''.join(_KANJI_RE.findall(text))
        if len(kanji_only) < 4:
            return set()
        return set(kanji_only[i:i+2] for i in range(len(kanji_only) - 1))

    def _english_tokens(norm_title: str) -> set:
        """正規化済み小文字タイトルから、長さ3以上・ストップワード以外の英数トークン集合を作る。"""
        toks = re.findall(r'[a-z0-9]+', norm_title)
        return {t for t in toks if len(t) >= 3 and t not in STOPWORDS}

    # 前計算: 各エントリについて (正規化タイトル小文字, 漢字bigram集合, 英語トークン集合,
    # 概要小文字, 情報量=タイトル+概要の文字数) を1回だけ計算しておく。
    # dedupe の全ペア比較のたびに再計算していた無駄を省く。
    precomputed: list[tuple] = []
    for entry in all_entries:
        norm = _normalize_title(entry['title'].lower().strip())
        precomputed.append((
            norm,
            _kanji_bigrams(norm),
            _english_tokens(norm),
            entry['summary'].lower().strip(),
            len(entry['title']) + len(entry['summary']),
        ))

    def _is_duplicate(pa: tuple, pb: tuple) -> bool:
        norm_a, bg_a, tok_a, s_a, _ = pa
        norm_b, bg_b, tok_b, s_b, _ = pb
        seq = difflib.SequenceMatcher(None, norm_a, norm_b).ratio()
        if seq >= SEQ_HIGH:
            return True
        # 漢字bigram の重なり指標
        if bg_a and bg_b:
            inter = len(bg_a & bg_b)
            union = len(bg_a | bg_b)
            smaller = min(len(bg_a), len(bg_b))
            jaccard = inter / union if union else 0
            overlap = inter / smaller if smaller else 0
            if jaccard >= KANJI_JACCARD_MIN:
                return True
            if overlap >= KANJI_OVERLAP_MIN and inter >= KANJI_INTER_MIN:
                return True
        # 英語 word Jaccard（漢字bigramブロックと対称の位置）
        # 両タイトルの英語トークンがそれぞれ4語以上あるときのみ評価
        if len(tok_a) >= WORD_MIN_TOKENS and len(tok_b) >= WORD_MIN_TOKENS:
            w_inter = len(tok_a & tok_b)
            w_union = len(tok_a | tok_b)
            w_jaccard = w_inter / w_union if w_union else 0
            if w_jaccard >= WORD_JACCARD_MIN:
                return True
        # フォールバック: タイトル中程度 + 概要も類似
        if seq >= SEQ_MID and s_a and s_b:
            summary_ratio = difflib.SequenceMatcher(None, s_a, s_b).ratio()
            if summary_ratio >= SUMMARY_MID:
                return True
        return False

    deduped_entries: list[dict] = []
    deduped_pre: list[tuple] = []
    for entry, pre in zip(all_entries, precomputed):
        is_duplicate = False
        len_a = pre[4]

        for idx, existing_pre in enumerate(deduped_pre):
            if _is_duplicate(pre, existing_pre):
                is_duplicate = True
                existing = deduped_entries[idx]
                # 残すべき記事の選択基準:
                #  ① 公開日時が新しい方を優先（最新情報を採用）
                #  ② 同時刻なら情報量（タイトル+概要の文字数）が多い方を採用
                existing_pub = existing.get('published')
                entry_pub = entry.get('published')
                len_b = existing_pre[4]
                replace = False
                if entry_pub and existing_pub and entry_pub != existing_pub:
                    replace = entry_pub > existing_pub
                else:
                    replace = len_a > len_b
                if replace:
                    deduped_entries[idx] = entry
                    deduped_pre[idx] = pre
                break

        if not is_duplicate:
            deduped_entries.append(entry)
            deduped_pre.append(pre)

    if len(all_entries) != len(deduped_entries):
        print(f"  [INFO] 重複排除完了: {len(all_entries)} 件 → {len(deduped_entries)} 件")

    return deduped_entries


# ===========================================================
# フィルタリング / Filtering
# ===========================================================

_NON_ASCII_RE = re.compile(r'[^\x00-\x7f]')

def _keyword_in_text(kw_lower: str, search_text: str) -> bool:
    """
    キーワードがテキスト中に出現するか判定する。

    短い英数字キーワード（5文字以下、ASCII のみ）は **単語境界(\\b)** を使った
    正規表現マッチに切り替える。これにより、`lan` が "p**lan**" や "**lan**guage"、
    `wan` が "t**wan**g"、`sse` が "addre**sse**s" などの無関係な英単語の部分文字列に
    誤マッチする問題を防ぐ。

    日本語/中国語/記号を含むキーワード、および 6 文字以上の英数字キーワードは
    従来通りの部分文字列マッチ（substring match）を使う（日本語は単語境界の概念が
    希薄であり、長い語は偶然の部分一致リスクが低いため）。
    """
    if _NON_ASCII_RE.search(kw_lower):
        return kw_lower in search_text
    if len(kw_lower) <= 5:
        return re.search(r'\b' + re.escape(kw_lower) + r'\b', search_text) is not None
    return kw_lower in search_text


def filter_by_category(
    entries: list[dict],
    categories: list[str] | None,
    category_keywords: dict[str, list[str]],
    min_score: int = 4,
) -> list[dict]:
    """
    カテゴリキーワードでエントリをスコアリング方式でフィルタリングします。
    Filters entries by category using a weighted-score scheme.

    スコア計算 / Score:
      - 必須キーワード (! プレフィックス) のマッチ = 3点 / 件
      - 通常キーワードのマッチ                    = 1点 / 件

    合格条件 / Pass criteria:
      1. 必須キーワードが定義されている場合、少なくとも1つは必須語にマッチしていること。
      2. 合計スコアが min_score（デフォルト 4）以上であること。

    最低ラインの例 / Minimum-pass examples:
      - 必須1 + 通常1 = 4点 → 合格（最小）
      - 必須2          = 6点 → 合格
      - 通常4          = 4点 → 合格（必須語が定義されていないカテゴリ）
      - 必須1 のみ     = 3点 → 不合格（必須語だけでは通さない）
      - 通常3 のみ     = 3点 → 不合格
    """
    if not categories:
        return entries

    must_keywords: list[str] = []
    normal_keywords: list[str] = []

    for cat in categories:
        if cat in category_keywords:
            for kw in category_keywords[cat]:
                if kw.startswith("!"):
                    must_keywords.append(kw[1:]) # `!` を除外した文字列を登録
                else:
                    normal_keywords.append(kw)

    if not must_keywords and not normal_keywords:
        return entries

    # URL深度マッチを許可するキーワード（リスト中の文字列がURLに含まれていれば
    # search_text にURLを連結する）。
    # 設計理由:
    #   - blogs.cisco.com / community.cisco.com 等の記事はタイトルに
    #     "Cisco" を含まないことが多く、URLで補完する価値がある。
    #   - 一方、news.google.com / news.yahoo.co.jp 等のアグリゲーター
    #     リダイレクトURLは "google" 等の一般語に誤マッチし、
    #     my-fab (例: 「元my-fabOL」のスポーツ記事) など他カテゴリを汚染する。
    #   - そのため URL は **明確なソースドメインを含む場合のみ** 評価対象に含める。
    URL_INCLUDE_KEYWORDS = ("cisco",)

    filtered = []
    for entry in entries:
        link_lower = entry.get("link", "").lower()
        search_parts = [
            entry["title"].lower(),
            entry["summary"].lower(),
            " ".join(entry["tags"]).lower(),
        ]
        if any(kw in link_lower for kw in URL_INCLUDE_KEYWORDS):
            search_parts.append(link_lower)
        search_text = " ".join(search_parts)

        must_matched_count = sum(1 for kw in must_keywords if _keyword_in_text(kw.lower(), search_text))
        normal_matched_count = sum(1 for kw in normal_keywords if _keyword_in_text(kw.lower(), search_text))
        # スコアリング: 必須語×3点、通常語×1点
        score = must_matched_count * 3 + normal_matched_count * 1

        # 条件1: 必須キーワード定義あり ⇒ 少なくとも1つにマッチしていること
        if must_keywords and must_matched_count == 0:
            continue

        # 条件2: スコアが min_score 以上であること
        if score >= min_score:
            # 配信時にスコア優先抽出するため、entry にスコアを記録。
            # entry は複数チャンネル間で共有される dict なので、直接書き込むと
            # 後からフィルタした別カテゴリのスコアで上書きされてしまう。
            # 浅いコピーを作り、そのコピーにのみ _score を持たせる。
            e2 = dict(entry)
            e2["_score"] = score
            filtered.append(e2)

    return filtered


def filter_by_source_feeds(entries: list[dict], source_feeds: list[str]) -> list[dict]:
    """
    エントリを「取得元 RSS フィードの URL」で絞り込みます。
    Filters entries by the RSS feed URL they were collected from.

    キーワードマッチ（filter_by_category）とは独立した振り分け軸。
    「Cisco Security Advisories」のように、特定フィード由来の記事を丸ごと
    専用チャンネルへ送りたい場合に使う。
    """
    feeds = {str(u).strip() for u in source_feeds if u}
    if not feeds:
        return []
    return [e for e in entries if e.get("source_feed", "") in feeds]


def stratified_pick(entries: list[dict], n: int = 15) -> list[dict]:
    """
    スコア階層化優先抽出:
    高スコアから順に採用していき、合計が n を超える階層で
    その階層内でランダム抽出して n 件に絞る。

    例: entries = [score=12×2, score=10×5, score=9×12, score=4×131]
        n = 15
        → score=12 全採用 (2件)
        → score=10 全採用 (累計 7件)
        → score=9 で累計が 19 になるため、不足分 8件を score=9 群からランダム抽出
        → score=4 群は評価しない（既に 15件確保したため）

    score < 4 は filter_by_category で既に除外済み。
    """
    if len(entries) <= n:
        return entries

    # スコアでグループ化
    by_score: dict[int, list[dict]] = {}
    for e in entries:
        s = e.get("_score", 0)
        by_score.setdefault(s, []).append(e)

    result: list[dict] = []
    # 高スコアから順に処理
    for score in sorted(by_score.keys(), reverse=True):
        group = by_score[score]
        remaining = n - len(result)
        if remaining <= 0:
            break
        if len(group) <= remaining:
            # この階層は全件採用しても枠が余る
            result.extend(group)
        else:
            # この階層で枠が埋まる → 階層内でランダム抽出
            result.extend(random.sample(group, remaining))
            break

    return result


def rerank_with_llm(
    channel_name: str,
    cat_label: str,
    entries: list[dict],
    n: int,
    api_key: str,
    model: str,
) -> list[dict] | None:
    """
    LLM（Claude）で候補記事を重要度順に再ランクし、上位 n 件を返します。

    stratified_pick の置き換え（ランダム抽出ではなく内容ベースで選ぶ）。
    API エラー・パース失敗・空配列時は None を返し、呼び出し側で
    stratified_pick にフォールバックできるようにする（例外は外に漏らさない）。
    """
    if not api_key or not entries:
        return None

    # 候補カット: スコア降順 → published 降順で上位40件に絞る
    _epoch = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)
    candidates = sorted(
        entries,
        key=lambda e: (e.get("_score", 0), e.get("published") or _epoch),
        reverse=True,
    )[:40]

    # 候補一覧をプロンプト用に整形
    jst = datetime.timezone(datetime.timedelta(hours=9))
    lines: list[str] = []
    for i, e in enumerate(candidates):
        pub = e.get("published")
        date_str = pub.astimezone(jst).strftime('%Y-%m-%d %H:%M') if pub else "?"
        domain = urlparse(e.get("link", "")).netloc
        summary = (e.get("summary") or "")[:120]
        lines.append(f"[{i}] {e.get('title', '')} | {summary} | {date_str} JST | {domain}")
    candidate_block = "\n".join(lines)

    prompt = (
        "あなたはニュースキュレーターです。以下の読者に向けて、候補記事から重要な記事を選びます。\n"
        "読者プロフィール: 日本の Cisco Systems の SE（ネットワーク／セキュリティ／AI の実務者）。\n"
        f"配信チャンネル: {channel_name}\n"
        f"カテゴリ: {cat_label}\n\n"
        f"候補一覧（インデックス / タイトル / 概要先頭120字 / 公開日時(JST) / ドメイン）:\n"
        f"{candidate_block}\n\n"
        f"重要度順に上位 {n} 件のインデックス番号だけを JSON 配列で出力してください（例: [3,0,12]）。\n"
        "説明文・コードブロックは禁止。\n"
        "基準: ①読者の業務への関連度 ②影響の大きさ・新規性 ③同種話題ばかりにならない多様性。"
    )

    try:
        text = call_llm(prompt, api_key, model, max_tokens=200)
    except Exception as e:
        print(f"    [WARN] LLM再ランクのAPI呼び出しに失敗（{LLM_PROVIDER}）: {e}")
        return None

    # 応答テキストから最初の JSON 配列を抽出
    m = re.search(r'\[[\d,\s]*\]', text)
    if not m:
        return None
    try:
        raw_indices = json.loads(m.group(0))
    except Exception:
        return None
    if not isinstance(raw_indices, list) or not raw_indices:
        return None

    # 範囲外・重複インデックスを除去
    picked: list[int] = []
    seen: set[int] = set()
    for idx in raw_indices:
        if isinstance(idx, int) and 0 <= idx < len(candidates) and idx not in seen:
            picked.append(idx)
            seen.add(idx)

    if not picked:
        return None

    # n 件に満たなければ候補のスコア降順（=candidates の並び）から不足分を補完
    if len(picked) < n:
        for i in range(len(candidates)):
            if len(picked) >= n:
                break
            if i not in seen:
                picked.append(i)
                seen.add(i)

    return [candidates[i] for i in picked[:n]]


# ===========================================================
# Webex 送信 / Webex messaging
# ===========================================================

def send_webex_message(room_id: str, message_text: str, bot_token: str) -> bool:
    """
    Webexスペースにメッセージを送信します。
    Sends a Markdown message to the specified Webex space.
    """
    url = get_endpoint("webex", "messages")
    headers = {
        "Authorization": f"Bearer {bot_token}",
        "Content-Type":  "application/json",
    }
    payload = {"roomId": room_id, "markdown": message_text}

    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=15, verify=SSL_VERIFY)
        response.raise_for_status()
        print("  [OK] Webexメッセージを送信しました。")
        return True
    except requests.exceptions.RequestException as e:
        body = response.text if "response" in dir() else "N/A"
        print(f"  [ERROR] Webexメッセージ送信失敗: {e} / レスポンス: {body}")
        return False


def build_and_send(
    entries: list[dict],
    header: str,
    space_id: str,
    bot_token: str,
    dry_run: bool = False,
    max_chars: int = 6000,
    morning_message: str = "",
) -> None:
    """
    エントリをMarkdown形式でメッセージ化し、最大文字数を超えた場合は分割して送信します。
    Formats entries as Markdown and sends (or prints in dry-run), splitting if needed.
    """
    if not entries:
        return

    message_parts = [header]

    for entry in entries:
        pub_jst = entry["published"].astimezone(datetime.timezone(datetime.timedelta(hours=9)))
        fallback_tag = " 📌*最新記事*" if entry.get("fallback") else ""
        cvss_tag = f"　{entry.get('cvss_color') or '🔺'} CVSS {entry['cvss']}" if entry.get("cvss") else ""
        summary_line = f"  📝 {entry['summary']}\n" if entry.get("summary") else ""
        date_str = pub_jst.strftime('%Y-%m-%d %H:%M')

        # タイトルと日付を同一行に表示（要約は次行）。Cisco Advisory は CVSS を危険度カラーで併記。
        line = (
            f"\n- [{entry['title']}]({entry['link']})　（📅 {date_str} JST）{cvss_tag}{fallback_tag}\n"
            f"{summary_line}"
        )
        if len("\n".join(message_parts)) + len(line) > max_chars:
            if dry_run:
                print("\n".join(message_parts))
                print("--- (分割) ---")
            else:
                send_webex_message(space_id, "\n".join(message_parts), bot_token)
            message_parts = ["**(続き / Continued)**"]
            time.sleep(2)
        message_parts.append(line)

    final = "\n".join(message_parts)
    if final.strip() not in ("**(続き / Continued)**", header.strip()):
        if morning_message:
            final += f"\n\n{morning_message}"
        if dry_run:
            print(final)
        else:
            send_webex_message(space_id, final, bot_token)


# ===========================================================
# チャンネル処理 / Channel processing
# ===========================================================

def process_channel(
    channel_name: str,
    space_id: str,
    bot_token: str,
    categories: list[str] | None,
    all_entries: list[dict],
    category_keywords: dict[str, list[str]],
    hours_ago: int,
    now_jst: datetime.datetime,
    dry_run: bool,
    anthropic_api_key: str = "",
    summarize_cache: dict = None,
    anthropic_model: str = "claude-3-haiku-20240307",
    morning_message: str = "",
    pre_filtered: list[dict] | None = None,
    cat_label_override: str | None = None,
    digest_collector: dict[str, list[dict]] | None = None,
    cvrf_url_template: str = "",
    max_items: int = MAX_ITEMS_DEFAULT,
) -> None:
    """
    1チャンネル分のフィルタリングと送信を処理します。
    Processes filtering and sending for one channel.

    pre_filtered が指定された場合は再フィルタを行わず、その結果を採用する
    （チャンネル間の再配分処理後にメインから呼ばれる用途）。

    cat_label_override が指定された場合は、ヘッダーのカテゴリ表示に使う。
    source_feeds 専用チャンネル（categories なし）で「全カテゴリ」と誤表示させない用途。
    """
    cat_label = cat_label_override or ("、".join(categories) if categories else "全カテゴリ")
    print(f"\n  ▶ チャンネル: {channel_name} ({cat_label})")

    if pre_filtered is not None:
        filtered = list(pre_filtered)
    else:
        filtered = filter_by_category(all_entries, categories, category_keywords)

    if len(filtered) > max_items:
        # スコア降順で集計（ログ用）
        from collections import Counter
        score_dist = Counter(e.get("_score", 0) for e in filtered)
        dist_str = " / ".join(f"score={s}:{c}" for s, c in sorted(score_dist.items(), reverse=True))
        # まず LLM 再ランクを試み、失敗（None）時のみ従来の階層化抽出にフォールバック。
        reranked = None
        if anthropic_api_key:
            reranked = rerank_with_llm(
                channel_name, cat_label, filtered, max_items,
                anthropic_api_key, ANTHROPIC_RERANK_MODEL,
            )
        if reranked is not None:
            filtered = reranked
            print(f"    LLM再ランク採用 ({ANTHROPIC_RERANK_MODEL})")
        else:
            if anthropic_api_key:
                print("    LLM再ランク失敗 → stratified_pick にフォールバック")
            # 高スコア優先で上限まで絞る（同階層内のみランダム抽出）
            filtered = stratified_pick(filtered, max_items)
        kept_dist = Counter(e.get("_score", 0) for e in filtered)
        kept_str = " / ".join(f"score={s}:{c}" for s, c in sorted(kept_dist.items(), reverse=True))
        print(f"    {max_items}件超 → 絞り込み後: {len(filtered)} 件")
        print(f"      抽出前 ({sum(score_dist.values())}件): {dist_str}")
        print(f"      抽出後 ({sum(kept_dist.values())}件): {kept_str}")
    else:
        print(f"    {max_items}件以下（再ランク不要）: {len(filtered)} 件")

    filtered.sort(key=lambda x: x["published"], reverse=True)

    # Cisco Security Advisory は CVSS スコアを取得して付与（要約より前に実行）。
    # 非 advisory エントリはネットワーク取得を行わないため他チャンネルには無影響。
    enrich_cisco_cvss_in_place(filtered, cvrf_url_template)

    # Claudeによる要約を実行 (APIキーが設定されている場合のみ)
    if anthropic_api_key and summarize_cache is not None:
        summarize_entries_in_place(filtered, anthropic_api_key, summarize_cache, model=anthropic_model)

    print(f"    送信対象: {len(filtered)} 件")

    # デイリーダイジェスト用に「実際に送る記事」を記録する（dry-run でも記録＝プレビュー可能）。
    # 見出しのみ採用のため要約有無に依存しない。0件チャンネルは記録しない。
    if digest_collector is not None and filtered:
        digest_collector[channel_name] = list(filtered)

    # 表示名を categories から生成した場合、見出しとカテゴリ表示が同じ文字列になる。
    # その場合は「🏷 カテゴリ」を省いて重複表示を避ける。
    meta = f"✅ {len(filtered)} 件　｜　⏱ {now_jst.strftime('%Y-%m-%d %H:%M')} JST"
    if cat_label != channel_name:
        meta = f"🏷 カテゴリ: **{cat_label}**　｜　" + meta
    header = (
        f"🗞️ **{channel_name}**\n"
        f"{meta}\n"
        f"{'─' * 40}"
    )

    if not filtered:
        # 当日に該当ニュースが無いスペースには、空通知も含め一切投稿しない。
        # （以前は「該当ニュースはありませんでした」と投稿していたが、これを廃止）
        print(f"    該当ニュース 0 件 → {channel_name} には投稿しません（スキップ）")
        return

    if dry_run:
        print(f"\n{'='*50}")
        print(header)
        for e in filtered:
            pub_jst = e["published"].astimezone(datetime.timezone(datetime.timedelta(hours=9)))
            fb = " [📌最新記事]" if e.get("fallback") else ""
            cvss_tag = f"　{e.get('cvss_color') or '🔺'} CVSS {e['cvss']}" if e.get("cvss") else ""
            date_str = pub_jst.strftime('%Y-%m-%d %H:%M')
            # タイトルと日付を同一行（Cisco Advisory は CVSS を危険度カラーで併記）
            print(f"  - {e['title']}　（📅 {date_str} JST）{cvss_tag}{fb}")
            if e.get("summary"):
                print(f"    📝 {e['summary']}")
            print(f"    🔗 {e['link']}")
        if morning_message:
            print(f"\n{morning_message}")
        print(f"{'='*50}")
    else:
        build_and_send(filtered, header, space_id, bot_token, dry_run=False, morning_message=morning_message)


# ===========================================================
# デイリーダイジェスト（天気＋投稿ニュース集約）/ Daily digest
# ===========================================================

DIGEST_TOP_N = 5          # ダイジェストで各チャンネルに載せる見出しの上限
DIGEST_MIN_JAPANESE = 5   # 「日本のニュース」枠の最低件数

# ダイジェストに載せられる枠。channels.yml の digest_blocks で選ぶ。
DIGEST_BLOCK_NAMES = ("weather", "channels", "jiji")
# 既定で出す枠と順番。時事（jiji）は既定では出さない（必要なら digest_blocks に足す）。
DEFAULT_DIGEST_BLOCKS = ["weather", "channels"]
# 天気の見せ方。table = コードブロックの表 / list = 箇条書き。
DEFAULT_WEATHER_STYLE = "table"


def _digest_entry_line(e: dict) -> str:
    """ダイジェスト1行（見出し＋リンク＋日付）。要約は載せず簡潔に。"""
    date = e["published"].astimezone(
        datetime.timezone(datetime.timedelta(hours=9))
    ).strftime('%m/%d %H:%M')
    return f"- [{e['title']}]({e['link']})　（📅 {date} JST）"


def build_jiji_section(
    all_entries: list[dict],
    category_keywords: dict[str, list[str]],
    regions_cfg: dict,
    exclude_links: set[str],
) -> str:
    """
    時事ダイジェスト（地域バランス）ブロックを生成する。

    候補プール = 「一般（時事）カテゴリにマッチする記事」かつ「既掲載でない」記事。
    → 「一般」の必須語ゲート（災害/事件/政治/社会 等）で時事のみを positively 抽出する。
      これにより、ファッション・ペット・美容・芸能などのライフスタイル記事は自然に除外され、
      テック（AI/セキュリティ 等）・経済も別カテゴリのため入らない（＝ユーザー指定「一般・世の中のみ」）。
    地域別クオータ（日本/米国/その他）で新着順に選び、不足は日本→その他で補充する。
    """
    general_pool = [
        e for e in filter_by_category(all_entries, ["一般"], category_keywords)
        if (e.get("link") or "") not in exclude_links
    ]

    selected = select_by_region_quota(
        general_pool,
        regions_cfg["us_keywords"],
        regions_cfg["other_keywords"],
        regions_cfg["quota"],
    )
    nj, nu, no = len(selected["japan"]), len(selected["us"]), len(selected["other"])
    if nj + nu + no == 0:
        return ""

    lines = [f"\n📰 **時事ダイジェスト**（🇯🇵日本 {nj}・🇺🇸米国 {nu}・🌐その他 {no}）"]
    for key, label in (("japan", "🇯🇵 日本"), ("us", "🇺🇸 米国"), ("other", "🌐 その他")):
        items = selected[key]
        if not items:
            continue
        lines.append(f"\n**{label}**")
        for e in items:
            lines.append(_digest_entry_line(e))
    return "\n".join(lines)


def build_digest_message(
    weather_results: list[dict],
    digest_collector: dict[str, list[dict]],
    all_entries: list[dict],
    now_jst: datetime.datetime,
    top_n: int = DIGEST_TOP_N,
    min_japanese: int = DIGEST_MIN_JAPANESE,
    category_keywords: dict[str, list[str]] | None = None,
    regions_cfg: dict | None = None,
    blocks: list[str] | None = None,
    weather_style: str = DEFAULT_WEATHER_STYLE,
) -> str:
    """
    ダイジェストのメッセージを組み立てる。

    blocks に載せる枠を「出す順」で指定する（既定は DEFAULT_DIGEST_BLOCKS）。
      weather  … 今日・明日の天気（weather_style で表形式／箇条書きを切替）
      channels … 各チャンネルが投稿した記事のまとめ
      jiji     … 時事ダイジェスト（regions.yml の地域バランス。既定では出さない）

    jiji は regions_cfg と category_keywords が揃っていれば地域バランス型、
    無ければ従来の「🇯🇵 日本のニュース（最低 min_japanese 件）」枠になる（後方互換）。
    """
    wanted = [b for b in (blocks if blocks is not None else DEFAULT_DIGEST_BLOCKS)
              if b in DIGEST_BLOCK_NAMES]
    weekday = "月火水木金土日"[now_jst.weekday()]
    parts = [
        f"🌅 **デイリーブリーフィング**　{now_jst.strftime('%Y-%m-%d')} ({weekday})",
        "─" * 40,
    ]
    # 既にダイジェストへ載せた link（時事枠の重複回避に使う）
    shown_links: set[str] = set()

    for name in wanted:
        if name == "weather":
            block = format_weather(weather_results, weather_style)
            if block:
                parts.append(block)
                parts.append("─" * 40)
        elif name == "channels":
            parts.append(_digest_channels_section(digest_collector, top_n, shown_links))
        elif name == "jiji":
            parts.append(_digest_jiji_section(
                all_entries, category_keywords, regions_cfg, shown_links, min_japanese))

    return "\n".join(p for p in parts if p)


def max_items_of(channel: dict) -> int:
    """チャンネル設定から1回に投稿する記事数の上限を返す。

    未指定なら既定（MAX_ITEMS_DEFAULT）。1未満や上限超え、数値でない値は
    既定に戻して知らせる（黙って想定外の件数で配信しないため）。
    """
    raw = channel.get("max_items")
    if raw is None:
        return MAX_ITEMS_DEFAULT
    try:
        value = int(raw)
    except (TypeError, ValueError):
        print(f"  [WARN] {channel.get('name')}: max_items は数字で書いてください"
              f"（'{raw}'）。既定の {MAX_ITEMS_DEFAULT} 件を使います")
        return MAX_ITEMS_DEFAULT
    if not 1 <= value <= MAX_ITEMS_LIMIT:
        print(f"  [WARN] {channel.get('name')}: max_items は 1〜{MAX_ITEMS_LIMIT} の範囲で"
              f"書いてください（{value}）。既定の {MAX_ITEMS_DEFAULT} 件を使います")
        return MAX_ITEMS_DEFAULT
    return value


def digest_blocks_of(channel: dict) -> list[str]:
    """チャンネル設定から、ダイジェストに載せる枠を「出す順」で返す。

    digest_blocks を書いていなければ既定（天気＋チャンネルまとめ）。
    知らない名前は無視し、その旨を知らせる（設定ミスに気付けるように）。
    """
    raw = channel.get("digest_blocks")
    if raw is None:
        return list(DEFAULT_DIGEST_BLOCKS)
    if not isinstance(raw, list):
        print(f"  [WARN] {channel.get('name')}: digest_blocks はリストで書いてください。既定を使います")
        return list(DEFAULT_DIGEST_BLOCKS)
    blocks, unknown = [], []
    for item in raw:
        name = str(item).strip().lower()
        if name in DIGEST_BLOCK_NAMES:
            blocks.append(name)
        elif name:
            unknown.append(name)
    if unknown:
        print(f"  [WARN] {channel.get('name')}: 知らない digest_blocks を無視しました: "
              f"{'、'.join(unknown)}（使えるのは {'、'.join(DIGEST_BLOCK_NAMES)}）")
    return blocks


def _digest_channels_section(digest_collector: dict[str, list[dict]],
                             top_n: int, shown_links: set[str]) -> str:
    """各チャンネルが投稿した記事のまとめ。載せた link は shown_links に足す。"""
    parts = ["🗞 **本日のニュースダイジェスト**"]
    any_channel = False
    for ch_name, entries in digest_collector.items():
        if not entries:
            continue
        any_channel = True
        block = [f"\n**▶ {ch_name}**（{len(entries)}件）"]
        for e in entries[:top_n]:
            block.append(_digest_entry_line(e))
            link = e.get("link") or ""
            if link:
                shown_links.add(link)
        if len(entries) > top_n:
            block.append(f"　…他 {len(entries) - top_n} 件")
        parts.append("\n".join(block))
    if not any_channel:
        parts.append("（本日は各チャンネルへの投稿がありませんでした）")
    return "\n".join(parts)


def _digest_jiji_section(all_entries: list[dict],
                         category_keywords: dict[str, list[str]] | None,
                         regions_cfg: dict | None,
                         shown_links: set[str], min_japanese: int) -> str:
    """時事枠。regions.yml があれば地域バランス型、無ければ日本のニュース枠。"""
    if regions_cfg and category_keywords:
        return build_jiji_section(all_entries, category_keywords, regions_cfg, shown_links)
    jp = pick_japanese(all_entries, shown_links, min_japanese)
    if not jp:
        return ""
    block = ["\n🇯🇵 **日本のニュース**"]
    block.extend(_digest_entry_line(e) for e in jp)
    return "\n".join(block)


def send_digest(
    message: str,
    space_id: str,
    bot_token: str,
    dry_run: bool,
    max_chars: int = 6000,
) -> None:
    """ダイジェストを送信する。max_chars を超える場合は行単位で分割。dry-run 時は出力のみ。"""
    lines = message.split("\n")
    chunks: list[str] = []
    buf: list[str] = []
    for ln in lines:
        if buf and len("\n".join(buf)) + len(ln) + 1 > max_chars:
            chunks.append("\n".join(buf))
            buf = ["**(続き / Continued)**"]
        buf.append(ln)
    if buf:
        chunks.append("\n".join(buf))

    for i, chunk in enumerate(chunks):
        if dry_run:
            if i:
                print("--- (分割) ---")
            print(chunk)
        else:
            send_webex_message(space_id, chunk, bot_token)
            time.sleep(1)


# ===========================================================
# メイン処理 / Main
# ===========================================================

def main() -> None:
    category_keywords = load_categories()
    channels = load_channels()
    multi_mode = len(channels) > 0

    parser = argparse.ArgumentParser(
        description=(
            "RSS to Webex Bot: カテゴリ別ニュース通知 / Category-based RSS news notifier\n"
            f"モード: {'マルチチャンネル (channels.yml channels:)' if multi_mode else 'シングルボット'}"
        )
    )
    if not multi_mode:
        parser.add_argument(
            "--category", "-c",
            nargs="+",
            choices=list(category_keywords.keys()),
            help=f"通知するカテゴリ（指定なし=全件）。選択肢: {list(category_keywords.keys())}",
        )
    else:
        parser.add_argument(
            "--channel",
            nargs="+",
            choices=[ch["name"] for ch in channels],
            metavar="NAME",
            help=f"実行するチャンネル名を絞り込む（省略時は全チャンネル）。選択肢: {[ch['name'] for ch in channels]}",
        )
    parser.add_argument("--hours", "-t", type=int, default=24,
                        help="取得期間（時間）デフォルト: 24")
    parser.add_argument("--weekend-catchup", action="store_true",
                        help="月曜の実行時のみ、取得期間を72時間（金土日の3日分）に自動拡張する。"
                             "平日9時運用で週末の未配信分をキャッチアップする用途。")
    parser.add_argument("--dry-run", action="store_true",
                        help="Webexに送信せず、収集結果をターミナルに表示するのみ")
    parser.add_argument("--fallback-items", type=int, default=3, metavar="N",
                        help="時間内0件のフィードから最新N件を追加（デフォルト: 3、0で無効）")
    parser.add_argument("--categories-file", default=CATEGORIES_FILE,
                        help=f"カテゴリ設定ファイルのパス（デフォルト: {CATEGORIES_FILE}）")
    parser.add_argument("--urls-file", default=URLS_FILE,
                        help=f"収集するフィードの設定ファイル（デフォルト: {URLS_FILE}）")
    parser.add_argument("--channels-file", default=CHANNELS_FILE,
                        help=f"配信先チャンネルの設定ファイル（デフォルト: {CHANNELS_FILE}）")
    args = parser.parse_args()

    # カスタムファイルパスが指定された場合は再読み込み
    rss_urls = load_urls(args.urls_file)
    url_groups = load_url_groups(args.urls_file)
    weather_config = load_weather_config(args.urls_file)  # デイリーダイジェスト用（urls.yml に集約）
    cvrf_url_template = load_advisory_config(args.urls_file)  # CVSS 取得用（urls.yml に集約）
    regions_cfg = load_regions_config()  # 時事ダイジェストの地域バランス（regions.yml に集約）
    if args.categories_file != CATEGORIES_FILE:
        category_keywords = load_categories(args.categories_file)
    if args.channels_file != CHANNELS_FILE:
        channels = load_channels(args.channels_file)
        multi_mode = len(channels) > 0

    # categories を省略したチャンネルは、name を categories.yml のカテゴリ名として解決する。
    # 完全一致のみ（name がカテゴリ名そのものであること）。一致しないとキーワード0件＝
    # 全記事が通過してしまうため、その場合は配信せずスキップして設定ミスを知らせる。
    for ch in channels:
        if not ch.get("_categories_from_name"):
            continue
        name = str(ch.get("name") or "")
        resolved_cats = resolve_categories_from_name(name, category_keywords)
        if resolved_cats:
            ch["categories"] = resolved_cats
        else:
            print(f"  [WARN] channels.yml channel ({name}): name が categories.yml の"
                  f"カテゴリ名と完全一致しません → このチャンネルはスキップされます")
            print(f"         name をカテゴリ名と同じにするか、categories: を明示してください。"
                  f"（定義済み: {list(category_keywords.keys())}）")
            ch["_skip_reason"] = f"name '{name}' が categories.yml のカテゴリ名と一致しない（categories: を明示してください）"

    # defers_to / source_groups の参照先は名前で解決するため、綴りが違うと
    # 黙って無視される（＝譲渡が効かない）。設定ミスに気づけるよう検証する。
    known_names = {str(c.get("name") or "") for c in channels}
    for ch in channels:
        missing = [str(t) for t in (ch.get("defers_to") or []) if str(t) not in known_names]
        if missing:
            print(f"  [WARN] channels.yml channel ({ch.get('name','?')}): defers_to の {missing} は "
                  f"存在しないチャンネル名です → この譲渡は行われません")
            print(f"         定義済みのチャンネル名: {sorted(known_names)}")

    # channels.yml の source_groups（urls.yml のグループ名参照）を実URLへ解決し、
    # チャンネルの source_feeds に反映する。URL の正本は urls.yml 側に一本化され、
    # channels.yml にはグループ名だけを書けばよい。
    for ch in channels:
        groups = ch.get("source_groups") or []
        if not groups:
            continue
        resolved: list[str] = []
        for g in groups:
            g = str(g).strip()
            urls = url_groups.get(g)
            if not urls:
                print(f"  [WARN] channels.yml channel ({ch.get('name','?')}): source_groups の '{g}' が urls.yml に見つかりません")
                continue
            resolved.extend(urls)
        existing = ch.get("source_feeds") or []
        ch["source_feeds"] = list(dict.fromkeys(existing + resolved))

        # source_groups 専用チャンネル（categories: [] ＝ カテゴリで絞らない）で
        # グループ名が1つも解決できないと、絞り込みが全て外れて全記事が流れ込む。
        # 設定ミスでスペースを埋め尽くさないよう、配信せずスキップする。
        if not ch["source_feeds"] and not (ch.get("categories") or []):
            print(f"  [WARN] channels.yml channel ({ch.get('name','?')}): source_groups が1つも解決できず "
                  f"categories も空です → 全記事が流れ込むため、このチャンネルはスキップされます")
            print(f"         feeds: 側の group 名と綴りを揃えてください。"
                  f"（定義済みグループ: {sorted(url_groups.keys())}）")
            ch["_skip_reason"] = "source_groups が解決できず categories も空（全記事配信になるため停止）"

    # シングルボットモードの事前チェック
    if not multi_mode and not WEBEX_BOT_TOKEN:
        print("[ERROR] WEBEX_BOT_TOKEN が設定されていません。.env を確認してください。")
        sys.exit(1)
    if not multi_mode and not WEBEX_SPACE_ID and not args.dry_run:
        print("[ERROR] WEBEX_SPACE_ID が設定されていません。.env を確認してください。")
        sys.exit(1)

    summarize_cache = {}
    now_jst = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    mode_label = "マルチチャンネル" if multi_mode else "シングルボット"
    morning_message = load_random_morning_message()

    # 週末キャッチアップ: 月曜(JST)の実行時は取得期間を 72時間（金土日の3日分）に拡張する。
    # 平日9時運用のため、月曜は前回実行(金曜)以降の未配信分をまとめて配信する。
    WEEKEND_CATCHUP_HOURS = 72
    hours = args.hours
    if args.weekend_catchup and now_jst.weekday() == 0:  # 0 = 月曜
        hours = WEEKEND_CATCHUP_HOURS
        print(f"  [INFO] 月曜のため週末キャッチアップ: 取得期間を {args.hours}h → {hours}h（金土日）に拡張")

    print(f"=== RSS Bot 起動 / Started ===")
    print(f"  実行時刻    : {now_jst.strftime('%Y-%m-%d %H:%M')} JST")
    print(f"  モード      : {mode_label}")
    if morning_message:
        print(f"  朝メッセージ: {morning_message}")
    if multi_mode:
        active_channels = channels
        if hasattr(args, "channel") and args.channel:
            active_channels = [ch for ch in channels if ch["name"] in args.channel]
        # ダイジェストチャンネル（digest: true）は通常のフィルタ・配信ループから分離する。
        # 全チャンネル配信後に、天気＋各チャンネルの投稿ダイジェストをまとめて送る。
        digest_channels = [ch for ch in active_channels if ch.get("digest")]
        active_channels = [ch for ch in active_channels if not ch.get("digest")]
        print(
            f"  チャンネル数: {len(active_channels)} / {len(channels)}"
            + (f"（＋ダイジェスト {len(digest_channels)}）" if digest_channels else "")
        )
    else:
        cat_label = "、".join(args.category) if getattr(args, "category", None) else "全カテゴリ"
        print(f"  対象カテゴリ: {cat_label}")
    print(f"  取得期間    : 過去 {hours} 時間")
    print(f"  Dry-run     : {args.dry_run}")
    print()

    # 収集対象URLの確定。
    # urls.yml（全チャンネル共通）に加えて、各チャンネルの source_feeds も収集する。
    # → source_feeds のフィードは urls.yml に重複して書く必要がない。
    #   専用フィード（例: Cisco Security Advisories）はチャンネル定義に一元化できる。
    collect_urls = list(rss_urls)
    if multi_mode:
        seen = set(collect_urls)
        added = 0
        for ch in active_channels:
            for u in (ch.get("source_feeds") or []):
                u = str(u).strip()
                if u and u not in seen:
                    collect_urls.append(u)
                    seen.add(u)
                    added += 1
        if added:
            print(f"  [INFO] source_feeds から {added} 件のフィードを収集対象に追加（urls.yml 外）")

    # RSS 収集（1回だけ）/ Collect RSS once
    print("--- RSS 収集 ---")
    all_entries = collect_all_entries(collect_urls, hours, args.fallback_items)
    print(f"\n  合計 {len(all_entries)} 件取得\n")

    # ===== マルチチャンネルモード =====
    if multi_mode:
        SAMPLE_LIMIT = 15  # 1チャンネルあたりの上限件数（process_channel内のランダム抽出と同値）

        # Phase 1: 全チャンネルを事前フィルタして件数を把握
        # Phase 1: pre-filter every channel so we know each channel's pre-sample size.
        #
        # 振り分け軸は2つ:
        #   - categories : 記事本文のキーワードマッチ（従来）
        #   - source_feeds: 取得元 RSS フィード URL によるマッチ（新規）
        # source_feeds を持つチャンネルは、そのフィード由来の記事を対象にする。
        # categories も併記されていれば、両者の和集合を対象にする。
        channel_filtered: dict[str, list[dict]] = {}
        for ch in active_channels:
            ch_name = ch.get("name", "Unnamed")
            cats = ch.get("categories") or []
            src_feeds = ch.get("source_feeds") or []
            if src_feeds:
                matched = filter_by_source_feeds(all_entries, src_feeds)
                if cats:
                    # filter_by_category は entry の浅いコピーを返すため id() では
                    # 一致判定できない。link ベースで重複排除する。
                    seen = {e.get("link") for e in matched}
                    matched = matched + [
                        e for e in filter_by_category(all_entries, cats, category_keywords)
                        if e.get("link") not in seen
                    ]
                channel_filtered[ch_name] = matched
            else:
                channel_filtered[ch_name] = filter_by_category(
                    all_entries, cats if cats else None, category_keywords
                )

        # Phase 1.4: 「source_feeds 専有配信」
        # source_feeds を持つチャンネルは、そのフィード由来の記事を専有する。
        # 対象記事の link を他の全チャンネル（priority チャンネル含む）から除外し、
        # その専用チャンネルでのみ配信する。
        # 用途: Cisco Security Advisories を専用スペースへ隔離し、
        #       セキュリティ/Cisco 等の一般チャンネルへの重複投稿を止める。
        source_feed_channel_names = [
            ch.get("name", "Unnamed") for ch in active_channels if ch.get("source_feeds")
        ]
        source_claimed_links: set[str] = set()
        for sname in source_feed_channel_names:
            for e in channel_filtered.get(sname, []):
                link = e.get("link") or ""
                if link:
                    source_claimed_links.add(link)

        source_exclusive_log: list[tuple[str, int, int]] = []
        if source_claimed_links:
            for name, ents in list(channel_filtered.items()):
                if name in source_feed_channel_names:
                    continue  # 専有チャンネル自身からは除外しない
                before = len(ents)
                channel_filtered[name] = [
                    e for e in ents if (e.get("link") or "") not in source_claimed_links
                ]
                after = len(channel_filtered[name])
                if before != after:
                    source_exclusive_log.append((name, before, after))

        if source_exclusive_log:
            print(f"--- source_feeds 専有配信（{', '.join(source_feed_channel_names)}）---")
            for name, before, after in source_exclusive_log:
                print(f"  ▷ {name}: {before} 件 → {after} 件（{before - after} 件を専用チャンネルへ）")

        # Phase 1.5: 「優先チャンネル独占配信」
        # channels.yml で priority: true が指定されたチャンネルは、そのチャンネルにマッチする
        # 記事を他チャンネルから除外し、独占的に配信する。
        # Cisco や my-fab のような専門カテゴリで、混雑チャンネル(AI/セキュリティ等)に
        # 流れてランダム抽出で消える事態を防ぐ。
        priority_channel_names = [
            ch.get("name", "Unnamed") for ch in active_channels if ch.get("priority")
        ]
        priority_links: set[str] = set()
        for pname in priority_channel_names:
            for e in channel_filtered.get(pname, []):
                link = e.get("link") or ""
                if link:
                    priority_links.add(link)

        priority_log: list[tuple[str, int, int]] = []
        if priority_links:
            for name, ents in list(channel_filtered.items()):
                if name in priority_channel_names:
                    continue
                before = len(ents)
                channel_filtered[name] = [
                    e for e in ents if (e.get("link") or "") not in priority_links
                ]
                after = len(channel_filtered[name])
                if before != after:
                    priority_log.append((name, before, after))

        if priority_log:
            print(f"--- 優先チャンネル独占配信（{', '.join(priority_channel_names)}）---")
            for name, before, after in priority_log:
                print(f"  ▷ {name}: {before} 件 → {after} 件（{before - after} 件を優先チャンネルへ）")

        # Phase 1.6: 「defers_to による譲渡」
        # channels.yml で defers_to: [チャンネル名] が指定されているチャンネルは、
        # 自分の記事のうち、指定した譲渡先チャンネルにも該当する記事を
        # そちらに譲って自分の枠から除外する。
        # 例: AI・機械学習 defers_to: [セキュリティ, ネットワーク]
        #     → AI記事のうちセキュリティ／ネットワーク側にも該当するものは
        #       そちらでのみ配信される
        defer_log: list[tuple[str, list[str], int, int]] = []
        for ch in active_channels:
            defer_targets = ch.get("defers_to") or []
            if not defer_targets:
                continue
            ch_name = ch.get("name", "Unnamed")
            target_links: set[str] = set()
            for target_name in defer_targets:
                for e in channel_filtered.get(target_name, []):
                    link = e.get("link") or ""
                    if link:
                        target_links.add(link)
            if not target_links:
                continue
            before = len(channel_filtered.get(ch_name, []))
            channel_filtered[ch_name] = [
                e for e in channel_filtered.get(ch_name, [])
                if (e.get("link") or "") not in target_links
            ]
            after = len(channel_filtered[ch_name])
            if before != after:
                defer_log.append((ch_name, defer_targets, before, after))

        if defer_log:
            print("--- defers_to 譲渡 ---")
            for name, targets, before, after in defer_log:
                print(f"  ▷ {name}: {before} 件 → {after} 件（{before - after} 件を {', '.join(targets)} へ譲渡）")

        # Phase 2: 「ニッチチャンネル優先の再配分」
        # 15件以下のチャンネルに含まれる記事の link を spacious_links に集める。
        # 同じ link が15件超のチャンネルにも含まれていれば、そちらから削除する。
        # → 結果として、ニッチカテゴリの記事はそのチャンネルでのみ配信され、
        #   混雑チャンネル側の枠を他の記事に譲ることになる。
        spacious_links: set[str] = set()
        for name, ents in channel_filtered.items():
            if len(ents) <= SAMPLE_LIMIT:
                for e in ents:
                    link = e.get("link") or ""
                    if link:
                        spacious_links.add(link)

        redistribution_log: list[tuple[str, int, int]] = []  # (channel, before, after)
        for name, ents in list(channel_filtered.items()):
            if len(ents) > SAMPLE_LIMIT:
                before = len(ents)
                channel_filtered[name] = [
                    e for e in ents if (e.get("link") or "") not in spacious_links
                ]
                after = len(channel_filtered[name])
                if before != after:
                    redistribution_log.append((name, before, after))

        if redistribution_log:
            print("--- チャンネル間再配分（ニッチ優先） ---")
            for name, before, after in redistribution_log:
                print(f"  ▷ {name}: {before} 件 → {after} 件（{before - after} 件をニッチチャンネルへ譲渡）")

        # Phase 2.5: 「日本語ニュース最低件数の補充」
        # min_japanese 指定チャンネル（＝世の中ニュース/一般）が最低件数に満たない場合、
        # 厳格な必須語ゲートを迂回して all_entries の日本語記事で新着順に補充する。
        # 他チャンネルが既に配信する記事とは重複させない（all_claimed_links）。
        all_claimed_links: set[str] = set()
        for ents in channel_filtered.values():
            for e in ents:
                link = e.get("link") or ""
                if link:
                    all_claimed_links.add(link)

        for ch in active_channels:
            min_jp = ch.get("min_japanese")
            if not min_jp:
                continue
            name = ch.get("name", "Unnamed")
            current = channel_filtered.get(name, [])
            shortfall = int(min_jp) - len(current)
            if shortfall <= 0:
                continue
            backfill = pick_japanese(all_entries, all_claimed_links, shortfall)
            if backfill:
                channel_filtered[name] = current + backfill
                for e in backfill:
                    link = e.get("link") or ""
                    if link:
                        all_claimed_links.add(link)
                print(f"--- 日本語ニュース補充（{name}）---")
                print(
                    f"  ▷ {name}: {len(current)} 件 → {len(channel_filtered[name])} 件"
                    f"（日本語記事 {len(backfill)} 件を必須語ゲート迂回で補充）"
                )

        # デイリーダイジェスト用: 各チャンネルが実際に送った記事を集める入れ物。
        digest_collector: dict[str, list[dict]] = {}

        # Phase 3: チャンネルごとに配信処理（事前フィルタ結果を渡す）
        print("\n--- チャンネル別配信 ---")
        for ch in active_channels:
            ch_name    = ch.get("name", "Unnamed")
            space_id   = ch.get("webex_space_id", "")
            bot_token  = ch.get("webex_bot_token", "") or WEBEX_BOT_TOKEN
            categories = ch.get("categories") or []  # 空リスト = 全カテゴリ
            src_feeds  = ch.get("source_feeds") or []

            # 環境変数が未解決のチャンネルはスキップ（トークン後日用意の運用に対応）
            if ch.get("_skip_reason") or not space_id:
                reason = ch.get("_skip_reason") or "webex_space_id が未設定"
                print(f"  [SKIP] {ch_name}: {reason}")
                continue

            if not bot_token:
                print(f"  [SKIP] {ch_name}: bot_token が未設定です (.env の WEBEX_BOT_TOKEN または channels.yml の webex_bot_token を設定してください)")
                continue

            # ラベル: source_feeds 専用（categories なし）のチャンネルは
            # 「全カテゴリ」ではなく RSS 専用配信であることを明示する。
            cat_label_override = None
            if src_feeds and not categories:
                cat_label_override = "Cisco Security Advisories（RSS 専用）"

            process_channel(
                channel_name=ch_name,
                space_id=space_id,
                bot_token=bot_token,
                categories=categories if categories else None,
                all_entries=all_entries,
                category_keywords=category_keywords,
                hours_ago=hours,
                now_jst=now_jst,
                dry_run=args.dry_run,
                anthropic_api_key=llm_api_key(),
                summarize_cache=summarize_cache,
                anthropic_model=ANTHROPIC_MODEL,
                morning_message=morning_message,
                pre_filtered=channel_filtered.get(ch_name),
                cat_label_override=cat_label_override,
                digest_collector=digest_collector,
                cvrf_url_template=cvrf_url_template,
                max_items=max_items_of(ch),
            )
            time.sleep(1)  # チャンネル間のレート制限

        # Phase 4: デイリーダイジェスト（天気＋各チャンネル投稿ダイジェスト＋日本のニュース枠）
        # 全チャンネル配信後に、実際に送られた記事を集約して1通投稿する。
        if digest_channels:
            print("\n--- デイリーダイジェスト ---")
            if weather_config:
                locs = weather_config["locations"]
                api_url = weather_config["api_url"]
                labels = "/".join(l for (l, _, _) in locs)
                print(f"  天気を取得中（Open-Meteo, {len(locs)}地点: {labels}）...")
                weather_results = [
                    fetch_weather(api_url, label, lat, lon) for (label, lat, lon) in locs
                ]
                ok_weather = sum(1 for r in weather_results if r)
                print(f"  天気取得: {ok_weather}/{len(locs)} 地点")
            else:
                weather_results = []
                print("  [INFO] urls.yml に weather 設定が無いため天気ブロックを省略します")

            for ch in digest_channels:
                ch_name   = ch.get("name", "Unnamed")
                blocks = digest_blocks_of(ch)
                weather_style = str(ch.get("weather_format")
                                    or DEFAULT_WEATHER_STYLE).strip().lower()
                print(f"  {ch_name} の構成: {'、'.join(blocks) or '（なし）'}"
                      f" / 天気は{'表' if weather_style != 'list' else '箇条書き'}形式")
                if "jiji" in blocks and regions_cfg:
                    print(
                        "  時事ダイジェスト: 地域バランス "
                        f"日本{regions_cfg['quota']['japan']}/米{regions_cfg['quota']['us']}"
                        f"/その他{regions_cfg['quota']['other']}（regions.yml）"
                    )
                digest_message = build_digest_message(
                    weather_results, digest_collector, all_entries, now_jst,
                    category_keywords=category_keywords, regions_cfg=regions_cfg,
                    blocks=blocks, weather_style=weather_style,
                )
                space_id  = ch.get("webex_space_id", "")
                bot_token = ch.get("webex_bot_token", "") or WEBEX_BOT_TOKEN
                if ch.get("_skip_reason") or not space_id:
                    reason = ch.get("_skip_reason") or "webex_space_id が未設定"
                    print(f"  [SKIP] {ch_name}: {reason}")
                    continue
                if not bot_token:
                    print(f"  [SKIP] {ch_name}: bot_token が未設定です (.env の WEBEX_BOT_TOKEN または channels.yml の webex_bot_token を設定してください)")
                    continue
                print(f"  ▶ {ch_name} へダイジェストを送信")
                if args.dry_run:
                    print(f"\n{'='*50}")
                send_digest(digest_message, space_id, bot_token, dry_run=args.dry_run)
                if args.dry_run:
                    print(f"{'='*50}")
                time.sleep(1)

    # ===== シングルボットモード =====
    else:
        category = getattr(args, "category", None)
        cat_label = "、".join(category) if category else "全カテゴリ"
        process_channel(
            channel_name=f"RSS Bot ニュース通知 / News Digest",
            space_id=WEBEX_SPACE_ID,
            bot_token=WEBEX_BOT_TOKEN,
            categories=category,
            all_entries=all_entries,
            category_keywords=category_keywords,
            hours_ago=hours,
            now_jst=now_jst,
            dry_run=args.dry_run,
            anthropic_api_key=llm_api_key(),
            summarize_cache=summarize_cache,
            anthropic_model=ANTHROPIC_MODEL,
            morning_message=morning_message,
            cvrf_url_template=cvrf_url_template,
        )

    print("\n=== 完了 / Done ===")


if __name__ == "__main__":
    main()