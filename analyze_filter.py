#!/usr/bin/env python3
"""
analyze_filter.py
カテゴリフィルタの動作を診断するツール。

各カテゴリについて以下の内訳を可視化:
  - passed             : フィルタ通過（score >= 4 かつ必須語マッチ）
  - near_miss          : 必須語マッチあり／スコア不足（あと一歩）
  - normal_only        : 通常語はマッチするが必須語ゼロ（必須語追加候補の判定材料）
  - no_match           : タイトル・概要・タグに該当キーワード皆無

使い方:
  python analyze_filter.py                 # 全カテゴリ
  python analyze_filter.py Cisco セキュリティ   # 指定カテゴリのみ
"""

import importlib.util
import os
import sys
import time

_BASE = os.path.dirname(os.path.abspath(__file__))

# bot本体を import する前に time.sleep を無効化（フィード取得を高速化）
_orig_sleep = time.sleep
time.sleep = lambda s: None

# webex-news-rss-bot.py をモジュールとして読み込む（ハイフン入りのため importlib 経由）
_spec = importlib.util.spec_from_file_location("bot", os.path.join(_BASE, "webex-news-rss-bot.py"))
bot = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bot)


def analyze_category(entries, cat_name, category_keywords, min_score=4):
    if cat_name not in category_keywords:
        print(f"\n[SKIP] '{cat_name}' は categories.yml に未定義")
        return

    must = [k[1:] for k in category_keywords[cat_name] if str(k).startswith("!")]
    normal = [k for k in category_keywords[cat_name] if not str(k).startswith("!")]

    passed = []
    near_miss = []      # 必須OKだがscore < min_score、または必須未定義で score < min_score
    normal_only = []    # 必須語定義あり・通常語のみマッチ・必須語ゼロ
    no_match = 0

    for e in entries:
        text = (e["title"] + " " + e["summary"] + " " + " ".join(e.get("tags", []))).lower()
        mm = [k for k in must if k.lower() in text]
        nm = [k for k in normal if k.lower() in text]
        score = len(mm) * 3 + len(nm)

        info = {
            "title": e["title"][:70],
            "score": score,
            "must": mm,
            "normal": nm,
        }

        if must:
            if not mm:
                if nm:
                    normal_only.append(info)
                else:
                    no_match += 1
            elif score >= min_score:
                passed.append(info)
            else:
                near_miss.append(info)
        else:
            # 必須語未定義のカテゴリ
            if not nm:
                no_match += 1
            elif score >= min_score:
                passed.append(info)
            else:
                near_miss.append(info)

    print(f"\n{'=' * 78}")
    print(f"カテゴリ: {cat_name}  (必須語 {len(must)}件 / 通常語 {len(normal)}件 / 合格ライン score>={min_score})")
    print(f"{'=' * 78}")
    print(f"  ✅ 合格 (passed):                     {len(passed):4d} 件")
    print(f"  🟡 必須OKだがスコア不足 (near_miss): {len(near_miss):4d} 件 ← スコア閾値下げ or 通常語追加で救済可")
    print(f"  🟠 通常語のみマッチ・必須語ゼロ:        {len(normal_only):4d} 件 ← 必須語追加候補")
    print(f"  ⬜ 完全不一致:                         {no_match:4d} 件")

    if passed:
        print(f"\n  [合格記事サンプル 最大3件]")
        for info in passed[:3]:
            print(f"    score={info['score']:2d} 必須={info['must']} 通常={info['normal'][:4]}")
            print(f"           {info['title']}")

    if near_miss:
        print(f"\n  [🟡 おしい記事 - スコア降順 上位10件]")
        near_miss.sort(key=lambda x: -x["score"])
        for info in near_miss[:10]:
            print(f"    score={info['score']:2d} 必須={info['must']} 通常={info['normal'][:5]}")
            print(f"           {info['title']}")

    if normal_only:
        print(f"\n  [🟠 通常語のみマッチ - 通常語マッチ数降順 上位8件] ※タイトルに該当キーワード追加で救済可")
        normal_only.sort(key=lambda x: -len(x["normal"]))
        for info in normal_only[:8]:
            print(f"    通常語マッチ数={len(info['normal'])}: {info['normal'][:6]}")
            print(f"           {info['title']}")


def main():
    print("=== カテゴリフィルタ診断ツール ===\n")
    urls = bot.load_urls()
    cats = bot.load_categories()

    target = sys.argv[1:] if len(sys.argv) > 1 else list(cats.keys())
    print(f"対象カテゴリ: {target}")
    print(f"RSSフィード数: {len(urls)}（time.sleep無効化で高速取得）\n")

    entries = bot.collect_all_entries(urls, hours_ago=24, fallback_items=0)
    print(f"\n取得記事合計: {len(entries)} 件\n")

    for cat in target:
        analyze_category(entries, cat, cats, min_score=4)

    print(f"\n{'=' * 78}")
    print("分析完了")


if __name__ == "__main__":
    main()
