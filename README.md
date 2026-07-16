# webex-news-rss-bot

![Version](https://img.shields.io/badge/version-v1.1.0-blue)
![Release Date](https://img.shields.io/badge/release-2026--07--13-green)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

**Version**: `v1.1.0` ／ **Release Date**: 2026-07-13

> **RSS → Webex Bot ニュース通知 ＆ LLM自動要約・再ランクスクリプト / RSS-to-Webex News Notifier with LLM Summary & Re-ranking**

カテゴリキーワードに基づいて当日のRSSニュースを並列収集し、重複排除・Claudeによる重要度再ランク・自動要約を行った上で、Webex Bot経由で複数の指定スペースに自動配信する高機能ニュース通知スクリプトです。  
A Python script that collects today's RSS news in parallel, deduplicates, re-ranks by importance and summarizes using Claude API (LLM), and notifies Webex spaces via Bot.

> **カテゴリ設定は `categories.yml`、フィードリストは `urls.yml`、配信先は `bots.yml` で完全外部管理。Pythonコードを一切書き換えることなく、運用のすべてをカスタマイズできます。**  
> **Completely managed via YAML configs (`categories.yml`, `urls.yml`, `bots.yml`). You can fully customize feeds, filters, and routing without editing any Python script.**

---

## 目次 / Table of Contents

- [機能 / Features](#機能--features)
- [動作環境 / Requirements](#動作環境--requirements)
- [セットアップ / Setup](#セットアップ--setup)
- [使い方 / Usage](#使い方--usage)
- [ルームID確認ツール / Room ID Checker (check_rooms.py)](#ルームid確認ツール--room-id-checker-check_roomspy)
- [各種設定ファイル / Configuration Files](#各種設定ファイル--configuration-files)
- [プライベートカテゴリ運用（my-fab パターン）/ Private Category Usage](#プライベートカテゴリ運用my-fab-パターン-private-category-usage)
- [Claudeによる自動要約 ＆ 超エコノミーモード / LLM Summarization & Eco-mode](#claudeによる自動要約--超エコノミーモード--llm-summarization--eco-mode)
- [LLMによるニュース選出（再ランク）/ LLM Re-ranking](#llmによるニュース選出再ランク--llm-re-ranking)
- [自動実行 / Automation (cron)](#自動実行--automation-cron)
- [macOS の制限と設計上の理由 / macOS Restrictions & Design Rationale](#macos-の制限と設計上の理由--macos-restrictions--design-rationale)
- [Windows での利用 / Running on Windows](#windows-での利用--running-on-windows)
- [ファイル構成 / File Structure](#ファイル構成--file-structure)
- [トラブルシューティング / Troubleshooting](#トラブルシューティング--troubleshooting)
- [更新履歴 / Version History](#更新履歴--version-history)

---

## 機能 / Features

| 機能 | 用途・詳細 | Description |
|:---|:---|:---|
| **複数RSSの並列取得** | `urls.yml` の約170フィードを **ホスト別に最大12並列** で取得（同一ホスト内はリクエスト間1秒sleepの直列＝サーバへの礼儀は維持）。全体実行時間を大幅短縮 | Parallel fetching (up to 12 host-workers; per-host 1s throttle) |
| **スコアリング型カテゴリフィルタ** | `categories.yml` に定義したキーワードを **必須語(`!`)×3点 + 通常語×1点** でスコア計算、`>=4点`で合格 | Weighted keyword scoring (must×3 + normal×1, threshold 4) |
| **単語境界マッチ** | 5文字以下の英数字キーワードは `\b` で境界判定（`lan`は `LAN`にマッチするが`plan`にはマッチしない） | Word-boundary regex for short ASCII keywords |
| **Cisco限定URL深度マッチ** | URLに `cisco` を含む記事のみ URL文字列を判定対象に追加（Google News等の汎用URLによる誤マッチを防止） | URL inclusion limited to cisco domains |
| **マルチチャンネル配信** | `bots.yml` に基づき、複数Webexスペースへカテゴリ毎に自動配信 | Route different categories to separate spaces |
| **優先独占チャンネル** | `priority: true` のチャンネル（Cisco等）は該当記事を他チャンネルから除外して独占配信 | Priority channel claims its articles exclusively |
| **チャンネル間譲渡 (defers_to)** | 汎用チャンネル（AI・機械学習・世の中 等）から専門チャンネル（セキュリティ/ネットワーク/経済）へ自動譲渡 | Auto-defer articles to more specific channels |
| **ニッチ優先再配分** | 15件超の混雑チャンネルから、同じ記事が15件以下の余裕チャンネルにも該当する場合、余裕側のみに残して混雑側から除外 | Crowded→spacious redistribution |
| **ソースベース振り分け (source_groups)** | 記事本文のキーワードではなく「どの RSS フィード由来か」でチャンネルを決定。`urls.yml` の名前付きグループを `bots.yml` の `source_groups` で参照し、そのフィード由来の記事を専有配信（例: Cisco Security Advisories を専用スペースへ隔離） | Route by source feed via named `urls.yml` groups |
| **Cisco Advisory の CVSS 併記（危険度カラー）** | Cisco Security Advisory の記事に、Cisco 公開の構造化データ（CVRF）から取得した実際の **CVSS Base Score** を、深刻度に応じた色付きバッジで表示（🔴 Critical / 🟠 High / 🟡 Medium・Low）。複数スコアは範囲表記＋最大値で色付け（`🔴 CVSS 7.5〜9.1（複数該当）`）。LLM には推測させず実値を取得 | Color-coded CVSS badge for Cisco advisories (fetched from CVRF) |
| **空チャンネルは無投稿** | 当日に該当ニュースが0件のスペースには、空通知も含め一切投稿しない | Skip posting entirely when a channel has no matching news |
| **高度な重複排除** | 媒体名(`(共同通信)`等)除去後、①タイトル類似度85%以上、②漢字bigram Jaccard 20%以上、③漢字bigram Overlap 50%以上+共通5件以上、④タイトル55%+概要55%、⑤**英語タイトルの単語Jaccard 50%以上（両者4語以上）** のいずれかで統合し **最新公開日時の記事を採用**。正規化・bigram・トークン集合は前計算済みで高速 | Hybrid 5-way dedup: kanji-bigram for Japanese + word-level Jaccard for English; precomputed for speed |
| **LLM再ランク（ニュース選出）** | 1チャンネル15件超のとき、スコア上位40候補を Claude が**読者（Cisco SE）にとっての重要度順**に15件選定。API未設定・失敗時はスコア階層＋ランダム抽出に自動フォールバック | LLM re-ranking picks top 15 by reader relevance; falls back to stratified random sampling |
| **SSLフォールバック** | SSL証明書検証失敗時に自動で `verify=False` リトライ（HuggingFace等のmacOS証明書問題に対応） | Auto-fallback to `verify=False` on SSL failure |
| **フィードリーダ系User-Agent** | `rss-bot/1.0` UAでCISA等のbot対策サイトに対応（※community.cisco.com は2026-07現在それでも403 → トラブルシューティング参照） | Feed-reader UA mitigates anti-bot blocks (some sites still reject) |
| **Markdownリンク形式** | タイトルと日付を同一行に表示 (`[Title](URL)　（📅 date JST）`) | Title and date on same line with Markdown link |
| **Claude自動要約** | Claude APIで「自然な日本語1〜2文（110字以内）」に要約。**英文RSSは自動で日本語に翻訳** | LLM summary + English→Japanese translation |
| **超エコノミーモード** | プロンプト圧縮（~22トークン）+ 短い綺麗な日本語概要のスキップ + 要約キャッシュ | Compressed prompt (~22 tokens), skip for short Japanese, in-memory cache |
| **Dry-runモード** | 送信せずターミナルで取得・要約結果を確認 | Dry-run preview |
| **launchdデプロイ** | macOSのDocuments保護を回避してホーム直下に同期配置する自動デプロイスクリプト | Auto-deploy script for macOS launchd |
| **スリープ復帰対応** | `pmset` で毎朝 Mac を自動wakeさせる運用ガイドを完備（launchdがスリープ中は fire しない問題の回避） | `pmset` wake schedule for reliable launchd execution on Mac sleep |

---

## 動作環境 / Requirements

- Python 3.10 以上 / Python 3.10 or later
- Webex Bot アカウントとアクセストークン / Webex Bot account and access token
- Anthropic (Claude) API キー (要約機能用・任意) / Anthropic API Key (optional for summaries)

### 依存パッケージ / Python dependencies
※詳細は `requirements.txt` を参照 / See `requirements.txt` for details
* `feedparser` — RSS解析 / RSS parsing
* `requests` — Webex/Claude API通信 / HTTP client for Webex & Claude APIs
* `python-dotenv` — `.env` 読み込み / Environment variable loading
* `PyYAML` — YAML設定読み込み / YAML config loading

---

## セットアップ / Setup

### 1. 仮想環境の有効化とパッケージインストール / Activate venv and install dependencies
```bash
cd rss-bot
source bin/activate
pip install -r requirements.txt
```

### 2. 環境変数設定ファイル (`.env`) の作成 / Create `.env` from template
`.env.example` をコピーして `.env` を作成します。  
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

`.env` を開き、各項目に実際の値を設定します。`.env.example` にすべての変数の説明とデフォルト値が記載されています。  
Open `.env` and fill in your actual values. All variables with descriptions are documented in `.env.example`.

| 変数 | 必須 | 説明 |
|:---|:---:|:---|
| `WEBEX_BOT_TOKEN` | ✅ | Webex Bot のアクセストークン |
| `WEBEX_SPACE_ID` | ✅ | 送信先 Webex スペース ID（シングルボットモード） |
| `WEBEX_SPACE_ID_*` | — | マルチチャンネルモード用 Space ID（`bots.yml` で参照） |
| `WEBEX_BOT_TOKEN_*` | — | チャンネル別 Bot トークン（省略時は共通トークンを使用） |
| `ANTHROPIC_API_KEY` | — | Claude API キー（要約・再ランク機能を使う場合のみ） |
| `ANTHROPIC_MODEL` | — | **要約**用モデル名（コード既定: `claude-3-haiku-20240307`。`.env` で新しいモデルに上書き推奨） |
| `ANTHROPIC_RERANK_MODEL` | — | **再ランク**用モデル名（既定: `claude-haiku-4-5-20251001`） |
| `SSL_VERIFY` | — | `false` にすると SSL 検証を無効化（社内プロキシ等） |
| `MYFAB_KEYWORD` 等 | — | プライベートカテゴリ用（my-fab パターン参照） |

> `.env` は `.gitignore` により Git 管理対象外です。絶対にコミットしないでください。  
> `.env` is excluded by `.gitignore` and must never be committed.

---

## 使い方 / Usage

### 基本実行 / Basic run
```bash
python webex-news-rss-bot.py
```
`bots.yml` に定義されたマルチチャンネルすべてに対して、過去24時間の記事を自動的に収集・要約・配信します。  
Collects, summarizes, and delivers the last 24 hours of articles to every channel defined in `bots.yml`.

### ドライラン / Dry-run (テストモード：メッセージ送信せず画面確認のみ / preview without sending)
```bash
python webex-news-rss-bot.py --dry-run
```
要約の挙動や、スキップ処理が正常に働いているかを画面上で安全に確認できます。  
Safely inspect summarization, skipping logic, and channel routing from your terminal.

### 特定カテゴリ・特定の時間を指定して実行 / Run with a specific category and time range
```bash
# 過去12時間の「AI・機械学習」のみをドライランで取得
# Dry-run for the last 12 hours of "AI・機械学習" only
python webex-news-rss-bot.py -c "AI・機械学習" --hours 12 --dry-run
```

---

## ルームID確認ツール / Room ID Checker (`check_rooms.py`)

Webex Botが参加しているスペース（ルーム）の「ルーム名」と「Room ID」を一覧でターミナルに出力する補助ツールです。`bots.yml` を設定する際のID調査に利用します。  
A helper tool that lists the **name** and **Room ID** of every Webex space the Bot has joined. Useful when populating `bots.yml`.

### 実行方法 / How to run
```bash
python check_rooms.py
```
実行すると、Webex Botのトークンの入力を求められます。**入力したトークン文字は画面上に一切表示されません（非表示入力）**。  
You will be prompted for the Webex Bot token. **Input is hidden** for security.

出力された一覧から必要なルームの `id` をコピーし、`bots.yml` の `webex_space_id` に設定してください。  
Copy the desired `id` from the output and paste it into `bots.yml`'s `webex_space_id`.

---

## 各種設定ファイル / Configuration Files

### 1. 配信ルール設定 (`bots.yml`) / Delivery routing
どのWebexスペースに、どのカテゴリを配信するかを定義します。本リポジトリの実構成例：  
Defines which categories are routed to which Webex spaces. The actual configuration used in this repository:

```yaml
channels:
  - name: 世の中ニュース
    webex_space_id: ${WEBEX_SPACE_ID_GENERAL}
    webex_bot_token: ${WEBEX_BOT_TOKEN_GENERAL}
    defers_to:                     # 経済寄りの記事は経済チャンネルへ譲渡
      - 世の中経済ニュース
    categories:
      - 一般

  - name: AI・機械学習ニュース
    webex_space_id: ${WEBEX_SPACE_ID_AI}
    webex_bot_token: ${WEBEX_BOT_TOKEN_AI}
    defers_to:                     # AI×Security / AI×Network はそちらへ譲渡
      - セキュリティニュース
      - ネットワークニュース
    categories:
      - AI・機械学習
```

> Webex Bot トークンは `webex_bot_token` を省略すると `.env` の `WEBEX_BOT_TOKEN` を共通利用します。
> `${VAR}` 形式の値は実行時に環境変数（`.env`）で展開されます。

#### チャンネル間の配信制御 / Cross-channel routing

複数のカテゴリにマッチする記事を、目的に合ったチャンネルへ効率よく振り分けるために以下のロジックが順番に適用されます。

| Phase | 内容 |
|:---:|:---|
| **1. 事前フィルタ** | 各チャンネルの該当記事を抽出（キーワード + `source_groups`/`source_feeds`） |
| **1.4. source 専有** | `source_groups`/`source_feeds` を持つチャンネルは、そのフィード由来の記事を専有し、他の全チャンネル（`priority` 含む）から除外（例: Cisco Security Advisories を専用スペースへ隔離） |
| **1.5. 優先独占** | `priority: true` のチャンネルにマッチした記事を、他チャンネルから自動除外（例: Cisco記事は Cisco チャンネルでのみ配信） |
| **1.6. 譲渡 (defers_to)** | `defers_to: [...]` のチャンネルは、指定された譲渡先チャンネルにも該当する記事を譲渡先のみに残し、自分の側から除外（例: AI・機械学習はセキュリティ／ネットワーク寄りの記事を譲る） |
| **2. ニッチ優先** | 15件超の混雑チャンネルから、同じ記事が15件以下の余裕チャンネルにも該当する場合、余裕側のみに残して混雑側から除外 |
| **3. LLM再ランク** | それでも15件を超えるチャンネルでは、Claude がスコア上位40候補から**重要度順に15件を選定**（API未設定・失敗時はスコア階層＋階層内ランダム抽出にフォールバック）。詳細は[LLMによるニュース選出](#llmによるニュース選出再ランク--llm-re-ranking)参照 |

**`priority: true`**: Cisco のような専門カテゴリ向け。該当記事を独占的に配信。  
**`defers_to: [チャンネル名]`**: AI・機械学習のような汎用カテゴリで、より専門的なチャンネル（セキュリティ・ネットワーク等）にも該当する場合、そちらに譲るための設定。

```yaml
- name: AI・機械学習ニュース
  defers_to:
    - セキュリティニュース    # AI×Security の記事はセキュリティ側でのみ配信
    - ネットワークニュース    # AI×Network の記事はネットワーク側でのみ配信
  categories:
    - AI・機械学習
```

#### ソースベース振り分けと Cisco Security Advisories / Source-based routing & CVSS

記事本文のキーワードではなく **「どの RSS フィード由来か」** でチャンネルを決めたい場合は、`urls.yml` に名前付きグループを定義し、`bots.yml` の `source_groups` で参照します。URL の正本は `urls.yml` 側に一本化され、`bots.yml` にはグループ名だけを書きます。

```yaml
# urls.yml — フィードの正本（グループにまとめる）
- group: cisco-advisory
  urls:
    - https://sec.cloudapps.cisco.com/security/center/psirtrss20/CiscoSecurityAdvisory.xml
```

```yaml
# bots.yml — グループ名だけを参照（URL は書かない）
- name: "News Today : Cisco Security Advisories"
  webex_space_id: ${WEBEX_SPACE_ID_CISCO_ADVISORY}
  webex_bot_token: ${WEBEX_BOT_TOKEN_CISCO_ADVISORY}
  priority: true
  source_groups:
    - cisco-advisory   # urls.yml の group を参照
  categories: []       # キーワード分類はせず、このグループ由来のみ配信
```

- `source_groups` のフィードは `urls.yml` に定義されていれば自動で収集対象になります（別途 `urls.yml` の平文リストに重複して書く必要はありません）。
- グループ由来の記事は Phase 1.4 で他の全チャンネルから除外され、この専用スペースにのみ配信されます（セキュリティ等への重複投稿を停止）。
- `webex_space_id` / `webex_bot_token` の環境変数が未設定（未解決）の間、そのチャンネルは自動的にスキップされます（トークンを後から用意する運用に対応）。
- URL を直接書きたい場合は `source_groups` の代わりに `source_feeds:`（URL のリスト）も使えます。

**CVSS スコアの併記（危険度カラー） / Color-coded CVSS badge** — Cisco Security Advisory の記事には、Cisco 公開の構造化データ（advisory ごとの **CVRF XML**）から取得した実際の **CVSS Base Score** を、深刻度に応じた色付きバッジでタイトル行に表示します。

色は標準的な CVSS v3.x の深刻度バンドに対応します。

| CVSS Base Score | 深刻度 / Severity | 色 |
|:---:|:---|:---:|
| 9.0 – 10.0 | Critical | 🔴 |
| 7.0 – 8.9 | High | 🟠 |
| 0.1 – 6.9 | Medium / Low | 🟡 |

| ケース | 表示例 |
|:---|:---|
| 単一スコア（High） | `🟠 CVSS 7.8` |
| 単一スコア（Medium/Low） | `🟡 CVSS 5.5` |
| 複数スコア（複数 CVE） | `🔴 CVSS 7.5〜9.1（複数該当）`（最小〜最大） |
| スコアなし（事前通知等） | バッジなし |

> 複数スコアがある場合、**色は最大値（最悪ケース）** で決定します（例: `7.5〜9.1` は最大 9.1 が Critical のため 🔴）。

> CVSS は RSS 本文には含まれないため、LLM には推測させず CVRF から実値を取得します。**要約プロンプトでは CVSS を問い合わせません**（課金削減）。それでも LLM が概要文から CVSS を拾って要約に含めることがあるため、要約後に CVSS 表記を自動除去し、バッジとの二重表示を防ぎます。
>
> なお advisory の記事は、**深刻度に見合う影響（攻撃前提・想定被害）を簡潔にまとめる専用の要約プロンプト**を使います（深刻度はモデルが本文から推測。CVSS 数値はバッジ側で表示）。一般ニュース等は従来どおりの汎用要約プロンプトです。

**空チャンネルは無投稿 / Skip when empty** — 当日に該当ニュースが 0 件のスペースには、空通知も含め一切投稿しません。

### 2. キーワード設定 (`categories.yml`) / Category keywords
記事のタイトル・概要・タグ・**URL（リンク）** からカテゴリを判定するためのキーワードを定義します。  
Defines keywords used to classify articles by their title, summary, tags and **URL (link)**.

```yaml
AI・機械学習:
  - ai
  - llm
  - 生成ai
  - machine learning

セキュリティ:
  - "!security"         # ← "!" 付き = 必須語
  - "!セキュリティ"
  - "!vulnerability"
  - "!脆弱性"
  - "!ransomware"
  # 以下は通常語（補強）
  - インシデント
  - threat
  - exploit
```

#### `!` プレフィックスの意味 / Must-keyword marker

キーワードの先頭に `!` を付けると **「必須語」** として扱われます。  
通常語（`!` なし）はマッチしても加点のみですが、必須語は **「少なくとも1つはマッチしていること」が合格の絶対条件** になります。  
This `!` marker designates a keyword as a *must-match*: at least one such keyword **must** appear in the article for it to qualify.

#### スコアリングアルゴリズム / Scoring algorithm

記事が以下のすべてを満たすとそのカテゴリに **合格** し、配信対象になります。  
An article **passes** a category (and is delivered) when **all** of the following conditions are met:

| 観点 | 内容 |
|:---|:---|
| **検索対象 / Search text** | `title` + `summary` + `tags` を連結し小文字化したテキスト。**URLは `cisco` を含む場合のみ追加**（Google News等の汎用リダイレクトURLで誤マッチしないため） |
| **マッチ方式 / Match mode** | **5文字以下のASCII英数字キーワード**は単語境界 `\b` でマッチ（例：`lan` は "LAN" にはマッチするが "p**lan**" "**lan**guage" にはマッチしない）。日本語や6文字以上の英数字キーワード、複合語は従来通りの部分文字列マッチ |
| **必須語の判定** | カテゴリ内に `!` 付き語が1つでも定義されている場合、それらのうち **少なくとも1つにマッチが必要** |
| **スコア計算** | `score = (必須語マッチ数 × 3) + (通常語マッチ数 × 1)` |
| **合格ライン** | `score >= 4`（デフォルト、`webex-news-rss-bot.py` の `min_score` で変更可） |

合格・不合格の具体例 / Pass / fail examples:

| 構成 | スコア | 合否 | 補足 |
|:---|:---:|:---:|:---|
| 必須1 + 通常1 | 4点 | ✅ | 最低ライン（必須語あり） |
| 必須2 | 6点 | ✅ | 必須語2つで十分 |
| 通常4 | 4点 | ✅ | 必須語のないカテゴリでもOK |
| 必須1 のみ | 3点 | ❌ | あと1点足りず取りこぼし |
| 通常3 のみ | 3点 | ❌ | 同上 |
| 必須語が定義されているのに必須マッチなし | - | ❌ | 通常語が何件マッチしてもアウト |

> **Cisco限定のURL深度マッチ**: `blogs.cisco.com` / `community.cisco.com` 等のURLは `cisco` を含むためsearch_textに追加され、タイトルに「Cisco」と書かれていなくても `!cisco` 必須語にマッチします。一方、`news.google.com/...` のような汎用リダイレクトURLは含まれないため、Google News由来の記事が他カテゴリの通常語に誤マッチすることはありません。
>
> The URL inclusion is **limited to URLs containing `cisco`** to enable source-based auto-classification for Cisco articles while preventing false matches from generic aggregator URLs (e.g. `news.google.com/...`).

#### キーワード設計のコツ / Tuning tips

- **必須語は誤マッチしにくいブランド・製品名に限定**: 単独の `!nexus`, `!duo`, `!umbrella` 等は英語の一般語(`Belarus-nexus`等)に誤マッチするため、`!cisco nexus`, `!nexus 9000`, `!cisco duo`, `!duo security` のような **compound (複合語) 必須語**を採用しています。  
  **Keep must-keywords highly specific to brand/product names.** Single words like `!nexus`, `!duo`, `!umbrella` collide with English words (e.g. "Belarus-nexus"). Prefer compounds such as `!cisco nexus`, `!cisco duo`, `!duo security`.
- **複数形のバリアントも忘れずに**: `!vulnerability` だけだと "vulnerabilities" (複数形) にマッチしません。`!vulnerabilities`, `!exploits`, `!breaches` などの複数形も別途登録するか、語幹 `!vulnerabilit` のような部分一致語を併用してください。  
  **Don't forget plural variants.** `!vulnerability` does not match "vulnerabilities". Register plurals such as `!vulnerabilities`, `!exploits`, `!breaches`, or use a stem like `!vulnerabilit`.
- **広いカテゴリ（一般・経済等）には `!` 付き語を多めに設定** すると、雑多なRSSからのノイズを排除しやすくなります。  
  Broad categories (general news, economy, etc.) benefit from many `!` must-keywords to suppress noise.
- **トレンド語（時事の固有名詞）は陳腐化前提で定期見直し**: `categories.yml` の「── トレンド語」ブロックにコメントで最終見直し日を記録する運用にしています（最終見直し: 2026-07-13）。政権交代・紛争の終結などがあったら更新してください。  
  **Trend keywords (current-events proper nouns) rot.** Record the last-review date as a comment in the trend block and refresh periodically (last review: 2026-07-13).
- **`min_score` を変更したい場合** は [webex-news-rss-bot.py](webex-news-rss-bot.py) の `filter_by_category(..., min_score=4)` のデフォルト値を調整します。値を下げると緩く、上げると厳しくなります。  
  To change `min_score`, edit the default in `filter_by_category(..., min_score=4)`. Lower = lax, higher = strict.

#### カテゴリの現状サマリ / Current category sizes

本リポジトリの `categories.yml` の規模（参考値）：  
Approximate size of each category in this repository's `categories.yml`:

| カテゴリ | 必須語(`!`) | 通常語 | 主な用途 |
|:---|---:|---:|:---|
| 一般 | 35 | 31 | 重大な災害・事件・政治イベント |
| 経済 | 17 | 39 | 値上げ/利上げ/買収/リストラ等の経済動向 |
| AI・機械学習 | 21 | 22 | OpenAI/Anthropic/Claude/LLM/Agentic AI |
| セキュリティ | 26 | 61 | CVE・脆弱性・ランサムウェア・APT等 |
| ネットワーク | 23 | 60 | SD-WAN/SASE/ZTNA/Wi-Fi/5G/プロトコル |
| クラウド | 19 | 73 | AWS/Azure/GCP/Kubernetes/データセンター |
| Cisco | 42 | 108 | Cisco固有ブランド + compound必須語 |

### 3. RSSフィード設定 (`urls.yml`) / RSS feed list
ニュースの収集元となるRSSフィードURLの一覧を管理します。各要素は **文字列（通常のURL）** または **名前付きグループ** のどちらでも記述できます。  
Lists the RSS feed URLs to collect articles from. Each item is either a plain URL string or a named group.
```yaml
# 通常のフィード（文字列）
- https://blogs.cisco.com/feed
- https://zenn.dev/topics/aiagent/feed
- https://b.hatena.ne.jp/search/tag?q=AI&mode=rss

# 名前付きグループ（bots.yml の source_groups から参照）
- group: cisco-advisory
  urls:
    - https://sec.cloudapps.cisco.com/security/center/psirtrss20/CiscoSecurityAdvisory.xml
```
> グループは、特定フィード由来の記事を専用チャンネルへ振り分けるための仕組みです。詳細は[ソースベース振り分けと Cisco Security Advisories](#ソースベース振り分けと-cisco-security-advisories--source-based-routing--cvss)を参照。

### 4. 朝メッセージ署名設定 (`morning_messages.txt`) / Morning footer phrases
配信メッセージの末尾にランダムで追加される署名フレーズを1行ずつ記述して管理します。  
List of footer phrases (one per line) randomly appended to the end of each delivered Webex message.
```text
Your daily news briefing, delivered around X AM sharp. 毎朝X時頃、デイリーニュースブリーフィングをお届けします。
Stay ahead of the curve: Your daily digest arrives around X AM. 常に先を行くために。毎朝X時頃に最新情報を配信します。
```

---

## プライベートカテゴリ運用（my-fab パターン）/ Private Category Usage

公開リポジトリに **自社名・パートナー名・社内ブランド名** を直接書きたくない場合のための仕組みです。2つの方法を組み合わせて、機密情報をコードから完全に分離できます。  
This section describes how to keep **company names, partner names, and internal brand names** out of your public repository. Two complementary mechanisms let you fully isolate sensitive data from the committed codebase.

---

### 方法1: `categories-private.yml` — 非公開キーワードオーバーレイ

`categories.yml` と同じディレクトリに `categories-private.yml` を置くと、起動時に自動的に読み込まれ、`categories.yml` の内容に **追加マージ** されます。このファイルは `.gitignore` で管理対象外になっているため、リポジトリには一切含まれません。  
テンプレートとして `categories-private.yml.example` が同梱されています。コピーして使い始めてください。  
A template is included as `categories-private.yml.example`. Copy it to get started:  
Place a `categories-private.yml` file in the same directory as `categories.yml`. It is automatically loaded at startup and **merged into** the existing category definitions. Because it is listed in `.gitignore`, it is never committed to the repository.  
A starter template is included as `categories-private.yml.example`:

```bash
cp categories-private.yml.example categories-private.yml
```

#### できること / What you can do

| 操作 | 説明 |
|:---|:---|
| **既存カテゴリへのキーワード追加** | 公開 `categories.yml` の `Cisco` や `セキュリティ` に、社内固有のキーワードを追記 |
| **新規プライベートカテゴリの追加** | 公開ファイルには存在しない完全新規のカテゴリ（例: 自社ブランド名）を丸ごと定義 |

**Merging into an existing category / 既存カテゴリへ追加:**
```yaml
# categories-private.yml
Cisco:
  - "!my internal product"   # Ciscoカテゴリに社内製品名の必須語を追加
  - my-internal-alias

セキュリティ:
  - "!社内SIEM"
  - "!インシデント対応"
```
起動ログに以下が出力されれば正常にマージされています：  
If merged successfully, the startup log will show:
```
[INFO] categories-private.yml をマージ: 既存追加=[Cisco(+2), セキュリティ(+2)], 新規=[]
```

**Adding a brand-new private category / 新規カテゴリとして追加:**
```yaml
# categories-private.yml
自社ブランド:          # ← 公開 categories.yml には存在しない完全新規カテゴリ
  - "!自社ブランド名"
  - "!MyFab"
  - 社内プロダクト
  - my-fab
```
```
[INFO] categories-private.yml をマージ: 既存追加=[], 新規=[自社ブランド(15)]
```

---

### 方法2: `${VAR}` 環境変数展開 — YAMLに会社名を直書きしない

`categories.yml` や `bots.yml` の中で **`${VAR}` 形式のプレースホルダー** を使うと、実行時に `.env` の値で展開されます。YAML ファイル自体には会社名が含まれないため、そのままリポジトリに公開できます。  
Use **`${VAR}` placeholders** inside `categories.yml` and `bots.yml`. They are resolved at runtime from `.env`. The YAML files themselves contain no sensitive names and can be safely committed.

#### `categories.yml` での使い方 / Usage in `categories.yml`

キーワード値だけでなく、**カテゴリ名（キー）自体**も `${VAR}` で展開できます。  
Both keyword values and **category name keys** support `${VAR}` expansion.

```yaml
# categories.yml（公開リポジトリにそのままコミット可）
${MY_FAB_BRAND}:           # カテゴリ名ごとプレースホルダー化
  - "!${MY_FAB_KEYWORD1}"  # 必須キーワードも変数化
  - "!${MY_FAB_KEYWORD2}"
  - my-fab                 # 機密性のない汎用語はそのまま書いてOK

Cisco:
  - "!${MY_PARTNER_ALIAS}"  # 特定キーワードだけを変数化
  - "!cisco"
```

```dotenv
# .env（gitignore済み）
MY_FAB_BRAND=自社ブランド
MY_FAB_KEYWORD1=MyFab
MY_FAB_KEYWORD2=my-fab-product
MY_PARTNER_ALIAS=FabPartner
```

実行時に展開される結果 / Runtime result:
```yaml
# 展開後のイメージ（実際にはメモリ内のみ）
自社ブランド:
  - "!MyFab"
  - "!my-fab-product"
  - my-fab

Cisco:
  - "!FabPartner"
  - "!cisco"
```

環境変数が未定義の場合、そのキーワードはスキップされ警告が出ます：  
If an env var is undefined, the keyword is skipped with a warning:
```
[WARN] categories.yml: 環境変数 ['MY_FAB_KEYWORD1'] が未定義のためキーワード '!${MY_FAB_KEYWORD1}' をスキップ
```

#### `bots.yml` での使い方 / Usage in `bots.yml`

チャンネル名・Space ID・Bot トークン・カテゴリ名のすべてを `${VAR}` で秘匿できます。  
Channel name, Space ID, Bot token, and category name can all be hidden with `${VAR}`.

```yaml
# bots.yml（公開リポジトリにそのままコミット可）
channels:
  - name: ${MY_FAB_BRAND}ニュース        # チャンネル名を変数化
    webex_space_id: ${WEBEX_SPACE_ID_MYFAB}
    webex_bot_token: ${WEBEX_BOT_TOKEN_MYFAB}
    priority: true
    categories:
      - ${MY_FAB_BRAND}                  # カテゴリ名も変数化
```

```dotenv
# .env（gitignore済み）
MY_FAB_BRAND=自社ブランド
WEBEX_SPACE_ID_MYFAB=Y2lzY29zcGFyazovL3...
WEBEX_BOT_TOKEN_MYFAB=NWQxYmU5ZW...
```

---

### 2つの方法の使い分け / When to use each

| 状況 | 推奨方法 |
|:---|:---|
| キーワードが多い・将来的に増える | `categories-private.yml` オーバーレイ（YAML として管理しやすい） |
| 既存カテゴリに数語だけ追加したい | `${VAR}` 展開（別ファイルを作らずに済む） |
| チャンネル名・Space ID を公開したくない | `bots.yml` の `${VAR}` 展開一択 |
| 新規チャンネルごと非公開にしたい | 両方の組み合わせ（`bots.yml` で `${VAR}`、キーワードは `categories-private.yml`） |

> **組み合わせ例 / Combined example**: `bots.yml` に `${MY_FAB_BRAND}` でチャンネルを定義し、キーワードは `categories-private.yml` に `${MY_FAB_BRAND}` カテゴリとして書く。`.env` で `MY_FAB_BRAND=自社ブランド` を設定するだけで両方が連動する。

---

## Claudeによる自動要約 ＆ 超エコノミーモード / LLM Summarization & Eco-mode

本スクリプトは、**Claude API** を用いて収集したニュースの概要を自然な日本語1〜2文（110字以内）に自動要約します。英文RSSは自動で日本語に翻訳されます。APIの課金を抑えるため、以下の**「超エコノミーモード（超節約設計）」**が自動適用されます。  
This script uses the **Claude API** to summarize each article into 1–2 natural Japanese sentences (≤110 chars). English RSS is auto-translated to Japanese. The following **eco-mode** optimizations are applied automatically to minimize API spend:

### 1. プロンプト極小化（約22トークン）/ Minimal prompt (~22 tokens)
指示プロンプトを以下の最短形に圧縮し、入力トークンを約89%削減：  
The instruction prompt is compressed to the shortest practical form, cutting input tokens by ~89%:
```
日本語110字以内1〜2文で要約のみ出力。
ラベル/前置き/改行/情報不足要求は禁止。
提供情報のみで完結、英文は翻訳。
T: {title}
S: {summary}
```
これにより `タイトル：`/`概要：` のような不要ラベルや「本文を提供してください」のような追加情報要求も発生しません。  
This prevents unwanted labels (`タイトル：`/`概要：`) or info-request replies ("please provide the article body").

### 2. SKIP-API（自動要約スキップ・API課金ゼロ）/ Skip Claude when not needed (zero API cost)
元のRSSから取得した概要が、以下の **すべて** を満たす場合はClaudeを呼ばずそのまま採用：  
If the original RSS summary satisfies **all** of the following, Claude is not called and the original text is used as-is:
- 文字数が **100文字以下** / Length ≤ **100 characters**
- 末尾が「...」「…」「続きを読む」「more」で途切れていない / Not truncated by `...` / `…` / `続きを読む` / `more`
- HTMLエンティティ（`&nbsp;`, `&gt;` 等）を含まないクリーンな文章 / Clean text without HTML entities (`&nbsp;`, `&gt;`, etc.)
- **日本語（ひらがな・カタカナ・漢字）を1文字以上含む** / Contains at least one Japanese character (hiragana/katakana/kanji)

### 3. 英文の自動翻訳 / Auto-translate English to Japanese
SKIP-API条件のうち「日本語含有」を満たさない記事（=純英文）は、たとえ短くても **必ずClaudeで日本語翻訳＋要約** します。  
Pure English articles (no Japanese chars) are **always** sent to Claude, even when short, to be translated and summarized.  
→ 例 / Example: `"SpaceX Falcon 9 launches Starlink mission from Florida"` → `"SpaceXのファルコン9ロケットがフロリダからStarlink衛星打ち上げミッションを実施した。"`

### 4. 要約キャッシュ / In-memory summary cache
複数チャンネルに同一URL記事が出現した場合、初回の要約結果をメモリにキャッシュして2回目以降は再利用（API再呼び出しを完全に回避）。  
When the same article URL appears in multiple channels, the first summary is cached in memory and reused (no re-call to the API).

### 5. 最大出力制限 / Hard output cap
Claudeからの返答を **`max_tokens = 140`** に強制制限し、出力の膨張を防止。  
Claude responses are hard-capped at **`max_tokens = 140`** to prevent runaway output.

### コスト削減効果（参考）/ Cost saving (rough estimate)
1日200記事に要約をかける場合：For 200 article summaries per day:
- **旧プロンプト / Old prompt**: ~200 tokens × 200 articles = 40,000 input tokens / day
- **新プロンプト / New prompt**: ~22 tokens × 200 articles = **4,400 input tokens / day (~89% reduction)**

---

## LLMによるニュース選出（再ランク） / LLM Re-ranking

1チャンネルの配信上限は15件です。キーワードスコアリング合格後も15件を超えるチャンネル（AI・一般など混雑カテゴリ）では、**Claude が最終選出**を行います。  
Each channel delivers at most 15 articles. When more than 15 candidates pass keyword scoring, **Claude makes the final pick**.

### 仕組み / How it works

1. 合格記事を **スコア降順 → 公開日時降順** で並べ、上位 **40件** に絞る（トークン節約）
2. 各候補の「タイトル / 概要先頭120字 / 公開日時(JST) / ソースドメイン」を1コールで Claude（`ANTHROPIC_RERANK_MODEL`）に渡す
3. 読者プロフィール（**日本の Cisco Systems SE：ネットワーク/セキュリティ/AI の実務者**）を基準に、①業務への関連度 ②影響の大きさ・新規性 ③話題の多様性 で重要度順に15件のインデックスを JSON で返させる
4. 応答のパースに失敗・API エラー時は、従来の **スコア階層化抽出（同一スコア帯内のみランダム）** に自動フォールバック

ログで採否を確認できます / Check adoption in the run log:
```
LLM再ランク採用 (claude-haiku-4-5-20251001)        ← 再ランクが機能
LLM再ランク失敗 → stratified_pick にフォールバック   ← フォールバック発動
15件以下（再ランク不要）                            ← そもそも枠内
```

### コスト / Cost
再ランクは **15件超のチャンネルにつき1コール**（max_tokens=200）のみ。要約のエコノミーモードと合わせても、1日あたりの追加コストは Haiku 数コール分に収まります。  
Re-ranking costs a single API call (max_tokens=200) per over-limit channel — a few Haiku calls per day at most.

---

## 自動実行 / Automation (cron / launchd)

定期的にスクリプトを自動実行し、Webexに最新ニュースを流すには、OSに合わせてスケジュール実行を設定します。
**macOS環境の場合、Macがスリープ（画面ロック）していると `cron` は指定時刻に動作しないことがあるため、`launchd` (plist) の利用を強く推奨します。**

### macOS の場合: launchd (推奨)

> **✅ 推奨構成（v1.1.0〜）: TCC 保護外のパスにリポジトリを置いて直接実行**  
> リポジトリを `~/Developer/rss-bot` のような **TCC 保護対象外のフォルダ**に置く場合、コピーデプロイは不要です。launchd の plist からこのリポジトリの `run_rssbot.sh` を直接指定してください（`run_rssbot.sh` は自身の場所を基準に動作します）。ログはリポジトリ内 `log/` にタイムスタンプ付きで出力されます。  
> If the repo lives outside TCC-protected folders (e.g. `~/Developer/rss-bot`), point launchd directly at `run_rssbot.sh` — no copy-deploy needed.

以下は、リポジトリが `~/Documents` など **TCC 保護下にある場合**の従来方式です。macOSのセキュリティ機能により、`Documents` や `Desktop` などの保護されたフォルダ内ではバックグラウンド実行がブロックされてしまう場合があります。そのため、ホームディレクトリ直下 (`~/rss-bot`) に専用の実行環境を構築・同期するデプロイスクリプトを用意しています。

**デプロイスクリプトの実行**
初めてセットアップする際、およびソースコードや設定ファイル（`bots.yml`等）を更新した後は、ターミナルで以下のスクリプトを実行してください。

```bash
bash deploy_to_launchd.sh
```

このスクリプトは以下の処理を自動で行います。
- `~/rss-bot` フォルダへコードと設定をコピー（同期）
- 必要なPythonライブラリ（仮想環境）の自動セットアップ
- `launchd` 用の plist ファイルを生成し、システムへ登録・有効化

> **日々の運用（アップデート）方法**: 
> 普段の設定変更（`.env` や `.yml` の編集）は、これまで通り現在の `Documents` 配下のフォルダで行ってください。編集が終わったら `bash deploy_to_launchd.sh` を叩くだけで、最新の状態が `launchd` の本番環境（`~/rss-bot`）に反映されます。

> **ヒント / Tips**:
> - 手動で今すぐテスト実行したい場合: `launchctl start com.webex-news.rssbot`
> - 実行ログの確認: `~/rss-bot/log/launchd_run-YYYYMMDD-HHMMSS.log` に出力されます（実行ごとにタイムスタンプ付きで生成）。
> - Manual test run: `launchctl start com.webex-news.rssbot`
> - View logs: `~/rss-bot/log/launchd_run-YYYYMMDD-HHMMSS.log` (timestamped per run; located under `~/` to bypass macOS TCC protection of `Documents/`)

#### ⏰ Mac スリープ対策（重要）/ Critical: Wake Mac from Sleep

**問題**: macOS の `launchd` は `StartCalendarInterval` の予定時刻に **Mac がスリープ中だと job を起動しません**。
出張や夜間電源OFFで Mac が完全スリープしていた日は、その日の自動配信がスキップされます。

**Problem**: macOS `launchd` does **not** fire `StartCalendarInterval` jobs while the Mac is asleep. Days when the Mac is suspended at the scheduled time will have **no delivery**.

**解決策 / Solution**: `pmset` で毎朝 Mac を自動起動するスケジュールを登録します。
Register an auto-wake schedule with `pmset` so the Mac is awake before launchd fires.

```bash
# 月～金の 08:55 に Mac を自動起動 (job は 09:01 に走る)
# Wake the Mac at 08:55 on weekdays (job fires at 09:01)
sudo pmset repeat wakeorpoweron MTWRF 08:55:00
```

設定確認・解除コマンド / Verify and cancel commands:

```bash
pmset -g sched              # 現在のスケジュール確認 / View current schedule
sudo pmset repeat cancel    # 解除 / Cancel the repeating wake
```

確認すると以下のように出れば成功 / Expected output:
```
Repeating power events:
  wakepoweron at 8:55AM weekdays only
```

##### `wakeorpoweron` の挙動 / Wake action semantics

- `wakeorpoweron`: Mac がスリープなら起こす、電源OFFなら自動起動。**最も確実**。
- `wake`: スリープのみ起こす (電源OFFでは起動しない)
- `poweron`: 電源OFFのみ起動 (スリープからは起こさない)
- `wakeorpoweron`: wakes from sleep or powers on if shutdown. **Most reliable**.

##### 注意点 / Caveats

- **ノートPCのクラムシェル閉**（蓋を閉じて外部ディスプレイ運用）状態の場合：
  - 電源接続 + 外部モニタ接続 → wake する
  - バッテリー駆動 + 蓋閉じ → **macOS は wake しない仕様**（バッテリー保護のため）
- 出張等で Mac を物理的に閉じて持ち出した場合、その日の朝の自動実行は諦めるか、午前中に Mac を開いた時点で launchd が past schedule を catch-up することを期待する形になります。
- For clamshell-mode laptops: wake works **only** when both power adapter and external display are connected. Battery-only with the lid closed does not wake.

### Linux 等の場合: cron

Linux環境などでcronを使用する場合は以下の通り設定します。

```bash
crontab -e
```

以下の行を記述します（毎日午前9時に実行。パスは環境に合わせて変更してください）：
```cron
0 9 * * * /<folder name>/rss-bot/bin/python /<folder name>/rss-bot/webex-news-rss-bot.py >> /<folder name>/rss-bot/log/cron_run.log 2>&1
```

---

## macOS の制限と設計上の理由 / macOS Restrictions & Design Rationale

### なぜ `cron` ではなく `launchd` (plist) を使うのか / Why launchd instead of cron

macOS では **`cron` はスリープ中に動作しません**。予定時刻に Mac がスリープしていると、その実行はそのままスキップされます。一方 `launchd` はスリープから復帰した際に missed job を実行できるため、毎朝確実にニュースを届けるには `launchd` が必須です。また Apple は公式に `cron` の代替として `launchd` を推奨しています。  
On macOS, **`cron` does not fire while the Mac is asleep**. If the Mac is sleeping at the scheduled time, the job is simply skipped. `launchd`, macOS's native scheduler, can catch up on missed jobs after the system wakes. Apple officially recommends `launchd` as the modern replacement for `cron`.

| 比較 / Comparison | `cron` | `launchd` (plist) |
|:---|:---:|:---:|
| スリープ復帰後に missed job を実行 / Catch up after sleep | ❌ | ✅ |
| macOS 公式推奨 / Officially recommended by Apple | ❌ | ✅ |
| ログ・環境変数の細かい制御 / Fine-grained log & env control | ❌ | ✅ |
| Linux でも使える / Works on Linux | ✅ | ❌ |

---

### なぜスクリプトを `~/rss-bot`（ホーム直下）にコピーするのか / Why copy scripts to `~/rss-bot`

macOS には **TCC（Transparency, Consent, and Control）** と呼ばれるプライバシー保護機能があり、`~/Documents`・`~/Desktop`・`~/Downloads` などのフォルダへのアクセスはユーザーの明示的な許可が必要です。  
macOS enforces **TCC (Transparency, Consent, and Control)**, a privacy protection mechanism that requires explicit user approval to access folders such as `~/Documents`, `~/Desktop`, and `~/Downloads`.

**問題 / The problem**: `launchd` はシステムデーモンとして動作するため、この TCC 許可を持っていません。`~/Documents` 配下のスクリプトをそのまま実行しようとすると、ファイルの読み書きがサイレントにブロックされたり、ログが出力されないまま失敗したりします。  
**Problem**: `launchd` runs as a system daemon and does not hold TCC permissions. Executing scripts directly under `~/Documents` can result in silently blocked file I/O or missing log output.

```
~/Documents/98.Tools/python/rss-bot/   ← 🔒 TCC 保護対象 / TCC-protected (launchd からアクセス不可 / inaccessible to launchd)
~/rss-bot/                             ← ✅ 保護対象外 / Not TCC-protected (launchd から自由にアクセス可 / freely accessible)
```

**解決策 / Solution**: `deploy_to_launchd.sh` がスクリプトと設定を `~/rss-bot` へコピー（同期）した上で、`launchd` はそこから実行します。これにより TCC の制限を回避できます。  
`deploy_to_launchd.sh` syncs scripts and configs into `~/rss-bot`, where `launchd` runs them — bypassing TCC restrictions entirely.

**副次的なメリット / Additional benefits**:

| メリット | 内容 |
|:---|:---|
| **開発と本番の分離** | `~/Documents` 配下で設定を編集しても、`deploy` を叩くまで本番に反映されない |
| **ログの確実な書き出し** | `~/rss-bot/log/` への書き込みが TCC に邪魔されない |
| **デプロイの明示化** | 誤った設定変更が即座に本番へ影響するリスクがない |

```
📝 ~/Documents/.../rss-bot/   ← 開発・編集はここで / Edit here
        ↓  bash deploy_to_launchd.sh
🚀 ~/rss-bot/                  ← launchd が実行する本番環境 / Production env for launchd
```

---

## Windows での利用 / Running on Windows

本スクリプトの Python コード本体（`webex-news-rss-bot.py`）は `os.path` を使用しており、**Windows でもそのまま動作します**。スケジュール実行のみ OS 固有の対応が必要です。  
The core Python script (`webex-news-rss-bot.py`) uses `os.path` and **runs on Windows without modification**. Only the scheduling mechanism needs OS-specific handling.

### macOS との対応関係 / macOS → Windows mapping

| macOS | Windows | 備考 |
|:---|:---|:---|
| `launchd` + `.plist` | **タスクスケジューラ** (Task Scheduler) | GUI または `schtasks` コマンドで設定 |
| `deploy_to_launchd.sh` (bash) | **`deploy_to_taskscheduler.ps1`** (PowerShell) | 現時点では未同梱（下記参照） |
| `~/rss-bot` へのコピー | **不要** | Windows に TCC 相当の制限はない |
| `pmset` スリープ対策 | **不要** | タスクスケジューラはスリープ復帰後に実行可能 |

### Windows でのセットアップ手順 / Setup on Windows

#### 1. Python の仮想環境を作成・有効化 / Create and activate venv
```powershell
cd C:\path\to\rss-bot
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

#### 2. タスクスケジューラへの登録 / Register with Task Scheduler

PowerShell から以下のコマンドで、毎日 09:01 に実行するタスクを登録できます。  
Run the following PowerShell command to register a daily task at 09:01:

```powershell
$action  = New-ScheduledTaskAction `
    -Execute "C:\path\to\rss-bot\venv\Scripts\python.exe" `
    -Argument "C:\path\to\rss-bot\webex-news-rss-bot.py" `
    -WorkingDirectory "C:\path\to\rss-bot"
$trigger = New-ScheduledTaskTrigger -Daily -At "09:01"
$settings = New-ScheduledTaskSettingsSet -WakeToRun  # スリープ復帰して実行
Register-ScheduledTask -TaskName "webex-news-rss-bot" `
    -Action $action -Trigger $trigger -Settings $settings -RunLevel Highest
```

> `-WakeToRun` オプションにより、タスク実行時刻に PC がスリープ中でも自動的に復帰して実行されます（BIOS/UEFI の Wake Timer が有効な場合）。  
> `-WakeToRun` wakes the PC from sleep at the scheduled time if the BIOS/UEFI Wake Timer is enabled.

#### 3. 手動テスト実行 / Manual test run
```powershell
python webex-news-rss-bot.py --dry-run
```

### 現時点での制限 / Current limitations

- `deploy_to_launchd.sh` に相当する **Windows 用デプロイスクリプト（PowerShell）は現時点では未同梱** です。需要があれば追加予定です。  
  A Windows equivalent of `deploy_to_launchd.sh` (PowerShell) is **not yet included**. It may be added in a future release.
- `.env` の読み込みは `python-dotenv` が担うため、Windows でも動作します。  
  `.env` loading via `python-dotenv` works on Windows without changes.

---

## ファイル構成 / File Structure

```text
rss-bot/
├── webex-news-rss-bot.py     # メインの実行スクリプト (ニュース収集・要約・配信)
├── analyze_filter.py          # フィルタ動作診断ツール (合格/near-miss/不一致を可視化)
├── check_rooms.py             # Webex ルーム名・ID確認ツール
├── webex_listener_bot.py      # Webex リスナーBot補助ツール
├── deploy_to_launchd.sh       # ~/rss-bot へ同期＆launchd登録するデプロイスクリプト
├── webex-news-rss-bot.plist   # launchd 用 plist テンプレート（com.webex-news.rssbot）
├── categories.yml             # キーワードによるカテゴリ分け設定（必須語/通常語）
├── bots.yml                   # 配信チャンネル・カテゴリ紐付け（priority/defers_to対応）
├── bots.yml.example           # bots.yml テンプレート
├── categories-private.yml.example  # 非公開キーワードオーバーレイのテンプレート
├── urls.yml                   # 取得元RSSフィードURLリスト (約170件)
├── morning_messages.txt       # 朝メッセージ（投稿末尾のランダム署名）のリスト
├── requirements.txt           # 依存ライブラリ一覧
├── .env                       # 認証情報＆環境変数（Git対象外）
├── .env.example               # 環境変数のテンプレート
├── .gitignore                 # Git除外設定
├── log/                       # 実行ログディレクトリ（launchd_run-YYYYMMDD-HHMMSS.log / launchd_err-YYYYMMDD-HHMMSS.log）
└── README.md                  # このドキュメント
```

### 補助ツール / Auxiliary tools

#### `analyze_filter.py` - フィルタ診断
カテゴリフィルタの動作を可視化する診断スクリプト。各カテゴリで「合格」「あと一歩(near_miss)」「通常語のみマッチ」「完全不一致」の内訳を表示します。

```bash
./bin/python analyze_filter.py                  # 全カテゴリ
./bin/python analyze_filter.py Cisco セキュリティ  # 指定カテゴリのみ
```

#### `deploy_to_launchd.sh` - launchd 自動デプロイ
コードと設定を `~/rss-bot` へ同期し、launchd plist を生成・登録します。詳細は次節を参照。

---

## トラブルシューティング / Troubleshooting

### ❌ `[WARN] SSL証明書検証に失敗。verify=Falseで再試行: ...`
* これは **エラーではなく情報ログ** です。SSLフォールバック機能により、`verify=False` で自動リトライしています。Anthropic/HuggingFace等の証明書チェーンが解決できないサイトでも自動的に取得を継続します。
* **根本対処**（任意）: macOSのPython証明書をインストール
  ```bash
  open "/Applications/Python 3.13/Install Certificates.command"
  ```

### ❌ Claude API が呼ばれない / 要約が機能しない
* **原因1**: シェル環境変数に `ANTHROPIC_API_KEY=''` (空文字) が設定されているケース。
  * **対処**: `unset ANTHROPIC_API_KEY` または新しいターミナルを開いて `.env` 値を読み込ませる。本スクリプトは `load_dotenv(override=True)` で .env を優先しますが、念のため確認してください。
* **原因2**: モデル名が無効 (`404 Client Error: Not Found`)
  * **対処**: `.env` の `ANTHROPIC_MODEL` を `claude-haiku-4-5-20251001` 等の有効なモデル名に修正。

### ❌ Cisco チャンネルに無関係な記事が混入
* **原因**: 必須語が英語の一般語と被って誤マッチ。
  * 例: `!nexus` → "Belarus-nexus" (関連の意) にマッチ
  * 例: `!umbrella` → "under the umbrella of" にマッチ
* **対処**: 単独必須語を **compound (複合語)** に変更（`!cisco nexus`, `!nexus 9000`, `!cisco umbrella` 等）。本リポジトリの Cisco カテゴリは既にこの対応済み。

### ❌ チャンネルが空になる / 該当記事が0件
* `analyze_filter.py` で診断します：
  ```bash
  ./bin/python analyze_filter.py Cisco セキュリティ
  ```
* 「必須OKだがスコア不足 (near_miss)」が多い → そのカテゴリの通常語を増やすかスコア閾値を下げる
* 「通常語のみマッチ・必須語ゼロ」が多い → 必須語のカバレッジが足りない可能性

### ❌ ある日 launchd が実行されなかった (Webex に配信が来なかった)

**症状 / Symptom**: 平日のはずなのに `~/rss-bot/log/` にその日付のログファイルが存在しない。

**原因 / Cause**: その日の予定時刻 (例: 09:01) に **Mac がスリープしていた**。macOS の launchd は `StartCalendarInterval` 予定時刻に Mac がスリープ中だと job を起動しません。  
The Mac was asleep at the scheduled time. macOS `launchd` does **not** fire `StartCalendarInterval` jobs while asleep.

**確認方法 / Verification**:
```bash
# 実行履歴の確認
ls -lt ~/rss-bot/log/ | head -10

# 現在のスケジュール wake が登録されているか
pmset -g sched
```

`Repeating power events: wakepoweron at 8:55AM weekdays only` が出ていない場合、未設定です。

**対処 / Fix**: 上記「自動実行 / Automation」→「Mac スリープ対策」セクション参照。下記コマンドで毎朝の自動 wake を有効化してください。

```bash
sudo pmset repeat wakeorpoweron MTWRF 08:55:00
```

ノートPC をクラムシェル閉で持ち出していた日は、それでも wake しません。出張時は手動で蓋を開けた時点で `launchctl start com.webex-news.rssbot` で即実行できます。  
For laptops in clamshell mode on battery, wake is impossible. On travel days, manually run `launchctl start com.webex-news.rssbot` after opening the lid.

---

## 更新履歴 / Version History

| Version | 日付 / Date | 主な変更 / Changes |
|:---|:---|:---|
| **v1.1.0** | 2026-07-13 | **ニュース選出と性能の大型アップデート / Selection & performance overhaul**<br>・**LLM再ランク導入**: 15件超のチャンネルは Claude が重要度順に15件を選定（従来のランダム抽出を置換。失敗時は自動フォールバック）。env `ANTHROPIC_RERANK_MODEL` 追加<br>・**フィード取得の並列化**: ホスト別に最大12並列（同一ホストは1秒間隔を維持）で実行時間を大幅短縮<br>・**重複排除の強化**: 英語タイトルの単語Jaccard判定（⑤）を追加、正規化・bigramの前計算で高速化<br>・**バグ修正**: `_score` が複数チャンネル間で上書きされる問題を修正（チャンネル別に独立スコア化）<br>・**ソースベース振り分け**: `source_groups` / `source_feeds` で特定RSSフィード由来の記事を専用チャンネルへ専有配信（Cisco Security Advisories 分離用）。URL正本は `urls.yml` のグループ定義に一元化<br>・`check_rooms.py` 関数化＋`--find` オプション追加<br>・トレンド語の定期見直し（2026-07-13: ガザ/スーダン/主要語の英語版を追加）<br>・README: TCC保護外パス（例 `~/Developer`）での直接実行を推奨構成として明記 |
| v1.0.4 | 2026-06-11 | launchd 実行ログをラッパースクリプト経由の**タイムスタンプ付きファイル**に変更（実行ごとに `log/launchd_run-YYYYMMDD-HHMMSS.log` を生成） |
| v1.0.3 | 2026-06-03 | README に **macOS の制限と設計上の理由**（launchd/TCC）および **Windows での利用**（タスクスケジューラ）セクションを追加 |
| v1.0.2 | 2026-06-03 | `.env.example` を全変数のドキュメント付きに拡充 |
| v1.0.1 | 2026-06-03 | MIT LICENSE を追加 |
| v1.0.0 | 2026-06-03 | 初版リリース: RSS並行収集・スコアリング型カテゴリフィルタ・マルチチャンネル配信（priority/defers_to/ニッチ優先再配分）・漢字bigramハイブリッド重複排除・Claude自動要約（超エコノミーモード）・プライベートカテゴリ運用（my-fabパターン）・launchdデプロイ |

---

### ❌ CISA や community.cisco.com が 403 になる
* 以前のバージョンではブラウザ風UA（Mozilla/Chrome）を使っており、これらのbot保護サイトで403が出ていました。現バージョンは `rss-bot/1.0` という **フィードリーダ系UA** を採用しており、多くのサイトで改善します。
* ただし **2026-07 現在、community.cisco.com はフィードリーダ系UAでも403を返す**ことが確認されています（サイト側のbot対策強化）。該当フィードのエラーはスクリプト内で握りつぶされ、他のフィードの収集は継続します。恒久対応（フィードの代替URL化・削除）は検討中です。
  As of 2026-07, community.cisco.com rejects even feed-reader UAs (403). These per-feed errors are caught and do not stop the run.

---

*Developed with ❤️ for webex-news-rss-bot*
