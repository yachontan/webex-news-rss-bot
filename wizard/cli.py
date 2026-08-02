"""初期設定ウィザードの CLI 版 / Terminal wizard for rss-bot setup.

ブラウザUI版（app.py）と同じ core.py を使うため、生成される設定は同じになる。

実行 / Run:
    ./bin/python -m wizard.cli
"""

from __future__ import annotations

import getpass
import sys
import webbrowser
from pathlib import Path

from . import core

RULE = "-" * 60


def _ask(prompt: str, default: str = "") -> str:
    """1行入力を受け取る。空入力なら default を返す。"""
    suffix = f" [{default}]" if default else ""
    try:
        answer = input(f"{prompt}{suffix}: ").strip()
    except EOFError:
        return default
    return answer or default


def _ask_yes(prompt: str, default: bool = True) -> bool:
    """はい/いいえを尋ねる。"""
    hint = "Y/n" if default else "y/N"
    answer = _ask(f"{prompt} ({hint})").lower()
    if not answer:
        return default
    return answer.startswith("y")


def step_diagnostics() -> bool:
    """ステップ0: 環境を診断し、続行してよいかを返す。"""
    print(f"\n{RULE}\nステップ 0 / 環境を確認します\n{RULE}")
    checks = core.run_diagnostics()
    for check in checks:
        mark = "✅" if check.ok else ("❌" if check.fatal else "⚠️ ")
        print(f"  {mark} {check.name}: {check.detail}")
        if check.hint:
            print(f"      → {check.hint}")
    if any(c.fatal for c in checks):
        print("\n続行できない問題があります。上の指示に従ってから、もう一度実行してください。")
        return False
    if any(not c.ok for c in checks):
        return _ask_yes("\n警告がありますが続けますか？", default=False)
    return True


def _guide_bot_creation() -> None:
    """Webex ポータルで chat bot を作る手順を案内し、作成ページを開く。"""
    print("\nWebex の chat bot は、開発者ポータルの画面から作成します。")
    print("（商用環境には bot を作成する API が無いため、ここだけはブラウザ操作が必要です）")
    print(f"\n  作成ページ: {core.BOT_CREATE_URL}")
    if _ask_yes("\nブラウザでこのページを開きますか？"):
        webbrowser.open(core.BOT_CREATE_URL)  # noqa: E04  ファイル入出力ではなくURLを開く
    print("""
  1. Bot name（表示名）と Bot username（@webex.bot のアドレス）を入力
  2. アイコンを選び、Description を書く
  3. 「Add Bot」を押す
  4. 次の画面に出る Bot Access Token をコピー（この画面を離れると二度と表示されません）

  ※ 作成した bot は、投稿したいスペースにメンバーとして追加しておいてください。
    追加していないスペースは、次のステップの一覧に出てきません。
""")


def step_bot() -> str:
    """ステップ1: chat bot を用意し、使うトークンを返す。"""
    print(f"\n{RULE}\nステップ 1 / chat bot を用意します\n{RULE}")
    known = core.detect_env_tokens()
    if known:
        print("設定済みのトークンが見つかりました（変数名のみ表示します）:")
        for i, name in enumerate(known, start=1):
            print(f"  {i}. {name}")
        print(f"  {len(known) + 1}. 新しく bot を作る")
        choice = _ask("番号", default="1")
        if choice.isdigit() and 1 <= int(choice) <= len(known):
            name = known[int(choice) - 1]
            print(f"  ✅ {name} を使います。")
            return core.get_env_token(name)
    _guide_bot_creation()
    return getpass.getpass("作成した bot のアクセストークンを貼り付けてください: ").strip()


def step_token(token: str) -> tuple[str, list[dict]]:
    """ステップ2: トークンを検証し、スペース一覧を返す。"""
    print(f"\n{RULE}\nステップ 2 / bot を確認します\n{RULE}")
    while True:
        ok, message = core.validate_token(token)
        print(f"  {'✅' if ok else '❌'} {message}")
        if ok:
            break
        if not _ask_yes("入力し直しますか？"):
            sys.exit(1)
        token = getpass.getpass("トークン: ").strip()
    spaces = core.list_spaces(token)
    print(f"  ✅ {len(spaces)} 件のスペースが見つかりました。")

    created = core.ensure_config_files()
    if created:
        print("  ✅ 設定ファイルをひな形から作りました: " + "、".join(created))
        print("     このあとの手順で中身を埋めていきます。")
    if not spaces:
        print("  ※ この bot が参加しているスペースがありません。")
        print("    Webex で bot をスペースに追加してから、もう一度実行してください。")
        sys.exit(1)
    return token, spaces


def _print_spaces(spaces: list[dict]) -> None:
    """スペース一覧を番号付きで表示する。"""
    for i, space in enumerate(spaces, start=1):
        print(f"  {i:3}. {space.get('title') or '(名前なし)'}")


def step_channels(spaces: list[dict], categories: list[str],
                  existing: core.ExistingConfig | None = None) -> list[core.ChannelPlan]:
    """ステップ3: 配信先スペースとカテゴリの組を作る。既存設定があれば現状を表示する。"""
    print(f"\n{RULE}\nステップ 3 / どのスペースに何を送るかを決めます\n{RULE}")
    assigned = existing.assigned if existing else {}
    if assigned:
        print("現在の設定:")
        for i, space in enumerate(spaces, start=1):
            current = assigned.get(space.get("id", ""))
            if current:
                print(f"  {i:3}. {space.get('title')} → {current}")
        print()
    _print_spaces(spaces)
    plans: list[core.ChannelPlan] = []
    while True:
        index = _ask("\n配信先スペースの番号（終わりは Enter）")
        if not index:
            break
        if not index.isdigit() or not 1 <= int(index) <= len(spaces):
            print("  番号が範囲外です。")
            continue
        space = spaces[int(index) - 1]
        print("  送るカテゴリ:")
        for i, name in enumerate(categories, start=1):
            print(f"    {i}. {name}")
        choice = _ask("  カテゴリの番号")
        if not choice.isdigit() or not 1 <= int(choice) <= len(categories):
            print("  番号が範囲外です。")
            continue
        category = categories[int(choice) - 1]
        space_id = space.get("id", "")
        default_name = assigned.get(space_id) or category
        name = _ask("  チャンネル名（投稿の見出しになります）", default=default_name)
        plans.append(core.ChannelPlan(
            name=name, categories=[category], space_id=space_id,
            space_title=space.get("title", ""),
            bot_token_ref=(existing.bot_tokens.get(space_id, "") if existing else ""),
        ))
        print(f"  ✅ {space.get('title')} ← {name}（カテゴリ: {category}）")
    return plans


def step_write(token: str, plans: list[core.ChannelPlan],
               existing: core.ExistingConfig | None = None) -> None:
    """ステップ5: .env と config.yml を書き出す。既存の高度な設定は引き継ぐ。"""
    print(f"\n{RULE}\nステップ 5 / 設定ファイルを作ります\n{RULE}")
    use_var = _ask_yes("カテゴリ名を .env の変数（${CATEGORY_*}）で管理しますか？"
                       "（チャンネル名と categories.yml のキーが必ず一致します）",
                       default=existing is None)
    for plan in plans:
        plan.use_category_var = use_var

    env_values: dict[str, str] = dict(core.DEFAULT_ENV_VALUES)
    for plan in plans:
        if use_var:
            env_values[plan.category_var] = plan.name
        env_values[plan.env_var] = plan.space_id
        if not plan.bot_token_ref:
            env_values[plan.token_var] = token
    feeds = existing.feed_urls if (existing and existing.feed_urls) else core.default_feed_urls()
    urls_text = core.build_urls_text(
        feeds, special_feeds=existing.special_feeds if existing else None)
    preserved = core.channels_to_preserve(existing, core.edited_channel_names(plans))
    channels_text = core.build_channels_text(plans, kept_channels=preserved)

    print("\n生成する config.yml の channels:")
    for plan in plans:
        print(f"  - name: {plan.name}  ←  {plan.space_title}（カテゴリ: {'、'.join(plan.categories)}）")
    if preserved:
        print(f"\n  編集せずそのまま残すチャンネル（{len(preserved)} 件）:")
        for channel in preserved:
            print(f"    - {channel.get('name')}")
    if existing:
        print(f"\n  フィード {len(feeds)} 件を引き継ぎます。")
        print("  ※ urls.yml / channels.yml のコメントは残りません（設定内容は保たれ、元は退避します）。")
    print(f"\n.env に書く変数: {', '.join(env_values)}（値は表示しません）")
    if not _ask_yes("\nこの内容で書き込みますか？"):
        print("中止しました。ファイルは変更していません。")
        return

    results = [core.backup_and_write(core.ENV_FILE, core.build_env_text(env_values)),
               core.backup_and_write(core.URLS_FILE, urls_text),
               core.backup_and_write(core.CHANNELS_FILE, channels_text)]
    if use_var:
        cat_text, cat_notes = core.sync_category_names(plans)
        if cat_notes:
            print("\n  categories.yml も揃えます: " + "、".join(cat_notes))
            results.append(core.backup_and_write(core.CATEGORIES_FILE, cat_text))
    for result in results:
        state = "作成" if result.created else "更新"
        print(f"  ✅ {result.path.name} を{state}しました"
              + (f"（元の内容は {result.backup.name} に退避）" if result.backup else ""))


def step_dry_run() -> None:
    """ステップ6: 送信せずに動作を確認する。"""
    print(f"\n{RULE}\nステップ 6 / 送信せずに動作を確認します\n{RULE}")
    if not _ask_yes("いま dry-run を実行しますか？（数分かかります）"):
        return
    python_path = core.venv_python() or Path(sys.executable)
    print("  収集中...")
    ok, output = core.run_dry_run(python_path)
    tail = "\n".join(output.splitlines()[-25:])
    print(tail)
    print(f"\n  {'✅ 正常に完了しました' if ok else '❌ 失敗しました。上の出力を確認してください'}")


def step_schedule() -> None:
    """ステップ7: 毎朝の自動実行を登録する（UI 版と同じ仕組みを使う）。"""
    print(f"\n{RULE}\nステップ 7 / 毎朝の自動実行を設定します\n{RULE}")
    registered, detail = core.schedule_status()
    print(f"  現在: {detail}")
    if not _ask_yes("自動実行を設定しますか？", default=not registered):
        print("  設定しませんでした。あとから「自動実行」タブでも設定できます。")
        return

    text = _ask("  何時に実行しますか（HH:MM）", default="09:01")
    try:
        hour, minute = (int(x) for x in text.split(":", 1))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError
    except ValueError:
        print("  時刻の書き方が違います（例: 09:01）。設定を中止しました。")
        return

    print("  曜日: 1=平日（月〜金） / 2=毎日 / 3=自分で選ぶ")
    choice = _ask("  番号", default="1")
    if choice == "2":
        weekdays = list(range(7))
    elif choice == "3":
        picked = _ask("  曜日を番号で（月=0 … 日=6、カンマ区切り）", default="0,1,2,3,4")
        weekdays = [int(x) for x in picked.split(",") if x.strip().isdigit() and 0 <= int(x) <= 6]
    else:
        weekdays = [0, 1, 2, 3, 4]

    print(f"  {core.describe_schedule(hour, minute, weekdays)}")
    if not _ask_yes("  この内容で登録しますか？"):
        print("  中止しました。")
        return
    ok, message = core.install_schedule(hour, minute, weekdays)
    print(f"  {'✅ 登録しました' if ok else '❌ 登録できませんでした'}: {message}")
    if ok:
        print("  ※ パソコンがスリープしていると実行されません。詳しくは README の「自動実行」を参照。")


def main() -> int:
    """CLI ウィザードのエントリポイント。"""
    print("=== rss-bot 初期設定ウィザード（CLI版）===")
    if not step_diagnostics():
        return 1
    categories = core.available_categories()
    if not categories:
        print("categories.yml が読めません。リポジトリが壊れていないか確認してください。")
        return 1
    token = step_bot()
    token, spaces = step_token(token)
    existing = core.load_existing_config()
    if existing:
        print(f"\n既存の設定を読み込みました（{existing.summary}）。")
    plans = step_channels(spaces, categories, existing)
    if not plans:
        print("\n配信先が選ばれていません。中止します。")
        return 1
    step_write(token, plans, existing)
    step_dry_run()
    step_schedule()
    print("\n完了しました。設定はいつでも `./bin/python -m wizard.cli` で見直せます。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
