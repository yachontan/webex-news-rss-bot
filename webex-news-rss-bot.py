#!/usr/bin/env python3
"""
webex-news-rss-bot.py
-------------------
Collects today's RSS news by category keyword and sends notifications via Webex Bot.
カテゴリキーワードに基づいて当日のRSSニュースを収集し、Webex Bot経由で通知します。

動作モード / Operation Modes:
  - マルチチャンネルモード: bots.yml が存在する場合。各チャンネルに個別配信。
  - シングルボットモード : bots.yml が存在しない場合。--category 引数で制御。
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

from dotenv import load_dotenv

# --- 環境変数の読み込み / Load environment variables ---
# override=True: シェル側に空文字などで既存セットされていても .env の値で上書きする。
# これがないと、たとえば shell 環境に ANTHROPIC_API_KEY='' があるだけで
# .env の API キーが無視されて Claude 要約が無効化される。
_BASE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_BASE, ".env"), override=True)


WEBEX_BOT_TOKEN = os.getenv("WEBEX_BOT_TOKEN", "")
WEBEX_SPACE_ID  = os.getenv("WEBEX_SPACE_ID", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL   = os.getenv("ANTHROPIC_MODEL", "claude-3-haiku-20240307")
SSL_VERIFY        = os.getenv("SSL_VERIFY", "True").strip().lower() != "false"

# SSL検証を無効にする場合、警告を非表示にします
if not SSL_VERIFY:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- ファイルパス定数 / File path constants ---

CATEGORIES_FILE = os.path.join(_BASE, "categories.yml")
BOTS_FILE       = os.path.join(_BASE, "bots.yml")
URLS_FILE       = os.path.join(_BASE, "urls.yml")
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

def load_urls(path: str = URLS_FILE) -> list[str]:
    """
    urls.yml からRSSフィードのURLリストを読み込みます。
    Loads RSS feed URLs from urls.yml.
    """
    if not os.path.exists(path):
        print(f"[ERROR] RSSフィード設定ファイルが見つかりません: {path}")
        sys.exit(1)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, list):
            print("[ERROR] urls.yml の形式が正しくありません。リスト形式（- URL）で記述してください。")
            sys.exit(1)
        return [str(url).strip() for url in data if url]
    except yaml.YAMLError as e:
        print(f"[ERROR] urls.yml の解析に失敗しました: {e}")
        sys.exit(1)

# ===========================================================
# LLM (Claude) 要約処理 / LLM (Claude) Summarization
# ===========================================================

def summarize_with_claude(title: str, summary: str, api_key: str, model: str = "claude-3-haiku-20240307") -> str:
    """
    Claude API を使用して記事を要約します。
    """
    if not api_key:
        return summary

    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    
    # 圧縮プロンプト: 主要制約を最短で記述（約45トークン）
    # - ラベル/前置き禁止: タイトル：/概要：等を防止
    # - 情報不足要求禁止: 「本文を提供してください」等を防止
    # - 英文は翻訳: 英語RSSを日本語化
    prompt = (
        "日本語110字以内1〜2文で要約のみ出力。"
        "ラベル/前置き/改行/情報不足要求は禁止。"
        "提供情報のみで完結、英文は翻訳。\n\n"
        f"T: {title}\nS: {summary}"
    )

    payload = {
        "model": model,  # 指定されたClaudeモデルを使用
        "max_tokens": 140,
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15, verify=SSL_VERIFY)
        response.raise_for_status()
        res_data = response.json()
        content = res_data["content"][0]["text"].strip()
        return content
    except Exception as e:
        body_str = ""
        if 'response' in locals() and hasattr(response, 'text'):
            body_str = f" / レスポンス内容: {response.text[:500]}"
        print(f"    [WARN] Claudeによる要約に失敗しました: {e}{body_str}。元の概要を使用します。")
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
        new_summary = summarize_with_claude(entry["title"], entry["summary"], api_key, model=model)
        cache[link] = new_summary
        entry["summary"] = new_summary
        time.sleep(0.5)  # レート制限対策
    print("    --- 要約完了 ---")

_CAT_ENV_VAR_RE = re.compile(r'\$\{([A-Za-z_][A-Za-z0-9_]*)\}')


def _expand_keyword_env(value: str) -> str | None:
    """
    キーワード文字列内の ${VAR} を環境変数（.env）で展開する。
    - 環境変数が定義されていれば、その値で置換した文字列を返す。
    - 未定義または空文字なら警告を出して None を返す（呼び出し側でスキップ）。
    - ${VAR} を含まない通常キーワードはそのまま返す。

    例: "!${MYFAB_KEYWORD}" + MYFAB_KEYWORD="fujitsu"  → "!fujitsu"

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


def load_bots(path: str = BOTS_FILE) -> list[dict]:
    """
    bots.yml からマルチチャンネル設定を読み込みます。
    ファイルが存在しない場合は空リストを返します（シングルボットモード）。
    Loads multi-channel configs from bots.yml.
    Returns [] if the file doesn't exist (single-bot mode).
    """
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict) or "channels" not in data:
            print("[ERROR] bots.yml の形式が正しくありません。'channels:' キーが必要です。")
            sys.exit(1)
        channels = data.get("channels") or []
        # 環境変数の展開と必須フィールドの検証 / Expand env vars and validate required fields
        for i, ch in enumerate(channels):
            # チャンネル表示名 (name) も ${VAR} を展開する
            # 例: "${MYFAB_KEYWORD}ニュース" + MYFAB_KEYWORD=Fujitsu → "Fujitsuニュース"
            # 用途: 公開リポジトリにチャンネル名（=会社名）を露出させない
            if "name" in ch and isinstance(ch["name"], str) and '$' in ch["name"]:
                resolved_name = os.path.expandvars(ch["name"])
                if '$' in resolved_name:
                    print(f"  [WARN] bots.yml channel[{i}]: name '{ch['name']}' に未定義の環境変数があります")
                else:
                    ch["name"] = resolved_name
            if "webex_space_id" in ch and isinstance(ch["webex_space_id"], str):
                ch["webex_space_id"] = os.path.expandvars(ch["webex_space_id"])
            if "webex_bot_token" in ch and isinstance(ch["webex_bot_token"], str):
                ch["webex_bot_token"] = os.path.expandvars(ch["webex_bot_token"])
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
                            print(f"  [WARN] bots.yml channel[{i}] ({ch.get('name','?')}): categories の '{cat_str}' に未定義の環境変数があります")
                            continue
                        expanded_cats.append(resolved)
                    else:
                        expanded_cats.append(cat_str)
                ch["categories"] = expanded_cats

            if not ch.get("webex_space_id"):
                print(f"[ERROR] bots.yml の channel[{i}] ({ch.get('name', '?')}) に webex_space_id がありません。")
                sys.exit(1)
        return channels
    except yaml.YAMLError as e:
        print(f"[ERROR] bots.yml の解析に失敗しました: {e}")
        sys.exit(1)


# ===========================================================
# RSS フィード取得 / RSS collection
# ===========================================================

def _parse_entry(entry) -> dict | None:
    """feedparser のエントリを辞書に変換します。日時情報がない場合は None を返します。"""
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
            parsed = _parse_entry(entry)
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
    """全RSSフィードから記事を収集し、重複排除を行います。 / Collect entries from all RSS feeds and deduplicate."""
    all_entries: list[dict] = []
    for url in rss_urls:
        print(f"  取得中: {url}")
        # フォールバックをやめるため、get_recent_rss_entries には fallback_items=0 を渡します
        entries = get_recent_rss_entries(url, hours_ago=hours_ago, fallback_items=0)
        print(f"    → {len(entries)} 件")
        all_entries.extend(entries)
        time.sleep(1)

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

    def _is_duplicate(t_a, t_b, s_a, s_b):
        t_a_n = _normalize_title(t_a)
        t_b_n = _normalize_title(t_b)
        seq = difflib.SequenceMatcher(None, t_a_n, t_b_n).ratio()
        if seq >= SEQ_HIGH:
            return True
        # 漢字bigram の重なり指標
        bg_a, bg_b = _kanji_bigrams(t_a_n), _kanji_bigrams(t_b_n)
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
        # フォールバック: タイトル中程度 + 概要も類似
        if seq >= SEQ_MID and s_a and s_b:
            summary_ratio = difflib.SequenceMatcher(None, s_a, s_b).ratio()
            if summary_ratio >= SUMMARY_MID:
                return True
        return False

    deduped_entries = []
    for entry in all_entries:
        is_duplicate = False
        title_a = entry['title'].lower().strip()
        summary_a = entry['summary'].lower().strip()
        len_a = len(entry['title']) + len(entry['summary'])

        for idx, existing in enumerate(deduped_entries):
            title_b = existing['title'].lower().strip()
            summary_b = existing['summary'].lower().strip()

            if _is_duplicate(title_a, title_b, summary_a, summary_b):
                is_duplicate = True
                # 残すべき記事の選択基準:
                #  ① 公開日時が新しい方を優先（最新情報を採用）
                #  ② 同時刻なら情報量（タイトル+概要の文字数）が多い方を採用
                existing_pub = existing.get('published')
                entry_pub = entry.get('published')
                len_b = len(existing['title']) + len(existing['summary'])
                replace = False
                if entry_pub and existing_pub and entry_pub != existing_pub:
                    replace = entry_pub > existing_pub
                else:
                    replace = len_a > len_b
                if replace:
                    deduped_entries[idx] = entry
                break

        if not is_duplicate:
            deduped_entries.append(entry)

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
            # 配信時にスコア優先抽出するため、entry にスコアを記録
            entry["_score"] = score
            filtered.append(entry)

    return filtered


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


# ===========================================================
# Webex 送信 / Webex messaging
# ===========================================================

def send_webex_message(room_id: str, message_text: str, bot_token: str) -> bool:
    """
    Webexスペースにメッセージを送信します。
    Sends a Markdown message to the specified Webex space.
    """
    url = "https://webexapis.com/v1/messages"
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
        summary_line = f"  📝 {entry['summary']}\n" if entry.get("summary") else ""
        date_str = pub_jst.strftime('%Y-%m-%d %H:%M')

        # タイトルと日付を同一行に表示（要約は次行）
        line = (
            f"\n- [{entry['title']}]({entry['link']})　（📅 {date_str} JST）{fallback_tag}\n"
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
) -> None:
    """
    1チャンネル分のフィルタリングと送信を処理します。
    Processes filtering and sending for one channel.

    pre_filtered が指定された場合は再フィルタを行わず、その結果を採用する
    （チャンネル間の再配分処理後にメインから呼ばれる用途）。
    """
    cat_label = "、".join(categories) if categories else "全カテゴリ"
    print(f"\n  ▶ チャンネル: {channel_name} ({cat_label})")

    if pre_filtered is not None:
        filtered = list(pre_filtered)
    else:
        filtered = filter_by_category(all_entries, categories, category_keywords)

    if len(filtered) > 15:
        # スコア降順で集計（ログ用）
        from collections import Counter
        score_dist = Counter(e.get("_score", 0) for e in filtered)
        dist_str = " / ".join(f"score={s}:{c}" for s, c in sorted(score_dist.items(), reverse=True))
        # 高スコア優先で15件に絞る（同階層内のみランダム抽出）
        filtered = stratified_pick(filtered, 15)
        kept_dist = Counter(e.get("_score", 0) for e in filtered)
        kept_str = " / ".join(f"score={s}:{c}" for s, c in sorted(kept_dist.items(), reverse=True))
        print(f"    15件超 → スコア階層化抽出: {len(filtered)} 件")
        print(f"      抽出前 ({sum(score_dist.values())}件): {dist_str}")
        print(f"      抽出後 ({sum(kept_dist.values())}件): {kept_str}")

    filtered.sort(key=lambda x: x["published"], reverse=True)
    
    # Claudeによる要約を実行 (APIキーが設定されている場合のみ)
    if anthropic_api_key and summarize_cache is not None:
        summarize_entries_in_place(filtered, anthropic_api_key, summarize_cache, model=anthropic_model)

    print(f"    送信対象: {len(filtered)} 件")

    header = (
        f"🗞️ **{channel_name}**\n"
        f"🏷 カテゴリ: **{cat_label}**　｜　✅ {len(filtered)} 件　｜　⏱ {now_jst.strftime('%Y-%m-%d %H:%M')} JST\n"
        f"{'─' * 40}"
    )

    if not filtered:
        msg = (
            f"📭 **{channel_name}**\n"
            f"過去 {hours_ago} 時間以内に **{cat_label}** に該当するニュースはありませんでした。\n"
            f"⏱ {now_jst.strftime('%Y-%m-%d %H:%M')} JST"
        )
        if dry_run:
            print(f"    {msg}")
        else:
            send_webex_message(space_id, msg, bot_token)
        return

    if dry_run:
        print(f"\n{'='*50}")
        print(header)
        for e in filtered:
            pub_jst = e["published"].astimezone(datetime.timezone(datetime.timedelta(hours=9)))
            fb = " [📌最新記事]" if e.get("fallback") else ""
            date_str = pub_jst.strftime('%Y-%m-%d %H:%M')
            # タイトルと日付を同一行
            print(f"  - {e['title']}　（📅 {date_str} JST）{fb}")
            if e.get("summary"):
                print(f"    📝 {e['summary']}")
            print(f"    🔗 {e['link']}")
        if morning_message:
            print(f"\n{morning_message}")
        print(f"{'='*50}")
    else:
        build_and_send(filtered, header, space_id, bot_token, dry_run=False, morning_message=morning_message)


# ===========================================================
# メイン処理 / Main
# ===========================================================

def main() -> None:
    category_keywords = load_categories()
    channels = load_bots()
    multi_mode = len(channels) > 0

    parser = argparse.ArgumentParser(
        description=(
            "RSS to Webex Bot: カテゴリ別ニュース通知 / Category-based RSS news notifier\n"
            f"モード: {'マルチチャンネル (bots.yml)' if multi_mode else 'シングルボット'}"
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
    parser.add_argument("--dry-run", action="store_true",
                        help="Webexに送信せず、収集結果をターミナルに表示するのみ")
    parser.add_argument("--fallback-items", type=int, default=3, metavar="N",
                        help="時間内0件のフィードから最新N件を追加（デフォルト: 3、0で無効）")
    parser.add_argument("--categories-file", default=CATEGORIES_FILE,
                        help=f"カテゴリ設定ファイルのパス（デフォルト: {CATEGORIES_FILE}）")
    parser.add_argument("--bots-file", default=BOTS_FILE,
                        help=f"マルチチャンネル設定ファイルのパス（デフォルト: {BOTS_FILE}）")
    parser.add_argument("--urls-file", default=URLS_FILE,
                        help=f"RSSフィードURL設定ファイルのパス（デフォルト: {URLS_FILE}）")
    args = parser.parse_args()

    # カスタムファイルパスが指定された場合は再読み込み
    rss_urls = load_urls(args.urls_file)
    if args.categories_file != CATEGORIES_FILE:
        category_keywords = load_categories(args.categories_file)
    if args.bots_file != BOTS_FILE:
        channels = load_bots(args.bots_file)
        multi_mode = len(channels) > 0

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

    print(f"=== RSS Bot 起動 / Started ===")
    print(f"  実行時刻    : {now_jst.strftime('%Y-%m-%d %H:%M')} JST")
    print(f"  モード      : {mode_label}")
    if morning_message:
        print(f"  朝メッセージ: {morning_message}")
    if multi_mode:
        active_channels = channels
        if hasattr(args, "channel") and args.channel:
            active_channels = [ch for ch in channels if ch["name"] in args.channel]
        print(f"  チャンネル数: {len(active_channels)} / {len(channels)}")
    else:
        cat_label = "、".join(args.category) if getattr(args, "category", None) else "全カテゴリ"
        print(f"  対象カテゴリ: {cat_label}")
    print(f"  取得期間    : 過去 {args.hours} 時間")
    print(f"  Dry-run     : {args.dry_run}")
    print()

    # RSS 収集（1回だけ）/ Collect RSS once
    print("--- RSS 収集 ---")
    all_entries = collect_all_entries(rss_urls, args.hours, args.fallback_items)
    print(f"\n  合計 {len(all_entries)} 件取得\n")

    # ===== マルチチャンネルモード =====
    if multi_mode:
        SAMPLE_LIMIT = 15  # 1チャンネルあたりの上限件数（process_channel内のランダム抽出と同値）

        # Phase 1: 全チャンネルを事前フィルタして件数を把握
        # Phase 1: pre-filter every channel so we know each channel's pre-sample size.
        channel_filtered: dict[str, list[dict]] = {}
        for ch in active_channels:
            ch_name = ch.get("name", "Unnamed")
            cats = ch.get("categories") or []
            channel_filtered[ch_name] = filter_by_category(
                all_entries, cats if cats else None, category_keywords
            )

        # Phase 1.5: 「優先チャンネル独占配信」
        # bots.yml で priority: true が指定されたチャンネルは、そのチャンネルにマッチする
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
        # bots.yml で defers_to: [チャンネル名] が指定されているチャンネルは、
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

        # Phase 3: チャンネルごとに配信処理（事前フィルタ結果を渡す）
        print("\n--- チャンネル別配信 ---")
        for ch in active_channels:
            ch_name    = ch.get("name", "Unnamed")
            space_id   = ch.get("webex_space_id", "")
            bot_token  = ch.get("webex_bot_token", "") or WEBEX_BOT_TOKEN
            categories = ch.get("categories") or []  # 空リスト = 全カテゴリ

            if not bot_token:
                print(f"  [SKIP] {ch_name}: bot_token が未設定です (.env の WEBEX_BOT_TOKEN または bots.yml の webex_bot_token を設定してください)")
                continue

            process_channel(
                channel_name=ch_name,
                space_id=space_id,
                bot_token=bot_token,
                categories=categories if categories else None,
                all_entries=all_entries,
                category_keywords=category_keywords,
                hours_ago=args.hours,
                now_jst=now_jst,
                dry_run=args.dry_run,
                anthropic_api_key=ANTHROPIC_API_KEY,
                summarize_cache=summarize_cache,
                anthropic_model=ANTHROPIC_MODEL,
                morning_message=morning_message,
                pre_filtered=channel_filtered.get(ch_name),
            )
            time.sleep(1)  # チャンネル間のレート制限

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
            hours_ago=args.hours,
            now_jst=now_jst,
            dry_run=args.dry_run,
            anthropic_api_key=ANTHROPIC_API_KEY,
            summarize_cache=summarize_cache,
            anthropic_model=ANTHROPIC_MODEL,
            morning_message=morning_message,
        )

    print("\n=== 完了 / Done ===")


if __name__ == "__main__":
    main()