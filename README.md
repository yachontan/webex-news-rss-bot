# webex-news-rss-bot

![Version](https://img.shields.io/badge/version-v4.13.0-blue)
![Release Date](https://img.shields.io/badge/release-2026--08--01-green)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

**Version**: `v4.13.0` ／ **Release Date**: 2026-08-01

> **RSS → Webex Bot ニュース通知 ＆ LLM自動要約・再ランクスクリプト / RSS-to-Webex News Notifier with LLM Summary & Re-ranking**

カテゴリキーワードに基づいて当日のRSSニュースを並列収集し、重複排除・Claudeによる重要度再ランク・自動要約を行った上で、Webex Bot経由で複数の指定スペースに自動配信する高機能ニュース通知スクリプトです。  
A Python script that collects today's RSS news in parallel, deduplicates, re-ranks by importance and summarizes using Claude API (LLM), and notifies Webex spaces via Bot.

> **フィードは `urls.yml`、配信先は `channels.yml`、カテゴリ判定は `categories.yml` で完全外部管理。Pythonコードを一切書き換えることなく、運用のすべてをカスタマイズできます。**  
> **Completely managed via YAML (`urls.yml` for feeds, `channels.yml` for routing, `categories.yml` for keywords) — no Python edits needed.**

---

## これは何をするもの？ / What is this?

**毎朝、決まった時間に「今日のニュース」を Webex に届けるしくみです。**

ニュースサイトが公開している更新情報（RSS）を自動で集め、内容ごとに仕分けして、Webex の「スペース」に投稿します。人が RSS リーダーを開いて回る作業を、まるごと肩代わりするイメージです。

```
   ニュースサイト約170か所            このツールがすること              Webex のスペース
  ┌──────────────┐        ┌────────────────┐      ┌──────────────┐
  │ Cisco ブログ      │  ──▶  │ 1. 記事を集める      │      │ セキュリティ       │
  │ セキュリティ系      │  ──▶  │ 2. 重複を除く        │ ──▶ │ ネットワーク       │
  │ 日本の一般ニュース   │  ──▶  │ 3. 内容ごとに仕分け   │      │ AI・機械学習       │
  │ 経済ニュース  ほか   │  ──▶  │ 4. 要約して投稿      │      │ 天気とまとめ       │
  └──────────────┘        └────────────────┘      └──────────────┘
```

**届くメッセージのイメージ**（実際の投稿例）

> 🗞 **セキュリティ**
> 🏷 カテゴリ: **セキュリティ**　｜　✅ 15 件　｜　⏱ 2026-08-02 09:01 JST
>
> - [Chrome の更新頻度が週2回に　AI によるバグ発見の影響](https://example.com/)　（📅 2026-08-02 02:00 JST）
>   📝 AI を使った脆弱性調査で見つかる不具合が増え、Google は修正の配信間隔を短くしました。
>
> ✅ 今日も一日がんばりましょう。

**うれしいところ**

- **読む場所が1つになる**: サイトを巡回しなくても、Webex を見れば今日の話題が分かります
- **同じ記事が何度も出ない**: 表現の違う同じニュースは1つにまとめます
- **話題ごとに分けて届く**: セキュリティの話はセキュリティのスペースへ、といった仕分けができます
- **要約が付く**（任意）: 長い記事も1〜2文で要点が分かります。英語の記事は日本語に直します
- **設定は画面から**: ファイルを手で書かなくても、ブラウザの設定画面で用意できます

---

## はじめに知っておく言葉 / Glossary

Python やサーバの知識は要りません。この README に出てくる言葉だけ、先に押さえておくと読みやすくなります。

| 言葉 | どういう意味か |
|:---|:---|
| **RSS（フィード）** | ニュースサイトが「新しい記事が出ました」と知らせるための、機械向けの更新情報。多くのサイトが公開しています |
| **Bot（ボット）** | Webex に自動で投稿するための専用アカウント。人のアカウントとは別に作ります |
| **スペース** | Webex のグループチャット部屋のこと。ここに Bot が投稿します |
| **トークン** | Bot が「自分は本物です」と示すための長い文字列。**パスワードと同じ扱い**で、他人に見せません |
| **Room ID（スペースID）** | スペースを指し示す長い文字列。どの部屋に投稿するかの指定に使います |
| **カテゴリ** | 記事の仕分け先（セキュリティ、経済など）。キーワードで判定します |
| **チャンネル** | 「このカテゴリの記事を、このスペースに送る」という配信設定1件のこと |
| **ダイジェスト** | 天気と、その日に各チャンネルが投稿したニュースのまとめを、1通にした投稿 |
| **dry-run（ドライラン）** | **実際には投稿せず**、画面で結果だけ確認する練習モード。設定を試すときに使います |
| **仮想環境（venv）** | このツール専用の Python 置き場。パソコン全体の環境を汚さずに済みます。ウィザードが自動で作ります |
| **`.env`** | トークンなど、**他人に見せない値**を書いておくファイル。Git には保存されません |
| **YAML（`.yml`）** | 設定を書くための、人が読みやすい形式のファイル。字下げ（インデント）に意味があります |

> **コマンドの読み方**: この README には `python webex-news-rss-bot.py` のような行が出てきます。これは「ターミナル（Windows はコマンド プロンプト）に打ち込む命令」です。とはいえ、**ふだんの操作はダブルクリックで完結**します（→ [クイックスタート](#クイックスタート--quick-start)）。

---

## 目次 / Table of Contents

- [**これは何をするもの？**](#これは何をするもの--what-is-this) ← まずここ
- [はじめに知っておく言葉 / Glossary](#はじめに知っておく言葉--glossary)
- [機能 / Features](#機能--features)
- [動作環境 / Requirements](#動作環境--requirements)
- [**クイックスタート / Quick Start**](#クイックスタート--quick-start) ← ダブルクリックで設定するウィザード
- [v1.x から更新する人へ / Upgrading from v1.x](#v1x-から更新する人へ--upgrading-from-v1x) ← 既存ユーザーはここから
- [セットアップ / Setup](#セットアップ--setup)
  - [**リポジトリの置き場所**（定時実行するなら必読）](#リポジトリの置き場所--where-to-put-this-repository)
  - [ステップ 2. 設定ファイルを作る（`.example` の使い方）](#ステップ-2-設定ファイルを作る--create-your-config-files)
  - [ステップ 3. 最低限の編集](#ステップ-3-最低限の編集--the-minimum-edits)
- [使い方 / Usage](#使い方--usage)
- [ルームID確認ツール / Room ID Checker（ブラウザUI / CLI）](#ルームid確認ツール--room-id-checker-check_roomspy)
- [各種設定ファイル / Configuration Files](#各種設定ファイル--configuration-files)
- [プライベートカテゴリ運用（my-fab パターン）/ Private Category Usage](#プライベートカテゴリ運用my-fab-パターン-private-category-usage)
- [AI による自動要約 ＆ 超エコノミーモード / LLM Summarization & Eco-mode](#ai-による自動要約--超エコノミーモード--llm-summarization--eco-mode)
- [LLMによるニュース選出（再ランク）/ LLM Re-ranking](#llmによるニュース選出再ランク--llm-re-ranking)
- [自動実行 / Automation (cron / launchd)](#自動実行--automation-cron--launchd)
- [macOS の制限と設計上の理由 / macOS Restrictions & Design Rationale](#macos-の制限と設計上の理由--macos-restrictions--design-rationale)
- [Windows での利用 / Running on Windows](#windows-での利用--running-on-windows)
- [ファイル構成 / File Structure](#ファイル構成--file-structure)
- [トラブルシューティング / Troubleshooting](#トラブルシューティング--troubleshooting)
- [更新履歴 / Version History](#更新履歴--version-history)

---

## 機能 / Features

**ざっくり言うと、次の4つを毎朝くり返します。**

1. **集める** — 登録した約170のニュースサイトから、24時間以内の記事をまとめて取得します
2. **整える** — 同じ内容の記事を1つにまとめ、キーワードで「これはセキュリティの話」と仕分けます
3. **選ぶ** — 1回の投稿が多くなりすぎないよう、重要そうな15件に絞ります
4. **届ける** — スペースごとに、要約を付けて投稿します

下の表は**細かい仕様の一覧**です。使い始めるだけなら読まなくて構いません。
気になった機能があるときに、辞書のように引いてください。

<details>
<summary><b>機能の一覧を開く</b></summary>

| 機能 | 用途・詳細 | Description |
|:---|:---|:---|
| **複数RSSの並列取得** | `urls.yml`（約170フィード）を **ホスト別に最大12並列** で取得（同一ホスト内はリクエスト間1秒sleepの直列＝サーバへの礼儀は維持）。全体実行時間を大幅短縮 | Parallel fetching (up to 12 host-workers; per-host 1s throttle) |
| **スコアリング型カテゴリフィルタ** | `categories.yml` に定義したキーワードを **必須語(`!`)×3点 + 通常語×1点** でスコア計算、`>=4点`で合格 | Weighted keyword scoring (must×3 + normal×1, threshold 4) |
| **単語境界マッチ** | 5文字以下の英数字キーワードは `\b` で境界判定（`lan`は `LAN`にマッチするが`plan`にはマッチしない） | Word-boundary regex for short ASCII keywords |
| **Cisco限定URL深度マッチ** | URLに `cisco` を含む記事のみ URL文字列を判定対象に追加（Google News等の汎用URLによる誤マッチを防止） | URL inclusion limited to cisco domains |
| **マルチチャンネル配信** | `channels.yml` に基づき、複数Webexスペースへカテゴリ毎に自動配信 | Route different categories to separate spaces |
| **優先独占チャンネル** | `priority: true` のチャンネル（Cisco等）は該当記事を他チャンネルから除外して独占配信 | Priority channel claims its articles exclusively |
| **チャンネル間譲渡 (defers_to)** | 汎用チャンネル（AI・機械学習・世の中 等）から専門チャンネル（セキュリティ/ネットワーク/経済）へ自動譲渡 | Auto-defer articles to more specific channels |
| **ニッチ優先再配分** | 15件超の混雑チャンネルから、同じ記事が15件以下の余裕チャンネルにも該当する場合、余裕側のみに残して混雑側から除外 | Crowded→spacious redistribution |
| **ソースベース振り分け (source_groups)** | 記事本文のキーワードではなく「どの RSS フィード由来か」でチャンネルを決定。`feeds:` の名前付きグループを `channels:` の `source_groups` で参照し、そのフィード由来の記事を専有配信（例: Cisco Security Advisories を専用スペースへ隔離） | Route by source feed via named `feeds:` groups |
| **Cisco Advisory の CVSS 併記（危険度カラー）** | Cisco Security Advisory の記事に、Cisco 公開の構造化データ（CVRF）から取得した実際の **CVSS Base Score** を、深刻度に応じた色付きバッジで表示（🔴 Critical / 🟠 High / 🟡 Medium・Low）。複数スコアは範囲表記＋最大値で色付け（`🔴 CVSS 7.5〜9.1（複数該当）`）。LLM には推測させず実値を取得 | Color-coded CVSS badge for Cisco advisories (fetched from CVRF) |
| **空チャンネルは無投稿** | 当日に該当ニュースが0件のスペースには、空通知も含め一切投稿しない | Skip posting entirely when a channel has no matching news |
| **デイリーダイジェスト (digest)** | `digest: true` の専用チャンネルが、全チャンネル配信後に **今日・明日の天気（東京・横浜・千葉・札幌）＋各チャンネルが実際に投稿したニュースのダイジェスト（見出し上位5件）＋🇯🇵日本のニュース枠** を1通に集約して配信。天気は **Open-Meteo**（APIキー不要・無料）。RSS再取得せず、投稿済み結果をメモリから集約するため内容が完全一致 | Daily briefing bot: weather (Open-Meteo, key-less) + digest of what each channel posted + a guaranteed Japanese-news section |
| **日本語ニュース下限保証 (min_japanese)** | `min_japanese: N` 指定チャンネルが N 件未満のとき、日本語記事（タイトルにひらがな/カタカナを含む）を新着順に補充。厳格なキーワードゲートで日本のニュースが減った場合の下限保証。ダイジェストの日本のニュース枠も同ロジックで最低5件を確保 | Guarantees a minimum count of Japanese-language articles (bypassing strict keyword gate) |
| **時事ダイジェストの地域バランス (regions.yml)** | デイジェストの日本ニュース枠を、一般・世の中ニュース（テック/経済は除外）から **日本6-7・米国3・その他5** の地域バランスで選ぶ「時事ダイジェスト」枠へ拡張。地域はキーワード判定（米＝アメリカ関連語）、不足時は日本優先で補充。クオータ・地域キーワードは `regions.yml` に集約（不在時は従来の日本ニュース枠にフォールバック） | Region-balanced current-affairs digest (JP 6-7 / US 3 / Other 5) configured via `regions.yml` |
| **週末キャッチアップ（月曜）** | `--weekend-catchup` 指定時、**月曜の実行のみ**取得期間を72時間（金土日の3日分）に自動拡張。平日9時運用で週末の未配信分をまとめて配信 | Monday auto-extends the window to 72h (Fri–Sun) |
| **高度な重複排除** | 媒体名(`(共同通信)`等)除去後、①タイトル類似度85%以上、②漢字bigram Jaccard 20%以上、③漢字bigram Overlap 50%以上+共通5件以上、④タイトル55%+概要55%、⑤**英語タイトルの単語Jaccard 50%以上（両者4語以上）** のいずれかで統合し **最新公開日時の記事を採用**。正規化・bigram・トークン集合は前計算済みで高速 | Hybrid 5-way dedup: kanji-bigram for Japanese + word-level Jaccard for English; precomputed for speed |
| **LLM再ランク（ニュース選出）** | 1チャンネル15件超のとき、スコア上位40候補を Claude が**読者にとっての重要度順**に15件選定。API未設定・失敗時はスコア階層＋ランダム抽出に自動フォールバック | LLM re-ranking picks top 15 by reader relevance; falls back to stratified random sampling |
| **SSLフォールバック** | SSL証明書検証失敗時に自動で `verify=False` リトライ（HuggingFace等のmacOS証明書問題に対応） | Auto-fallback to `verify=False` on SSL failure |
| **フィードリーダ系User-Agent** | `rss-bot/1.0` UAでCISA等のbot対策サイトに対応（※community.cisco.com は2026-07現在それでも403 → トラブルシューティング参照） | Feed-reader UA mitigates anti-bot blocks (some sites still reject) |
| **Markdownリンク形式** | タイトルと日付を同一行に表示 (`[Title](URL)　（📅 date JST）`) | Title and date on same line with Markdown link |
| **Claude自動要約** | Claude APIで「自然な日本語1〜2文（110字以内）」に要約。**英文RSSは自動で日本語に翻訳** | LLM summary + English→Japanese translation |
| **超エコノミーモード** | プロンプト圧縮（~22トークン）+ 短い綺麗な日本語概要のスキップ + 要約キャッシュ | Compressed prompt (~22 tokens), skip for short Japanese, in-memory cache |
| **Dry-runモード** | 送信せずターミナルで取得・要約結果を確認 | Dry-run preview |
| **初期設定ウィザード** | ダブルクリックで起動し、環境診断→依存導入→トークン検証→配信先設計→設定生成→dry-run まで案内（macOS/Windows 両対応、ブラウザUI と CLI の2方式） | Setup wizard for macOS/Windows (browser UI or CLI) |
| **launchdデプロイ** | macOSのDocuments保護を回避してホーム直下に同期配置する自動デプロイスクリプト | Auto-deploy script for macOS launchd |
| **スリープ復帰対応** | `pmset` で毎朝 Mac を自動wakeさせる運用ガイドを完備（launchdがスリープ中は fire しない問題の回避） | `pmset` wake schedule for reliable launchd execution on Mac sleep |

</details>

---

## 動作環境 / Requirements

| 必要なもの | 説明 | 必須 |
|:---|:---|:---:|
| **Python 3.10 以上** | 動かすための土台。入っているか分からない場合は、ウィザードが最初に確認して教えてくれます | ✅ |
| **Webex の Bot** | 投稿用のアカウント。[開発者ポータル](https://developer.webex.com/)の画面から数分で作れます（→ [クイックスタート](#クイックスタート--quick-start)のウィザードが案内します） | ✅ |
| **投稿先のスペース** | Webex のグループ。作ったら**その部屋に Bot を招待**しておきます | ✅ |
| **AI の API キー** | 記事の要約に使います。**Claude / OpenAI / Gemini** から選べます。**無くても配信は動きます**（その場合は元の紹介文をそのまま載せます） | — |

> **Python が入っているか分からないときは**、そのままウィザードを起動してください。見つからなければ、入手先を案内します。

### 依存パッケージ / Python dependencies
※詳細は `requirements.txt` を参照 / See `requirements.txt` for details
* `feedparser` — RSS解析 / RSS parsing
* `requests` — Webex/Claude API通信 / HTTP client for Webex & Claude APIs
* `python-dotenv` — `.env` 読み込み / Environment variable loading
* `PyYAML` — YAML設定読み込み / YAML config loading

---

## クイックスタート / Quick Start

**はじめての人は、ウィザードに任せてください。** clone してダブルクリックするだけで、環境の確認から設定ファイルの作成、動作確認まで進みます。  
New here? Let the wizard do it — clone, double-click, and follow the steps.

| OS | ダブルクリックするファイル |
|:---|:---|
| **macOS** | `はじめに設定する.command` |
| **Windows** | `はじめに設定する.bat` |

```bash
# 置き場所は TCC・同期フォルダーの外に（詳細は下の「リポジトリの置き場所」）
mkdir -p ~/Developer && cd ~/Developer
git clone <このリポジトリのURL> rss-bot
# → Finder / エクスプローラーで開き、上記のファイルをダブルクリック
```

ウィザードがやること:

| ステップ | 内容 |
|:---:|:---|
| 0 | **環境の確認** — Python のバージョン、**置き場所**（macOS: TCC 配下か / Windows: OneDrive 配下か）、書き込み権限。あわせて仮想環境の作成と依存パッケージの導入 |
| 1 | **chat bot の用意** — `.env` に設定済みの bot があれば**一覧から選ぶだけ**。無ければ Webex の作成ページを開いて手順を案内し、発行されたトークンを受け取る |
| 2 | bot の確認 — トークンの有効性をその場でチェックし、参加中のスペースを取得 |
| 3 | スペース一覧から配信先を選び、カテゴリを割り当て（**`categories:` を書かずに済む形**で生成） |
| 4 | 集めるRSSフィードの選択 |
| 6 | `.env`・`urls.yml`・`channels.yml` を**プレビューしてから**作成（既存ファイルは自動退避） |
| 6 | 送信せずに `--dry-run` で動作確認 |

**すでに設定がある場合は、それを読み込んで編集できます。** ウィザードは既存の設定を検出すると、現在のフィード一覧と配信先の割り当てを各ステップの初期値として表示します。設定をやり直したいときだけでなく、**フィードの追加・削除や配信先の変更にも使えます**。

| 既存の設定 | ウィザードでの扱い |
|:---|:---|
| フィードURL | 一覧に表示され、チェックを外して削除・欄に貼って追加 |
| 配信先（スペースとカテゴリ） | 現在の割り当てを初期値として表示、変更可 |
| 天気API・名前付きグループ | **編集せずそのまま引き継ぐ**（画面に明示） |
| 優先配信・譲渡・ダイジェスト等を持つチャンネル | **編集せずそのまま引き継ぐ**（画面に明示） |

> **上書き前のファイルは自動で退避されます。** `channels.yml.bak-20260802-012412` のように日時つきで同じフォルダに残るので、戻したいときはこれを元の名前に戻してください。退避ファイルには**設定の中身がそのまま入る**ため Git 管理対象外です（`.gitignore` で除外）。溜まってきたら削除して構いません。

> 設定は作り直しになるため、`urls.yml` / `channels.yml` に書いていた**コメントは残りません**（設定内容は保たれます）。元のファイルは `.bak-日時` に自動退避されるので、必要なら戻せます。

> **chat bot は Webex の画面で作ります。** 商用の Webex には bot を作成する API が無く、[開発者ポータル](https://developer.webex.com/my-apps/new/bot)のフォームから作る必要があります（API での作成は FedRAMP 環境限定）。ウィザードは作成ページを開いて手順を示し、発行されたトークンを受け取るところから自動化します。  
> Bots must be created in the Webex developer portal — there is no bot-creation API in the commercial environment (API creation is FedRAMP-only).

ウィザードは3つのタブに分かれています。設定を作った後も、いつでも開いて編集できます。

| タブ | できること |
|:---|:---|
| **設定の全体像** | いまの設定をまとめて確認（規模の指標・チャンネル一覧・**記事の流れ図**・カテゴリの語数・フィード・ダイジェスト・注意点） |
| **セットアップ** | 環境確認 → chat bot の用意 → **チャンネルごとの設定**（名前・種類・カテゴリ・詳細）→ フィード → 生成 → dry-run |
| **URL の設定** | 集めるRSSの確認・追加・削除。**名前付きグループ**の編集と新規作成（専有配信の注意つき）。**天気の観測地点**の編集 |
| **カテゴリの管理** | カテゴリのキーワード編集と、**新規カテゴリの作成**。チャンネル設定とは独立 |
| **ダイジェスト** | 天気の観測地点（**地名から緯度経度を自動取得**）と、**時事ダイジェストの地域バランス**（日本/米国/その他の件数と判定語） |
| **要約AI** | 要約・記事選定に使う AI（**Claude / OpenAI / Gemini**）とモデル名の設定。接続を試して確認できる |
| **自動実行** | 毎朝の実行時刻と曜日を設定（macOS は launchd、Windows はタスク スケジューラに登録） |

スペースごとに**送るものの種類**を選べます。

| 種類 | 内容 |
|:---|:---|
| **カテゴリ別のニュース** | 選んだカテゴリの記事を配信（カテゴリは複数可） |
| **ダイジェスト（天気＋まとめ）** | 毎日の配信後に、**今日・明日の天気**と**各チャンネルが投稿したニュースのまとめ**を1通で配信。観測地点は「URL の設定」タブで編集 |

**チャンネル名は Webex 投稿の見出しになります。** ウィザードでは名前を自由に決められ、送るカテゴリは複数選べます。名前と単一カテゴリが一致するときだけ `categories:` を省略した設定になります。

ブラウザで進める方式と、ターミナルで進める方式を選べます。どちらも同じ設定を作ります。  
Choose the browser UI or the terminal — both produce the same configuration.

```bash
python3 setup.py --ui    # ブラウザで設定する
python3 setup.py --cli   # ターミナルで設定する
```

> 定時実行（毎朝の自動配信）の登録は、ウィザードにはまだ含まれていません。[自動実行](#自動実行--automation-cron--launchd) の手順で設定してください。

<details>
<summary><b>ウィザードを使わず手作業で設定する / Manual setup</b></summary>

```bash
cd rss-bot
python3 -m venv .
source bin/activate
pip install -r requirements.txt

cp .env.example .env          # Webex トークンと Space ID を書く
cp urls.yml.example urls.yml           # 集めるフィードを書く
cp channels.yml.example channels.yml   # 配信先を書く

python webex-news-rss-bot.py --dry-run   # 送信せず確認
python webex-news-rss-bot.py             # 本番実行
```

各ファイルの書き方は下の [セットアップ](#セットアップ--setup) を参照してください。

</details>

---

## v1.x から更新する人へ / Upgrading from v1.x

すでに v1.x で運用している場合、設定ファイルの構成が変わっています。**既存の `urls.yml` と `bots.yml` はそのまま残して構いません**（読み込まれなくなるだけです）。

### 1. `config.yml` へ統合する（v2.0.0）

`urls.yml`（フィード）と `bots.yml`（配信先）は `config.yml` の `feeds:` / `channels:` に統合されました。次のコマンドで、コメントを保ったまま変換できます。

```bash
python3 - << 'EOF'
from pathlib import Path
feeds = Path("urls.yml").read_text(encoding="utf-8").splitlines()
bots = Path("bots.yml").read_text(encoding="utf-8")
lines = ["feeds:"] + [("  " + l if l.strip() else "") for l in feeds] + ["", ""]
Path("config.yml").write_text("\n".join(lines) + bots, encoding="utf-8")
print("config.yml を作成しました")
EOF
```

変換したら `python webex-news-rss-bot.py --dry-run` で、これまでと同じ配信内容になることを確認してください。

### 2. `クラウド` カテゴリの置き換え（v3.0.0）

`categories.yml` の `クラウド` は `ネットワーク` に統合されました。`config.yml` に `categories: [クラウド]` と書いている箇所があれば、`ネットワーク` に置き換えてください（AWS/Azure/GCP/Kubernetes などのキーワードは `ネットワーク` 側に入っています）。

### 3. `urls.yml` と `channels.yml` へ分ける（v4.0.0）

編集しやすさのため、`config.yml` は再び2つに分かれました。**`config.yml` のままでも動きます**が、次のコマンドで分割できます。

```bash
python3 - << 'EOF'
from pathlib import Path
lines = Path("config.yml").read_text(encoding="utf-8").splitlines()
fs = next(i for i, l in enumerate(lines) if l.rstrip() == "feeds:")
cs = next(i for i, l in enumerate(lines) if l.rstrip() == "channels:")
Path("urls.yml").write_text("\n".join(lines[fs:cs]).rstrip() + "\n", encoding="utf-8")
Path("channels.yml").write_text("\n".join(lines[cs:]).rstrip() + "\n", encoding="utf-8")
print("urls.yml と channels.yml を作成しました")
EOF
```

分割後に `python webex-news-rss-bot.py --dry-run` で同じ結果になることを確認してください。`urls.yml` と `channels.yml` があれば `config.yml` は読まれません（消しても構いません）。

### 3. 設定を短くする（任意）

`name` を `categories.yml` のカテゴリ名と同じにすると、`categories:` を省略できます。

```yaml
# 変更前
- name: セキュリティニュース
  webex_space_id: ${WEBEX_SPACE_ID_SECURITY}
  categories:
    - セキュリティ

# 変更後（name がカテゴリ名と完全一致するので categories: は不要）
- name: セキュリティ
  webex_space_id: ${WEBEX_SPACE_ID_SECURITY}
```

---

## セットアップ / Setup

### リポジトリの置き場所 / Where to put this repository

**定時実行を使うなら、置き場所で結果が変わります。** 手動実行は成功するのに、スケジューラからの実行だけが無言で失敗する、という形で表面化します。最初に置き場所を決めてください。  
**Where you clone this matters for scheduled runs.** A bad location fails silently under the scheduler while manual runs succeed.

#### macOS — TCC（プライバシー保護）の対象外に置く

macOS は `~/Documents` `~/Desktop` `~/Downloads` と iCloud Drive 配下を **TCC** で保護しています。`launchd` から起動されたプロセスにはこれらのフォルダへのアクセス権が無いため、**設定ファイルを読めずに失敗します**（ターミナルからの手動実行は、ターミナル自身に許可があるので成功します）。

| 置き場所 | 定時実行（launchd） | 備考 |
|:---|:---:|:---|
| `~/Developer/rss-bot` | ✅ 推奨 | TCC 対象外。plist から直接このパスを指定できる |
| `~/rss-bot` | ✅ | ホーム直下も対象外 |
| `~/Documents/...`<br>`~/Desktop/...`<br>`~/Downloads/...` | ❌ | TCC でブロックされる。同梱の `deploy_to_launchd.sh` で `~/rss-bot` へ同期する回避策あり |
| `~/Library/Mobile Documents/...`（iCloud Drive） | ❌ | 同期の実体化タイミングにも依存するため不可 |

> **フルディスクアクセスを付与すれば動かせますが、推奨しません。** バックグラウンド実行のためだけに広い権限を与えることになります。TCC 対象外のフォルダに置く方が安全で確実です。

#### Windows — 同期・保護されるフォルダーを避ける

Windows には macOS の TCC のような一律の制限はなく、タスクスケジューラは任意のフォルダのスクリプトを実行できます。ただし**同じ症状（定時実行だけ失敗）を起こす要因が2つ**あります。

| 要因 | 何が起きるか | 対処 |
|:---|:---|:---|
| **OneDrive のフォルダー バックアップ** | `Documents` `Desktop` `Pictures` が OneDrive 配下に移され、パスが `C:\Users\<user>\OneDrive\...` に変わる。「ファイル オンデマンド」でプレースホルダー化されていると、実行時の読み込みが失敗・遅延することがある | 同期対象外のフォルダに置く。置く必要がある場合は対象フォルダを「このデバイス上に常に保持する」に設定 |
| **Microsoft Defender の「制御されたフォルダー アクセス」** | 有効にしていると、許可していないアプリ（`python.exe`）が `Documents` `Desktop` 配下へ**書き込めず**、`log/` の出力に失敗する | 同機能の対象外フォルダに置くか、`python.exe` を「許可されたアプリ」に追加 |

| 置き場所 | 定時実行（タスクスケジューラ） |
|:---|:---:|
| `C:\tools\rss-bot`、`C:\Users\<user>\rss-bot` | ✅ 推奨 |
| `C:\Users\<user>\OneDrive\...` 配下 | ⚠️ 上記の設定が必要 |
| ネットワークドライブ（`\\server\share\...`） | ❌ 「ユーザーがログオンしていなくても実行」時にドライブを解決できない |

詳細は [macOS の制限と設計上の理由](#macos-の制限と設計上の理由--macos-restrictions--design-rationale) と [Windows での利用](#windows-での利用--running-on-windows) を参照してください。

---

### ステップ 1. 仮想環境とパッケージ / Virtual environment and dependencies

```bash
cd rss-bot
python3 -m venv .          # 初回のみ / first time only
source bin/activate
pip install -r requirements.txt
```

> `python3 -m venv .`（ドット）でリポジトリ直下に `bin/` `lib/` が作られます。`python3 -m venv venv` とした場合は、以降のコマンドの `bin/python` を `venv/bin/python` に読み替えてください。

---

### ステップ 2. 設定ファイルを作る / Create your config files

#### `.example` ファイルとは / What the `.example` files are

このリポジトリには、**設定ファイルの見本**が `.example` という拡張子付きで入っています。

- **`.example` 付き**（例: `.env.example`）… Git に入っている**見本**。そのままでは読み込まれません。**編集しないでください**（更新時に上書きされます）。
- **`.example` を外した名前**（例: `.env`）… プログラムが実際に読む**あなたの設定ファイル**。Git 管理対象外なので、`git pull` しても消えず、あなたのトークンが誤って公開されることもありません。

つまり **「`.example` を外した名前でコピーして、コピーした側を編集する」** のが基本ルールです。  
**Copy each template to the same filename without `.example`, then edit the copy.**

```bash
# 例: .env.example → .env
cp .env.example .env
```

> **ウィザードを使う場合、この作業は不要です。** bot を用意した時点で、足りない設定ファイルを**ひな形から自動で作ります**（既にあるファイルには触れません）。下のコマンドは、手作業で進めたい場合の手順です。

#### 一括で作る / Create them all at once

```bash
# 必須 / Required
cp .env.example .env
cp urls.yml.example urls.yml
cp channels.yml.example channels.yml

# 任意（使う機能に応じて）/ Optional
cp morning_messages.txt.example morning_messages.txt
cp regions.yml.example regions.yml
cp categories-private.yml.example categories-private.yml

# 自動実行（macOS launchd）を使う場合のみ / Only for scheduled runs on macOS
cp run_rssbot.sh.example run_rssbot.sh && chmod +x run_rssbot.sh
cp webex-news-rss-bot.plist.example webex-news-rss-bot.plist
```

#### 一覧 / Overview

| テンプレート | コピー先 | 必須 | 何のファイルか | 何を編集するか |
|:---|:---|:---:|:---|:---|
| `.env.example` | `.env` | ✅ | 認証情報（トークン・APIキー） | Webex Bot トークンと送信先スペースIDを実際の値に |
| `urls.yml.example` | `urls.yml` | ✅ | **集めるRSSフィード** | そのままでも動く。読みたいフィードの行を追加・削除 |
| `channels.yml.example` | `channels.yml` | ✅ | **配信先スペースとカテゴリ** | 使うチャンネルだけ残し、スペースIDとカテゴリを設定 |
| `morning_messages.txt.example` | `morning_messages.txt` | — | 投稿末尾のランダム署名 | 好きな文言を1行に1つ |
| `regions.yml.example` | `regions.yml` | — | ダイジェストの地域バランス（日本/米国/その他） | 件数（`quota`）と地域判定キーワード |
| `categories-private.yml.example` | `categories-private.yml` | — | 社外に出せないキーワードの追加定義 | 自社名などのキーワード |
| `run_rssbot.sh.example` | `run_rssbot.sh` | — | 自動実行用のラッパー | **編集不要**（`chmod +x` だけ必要） |
| `webex-news-rss-bot.plist.example` | `webex-news-rss-bot.plist` | — | 自動実行のスケジュール定義 | `__REPO_DIR__` をこのフォルダの絶対パスに置換 |

> **`categories.yml`（カテゴリ判定キーワード）だけは `.example` がありません。** これは Git 管理対象の本体設定で、コピー不要でそのまま使えます。分類を変えたくなったら直接編集してください。  
> `categories.yml` is tracked in Git — use it as-is, no copy needed.

---

### ステップ 3. 最低限の編集 / The minimum edits

#### 3-1. `.env` — 認証情報（必須）

`.env` を開き、`your_..._here` となっている箇所を実際の値に置き換えます。**まずはこの2つだけで動きます。**

```diff
- WEBEX_BOT_TOKEN=your_webex_bot_token_here
+ WEBEX_BOT_TOKEN=ZDU4M2Y...（Webex Developer で発行したBotトークン）

- WEBEX_SPACE_ID_AI=your_ai_space_id_here
+ WEBEX_SPACE_ID_AI=Y2lzY29zcGFyazovL3VzL1JPT00v...（送信先スペースのID）
```

- **Bot トークンの取得**: [Webex Developer Portal](https://developer.webex.com/) で Bot を作成して発行します。
- **スペースIDの取得**: Bot をスペースに招待したうえで、同梱の `check_rooms.py` を実行すると一覧表示されます（→ [ルームID確認ツール](#ルームid確認ツール--room-id-checker-check_roomspy)）。

| 変数 | 必須 | 説明 |
|:---|:---:|:---|
| `WEBEX_BOT_TOKEN` | ✅ | Webex Bot のアクセストークン |
| `WEBEX_SPACE_ID` | ✅ | 送信先 Webex スペース ID（シングルボットモード） |
| `WEBEX_SPACE_ID_*` | — | マルチチャンネルモード用 Space ID（`channels.yml` で参照） |
| `WEBEX_BOT_TOKEN_*` | — | チャンネル別 Bot トークン（省略時は共通トークンを使用） |
| `ANTHROPIC_API_KEY` | — | Claude API キー（要約・再ランク機能を使う場合のみ。既定はコメントアウト＝要約なし） |
| `ANTHROPIC_MODEL` | — | **要約**用モデル名（コード既定: `claude-3-haiku-20240307`。`.env` で新しいモデルに上書き推奨） |
| `ANTHROPIC_RERANK_MODEL` | — | **再ランク**用モデル名（既定: `claude-haiku-4-5-20251001`） |
| `SSL_VERIFY` | — | `false` にすると SSL 検証を無効化（社内プロキシ等） |
| `MYFAB_KEYWORD` 等 | — | プライベートカテゴリ用（my-fab パターン参照） |

> **⚠️ `.env` は絶対にコミットしないでください。** `.gitignore` で除外済みですが、内容をチャットや Issue に貼るのも避けてください。  
> `.env` is gitignored — never commit or paste its contents.

#### 3-2. `urls.yml` と `channels.yml` — フィードと配信先（必須）

設定はこの1ファイルだけです。中身は**2つのセクション**に分かれています。

```yaml
feeds:                    # ← ① どのRSSを集めるか
  - https://blogs.cisco.com/feed
  - https://www.itmedia.co.jp/rss/2.0/news_bursts.xml   # ← こんな風に1行追加

channels:                 # ← ② どこへ何を送るか
  - name: AI・機械学習                     # カテゴリ名をそのまま名前にすれば categories: は不要
    webex_space_id: ${WEBEX_SPACE_ID_AI}  # .env の変数名を参照する書き方

  - name: セキュリティ & ネットワーク       # 名前とカテゴリが違うときは categories: を書く
    webex_space_id: ${WEBEX_SPACE_ID_SECURITY}
    categories:
      - セキュリティ                       # categories.yml にあるカテゴリ名を書く
      - ネットワーク
```

**① `feeds:` — 収集するRSS（編集は任意）**

コピーしたままで動きます。読みたいサイトを増やしたければ、`  - ` で始まる行を足すだけです。RSS が無いサイトは Google News の検索フィードで代用できます（テンプレート末尾にコメントで例があります）。

**② `channels:` — 配信先（ここは要編集）**

「どのスペースに、どのカテゴリのニュースを送るか」を決めます。テンプレートには2チャンネル分の例が入っています。**使わないチャンネルは丸ごと削除する**のが最も簡単です。

- `webex_space_id` は `${WEBEX_SPACE_ID_AI}` のように書くと `.env` の値を読み込みます（IDを直接書いてもOK）。スペースIDは [ルームID確認ツール](#ルームid確認ツール--room-id-checker-check_roomspy)（ブラウザUIあり）で調べられます。
- **`.env` にその変数が無い／未設定のチャンネルは、警告を出して自動でスキップ**されます。まずは1チャンネルだけ設定して試すのが安全です。
- `categories:` に書けるのは `categories.yml` に定義されたカテゴリ名です（既定: `一般` / `経済` / `AI・機械学習` / `セキュリティ` / `ネットワーク` / `Cisco`）。
- **`categories:` を省略すると、`name` がそのままカテゴリ名として使われます。** カテゴリ名をそのままチャンネル名にするなら `- name: セキュリティ` の1行で済みます。`name` は投稿の見出し・ダイジェスト・`defers_to` の参照名としても従来どおり使われます。
- `name` が `categories.yml` に無い名前のまま `categories:` を省略した場合は、**警告を出してそのチャンネルをスキップ**します（キーワード無し＝全記事配信、という暴発を防ぐため）。その場合は `categories:` を明示してください。
- 詳しい書き方（優先度・重複回避・ダイジェスト）は [配信ルール設定 (`channels.yml`)](#1-配信ルール設定-channelsyml--delivery-routing) を参照。

> インデントに注意: `feeds:` / `channels:` の下の項目は**半角スペース2つ**下げて書きます。テンプレートの書き方をそのまま真似るのが確実です。

#### 3-3. 任意ファイル / Optional files

| ファイル | 使うとどうなるか | 編集のしかた |
|:---|:---|:---|
| `morning_messages.txt` | 投稿の末尾にランダムな一言が付く | 1行1メッセージで好きなだけ書く |
| `regions.yml` | ダイジェストのニュースを日本/米国/その他のバランスで選ぶ | `quota` の件数と、地域を判定する `keywords` を調整 |
| `categories-private.yml` | 社外に出せないキーワードを Git に載せずに追加できる | 自社名などを追記（→ [プライベートカテゴリ運用](#プライベートカテゴリ運用my-fab-パターン-private-category-usage)） |

---

### ステップ 4. 動作確認 / Verify

```bash
python webex-news-rss-bot.py --dry-run     # 送信せず、収集結果だけ画面表示
```

`=== 完了 / Done ===` まで進み、記事一覧が表示されれば成功です。問題なければ `--dry-run` を外して本番実行します。  
If you see the article list and `=== 完了 / Done ===`, you're set — drop `--dry-run` to deliver for real.

毎朝の自動実行まで進めたい場合は [自動実行 / Automation](#自動実行--automation-cron--launchd) へ。

---

## 使い方 / Usage

### 基本実行 / Basic run
```bash
python webex-news-rss-bot.py
```
`channels.yml` に定義されたマルチチャンネルすべてに対して、過去24時間の記事を自動的に収集・要約・配信します。  
Collects, summarizes, and delivers the last 24 hours of articles to every channel defined in `channels.yml`.

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

Webex Botが参加しているスペース（ルーム）の「ルーム名」と「Room ID」を確認する補助ツールです。`channels.yml` の `webex_space_id` を設定する際のID調査に使います。**ブラウザUI版**と**コマンド版**があり、どちらも同じロジックです。  
Lists the **name** and **Room ID** of every Webex space the Bot has joined — available as a browser UI and as a CLI.

### 方法A: アイコンをダブルクリック（いちばん簡単）/ Double-click the launcher

リポジトリを開き、お使いの OS のファイルを**ダブルクリック**するだけです。ウィンドウが開いて、ブラウザに UI が表示されます。  
Just double-click the launcher for your OS — it opens the UI in your browser.

| OS | ダブルクリックするファイル |
|:---|:---|
| **macOS** | `起動_スペースID確認UI.command` |
| **Windows** | `起動_スペースID確認UI.bat` |

- 初回だけ、必要なパッケージ（Streamlit）を**自動でインストール**します（数分かかることがあります）。
- 止めるときは、開いたターミナルのウィンドウで **Control + C**。
- ダブルクリックしても開かない場合は、実行権限を付け直してください:

  ```bash
  chmod +x "起動_スペースID確認UI.command"
  ```

> `.command` ファイルをブラウザ経由でダウンロードした場合、macOS の Gatekeeper が「開発元を確認できません」と警告することがあります。`git clone` で取得した場合は警告は出ません。警告が出たときは、右クリック →「開く」を選ぶか、下の方法B/Cを使ってください。

### 方法B: ブラウザUI をコマンドで起動 / Browser UI from the CLI

初回のみ追加パッケージを入れます（ニュース配信本体には不要）。  
One-time install (not needed by the news bot itself):

```bash
./bin/python -m pip install -r requirements-ui.txt
```

起動するとブラウザが開きます。  
Launch — it opens in your browser:

```bash
./bin/streamlit run check_rooms_ui.py
```

UI でできること / What you can do:

- **`.env` のトークンを自動検出**して一覧から選ぶ（`WEBEX_BOT_TOKEN` と `WEBEX_BOT_TOKEN_*` の両方に対応。**変数名だけを表示し、値は画面に出しません**）。`.env` が無ければ手入力もできます。
- スペース一覧を表で表示し、名前で絞り込み（完全一致の切り替えあり）
- 選んだスペースから **`.env` に貼り付ける行**（`WEBEX_SPACE_ID_XXX=...`）と、**`channels.yml` に書く雛形**を生成

> Bot は**自分が参加しているスペースしか見えません**。目的のスペースが出てこない場合は、Webex 側でそのスペースに Bot を追加してから再取得してください。複数の Bot を使い分けている場合は、UI 上でトークンを切り替えて確認できます。

### 方法C: コマンド版 check_rooms.py / CLI

```bash
python check_rooms.py                                  # 全スペース一覧
python check_rooms.py --find "Cisco Security Advisories"  # 名前で絞り込み
```

実行すると、Webex Botのトークンの入力を求められます（`.env` の `WEBEX_BOT_TOKEN` があればそれを使用）。**入力したトークン文字は画面上に一切表示されません（非表示入力）**。  
You will be prompted for the Webex Bot token. **Input is hidden** for security.

出力された一覧から必要なルームの `id` をコピーし、`channels.yml` の `webex_space_id` に設定してください。  
Copy the desired `id` from the output and paste it into `channels.yml`'s `webex_space_id`.

---

## 各種設定ファイル / Configuration Files

ここから先は**各設定ファイルの詳細な書き方**です。最初の1回で必要な作業は [セットアップ](#セットアップ--setup) に集約してあります（`*.example` をコピーして編集するだけ）。この章は、動かした後に「もっと細かく調整したい」と思ったときに読んでください。  
This chapter is the detailed reference. For first-time setup, the [Setup](#セットアップ--setup) chapter is all you need.

> 以下で `urls.yml` / `channels.yml` などと書いているのは、すべて `*.example` から `.example` を外してコピーした**あなたの設定ファイル**のことです。`*.example` 側は見本なので編集しません。

### 1. 配信ルール設定 (`channels.yml`) / Delivery routing
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

#### `name` と `categories` の関係 / How `name` and `categories` relate

`name` はチャンネルの**識別子と表示名を兼ねます**。使われる場所は次の3つです。

1. Webex 投稿の見出し（`🗞️ **世の中ニュース**`）とデイリーダイジェストの各チャンネル見出し
2. `defers_to: [チャンネル名]` の参照先
3. `--channel <名前>` で実行対象を絞るときの指定値

**`categories:` を省略すると、`name` がそのままカテゴリ名として使われます（完全一致のみ）。** チャンネル名を `categories.yml` のカテゴリ名と揃えておけば、`categories:` を書く必要がありません。

```yaml
channels:
  # ① name がカテゴリ名と完全一致 → categories: は不要
  - name: セキュリティ
    webex_space_id: ${WEBEX_SPACE_ID_SECURITY}

  # ② name がカテゴリ名と違う → categories: を明示（name は自由）
  - name: 世の中ニュース
    webex_space_id: ${WEBEX_SPACE_ID_GENERAL}
    categories:
      - 一般
```

| `name` | 省略時の扱い |
|:---|:---|
| `セキュリティ` | `セキュリティ` を配信（カテゴリ名と完全一致） |
| `AI・機械学習` | `AI・機械学習` を配信 |
| `セキュリティニュース` | **スキップ**（完全一致しない）→ `name` を `セキュリティ` にするか `categories:` を明示 |
| `世の中ニュース` | **スキップ**（同上）→ `categories: [一般]` を明示する |

- 部分一致は採用しません。`name` の一部がたまたまカテゴリ名と重なったときに、意図しないカテゴリまで配信される事故を避けるためです。
- 見出しとカテゴリ表示が同じ文字列になる場合（上の①）は、投稿ヘッダーの `🏷 カテゴリ:` 行を自動で省き、重複表示を避けます。
- **完全一致しない場合は、警告を出してそのチャンネルをスキップ**します。キーワードが1つも無い状態＝全記事が通過してしまうため、意図しない大量配信を防ぐ安全策です。`categories:` を明示すれば解決します。
- `categories: []`（空リストを明示）は従来どおり「カテゴリで絞らない」の意味で、`source_groups` 専用チャンネルや `digest: true` チャンネルで使います。

#### カテゴリ名を変数で管理する / Declaring category names as variables

チャンネル名（`channels.yml`）とカテゴリ名（`categories.yml`）は**完全一致している必要があります**。手で両方を書くとずれるため、`.env` の変数1つに正本を寄せられます。

```bash
# .env — カテゴリ名の正本はここ1行だけ
CATEGORY_SECURITY=セキュリティ
WEBEX_SPACE_ID_SECURITY=Y2lzY29zcGFyazovL3VzL1JPT00v...
WEBEX_BOT_TOKEN_SECURITY=...        # 省略時は共通の WEBEX_BOT_TOKEN
```

```yaml
# channels.yml
channels:
  - name: ${CATEGORY_SECURITY}
    webex_space_id: ${WEBEX_SPACE_ID_SECURITY}

# categories.yml
${CATEGORY_SECURITY}:
  - "!セキュリティ"
  - ランサムウェア
```

**サフィックス（`SECURITY`）が配列の添字**にあたります。チャンネルを増やすときは、同じサフィックスで変数を足すだけです。カテゴリ名を変えたいときも `.env` の1行を直せば、チャンネル名・カテゴリ定義・投稿見出しが同時に変わるため、**名前がずれる余地がありません**。

- 既定の `${MYFAB_KEYWORD}` もこの仕組みです（社名を公開リポジトリに出さない用途）。
- **直書き（`name: セキュリティ`）もこれまでどおり動きます。** 変数方式は任意で、混在も可能です。
- 初期設定ウィザードのステップ5で「カテゴリ名を `.env` の変数で管理する」を選ぶと、`.env`・`config.yml`・`categories.yml` の3つを揃えて生成します（既存の設定を変数方式へ移行することもできます）。

#### 名前の綴り違いを検出する / Name-reference checks

`defers_to` と `source_groups` は**名前で参照**するため、綴りがずれると黙って無効化されます。これを防ぐため、実行時に次を検証します。

| 検出内容 | 動作 |
|:---|:---|
| `defers_to` が存在しないチャンネル名を指している | 警告を表示（その譲渡は行われない旨と、定義済みチャンネル名の一覧） |
| `source_groups` が `feeds:` のグループ名と一致しない | 警告を表示 |
| 上に加えて `categories: []` のとき | **そのチャンネルをスキップ**（絞り込みが全て外れ、全記事が流れ込むため） |

#### チャンネル間の配信制御 / Cross-channel routing

複数のカテゴリにマッチする記事を、目的に合ったチャンネルへ効率よく振り分けるために以下のロジックが順番に適用されます。

| Phase | 内容 |
|:---:|:---|
| **1. 事前フィルタ** | 各チャンネルの該当記事を抽出（キーワード + `source_groups`/`source_feeds`） |
| **1.4. source 専有** | `source_groups`/`source_feeds` を持つチャンネルは、そのフィード由来の記事を専有し、他の全チャンネル（`priority` 含む）から除外（例: Cisco Security Advisories を専用スペースへ隔離） |
| **1.5. 優先独占** | `priority: true` のチャンネルにマッチした記事を、他チャンネルから自動除外（例: Cisco記事は Cisco チャンネルでのみ配信） |
| **1.6. 譲渡 (defers_to)** | `defers_to: [...]` のチャンネルは、指定された譲渡先チャンネルにも該当する記事を譲渡先のみに残し、自分の側から除外（例: AI・機械学習はセキュリティ／ネットワーク寄りの記事を譲る） |
| **2. ニッチ優先** | 15件超の混雑チャンネルから、同じ記事が15件以下の余裕チャンネルにも該当する場合、余裕側のみに残して混雑側から除外 |
| **2.5. 日本語下限保証** | `min_japanese: N` を持つチャンネルが N 件未満の場合、`all_entries` の日本語記事（タイトルにひらがな/カタカナを含む）を新着順に補充（他チャンネル配信分とは重複させない）。厳格な必須語ゲートを迂回して日本のニュースの下限を保証 |
| **3. LLM再ランク** | それでも15件を超えるチャンネルでは、Claude がスコア上位40候補から**重要度順に15件を選定**（API未設定・失敗時はスコア階層＋階層内ランダム抽出にフォールバック）。詳細は[LLMによるニュース選出](#llmによるニュース選出再ランク--llm-re-ranking)参照 |
| **4. デイリーダイジェスト** | `digest: true` チャンネルへ、全チャンネル配信後に天気（今日・明日／4地点）＋各チャンネルの投稿ダイジェスト＋時事ダイジェスト（`regions.yml` があれば地域バランス日本/米国/その他、無ければ🇯🇵日本のニュース枠）を1通で配信 |

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

記事本文のキーワードではなく **「どの RSS フィード由来か」** でチャンネルを決めたい場合は、`urls.yml` に名前付きグループを定義し、`channels.yml` の `source_groups` で参照します。URL の正本は `urls.yml` に一本化され、`channels.yml` にはグループ名だけを書きます。

```yaml
# urls.yml — フィードの正本（グループにまとめる）
- group: cisco-advisory
  urls:
    - https://sec.cloudapps.cisco.com/security/center/psirtrss20/CiscoSecurityAdvisory.xml
```

```yaml
# channels.yml — グループ名だけを参照（URL は書かない）
- name: "News Today : Cisco Security Advisories"
  webex_space_id: ${WEBEX_SPACE_ID_CISCO_ADVISORY}
  webex_bot_token: ${WEBEX_BOT_TOKEN_CISCO_ADVISORY}
  priority: true
  source_groups:
    - cisco-advisory   # feeds: の group を参照
  categories: []       # キーワード分類はせず、このグループ由来のみ配信
```

- `source_groups` のフィードは `feeds:` に定義されていれば自動で収集対象になります（別途 `feeds:` の平文リストに重複して書く必要はありません）。
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

#### デイリーダイジェスト（天気＋投稿ニュース集約）/ Daily digest (weather + posted-news recap)

朝に全体像を1か所で把握するための専用チャンネルです。`digest: true` を指定すると、そのチャンネルは自前のカテゴリ収集を行わず、**全チャンネル配信後**に以下を1通へ集約して配信します。

1. **今日・明日の天気**（東京・横浜・千葉・札幌の4地点）… [Open-Meteo](https://open-meteo.com/) から取得（**APIキー不要・無料**）。天気絵文字・最高/最低気温・降水確率を地点ごとに今日/明日の2列で表示。取得に失敗した地点はスキップ（全滅時は天気ブロックごと省略）し、ダイジェスト本体は必ず配信します。
2. **各チャンネルの投稿ダイジェスト**… 各チャンネルが**実際に投稿した**記事を、チャンネル別に見出し上位5件（超過分は「…他M件」）で列挙。RSS を再取得せず、配信結果をメモリから集約するため本体投稿と内容が完全一致します。
3. **📰 時事ダイジェスト（地域バランス）** … `regions.yml` があれば、一般・世の中ニュース（テック/経済/専門カテゴリは除外）から **日本6-7・米国3・その他5** の地域バランスで新着順に選出（下記）。`regions.yml` が無い場合は従来の**🇯🇵 日本のニュース枠**（日本語記事を新着順に最低5件）にフォールバックします。いずれも各チャンネル枠で既出の記事とは重複させません。

```yaml
# config.yml
- name: デイリーダイジェスト
  webex_space_id: ${WEBEX_SPACE_ID_DIGEST}
  webex_bot_token: ${WEBEX_BOT_TOKEN_DIGEST}
  digest: true         # 自身は収集せず、他チャンネルの投稿結果＋天気を集約
  categories: []
```

`.env` に `WEBEX_SPACE_ID_DIGEST`（必要なら `WEBEX_BOT_TOKEN_DIGEST`）を設定するまで、このチャンネルは自動的にスキップされます（段階導入が安全）。Room ID は `python check_rooms.py --find "デイリーダイジェスト"` で確認できます。

**日本語ニュースの下限保証（`min_japanese`）** — 厳格なキーワードゲート（`一般` カテゴリの必須語）で日本のニュースが減った場合の保険として、通常チャンネルにも `min_japanese: N` を指定できます。確定件数が N 件未満なら、日本語記事を新着順に補充して下限を満たします（Phase 2.5、他チャンネル配信分とは重複させない）。

```yaml
- name: 世の中ニュース
  min_japanese: 5      # 5件未満なら日本語記事で補充
  categories:
    - 一般
```

**時事ダイジェストの地域バランス（`regions.yml`）** — デイジェストの時事枠を地域バランスで構成します。候補は**一般・世の中ニュース**のみ（AI/セキュリティ/ネットワーク/クラウド/Cisco/**経済**などの専門カテゴリは除外。経済は専用スペースの配信で扱う想定）。各記事を「日本 / 米国 / その他」に分類し、クオータに従って新着順に選び、不足分は**日本→その他**の順で補充します（**米国は上限を超えない**）。

- **地域判定**: タイトル＋概要に **米国キーワード**（アメリカ / 米国 / トランプ / ワシントン 等）があれば「米国」、なければ**その他外国キーワード**（中国 / 韓国 / ロシア / 欧州 等）があれば「その他」、いずれも無ければ「日本（国内）」。
- **設定の集約**: クオータと地域キーワードの正本は `regions.yml`（`regions.yml.example` が雛形）。コードには直書きしません。ファイルが無ければ従来の日本ニュース枠にフォールバックします。

```yaml
# regions.yml
quota: { japan: 7, us: 3, other: 5 }
keywords:
  us:    [アメリカ, 米国, トランプ, ワシントン, 米軍, 米中]
  other: [中国, 韓国, ロシア, ウクライナ, 欧州, EU]
# japan（国内）は上記いずれにも該当しない日本語ニュース
```

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
| 一般 | 35 | 39 | 重大な災害・事件・政治イベント |
| 経済 | 31 | 26 | 値上げ/利上げ/買収/リストラ等の経済動向 |
| AI・機械学習 | 22 | 22 | OpenAI/Anthropic/Claude/LLM/Agentic AI |
| セキュリティ | 26 | 61 | CVE・脆弱性・ランサムウェア・APT等 |
| ネットワーク | 42 | 128 | SD-WAN/SASE/ZTNA/Wi-Fi/5G/プロトコル ＋ **クラウド**（AWS/Azure/GCP/Kubernetes/データセンター）を統合 |
| Cisco | 43 | 108 | Cisco固有ブランド + compound必須語 |

### 3. RSSフィード設定 (`urls.yml`) / RSS feed list
ニュースの収集元となるRSSフィードURLの一覧を管理します。各要素は **文字列（通常のURL）** または **名前付きグループ** のどちらでも記述できます。  
Lists the RSS feed URLs to collect articles from. Each item is either a plain URL string or a named group.
```yaml
# 通常のフィード（文字列）
- https://blogs.cisco.com/feed
- https://zenn.dev/topics/aiagent/feed
- https://b.hatena.ne.jp/search/tag?q=AI&mode=rss

# 名前付きグループ（channels: の source_groups から参照）
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

`categories.yml` や `config.yml` の中で **`${VAR}` 形式のプレースホルダー** を使うと、実行時に `.env` の値で展開されます。YAML ファイル自体には会社名が含まれないため、そのままリポジトリに公開できます。  
Use **`${VAR}` placeholders** inside `categories.yml` and `config.yml`. They are resolved at runtime from `.env`. The YAML files themselves contain no sensitive names and can be safely committed.

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

#### `config.yml` での使い方 / Usage in `config.yml`

チャンネル名・Space ID・Bot トークン・カテゴリ名のすべてを `${VAR}` で秘匿できます。  
Channel name, Space ID, Bot token, and category name can all be hidden with `${VAR}`.

```yaml
# config.yml（公開リポジトリにそのままコミット可）
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
| チャンネル名・Space ID を公開したくない | `config.yml` の `${VAR}` 展開一択 |
| 新規チャンネルごと非公開にしたい | 両方の組み合わせ（`config.yml` で `${VAR}`、キーワードは `categories-private.yml`） |

> **組み合わせ例 / Combined example**: `config.yml` に `${MY_FAB_BRAND}` でチャンネルを定義し、キーワードは `categories-private.yml` に `${MY_FAB_BRAND}` カテゴリとして書く。`.env` で `MY_FAB_BRAND=自社ブランド` を設定するだけで両方が連動する。

---

## AI による自動要約 ＆ 超エコノミーモード / LLM Summarization & Eco-mode

**使う AI は3つから選べます**（`.env` の `LLM_PROVIDER`、または設定画面の「要約AI」タブ）。

| 選択肢 | `LLM_PROVIDER` | 使うキー | モデル名の例 |
|:---|:---|:---|:---|
| Claude（Anthropic） | `anthropic`（既定） | `ANTHROPIC_API_KEY` | `claude-haiku-4-5-20251001` |
| OpenAI | `openai` | `OPENAI_API_KEY` | `gpt-4o-mini` |
| Gemini（Google） | `gemini` | `GEMINI_API_KEY` | `gemini-2.0-flash` |

モデル名は `ANTHROPIC_MODEL`（要約用）と `ANTHROPIC_RERANK_MODEL`（記事の選定用）に書きます。
変数名は歴史的に `ANTHROPIC_` で始まりますが、**どの AI を選んだ場合でもこの2つを使います**。

> **何も設定しなければ、これまでどおり Claude として動きます。** 要約自体を使わない場合は、キーを設定しなければ RSS の紹介文がそのまま載ります。


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

> **✅ 推奨構成（v1.1.0〜）: TCC 保護外のパスにリポジトリを置いて直接実行**（→ [リポジトリの置き場所](#リポジトリの置き場所--where-to-put-this-repository)）  
> リポジトリを `~/Developer/rss-bot` のような **TCC 保護対象外のフォルダ**に置く場合、コピーデプロイは不要です。launchd の plist からこのリポジトリの `run_rssbot.sh` を直接指定してください（`run_rssbot.sh` は自身の場所を基準に動作します）。ログはリポジトリ内 `log/` にタイムスタンプ付きで出力されます。  
> If the repo lives outside TCC-protected folders (e.g. `~/Developer/rss-bot`), point launchd directly at `run_rssbot.sh` — no copy-deploy needed.

**推奨構成の手順 / Steps for the recommended setup**（テンプレートを2つコピーするだけ）

```bash
# 1. ラッパースクリプト（パス編集は不要。自分の位置から解決する）
cp run_rssbot.sh.example run_rssbot.sh
chmod +x run_rssbot.sh

# 2. launchd ジョブ定義（__REPO_DIR__ をこのリポジトリの絶対パスへ置換）
cp webex-news-rss-bot.plist.example webex-news-rss-bot.plist
sed -i '' "s|__REPO_DIR__|$(pwd)|g" webex-news-rss-bot.plist

# 3. LaunchAgents へ配置して読み込む
cp webex-news-rss-bot.plist ~/Library/LaunchAgents/com.webex-news.rssbot.plist
launchctl unload ~/Library/LaunchAgents/com.webex-news.rssbot.plist 2>/dev/null
launchctl load   ~/Library/LaunchAgents/com.webex-news.rssbot.plist

# 4. 手動テスト実行
launchctl start com.webex-news.rssbot
```

テンプレートの既定は **平日（月〜金）9:01 実行**で、`run_rssbot.sh` は `--weekend-catchup`（月曜のみ72時間分を取得）付きで本体を呼びます。毎日実行にしたい場合は plist の `StartCalendarInterval` を単一 `<dict>` にし、`--weekend-catchup` を外してください。  
The templates default to weekdays 09:01 with `--weekend-catchup`; edit both files for a daily schedule.

以下は、リポジトリが `~/Documents` など **TCC 保護下にある場合**の従来方式です。macOSのセキュリティ機能により、`Documents` や `Desktop` などの保護されたフォルダ内ではバックグラウンド実行がブロックされてしまう場合があります。そのため、ホームディレクトリ直下 (`~/rss-bot`) に専用の実行環境を構築・同期するデプロイスクリプトを用意しています。

**デプロイスクリプトの実行**
初めてセットアップする際、およびソースコードや設定ファイル（`config.yml`等）を更新した後は、ターミナルで以下のスクリプトを実行してください。

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

> **置き場所の注意**: `C:\tools\rss-bot` のように、**OneDrive 同期フォルダーと「制御されたフォルダー アクセス」の対象外**に置いてください。`Documents` や `Desktop` 配下は、OneDrive のフォルダー バックアップでパスが変わったり、Defender の設定で `log/` への書き込みが拒否されたりして、**タスクスケジューラからの実行だけが失敗**することがあります。詳細は [リポジトリの置き場所](#リポジトリの置き場所--where-to-put-this-repository) を参照。

#### 1. Python の仮想環境を作成・有効化 / Create and activate venv
```powershell
cd C:\tools\rss-bot
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

#### 2. タスクスケジューラへの登録 / Register with Task Scheduler

**同梱の `自動実行を登録.bat` をダブルクリックするのが簡単です。** 管理者権限は不要で、登録・解除・状態確認・今すぐ実行をメニューから選べます。  
The simplest way: double-click **`自動実行を登録.bat`** (no admin rights needed).

| メニュー | 内容 |
|:---:|:---|
| 1 | 平日 09:01 に実行するタスクを登録（タスク名 `rss-bot daily`） |
| 2 | 登録したタスクを解除 |
| 3 | 現在の状態を表示 |
| 4 | 今すぐ1回実行して動作確認 |

登録されるタスクは `run_rssbot.bat` を呼びます。これは macOS の `run_rssbot.sh` に相当するラッパーで、**実行ごとにタイムスタンプ付きログを `log\` に出力**し、スリープ復帰直後などに備えて**投稿先へ疎通できるまで最大5分待って**から本体を起動します。パス編集は不要です。

<details>
<summary><b>PowerShell で手動登録する場合 / Manual registration with PowerShell</b></summary>

PowerShell から以下のコマンドで、毎日 09:01 に実行するタスクを登録できます。  
Run the following PowerShell command to register a daily task at 09:01:

```powershell
$action  = New-ScheduledTaskAction `
    -Execute "C:\tools\rss-bot\venv\Scripts\python.exe" `
    -Argument "C:\tools\rss-bot\webex-news-rss-bot.py" `
    -WorkingDirectory "C:\tools\rss-bot"
$trigger = New-ScheduledTaskTrigger -Daily -At "09:01"
$settings = New-ScheduledTaskSettingsSet -WakeToRun  # スリープ復帰して実行
Register-ScheduledTask -TaskName "webex-news-rss-bot" `
    -Action $action -Trigger $trigger -Settings $settings -RunLevel Highest
```

> `-WakeToRun` オプションにより、タスク実行時刻に PC がスリープ中でも自動的に復帰して実行されます（BIOS/UEFI の Wake Timer が有効な場合）。  
> `-WakeToRun` wakes the PC from sleep at the scheduled time if the BIOS/UEFI Wake Timer is enabled.

</details>

#### 3. 手動テスト実行 / Manual test run
```powershell
python webex-news-rss-bot.py --dry-run
```

### 現時点での制限 / Current limitations

- `deploy_to_launchd.sh`（TCC 回避のためのコピー配置）に相当するものは Windows では不要です。Windows には TCC のような制限が無いため、リポジトリをその場に置いたまま `自動実行を登録.bat` で登録できます（同期フォルダーは避けてください）。  
  No Windows equivalent of `deploy_to_launchd.sh` is needed — Windows has no TCC-style restriction.
- `.env` の読み込みは `python-dotenv` が担うため、Windows でも動作します。  
  `.env` loading via `python-dotenv` works on Windows without changes.

---

## ファイル構成 / File Structure

Git に含まれるのはコードとテンプレート（`*.example`）です。`.example` の付かない設定ファイルは各自の環境で作成するもので、Git 管理対象外です（🔒印）。  
Only code and `*.example` templates are tracked. Files marked 🔒 are gitignored and created by you.

```text
rss-bot/
├── webex-news-rss-bot.py      # メインの実行スクリプト (ニュース収集・要約・配信)
├── analyze_filter.py          # フィルタ動作診断ツール (合格/near-miss/不一致を可視化)
├── check_rooms.py             # Webex ルーム名・ID確認ツール（CLI）
├── check_rooms_ui.py          # 同ツールのブラウザUI版（Streamlit）
├── setup.py                   # 初期設定ウィザードのブートストラップ（標準ライブラリのみ）
├── wizard/                    # ウィザード本体（core=共通ロジック / cli=対話版 / app=ブラウザ版）
├── はじめに設定する.command     # macOS: ダブルクリックで初期設定ウィザードを起動
├── はじめに設定する.bat         # Windows: ダブルクリックで初期設定ウィザードを起動
├── 起動_スペースID確認UI.bat    # Windows: ダブルクリックでスペースID確認UIを起動
├── 自動実行を登録.bat           # Windows: タスクスケジューラへ登録・解除・状態確認
├── run_rssbot.bat             # Windows: タスクから呼ばれるラッパー（ログ・ネットワーク待ち）
├── .gitattributes             # 改行コードの固定（.bat は CRLF）
├── deploy_to_launchd.sh       # ~/rss-bot へ同期＆launchd登録するデプロイスクリプト
├── categories.yml             # キーワードによるカテゴリ分け設定（必須語/通常語）
├── requirements.txt           # 依存ライブラリ一覧
├── requirements-ui.txt        # ブラウザUI用の追加依存（本体には不要）
├── .gitignore                 # Git除外設定
├── README.md                  # このドキュメント
│
│   # ─ テンプレート / Templates（コピーして使う）─
├── .env.example               # 認証情報＆環境変数のテンプレート
├── config.yml.example         # フィード一覧＋配信チャンネルのテンプレート（そのままでも動作）
├── regions.yml.example        # ダイジェストの地域バランス設定のテンプレート
├── morning_messages.txt.example    # 朝メッセージ（投稿末尾のランダム署名）のテンプレート
├── categories-private.yml.example  # 非公開キーワードオーバーレイのテンプレート
├── run_rssbot.sh.example      # launchd から呼ぶラッパースクリプトのテンプレート
├── webex-news-rss-bot.plist.example  # launchd 用 plist テンプレート（com.webex-news.rssbot）
│
│   # ─ 各自で作成 / Created by you（🔒 Git対象外）─
├── .env                    🔒 # 認証情報＆環境変数
├── config.yml              🔒 # フィード一覧（feeds:）＋配信チャンネル（channels:）
├── regions.yml             🔒 # 時事ダイジェストの地域バランス（任意）
├── morning_messages.txt    🔒 # 朝メッセージのリスト（任意）
├── categories-private.yml  🔒 # 非公開キーワードオーバーレイ（任意）
├── run_rssbot.sh           🔒 # launchd 用ラッパー（自動実行する場合）
├── webex-news-rss-bot.plist 🔒 # launchd ジョブ定義（自動実行する場合）
├── *.bak-YYYYMMDD-HHMMSS   🔒 # ウィザードが上書き前に作る退避ファイル（不要なら削除可）
├── log/                    🔒 # 実行ログ（launchd_run-YYYYMMDD-HHMMSS.log / launchd_err-...log）
└── bin/ lib/ include/      🔒 # 仮想環境 (python3 -m venv .)
```

### 補助ツール / Auxiliary tools

#### `check_rooms_ui.py` / `check_rooms.py` - スペースID確認
Webex スペースの一覧・検索と、`.env` / `config.yml` に書く行の生成。ブラウザUI版とCLI版があります（→ [ルームID確認ツール](#ルームid確認ツール--room-id-checker-check_roomspy)）。

```bash
./bin/streamlit run check_rooms_ui.py   # ブラウザUI（要 requirements-ui.txt）
./bin/python check_rooms.py --find AI   # CLI
```

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

### ❌ CISA や community.cisco.com が 403 になる
* 以前のバージョンではブラウザ風UA（Mozilla/Chrome）を使っており、これらのbot保護サイトで403が出ていました。現バージョンは `rss-bot/1.0` という **フィードリーダ系UA** を採用しており、多くのサイトで改善します。
* ただし **2026-07 現在、community.cisco.com はフィードリーダ系UAでも403を返す**ことが確認されています（サイト側のbot対策強化）。該当フィードのエラーはスクリプト内で握りつぶされ、他のフィードの収集は継続します。恒久対応（フィードの代替URL化・削除）は検討中です。
  As of 2026-07, community.cisco.com rejects even feed-reader UAs (403). These per-feed errors are caught and do not stop the run.

---

*Developed with ❤️ for webex-news-rss-bot*

---

## 更新履歴 / Version History

各版で**結局なにが変わったか**を1〜2行でまとめています。細かい仕様は本文の該当セクションを参照してください。

| Version | 日付 | 何をしたか |
|:---|:---|:---|
| **v4.13.0** | 2026-08-02 | **毎朝の自動実行を画面から設定**できるようにした（時刻・曜日を選ぶだけ。macOS は launchd、Windows はタスク スケジューラへ登録／解除／即時実行）。ブラウザUI・ターミナルの両方に対応。あわせて、**保存前に「何を上書き・追加するか」を一覧で示し、承諾しないと保存できない**ようにした。要約AI を切り替えるときは、他社のキーが設定済みである旨を警告する。 |
| **v4.12.0** | 2026-08-02 | 設定ファイルが1つも無い状態でも、**bot を用意した時点でひな形から自動生成**するようにした（`.env` / `urls.yml` / `channels.yml` / `regions.yml` / `morning_messages.txt`）。既にあるファイルには触れない。ブラウザUI・ターミナル、macOS・Windows のいずれでも同じように動く。 |
| **v4.11.0** | 2026-08-02 | 要約に使う AI を **Claude / OpenAI / Gemini から選べる**ようにした。モデル名は自由記述（新しいモデルが出てもそのまま書ける）で、書き方が違えばその場で指摘し、「接続を試す」で実際に使えるか確認できる。**設定していない場合は従来どおり Claude として動く**。 |
| **v4.10.0** | 2026-08-02 | README を Python 未経験者向けに整理。冒頭に「これは何をするもの？」「用語集」「届くメッセージの例」を追加し、細かい仕様一覧は折りたたみに。更新履歴は各版1〜2行の要約に書き直した。 |
| **v4.9.1** | 2026-08-02 | 上書き前の退避ファイル（`*.bak-日時`）を Git 管理から明示的に外し、README に戻し方を記載。 |
| **v4.9.0** | 2026-08-02 | 天気の観測地点を**地名から設定**できるようにした（緯度経度を自動取得）。既存設定にあった座標の誤りも修正。 |
| **v4.8.0** | 2026-08-02 | 設定画面に「**設定の全体像**」タブを追加。いまの設定・記事の流れ・注意点を1画面で確認できる。 |
| **v4.7.0** | 2026-08-02 | 設定画面が一部のチャンネル（変数で名前を決めているもの、フィード指定のもの）を正しく読めず、保存すると壊れる不具合を修正。bot とスペースを調べる画面も追加。 |
| **v4.6.0** | 2026-08-02 | 保存時にスペースIDの変数名が作り替えられ、配信が止まる不具合を修正。スペース一覧とトークンの一括確認を追加。 |
| **v4.5.1** | 2026-08-02 | bot を切り替えたときに、チャンネル名の欄に前の設定が残る不具合を修正。 |
| **v4.5.0** | 2026-08-02 | 設定画面を**チャンネル単位**に作り直した。1つのスペースに複数のチャンネルを向けられるようになった。 |
| **v4.4.0** | 2026-08-02 | 記事の譲り合い（`defers_to`）や日本語記事の下限などの細かい設定と、ダイジェストの**地域バランス**を画面から設定できるようにした。 |
| **v4.3.0** | 2026-08-02 | Claude（要約）の設定画面を追加。**設定を保存すると他の設定が消えてしまう重大な不具合**を2件修正。 |
| **v4.2.0** | 2026-08-02 | **天気とまとめを送るチャンネル**を画面から作れるようにした。天気の観測地点も設定可能に。 |
| **v4.1.0** | 2026-08-02 | 設定画面を3つのタブ（セットアップ／URL／カテゴリ）に整理し、それぞれ独立して編集できるようにした。 |
| **v4.0.0** | 2026-08-01 | ⚠️ 設定ファイルを用途ごとに分割（`urls.yml` = 集めるフィード、`channels.yml` = 配信先）。**旧 `config.yml` のままでも動く**。 |
| **v3.5.0** | 2026-08-01 | カテゴリ名を `.env` の変数にまとめられるようにし、チャンネル名とカテゴリ名がずれないようにした。 |
| **v3.4.0** | 2026-08-01 | ウィザードで**既存の設定を読み込んで編集**できるようにした。触らない設定はそのまま引き継ぐ。 |
| **v3.3.0** | 2026-08-01 | ウィザードに「chat bot の用意」を追加。設定済みの bot を選ぶか、Webex の作成ページへ案内する。 |
| **v3.2.0** | 2026-08-01 | Windows 用のバッチ一式（UI起動・定時実行・タスク登録）を用意し、文字化けも修正。 |
| **v3.1.0** | 2026-08-01 | **初期設定ウィザード**を追加。ダブルクリックで、環境確認から設定作成・動作確認まで案内する。 |
| **v3.0.0** | 2026-08-01 | ⚠️ `クラウド` カテゴリを `ネットワーク` に統合。あわせて**置き場所**（macOS の保護フォルダ、Windows の同期フォルダ）の注意を明文化。 |
| **v2.0.2** | 2026-07-31 | Cisco の脆弱性情報に、深刻度が一目で分かる **CVSS スコアのバッジ**を付けた。 |
| **v2.0.1** | 2026-07-31 | 該当ニュースが0件のスペースには、空の通知も含めて**何も投稿しない**ようにした。 |
| **v2.0.0** | 2026-07-31 | ⚠️ 設定を `config.yml` に一本化（のち v4.0.0 で再分割）。スペースIDを調べるブラウザUIを追加。チャンネル名がカテゴリ名と同じなら `categories:` を省略できるようにした。 |
| **v1.2.1** | 2026-07-31 | clone した人がコピーして編集するだけで動くよう、設定のひな形（`*.example`）を全部そろえ、README を初心者向けに整理。 |
| **v1.2.0** | 2026-07-25 | **デイリーダイジェスト**（天気＋その日の投稿まとめ）を追加。日本語記事の下限保証、月曜の週末キャッチアップも。 |
| **v1.1.0** | 2026-07-13 | 記事の選び方を改善（Claude が重要度順に選定）。取得を並列化して実行時間を短縮。フィード由来での振り分けにも対応。 |
| **v1.0.4** | 2026-06-11 | 実行ログを1回ごとの別ファイル（日時つき）に分けた。 |
| **v1.0.3** | 2026-06-03 | macOS で定時実行が動かない理由と対処、Windows での使い方を README に追記。 |
| **v1.0.2** | 2026-06-03 | `.env` のひな形に、全項目の説明を書いた。 |
| **v1.0.1** | 2026-06-03 | MIT ライセンスを追加。 |
| **v1.0.0** | 2026-06-03 | 初版。RSS の収集・仕分け・重複除去・要約・複数スペースへの配信と、毎朝の自動実行までを実装。 |

> ⚠️ 印は、**それまでの設定のままでは動かない可能性がある変更**です。該当する場合は [v1.x から更新する人へ](#v1x-から更新する人へ--upgrading-from-v1x) を参照してください。

---
