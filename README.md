# webex-news-rss-bot

![Version](https://img.shields.io/badge/version-v1.0.0-blue)
![Release Date](https://img.shields.io/badge/release-2026--05--25-green)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

**Version**: `v1.0.0` ／ **Release Date**: 2026-05-25

> **RSS → Webex Bot ニュース通知 ＆ LLM自動要約スクリプト / RSS-to-Webex News Notifier with LLM Summary**

カテゴリキーワードに基づいて当日のRSSニュースを収集し、重複排除やClaudeによる自動要約を行った上で、Webex Bot経由で複数の指定スペースに自動配信する高機能ニュース通知スクリプトです。  
A Python script that collects today's RSS news, deduplicates, automatically summarizes using Claude API (LLM), and notifies Webex spaces via Bot.

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
- [Claudeによる自動要約 ＆ 超エコノミーモード / LLM Summarization & Eco-mode](#claudeによる自動要約--超エコノミーモード--llm-summarization--eco-mode)
- [自動実行 / Automation (cron)](#自動実行--automation-cron)
- [ファイル構成 / File Structure](#ファイル構成--file-structure)
- [トラブルシューティング / Troubleshooting](#トラブルシューティング--troubleshooting)

---

## 機能 / Features

| 機能 | 用途・詳細 | Description |
|:---|:---|:---|
| **複数RSSの一括取得** | `urls.yml` に登録した約170フィードを順次取得（フィード間 1秒sleep） | Sequential fetching from ~170 feeds |
| **スコアリング型カテゴリフィルタ** | `categories.yml` に定義したキーワードを **必須語(`!`)×3点 + 通常語×1点** でスコア計算、`>=4点`で合格 | Weighted keyword scoring (must×3 + normal×1, threshold 4) |
| **単語境界マッチ** | 5文字以下の英数字キーワードは `\b` で境界判定（`lan`は `LAN`にマッチするが`plan`にはマッチしない） | Word-boundary regex for short ASCII keywords |
| **Cisco限定URL深度マッチ** | URLに `cisco` を含む記事のみ URL文字列を判定対象に追加（Google News等の汎用URLによる誤マッチを防止） | URL inclusion limited to cisco domains |
| **マルチチャンネル配信** | `bots.yml` に基づき、複数Webexスペースへカテゴリ毎に自動配信 | Route different categories to separate spaces |
| **優先独占チャンネル** | `priority: true` のチャンネル（Cisco等）は該当記事を他チャンネルから除外して独占配信 | Priority channel claims its articles exclusively |
| **チャンネル間譲渡 (defers_to)** | 汎用チャンネル（AI・機械学習・世の中 等）から専門チャンネル（セキュリティ/ネットワーク/経済）へ自動譲渡 | Auto-defer articles to more specific channels |
| **ニッチ優先再配分** | 15件超の混雑チャンネルから、同じ記事が15件以下の余裕チャンネルにも該当する場合、余裕側のみに残して混雑側から除外 | Crowded→spacious redistribution |
| **高度な重複排除** | 媒体名(`(共同通信)`等)除去後、①タイトル類似度85%以上、②漢字bigram Jaccard 20%以上、③漢字bigram Overlap 50%以上+共通5件以上、④タイトル55%+概要55% のいずれかで統合し **最新公開日時の記事を採用** | Hybrid 4-way dedup with kanji-bigram Jaccard/Overlap for Japanese; keeps the most recent |
| **SSLフォールバック** | SSL証明書検証失敗時に自動で `verify=False` リトライ（HuggingFace等のmacOS証明書問題に対応） | Auto-fallback to `verify=False` on SSL failure |
| **フィードリーダ系User-Agent** | `rss-bot/1.0` UAでCISA・community.cisco.com等のbot対策サイトに対応 | Feed-reader UA bypasses anti-bot blocks |
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

`.env` を開き、使用するトークンやAPIキーを設定します。  
Open `.env` and fill in your tokens / API keys:
```dotenv
# Webex Botトークン (共通デフォルト用) / Webex Bot token (shared default)
WEBEX_BOT_TOKEN=your_webex_bot_token_here
WEBEX_SPACE_ID=your_webex_space_id_here

# Anthropic (Claude) API設定 (要約を利用する場合) / Anthropic API key (optional, for summarization)
ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxx...
ANTHROPIC_MODEL=claude-haiku-4-5-20251001

# SSL検証設定 / SSL verification (set False for corporate proxy / Mac cert issues)
SSL_VERIFY=false
```

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

  - name: セキュリティニュース
    webex_space_id: ${WEBEX_SPACE_ID_SECURITY}
    categories: [セキュリティ]

  - name: ネットワークニュース
    webex_space_id: ${WEBEX_SPACE_ID_NETWORKING}
    categories: [ネットワーク, クラウド]

  - name: 世の中経済ニュース
    webex_space_id: ${WEBEX_SPACE_ID_ECONOMY}
    categories: [経済]

  - name: Ciscoニュース
    webex_space_id: ${WEBEX_SPACE_ID_CISCO}
    priority: true                 # Cisco記事は独占配信（他チャンネルから除外）
    categories: [Cisco]
```

> Webex Bot トークンは `webex_bot_token` を省略すると `.env` の `WEBEX_BOT_TOKEN` を共通利用します。
> `${VAR}` 形式の値は実行時に環境変数（`.env`）で展開されます。

#### チャンネル間の配信制御 / Cross-channel routing

複数のカテゴリにマッチする記事を、目的に合ったチャンネルへ効率よく振り分けるために以下のロジックが順番に適用されます。

| Phase | 内容 |
|:---:|:---|
| **1. 事前フィルタ** | 各チャンネルの該当記事を抽出 |
| **1.5. 優先独占** | `priority: true` のチャンネルにマッチした記事を、他チャンネルから自動除外（例: Cisco記事は Cisco チャンネルでのみ配信） |
| **1.6. 譲渡 (defers_to)** | `defers_to: [...]` のチャンネルは、指定された譲渡先チャンネルにも該当する記事を譲渡先のみに残し、自分の側から除外（例: AI・機械学習はセキュリティ／ネットワーク寄りの記事を譲る） |
| **2. ニッチ優先** | 15件超の混雑チャンネルから、同じ記事が15件以下の余裕チャンネルにも該当する場合、余裕側のみに残して混雑側から除外 |
| **3. ランダム抽出** | それでも15件を超えるチャンネルでは、最終的にランダム抽出で15件に圧縮 |

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

### 2. キーワード設定 (`categories.yml`)
記事のタイトル・概要・タグ・**URL（リンク）** からカテゴリを判定するためのキーワードを定義します。

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

| 観点 | 内容 |
|:---|:---|
| **検索対象 / Search text** | `title` + `summary` + `tags` を連結し小文字化したテキスト。**URLは `cisco` を含む場合のみ追加**（Google News等の汎用リダイレクトURLで誤マッチしないため） |
| **マッチ方式 / Match mode** | **5文字以下のASCII英数字キーワード**は単語境界 `\b` でマッチ（例：`lan` は "LAN" にはマッチするが "p**lan**" "**lan**guage" にはマッチしない）。日本語や6文字以上の英数字キーワード、複合語は従来通りの部分文字列マッチ |
| **必須語の判定** | カテゴリ内に `!` 付き語が1つでも定義されている場合、それらのうち **少なくとも1つにマッチが必要** |
| **スコア計算** | `score = (必須語マッチ数 × 3) + (通常語マッチ数 × 1)` |
| **合格ライン** | `score >= 4`（デフォルト、`webex-news-rss-bot.py` の `min_score` で変更可） |

合格・不合格の具体例：

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

- **必須語は誤マッチしにくいCisco固有のブランド・製品名に限定**: 単独の `!nexus`, `!duo`, `!umbrella` 等は英語の一般語(`Belarus-nexus`等)に誤マッチするため、`!cisco nexus`, `!nexus 9000`, `!cisco duo`, `!duo security` のような **compound (複合語) 必須語**を採用しています。
- **複数形のバリアントも忘れずに**: `!vulnerability` だけだと "vulnerabilities" (複数形) にマッチしません。`!vulnerabilities`, `!exploits`, `!breaches` などの複数形も別途登録するか、語幹 `!vulnerabilit` のような部分一致語を併用してください。
- **広いカテゴリ（一般・経済等）には `!` 付き語を多めに設定** すると、雑多なRSSからのノイズを排除しやすくなります。
- **`min_score` を変更したい場合** は [webex-news-rss-bot.py](webex-news-rss-bot.py) の `filter_by_category(..., min_score=4)` のデフォルト値を調整します。値を下げると緩く、上げると厳しくなります。

#### カテゴリの現状サマリ / Current category sizes

本リポジトリの `categories.yml` の規模（参考値）：

| カテゴリ | 必須語(`!`) | 通常語 | 主な用途 |
|:---|---:|---:|:---|
| 一般 | 35 | 31 | 重大な災害・事件・政治イベント |
| 経済 | 17 | 39 | 値上げ/利上げ/買収/リストラ等の経済動向 |
| AI・機械学習 | 21 | 22 | OpenAI/Anthropic/Claude/LLM/Agentic AI |
| セキュリティ | 26 | 61 | CVE・脆弱性・ランサムウェア・APT等 |
| ネットワーク | 23 | 60 | SD-WAN/SASE/ZTNA/Wi-Fi/5G/プロトコル |
| クラウド | 19 | 73 | AWS/Azure/GCP/Kubernetes/データセンター |
| Cisco | 42 | 108 | Cisco固有ブランド + compound必須語 |

### 3. RSSフィード設定 (`urls.yml`)
ニュースの収集元となるRSSフィードURLの一覧を管理します。
```yaml
- https://blogs.cisco.com/feed
- https://zenn.dev/topics/aiagent/feed
- https://b.hatena.ne.jp/search/tag?q=AI&mode=rss
```

### 4. 朝メッセージ署名設定 (`morning_messages.txt`)
配信メッセージの末尾にランダムで追加される署名フレーズを1行ずつ記述して管理します。
```text
Your daily news briefing, delivered around X AM sharp. 毎朝X時頃、デイリーニュースブリーフィングをお届けします。
Stay ahead of the curve: Your daily digest arrives around X AM. 常に先を行くために。毎朝X時頃に最新情報を配信します。
```

---

## Claudeによる自動要約 ＆ 超エコノミーモード / LLM Summarization & Eco-mode

本スクリプトは、**Claude API** を用いて収集したニュースの概要を自然な日本語1〜2文（110字以内）に自動要約します。英文RSSは自動で日本語に翻訳されます。APIの課金を抑えるため、以下の**「超エコノミーモード（超節約設計）」**が自動適用されます。

### 1. プロンプト極小化（約22トークン）
指示プロンプトを以下の最短形に圧縮し、入力トークンを約89%削減：
```
日本語110字以内1〜2文で要約のみ出力。
ラベル/前置き/改行/情報不足要求は禁止。
提供情報のみで完結、英文は翻訳。
T: {title}
S: {summary}
```
これにより `タイトル：`/`概要：` のような不要ラベルや「本文を提供してください」のような追加情報要求も発生しません。

### 2. SKIP-API（自動要約スキップ・API課金ゼロ）
元のRSSから取得した概要が、以下の **すべて** を満たす場合はClaudeを呼ばずそのまま採用：
- 文字数が **100文字以下**
- 末尾が「...」「…」「続きを読む」「more」で途切れていない
- HTMLエンティティ（`&nbsp;`, `&gt;` 等）を含まないクリーンな文章
- **日本語（ひらがな・カタカナ・漢字）を1文字以上含む**

### 3. 英文の自動翻訳
SKIP-API条件のうち「日本語含有」を満たさない記事（=純英文）は、たとえ短くても **必ずClaudeで日本語翻訳＋要約** します。  
→ 例: `"SpaceX Falcon 9 launches Starlink mission from Florida"` → `"SpaceXのファルコン9ロケットがフロリダからStarlink衛星打ち上げミッションを実施した。"`

### 4. 要約キャッシュ
複数チャンネルに同一URL記事が出現した場合、初回の要約結果をメモリにキャッシュして2回目以降は再利用（API再呼び出しを完全に回避）。

### 5. 最大出力制限
Claudeからの返答を **`max_tokens = 140`** に強制制限し、出力の膨張を防止。

### コスト削減効果（参考）
1日200記事に要約をかける場合：
- **旧プロンプト**: ~200トークン × 200記事 = 40,000入力トークン/日
- **新プロンプト**: ~22トークン × 200記事 = **4,400入力トークン/日（約89%削減）**

---

## 自動実行 / Automation (cron / launchd)

定期的にスクリプトを自動実行し、Webexに最新ニュースを流すには、OSに合わせてスケジュール実行を設定します。
**macOS環境の場合、Macがスリープ（画面ロック）していると `cron` は指定時刻に動作しないことがあるため、`launchd` (plist) の利用を強く推奨します。**

### macOS の場合: launchd (推奨)

macOSのセキュリティ機能により、`Documents` や `Desktop` などの保護されたフォルダ内ではバックグラウンド実行がブロックされてしまう場合があります。そのため、ホームディレクトリ直下 (`~/rss-bot`) に専用の実行環境を構築・同期するデプロイスクリプトを用意しています。

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
> - 実行ログの確認: `~/rss-bot/log/launchd_run.log` に出力されます（macOS の TCC 保護を回避するため `~/rss-bot` 直下に配置）。
> - Manual test run: `launchctl start com.webex-news.rssbot`
> - View logs: `~/rss-bot/log/launchd_run.log` (located under `~/` to bypass macOS TCC protection of `Documents/`)

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
├── urls.yml                   # 取得元RSSフィードURLリスト (約170件)
├── morning_messages.txt       # 朝メッセージ（投稿末尾のランダム署名）のリスト
├── requirements.txt           # 依存ライブラリ一覧
├── .env                       # 認証情報＆環境変数（Git対象外）
├── .env.example               # 環境変数のテンプレート
├── .gitignore                 # Git除外設定
├── log/                       # 実行ログディレクトリ（launchd_run.log, launchd_err.log）
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

**症状 / Symptom**: 平日のはずなのに ~/rss-bot/log/launchd_run.log の最後の `実行時刻` がその日を飛ばしている。

**原因 / Cause**: その日の予定時刻 (例: 09:01) に **Mac がスリープしていた**。macOS の launchd は `StartCalendarInterval` 予定時刻に Mac がスリープ中だと job を起動しません。  
The Mac was asleep at the scheduled time. macOS `launchd` does **not** fire `StartCalendarInterval` jobs while asleep.

**確認方法 / Verification**:
```bash
# 実行履歴の確認
grep "実行時刻" ~/rss-bot/log/launchd_run.log | tail -10

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

### ❌ CISA や community.cisco.com が 403 になる
* 以前のバージョンではブラウザ風UA（Mozilla/Chrome）を使っており、これらのbot保護サイトで403が出ていました。
* 現バージョンは `rss-bot/1.0` という **フィードリーダ系UA** を採用しており、ほぼ全てのサイトで200が返ります。古いバージョンを使っている場合はアップデートしてください。

---

*Developed with ❤️ for webex-news-rss-bot*
# webex-news-rss-bot