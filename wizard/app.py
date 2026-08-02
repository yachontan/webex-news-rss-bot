"""初期設定ウィザードのブラウザUI版 / Browser wizard for rss-bot setup.

CLI 版（cli.py）と同じ core.py を使うため、生成される設定は同じになる。

実行 / Run:
    ./bin/streamlit run wizard/app.py
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from wizard import core  # noqa: E402  sys.path を通してから読み込む必要がある

TOKEN_FROM_ENV = "`.env` から選ぶ"
TOKEN_MANUAL = "トークンを直接入力"

KIND_NEWS = "カテゴリ別のニュース"
KIND_DIGEST = "ダイジェスト（天気＋まとめ）"
KIND_SOURCE = "指定フィードのみ（グループ）"

st.set_page_config(page_title="rss-bot 初期設定ウィザード", page_icon="🧭", layout="wide")
st.title("🧭 rss-bot 初期設定ウィザード")
st.caption("clone したリポジトリを、あなたの環境に合わせて設定します。／ Configure rss-bot for your environment.")


def _render_change_review(env_values: dict[str, str], files: list[str],
                         key: str) -> bool:
    """保存前に「何が上書き・追加されるか」を見せて、承諾を得る。

    戻り値は「この内容で進めてよい」と利用者が同意したかどうか。
    """
    rows = core.diff_env_changes(env_values) if env_values else []
    changed = [r for r in rows if r["操作"] != "変更なし"]

    with st.container(border=True):
        st.write("**保存する前に確認してください**")
        if changed:
            st.caption(f"`.env` の設定: {core.summarize_env_changes(rows)}")
            st.dataframe(changed, width="stretch", hide_index=True)
        elif env_values:
            st.caption("`.env` の設定に変更はありません。")
        if files:
            st.warning("次のファイルは**いまの内容を作り直します**（コメントは残りません）: "
                       + "、".join(f"`{name}`" for name in files)
                       + "\n\n元のファイルは `.bak-日時` として同じ場所に残します。",
                       icon=":material/edit_note:")
        return st.checkbox("上の内容で上書き・追加してよい", key=f"agree_{key}")


def render_diagnostics() -> bool:
    """ステップ0: 環境診断。続行してよければ True。"""
    st.header("ステップ 0 ｜ 環境の確認")
    checks = core.run_diagnostics()
    for check in checks:
        if check.ok:
            st.success(f"**{check.name}**: {check.detail}")
        elif check.fatal:
            st.error(f"**{check.name}**: {check.detail}\n\n{check.hint}")
        else:
            st.warning(f"**{check.name}**: {check.detail}\n\n{check.hint}")
    if any(c.fatal for c in checks):
        st.stop()
    return True


def _render_bot_creation_guide() -> None:
    """Webex ポータルで Bot を新規作成する手順を示す。"""
    st.markdown(
        "Webex の chat bot は、**Webex 開発者ポータルの画面から作成します**"
        "（商用環境には bot を作成する API がないため、ここだけはブラウザでの操作が必要です）。"
    )
    st.link_button("Webex で chat bot を作成する", core.BOT_CREATE_URL,
                   icon=":material/open_in_new:", type="primary")
    st.markdown(
        """
        1. 開いたページで **Bot name**（表示名）と **Bot username**（`@webex.bot` のアドレスになる）を入力
        2. アイコンを選び、**Description** を書く
        3. **Add Bot** を押す
        4. 次の画面に表示される **Bot Access Token** をコピーする（この画面を離れると二度と表示されません）
        5. コピーしたトークンを下の欄に貼り付ける
        """
    )
    st.info("作成した bot は、投稿したいスペースに**メンバーとして追加**しておいてください。"
            "追加されていないスペースは、次のステップの一覧に出てきません。", icon=":material/info:")


def render_bot() -> str:
    """ステップ1: chat bot を用意する。使うトークンを返す（未確定なら空文字）。"""
    st.header("ステップ 1 ｜ chat bot の用意")
    known = core.detect_env_tokens()

    if known:
        choice = st.segmented_control(
            "使う bot",
            ["設定済みの bot を使う", "新しく bot を作る"],
            default="設定済みの bot を使う",
            key="bot_mode",
        )
    else:
        st.caption("まだ bot のトークンが設定されていません。新しく作りましょう。")
        choice = "新しく bot を作る"

    token = ""
    with st.container(border=True):
        if choice == "設定済みの bot を使う":
            st.caption("`.env` にあるトークンを検出しました。変数名だけを表示し、値は画面に出しません。")
            name = st.selectbox("使うトークン", known, key="known_token")
            token = core.get_env_token(name)
            st.caption(f"`{name}` を使用します。")
        else:
            _render_bot_creation_guide()
            token = st.text_input("作成した bot のアクセストークン", type="password",
                                  key="new_token",
                                  help="入力値は画面にもログにも残りません。").strip()
    return token


def render_token(token: str) -> str:
    """ステップ2: トークンを検証してスペース一覧を取得する。"""
    st.header("ステップ 2 ｜ bot の確認")
    if not token:
        st.info("上でトークンを選ぶか貼り付けると、続きの手順が表示されます。")
        return ""
    if st.session_state.get("validated_token") != token:
        with st.spinner("Webex に接続して確認しています..."):
            ok, message = core.validate_token(token)
        if not ok:
            st.error(message)
            return ""
        st.session_state["validated_token"] = token
        st.session_state["spaces"] = core.list_spaces(token)
    spaces = st.session_state.get("spaces", [])
    st.success(f"トークンは有効です。{len(spaces)} 件のスペースが見つかりました。")

    # 設定ファイルがまだ無ければ、この時点でひな形から作る（既存には触れない）
    created = core.ensure_config_files()
    if created:
        st.info("設定ファイルがまだ無かったので、ひな形から作りました: "
                + "、".join(f"`{name}`" for name in created)
                + "\n\nこのあとの手順で中身を埋めていきます。", icon=":material/note_add:")
    if not spaces:
        st.warning("この bot が参加しているスペースがありません。"
                   "Webex で bot をスペースに追加してから、ページを再読み込みしてください。",
                   icon=":material/warning:")
    else:
        st.caption("スペースの詳しい情報や Room ID は「bot とスペース」タブで確認できます。")
    return token


def _widget_key(space_id: str, name: str) -> str:
    """チャンネルを一意に指すウィジェットキー。

    連番だと bot を切り替えたときに別のチャンネルへ同じキーが割り当たり、
    前に表示していた値が session_state から復元されてしまう。
    スペースIDと元の名前から作ることで、並び順が変わっても取り違えない。
    """
    seed = f"{space_id}|{name}".encode("utf-8")
    return "ch_" + hashlib.md5(seed).hexdigest()[:10]


def _editable_channels(existing: core.ExistingConfig | None,
                       visible: dict[str, str]) -> tuple[list[dict], list[dict]]:
    """既存チャンネルを「この bot で編集できるもの」と「触らないもの」に分ける。"""
    if existing is None:
        return [], []
    editable, locked = [], []
    for channel in existing.all_channels:
        space_id = core._expand_env(channel.get("webex_space_id"))
        simple = not (set(channel) - core.SIMPLE_CHANNEL_KEYS)
        (editable if (simple and space_id in visible) else locked).append(channel)
    return editable, locked


def _channel_options_of(channel: dict) -> dict:
    """既存チャンネルの任意項目を取り出す。"""
    return {"defers_to": [str(x) for x in (channel.get("defers_to") or [])],
            "min_japanese": channel.get("min_japanese"),
            "priority": bool(channel.get("priority")),
            "source_groups": [str(x) for x in (channel.get("source_groups") or [])]}


def render_channels(categories: list[str],
                    existing: core.ExistingConfig | None) -> list[core.ChannelPlan]:
    """ステップ3: 配信するチャンネルを1件ずつ編集し、必要なら追加する。"""
    st.header("ステップ 3 ｜ 配信するチャンネル")
    spaces = st.session_state.get("spaces", [])
    visible = {s.get("id", ""): (s.get("title") or "(名前なし)") for s in spaces}
    st.caption("**チャンネル名は Webex 投稿の見出しになります。** 1つのスペースに複数のチャンネルを"
               "向けることもできます（例: ニュース配信とダイジェストを同じスペースへ）。")

    editable, locked = _editable_channels(existing, visible)
    all_names = [str(c.get("name") or "") for c in (existing.all_channels if existing else [])]

    plans: list[core.ChannelPlan] = []
    if editable:
        st.subheader(f"いまの設定（{len(editable)} 件）")
        for channel in editable:
            name = str(channel.get("name") or "")
            space_id = core._expand_env(channel.get("webex_space_id"))
            plan = _render_channel_card(
                key=_widget_key(space_id, name), name=name, space_id=space_id,
                space_label=visible.get(space_id, ""), categories=categories,
                current_cats=list(channel.get("categories") or [name]),
                options=_channel_options_of(channel),
                other_names=[n for n in all_names if n != name],
                is_digest=bool(channel.get("digest")),
                token_ref=str(channel.get("webex_bot_token") or ""),
                space_ref=str(channel.get("webex_space_id") or ""))
            if plan:
                plans.append(plan)
    else:
        st.caption("この bot で編集できる既存チャンネルはありません。下から追加できます。")

    used = {core._expand_env(c.get("webex_space_id"))
            for c in (existing.all_channels if existing else [])}
    plans.extend(_render_new_channel(categories, visible, used, all_names))

    if locked:
        st.divider()
        names = "、".join(str(c.get("name")) for c in locked)
        st.caption(f":material/lock: 次の {len(locked)} 件はこの画面では変更しません"
                   f"（そのまま残します）: {names}")
    return plans


def _render_new_channel(categories: list[str], visible: dict[str, str],
                        used: set[str], all_names: list[str]) -> list[core.ChannelPlan]:
    """新しいチャンネルを作る欄。追加しない場合は空リストを返す。"""
    st.subheader("チャンネルを追加する")
    label_of: dict[str, str] = {}
    for space_id, title in visible.items():
        suffix = "（設定済み・追加で送る）" if space_id in used else "（未設定）"
        label_of[f"{title}{suffix}"] = space_id
    if not label_of:
        st.caption("この bot が参加しているスペースがありません。")
        return []

    with st.container(border=True):
        picked = st.selectbox("追加先のスペース", ["（追加しない）"] + list(label_of), key="new_space")
        if picked == "（追加しない）":
            st.caption("スペースを選ぶと、新しいチャンネルを作れます。")
            return []
        space_id = label_of[picked]
        plan = _render_channel_card(
            key=_widget_key(space_id, "＋新規"), name=visible.get(space_id, ""), space_id=space_id,
            space_label=visible.get(space_id, ""), categories=categories,
            current_cats=[], options={}, other_names=all_names, is_digest=False)
    return [plan] if plan else []


def _render_target_picker(key: str, name: str, categories: list[str], current: list[str],
                          current_groups: list[str], kind: str) -> tuple[list[str], list[str]]:
    """このチャンネルに何を送るかを選ぶ。戻り値は (カテゴリ, グループ)。"""
    if kind == KIND_DIGEST:
        st.caption("毎日の配信のあとに、**天気（今日・明日）と各チャンネルが投稿したニュースのまとめ**を"
                   "1通で送ります。このチャンネルにはカテゴリ別のニュースは流れません。")
        st.caption("天気の地点と、まとめに載せる一般ニュースの地域バランスは"
                   "「ダイジェスト」タブで設定できます。")
        return [], []

    if kind == KIND_SOURCE:
        available = core.available_groups()
        st.caption("記事の内容ではなく、**どのフィード由来か**で振り分けます。"
                   "指定したグループの記事は、このチャンネルが専有します（他には配信されません）。")
        groups = st.multiselect("使うグループ（`urls.yml` で定義）", available,
                                default=[g for g in current_groups if g in available],
                                key=f"grp_{key}")
        if not available:
            st.warning("`urls.yml` にグループがありません。「URL の設定」タブで作成してください。",
                       icon=":material/warning:")
        elif not groups:
            st.warning("グループを1つ以上選んでください。", icon=":material/warning:")
        return [], groups

    # category_name_map() は {表示名: 原文}。既存設定は原文なので逆引きして表示名にする。
    raw_to_shown = {raw: shown for shown, raw in core.category_name_map().items()}
    shown = [raw_to_shown.get(c, c) for c in current]
    chosen = st.multiselect("送るカテゴリ（複数可）", categories,
                            default=[c for c in shown if c in categories] or
                                    ([name] if name in categories else []),
                            key=f"cats_{key}")
    if not chosen:
        st.warning("カテゴリを1つ以上選んでください。", icon=":material/warning:")
    else:
        expanded_name = core.expand_category_name(name) if "${" in name else name.strip()
        st.caption("この設定では `categories:` を省略できます。" if chosen == [expanded_name]
                   else f"`categories:` に {len(chosen)} 件を明示します。")
    # 保存時は categories.yml の原文（${VAR} など）に戻す
    to_raw = core.category_name_map()
    return [to_raw.get(c, c) for c in chosen], []


def _render_channel_options(key: str, options: dict, other_names: list[str], kind: str) -> dict:
    """チャンネルの詳しい設定（任意項目）。すべて空欄のままで構わない。"""
    with st.expander("詳しい設定（任意・空欄のままで構いません）"):
        st.caption("複数のチャンネルに同じ記事が届くのを防いだり、日本語記事が少ない日を"
                   "補ったりするための設定です。指定しなければ、記事はカテゴリだけで振り分けられます。")
        priority = st.checkbox(
            "このチャンネルが記事を独占する（priority）", value=bool(options.get("priority")),
            key=f"prio_{key}",
            help="オンにすると、ここに該当した記事は他のチャンネルには配信されません。")
        defers = st.multiselect(
            "この記事は他のチャンネルに譲る（defers_to）", other_names,
            default=[n for n in options.get("defers_to", []) if n in other_names],
            key=f"defer_{key}", disabled=kind == KIND_DIGEST,
            help="ここで選んだチャンネルにも該当する記事は、そちら側だけに配信します。")
        current_min = options.get("min_japanese")
        min_text = st.text_input(
            "日本語記事の下限（min_japanese）",
            value="" if current_min is None else str(current_min),
            key=f"minjp_{key}", disabled=kind == KIND_DIGEST, placeholder="空欄なら指定なし",
            help="日本語の記事が少ない日に、新着順で補ってこの件数まで埋めます。")
        min_japanese = None
        if min_text.strip():
            if min_text.strip().isdigit():
                min_japanese = int(min_text.strip())
            else:
                st.warning("日本語記事の下限は数字で入力してください（空欄なら指定なし）。",
                           icon=":material/warning:")
    return {"priority": priority, "defers_to": defers, "min_japanese": min_japanese}


def _render_channel_card(key: str, name: str, space_id: str, space_label: str,
                         categories: list[str], current_cats: list[str], options: dict,
                         other_names: list[str], is_digest: bool,
                         token_ref: str = "", space_ref: str = "") -> core.ChannelPlan | None:
    """チャンネル1件の編集欄。削除が選ばれた場合は None を返す。"""
    with st.container(border=True):
        head, remove_col = st.columns([5, 1])
        with head:
            shown = core.expand_category_name(name) if "${" in name else name
            label = f"**{shown}**" if shown == name else f"**{shown}**（`{name}`）"
            st.write(f"{label}　:material/arrow_forward: {space_label}")
        with remove_col:
            removed = st.checkbox("削除", key=f"del_{key}",
                                  help="このチャンネルへの配信をやめます。")
        if removed:
            st.caption("保存すると、このチャンネルは設定から削除されます。")
            return None

        new_name = st.text_input("チャンネル名（投稿の見出しになります）", value=name,
                                 key=f"name_{key}")
        if "${" in name:
            st.caption(f":material/settings: この名前は `.env` の変数で決まります"
                       f"（今の値: **{core.expand_category_name(name)}**）。"
                       "書き換えると変数参照が外れるので、名前を変えたいときは `.env` 側を編集してください。")
        current_kind = (KIND_DIGEST if is_digest
                        else KIND_SOURCE if options.get("source_groups") else KIND_NEWS)
        kind = st.segmented_control("このチャンネルに送るもの",
                                    [KIND_NEWS, KIND_DIGEST, KIND_SOURCE],
                                    default=current_kind, key=f"kind_{key}") or KIND_NEWS
        chosen, groups = _render_target_picker(key, new_name, categories, current_cats,
                                               options.get("source_groups", []), kind)
        adv = _render_channel_options(key, options, other_names, kind)

    if not new_name.strip():
        return None
    if kind == KIND_NEWS and not chosen:
        return None
    if kind == KIND_SOURCE and not groups:
        return None
    return core.ChannelPlan(
        name=new_name.strip(), categories=chosen, space_id=space_id, space_title=space_label,
        bot_token_ref=token_ref, space_ref=space_ref, is_digest=(kind == KIND_DIGEST),
        source_groups=groups,
        defers_to=adv["defers_to"], min_japanese=adv["min_japanese"], priority=adv["priority"])


def render_feeds(existing: core.ExistingConfig | None) -> list[str]:
    """ステップ4: 収集するフィードを選ぶ。既存設定があればそれを初期値にする。"""
    st.header("ステップ 4 ｜ 集めるRSSフィード")
    if existing and existing.feed_urls:
        defaults = existing.feed_urls
        st.caption(f":material/history: 既存の設定から {len(defaults)} 件のフィードを読み込みました。"
                   "チェックを外すと配信対象から除けます。")
    else:
        defaults = core.default_feed_urls()
        st.caption("テンプレートのフィードから取捨選択できます。あとから config.yml で追加・削除もできます。")

    chosen = st.multiselect("使うフィード", defaults, default=defaults, label_visibility="collapsed")
    extra = st.text_area("追加したいフィードURL（1行に1つ）", height=100).strip()
    if extra:
        chosen = chosen + [line.strip() for line in extra.splitlines() if line.strip()]
    st.write(f"合計 **{len(chosen)}** 件")
    if existing and existing.special_feeds:
        labels = ["天気API" if "weather" in e else f"グループ「{e.get('group')}」"
                  for e in existing.special_feeds]
        st.info("次の設定は、このウィザードでは変更せず**そのまま引き継ぎます**: "
                + "、".join(labels), icon=":material/lock:")
    return chosen


def _prepare_variable_mode(token: str, plans: list[core.ChannelPlan],
                          existing: core.ExistingConfig | None,
                          ) -> tuple[bool, dict[str, str], str, list[str]]:
    """カテゴリ名を変数で管理するかを尋ね、.env の値と categories.yml の同期案を返す。"""
    use_var = st.checkbox(
        "カテゴリ名を `.env` の変数で管理する（推奨）",
        value=(existing is None),
        help="オンにすると、チャンネル名と categories.yml のキーを ${CATEGORY_*} で書きます。"
             "カテゴリ名の正本が .env の1行になるので、名前がずれなくなります。",
    )
    for plan in plans:
        plan.use_category_var = use_var

    env_values: dict[str, str] = dict(core.DEFAULT_ENV_VALUES)
    for plan in plans:
        if use_var:
            env_values[plan.category_var] = plan.name
        env_values[plan.env_var] = plan.space_id
        # 既存のトークン参照が無いチャンネルは、他チャンネルと同じ命名で書く
        if not plan.bot_token_ref:
            env_values[plan.token_var] = token

    cat_text, cat_notes = "", []
    if use_var:
        cat_text, cat_notes = core.sync_category_names(plans)
        st.caption("チャンネル1つにつき `.env` の変数が組になります"
                   "（`CATEGORY_*` / `WEBEX_SPACE_ID_*` / 任意で `WEBEX_BOT_TOKEN_*`）。")
        if cat_notes:
            st.info("`categories.yml` も揃えます: " + "、".join(cat_notes), icon=":material/sync:")
    return use_var, env_values, cat_text, cat_notes


def render_write(token: str, plans: list[core.ChannelPlan], feeds: list[str],
                 existing: core.ExistingConfig | None) -> None:
    """ステップ5: 内容を見せてから書き込む。既存の高度な設定は引き継ぐ。"""
    st.header("ステップ 5 ｜ 設定ファイルの作成")

    use_var, env_values, cat_text, cat_notes = _prepare_variable_mode(token, plans, existing)
    urls_text = core.build_urls_text(
        feeds, special_feeds=existing.special_feeds if existing else None)
    preserved = core.channels_to_preserve(existing, core.edited_channel_names(plans))
    channels_text = core.build_channels_text(plans, kept_channels=preserved)

    if preserved:
        names = "、".join(str(c.get("name")) for c in preserved)
        st.info(f"次の **{len(preserved)} 件は編集せずそのまま残します**: {names}\n\n"
                "（優先配信・譲渡などの設定を持つチャンネルや、いま選んでいる bot からは"
                "見えないスペースのチャンネルです）", icon=":material/lock:")
    if existing:
        st.warning("設定は作り直しになるため、`urls.yml` / `channels.yml` に書かれていた**コメントは残りません**"
                   "（設定内容は保たれます）。元のファイルは自動で退避します。",
                   icon=":material/warning:")

    tab_ch, tab_urls = st.tabs(["channels.yml", "urls.yml"])
    with tab_ch:
        st.code(channels_text, language="yaml")
    with tab_urls:
        st.code(urls_text, language="yaml")
    st.subheader(".env に書く変数")
    st.write("、".join(f"`{key}`" for key in env_values) + " （値は表示しません）")

    targets = [f.name for f in (core.URLS_FILE, core.CHANNELS_FILE) if f.exists()]
    if cat_notes:
        targets.append(core.CATEGORIES_FILE.name)
    agreed = _render_change_review(env_values, targets, "setup")
    if st.button("この内容で書き込む", type="primary", disabled=not agreed):
        try:
            results = [
                core.backup_and_write(core.ENV_FILE, core.build_env_text(env_values)),
                core.backup_and_write(core.URLS_FILE, urls_text),
                core.backup_and_write(core.CHANNELS_FILE, channels_text),
            ]
            if cat_notes:
                results.append(core.backup_and_write(core.CATEGORIES_FILE, cat_text))
        except OSError as exc:
            st.error(f"設定ファイルを保存できませんでした: {exc}\n\n"
                     "フォルダの書き込み権限を確認してください。")
            return
        for result in results:
            state = "作成" if result.created else "更新"
            note = f"（元の内容は `{result.backup.name}` に退避）" if result.backup else ""
            st.success(f"`{result.path.name}` を{state}しました{note}")
        st.session_state["written"] = True


def render_dry_run() -> None:
    """ステップ6: 送信せずに動作を確認する。"""
    st.header("ステップ 6 ｜ 動作確認（送信しません）")
    if not st.session_state.get("written"):
        st.info("設定ファイルを書き込むと、ここで動作確認ができます。")
        return
    if st.button("dry-run を実行（数分かかります）"):
        python_path = core.venv_python() or Path(sys.executable)
        with st.spinner("フィードを収集しています..."):
            ok, output = core.run_dry_run(python_path)
        st.success("正常に完了しました") if ok else st.error("失敗しました。出力を確認してください。")
        st.code("\n".join(output.splitlines()[-40:]))
        if ok:
            st.info("定時実行の設定は README の「自動実行」を参照してください。")


def _save_urls(feed_urls: list[str], special: list[dict]) -> None:
    """urls.yml を書き出す。失敗した場合は画面にエラーを出す。"""
    try:
        result = core.backup_and_write(core.URLS_FILE, core.build_urls_text(feed_urls, special_feeds=special))
    except OSError as exc:
        st.error(f"`urls.yml` を保存できませんでした: {exc}")
        return
    st.success(f"`{result.path.name}` を更新しました（フィード {len(feed_urls)} 件）"
               + (f"／元の内容は `{result.backup.name}` に退避" if result.backup else ""))


def _render_group_editor(groups: list[dict], feed_urls: list[str], others: list[dict]) -> list[dict]:
    """名前付きグループの編集欄を描画し、更新後のグループ一覧を返す。"""
    st.info(
        "**名前付きグループ**は、記事の内容ではなく「どのフィード由来か」で配信先を決めるための仕組みです。"
        "`channels.yml` の `source_groups` から名前で参照します。\n\n"
        "グループに入れたフィードの記事は、**参照しているチャンネルが専有**します"
        "（他のチャンネルには配信されません）。Cisco Security Advisories のように、"
        "専用スペースへ隔離したいフィードに使ってください。",
        icon=":material/group_work:",
    )
    updated: list[dict] = []
    for entry in groups:
        name = str(entry.get("group") or "")
        urls = [str(u) for u in (entry.get("urls") or [])]
        with st.expander(f"グループ「{name}」（{len(urls)} 件）"):
            keep = st.multiselect("含めるURL", urls, default=urls, key=f"gkeep_{name}")
            add = st.text_area("追加するURL（1行に1つ）", key=f"gadd_{name}", height=80).strip()
            add_list = [line.strip() for line in add.splitlines() if line.strip()]
            for url in add_list:
                problem = core.validate_feed_url(url)
                if problem:
                    st.warning(f"{url}: {problem}", icon=":material/warning:")
            st.caption(f"保存後: {len(keep) + len(add_list)} 件")
            updated.append(core.build_group_entry(name, keep + add_list))
    return updated


def _render_place_search() -> None:
    """地名から緯度経度を調べて、下の表に行を足す。"""
    with st.expander("地名から緯度経度を調べる"):
        st.caption("Open-Meteo の地名検索を使います（APIキー不要）。"
                   "**ローマ字（例: Tokyo, Sapporo, Chiba）が確実**です。"
                   "日本語だと見つからなかったり、同名の別の場所が出ることがあります。")
        col_q, col_btn = st.columns([3, 1])
        with col_q:
            query = st.text_input("地名", key="geo_query", placeholder="Tokyo",
                                  label_visibility="collapsed")
        with col_btn:
            if st.button("検索", key="geo_search", width="stretch"):
                st.session_state["geo_results"] = core.geocode_place(query)
                st.session_state["geo_query_done"] = query

        results = st.session_state.get("geo_results")
        if results is None:
            return
        if not results:
            st.warning(f"「{st.session_state.get('geo_query_done', '')}」は見つかりませんでした。"
                       "ローマ字（例: Sapporo）で試してみてください。", icon=":material/search_off:")
            return

        labels = [f"{r['label']}（{r['detail']}） 緯度 {r['lat']:.3f} / 経度 {r['lon']:.3f}"
                  for r in results]
        index = st.selectbox("候補", range(len(results)), format_func=lambda i: labels[i],
                             key="geo_pick")
        picked = results[index]
        shown = st.text_input("投稿に表示する名前", value=picked["label"], key="geo_label",
                              help="日本語に書き換えて構いません（表示名として使われます）。")
        if st.button("この地点を追加", key="geo_add", type="primary"):
            added = st.session_state.setdefault("weather_added", [])
            added.append({"label": shown.strip() or picked["label"],
                          "lat": picked["lat"], "lon": picked["lon"]})
            st.session_state["geo_results"] = None
            st.success(f"「{shown}」を下の表に追加しました。保存を押すと反映されます。")


def _render_weather_editor(others: list[dict]) -> dict | None:
    """ダイジェストの天気に使う観測地点を編集する。使わない場合は None を返す。"""
    st.subheader("天気の観測地点")
    st.caption("**ダイジェスト（天気＋まとめ）チャンネル**で使う地点です。"
               "Open-Meteo を使うため API キーは要りません。")
    locations = core.read_weather_locations(others)
    use_weather = st.checkbox("ダイジェストに天気を載せる", value=bool(locations), key="use_weather")
    if not use_weather:
        st.caption("オフにすると、ダイジェストは天気ブロックを省いて配信します。")
        return None

    rows = list(locations or [{"label": "東京", "lat": 35.6895, "lon": 139.6917}])
    rows.extend(st.session_state.get("weather_added", []))
    _render_place_search()
    edited = st.data_editor(
        rows, num_rows="dynamic", key="weather_rows", width="stretch",
        column_config={
            "label": st.column_config.TextColumn("地点名", help="投稿に表示される名前"),
            "lat": st.column_config.NumberColumn("緯度", format="%.4f"),
            "lon": st.column_config.NumberColumn("経度", format="%.4f"),
        },
    )
    entry = core.build_weather_entry(list(edited))
    valid = entry["weather"]["locations"]
    if len(valid) != len(list(edited)):
        st.warning("地点名・緯度・経度がそろっていない行は保存されません。", icon=":material/warning:")
    st.caption(f"保存後: {len(valid)} 地点")
    return entry


def _pick_token(known: list[str]) -> tuple[str, str]:
    """確認に使うトークンを選ぶ。戻り値は (トークン, 表示用ラベル)。"""
    modes = ([TOKEN_FROM_ENV] if known else []) + [TOKEN_MANUAL]
    mode = st.segmented_control("トークンの指定", modes, default=modes[0],
                                key="inspect_mode") or modes[0]
    if mode == TOKEN_FROM_ENV:
        name = st.selectbox("確認する bot のトークン", known, key="inspect_token",
                            help="変数名だけを表示し、値は画面に出しません。")
        return core.get_env_token(name), f"`{name}`"
    st.caption("`.env` にまだ無い bot のトークンでも確認できます。"
               "入力値は画面にもログにも残りません。")
    token = st.text_input("Bot トークンを貼り付け", type="password",
                          key="inspect_manual").strip()
    return token, "入力したトークン"


def _render_env_line_builder(rows: list[dict]) -> None:
    """選んだスペースから、.env に書く行と channels.yml の雛形を作る。"""
    st.divider()
    st.write("**このスペースを使う設定を作る**")
    titles = [r["スペース名"] for r in rows]
    index = st.selectbox("スペースを選ぶ", range(len(rows)), format_func=lambda i: titles[i],
                         key="inspect_pick")
    picked = rows[index]
    suffix = st.text_input("変数名の末尾", value="NEW_SPACE", key="inspect_suffix",
                           help="`WEBEX_SPACE_ID_<ここ>` と `WEBEX_BOT_TOKEN_<ここ>` になります。"
                                "英大文字と _ で書いてください。").strip().upper() or "NEW_SPACE"
    st.caption("次の行を `.env` に追記し、`channels.yml` 側から変数名で参照します。")
    st.code(f"WEBEX_SPACE_ID_{suffix}={picked['Room ID']}\n"
            f"WEBEX_BOT_TOKEN_{suffix}=（この bot のトークン）", language="bash")
    st.code("channels:\n"
            f"  - name: {picked['スペース名'].strip() or 'チャンネル名'}\n"
            f"    webex_space_id: ${{WEBEX_SPACE_ID_{suffix}}}\n"
            f"    webex_bot_token: ${{WEBEX_BOT_TOKEN_{suffix}}}\n"
            "    categories:\n"
            "      - セキュリティ        # ← 送りたいカテゴリ名に置き換える\n", language="yaml")
    st.caption("トークンを `.env` に書いたあとは、セットアップタブから画面で設定できます。")


def _overview_metrics(existing: core.ExistingConfig | None) -> None:
    """設定の規模をひと目で分かる数値で示す。"""
    channels = existing.all_channels if existing else []
    feeds = existing.feed_urls if existing else []
    groups, others = core.split_special_feeds(existing.special_feeds if existing else [])
    cols = st.columns(5)
    cols[0].metric("配信チャンネル", f"{len(channels)} 件")
    cols[1].metric("RSSフィード", f"{len(feeds)} 件")
    cols[2].metric("フィードのグループ", f"{len(groups)} 件")
    cols[3].metric("カテゴリ", f"{len(core.category_keys())} 件")
    cols[4].metric("天気の地点", f"{len(core.read_weather_locations(others))} 地点")


def _overview_warnings(existing: core.ExistingConfig | None) -> None:
    """設定の抜けや注意点をまとめて出す。"""
    notes = []
    if existing:
        for channel in existing.all_channels:
            name = core.expand_category_name(str(channel.get("name") or ""))
            space = core._expand_env(channel.get("webex_space_id"))
            if "${" in space:
                notes.append(f"**{name}**: スペースIDが未設定のため配信されません"
                             f"（`{channel.get('webex_space_id')}` を `.env` に追加）")
            token = str(channel.get("webex_bot_token") or "")
            if token and "${" in core._expand_env(token):
                notes.append(f"**{name}**: Bot トークンが未設定です（`{token}`）")
    if not core.REGIONS_FILE.exists():
        notes.append("`regions.yml` がありません。ダイジェストの時事枠は従来の日本枠になります。")
    if notes:
        st.warning("**確認したい点**\n\n" + "\n\n".join(f"- {n}" for n in notes),
                   icon=":material/warning:")
    else:
        st.success("設定に目立った抜けはありません。", icon=":material/check_circle:")


def render_overview() -> None:
    """設定の全体像タブ: いまの設定をまとめて見る。"""
    st.header("設定の全体像")
    st.caption("いま保存されている設定を一覧します。この画面では変更しません。")

    existing = core.load_existing_config()
    if existing is None:
        st.info("まだ設定がありません。セットアップタブから作成してください。", icon=":material/info:")
        return

    _overview_metrics(existing)
    _overview_warnings(existing)

    st.subheader("配信チャンネル")
    st.dataframe(core.channel_summary(existing), width="stretch", hide_index=True)

    graph = core.routing_graph(existing)
    if "->" in graph:
        st.subheader("記事の流れ")
        st.caption("矢印は「重なった記事を相手側に譲る」関係です（`defers_to`）。"
                   "「独占」と付いたチャンネルは、該当記事を他へ流しません（`priority`）。")
        st.graphviz_chart(graph)

    st.subheader("カテゴリのキーワード数")
    st.caption("「非公開ファイル」は `categories-private.yml` にある語数です（実行時に合算されます）。")
    st.dataframe(core.category_summary(), width="stretch", hide_index=True)

    _render_overview_feeds(existing)


def _render_overview_feeds(existing: core.ExistingConfig) -> None:
    """フィードとダイジェストの設定を表示する。"""
    groups, others = core.split_special_feeds(existing.special_feeds)
    st.subheader("フィードとダイジェスト")
    col_feed, col_digest = st.columns(2)
    with col_feed:
        st.write(f"**RSSフィード**: {len(existing.feed_urls)} 件")
        if groups:
            for entry in groups:
                st.caption(f"グループ「{entry.get('group')}」: {len(entry.get('urls') or [])} 件")
        with st.expander("フィードの一覧を見る"):
            st.dataframe([{"URL": u} for u in existing.feed_urls],
                         width="stretch", hide_index=True)
    with col_digest:
        locations = core.read_weather_locations(others)
        st.write("**ダイジェスト**")
        st.caption("天気: " + ("、".join(str(x.get("label")) for x in locations)
                              if locations else "設定なし"))
        regions = core.load_regions()
        quota = regions["quota"]
        st.caption(f"時事の地域バランス: 日本 {quota.get('japan')} / "
                   f"米国 {quota.get('us')} / その他 {quota.get('other')}")
        st.caption(f"地域の判定語: 米国 {len(regions['keywords']['us'])} 語 / "
                   f"その他 {len(regions['keywords']['other'])} 語")


def render_scheduler() -> None:
    """自動実行タブ: 毎朝決まった時刻に動かす設定。"""
    st.header("自動実行の設定")
    st.caption("毎朝きまった時刻に、このツールを自動で動かします。"
               "**パソコンの電源が入っていて、スリープしていない**ことが前提です。")

    import platform
    system = platform.system()
    mechanism = {"Darwin": "macOS の launchd", "Windows": "Windows のタスク スケジューラ"}.get(
        system, f"{system}（cron などをお使いください）")
    st.caption(f"この環境では **{mechanism}** に登録します。")

    registered, detail = core.schedule_status()
    if registered:
        st.success(f"いま登録されています。{detail}", icon=":material/schedule:")
    else:
        st.info(f"まだ登録されていません。{detail}", icon=":material/info:")

    with st.container(border=True):
        st.write("**いつ動かすか**")
        col_time, col_days = st.columns([1, 3])
        with col_time:
            when = st.time_input("時刻", value=core.dt_time(9, 1), key="sched_time",
                                 help="ニュースを集めて配信する時刻です。")
        with col_days:
            picked = st.multiselect("曜日", core.WEEKDAY_LABELS,
                                    default=core.WEEKDAY_LABELS[:5], key="sched_days",
                                    help="既定は平日（月〜金）です。")
        weekdays = [core.WEEKDAY_LABELS.index(d) for d in picked]
        st.caption(core.describe_schedule(when.hour, when.minute, weekdays))

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        if st.button("この内容で登録", type="primary", key="sched_add", disabled=not weekdays):
            ok, message = core.install_schedule(when.hour, when.minute, weekdays)
            st.success(f"登録しました。{core.describe_schedule(when.hour, when.minute, weekdays)}") \
                if ok else st.error(f"登録できませんでした: {message}")
    with col_b:
        if st.button("解除", key="sched_del", disabled=not registered):
            ok, message = core.remove_schedule()
            st.success(message) if ok else st.error(message)
    with col_c:
        if st.button("いますぐ1回実行", key="sched_run", disabled=not registered,
                     help="動作確認用です。実際に Webex へ投稿されます。"):
            ok, message = core.run_schedule_now()
            st.success("実行を開始しました。結果は log フォルダに出ます。") \
                if ok else st.error(message or "実行できませんでした")

    with st.expander("うまく動かないときは"):
        st.markdown(
            "- **時刻になっても動かない**: パソコンがスリープしていると実行されません。"
            "macOS なら `sudo pmset repeat wakeorpoweron MTWRF 08:55:00` で自動起床を設定できます。\n"
            "- **手動では動くのに定時だけ失敗する**: 置き場所が原因のことがあります"
            "（→ [リポジトリの置き場所](#リポジトリの置き場所--where-to-put-this-repository)）。\n"
            f"- **ログの場所**: `{core.REPO_ROOT / 'log'}` に、実行ごとの記録が残ります。")


def render_space_inspector() -> None:
    """bot とスペースの確認タブ: 参加スペースの一覧と、全トークンの有効性。"""
    st.header("bot とスペースの確認")
    st.caption("設定を変えずに、bot がどのスペースに入っているか・トークンが使えるかを確認します。"
               "配信が届かないときの切り分けに使ってください。")

    known = core.detect_env_tokens()
    existing = core.load_existing_config()
    configured: dict[str, str] = {}
    for channel in (existing.all_channels if existing else []):
        sid = core._expand_env(channel.get("webex_space_id"))
        label = core.expand_category_name(str(channel.get("name") or ""))
        configured[sid] = (configured[sid] + "、" + label) if sid in configured else label

    st.subheader("スペースとその ID を調べる")
    token, label = _pick_token(known)
    if st.button("スペースを取得", key="fetch_spaces", type="primary", disabled=not token):
        with st.spinner("Webex に問い合わせています..."):
            ok, message = core.validate_token(token)
            st.session_state["inspect_error"] = None if ok else f"{message}（{label}）"
            st.session_state["inspect_rows"] = (
                core.space_rows(core.list_spaces(token), configured) if ok else None)

    if st.session_state.get("inspect_error"):
        st.error(st.session_state["inspect_error"])
    rows = st.session_state.get("inspect_rows")
    if rows:
        st.success(f"{len(rows)} 件のスペースが見つかりました。")
        st.dataframe(rows, width="stretch", hide_index=True)
        st.caption("「配信設定」は現在の `channels.yml` と突き合わせた結果です。"
                   "Room ID は表のセルを選択してコピーできます。")
        _render_env_line_builder(rows)

    st.divider()
    st.subheader("すべてのトークンを確認")
    st.caption("`.env` にあるトークンを順に試し、有効かどうかと参加スペース数を表示します"
               "（値は表示しません）。")
    if st.button("まとめて確認", key="check_tokens"):
        with st.spinner("Webex に問い合わせています..."):
            st.session_state["token_rows"] = core.check_all_tokens()
    token_rows = st.session_state.get("token_rows")
    if token_rows:
        st.dataframe(token_rows, width="stretch", hide_index=True)
        broken = [r for r in token_rows if r["状態"] != "有効"]
        if broken:
            names = "、".join(r["変数名"] for r in broken)
            st.error(f"次のトークンが使えません: {names}\n\n"
                     "Webex Developer Portal で該当 bot のトークンを再発行し、"
                     "`.env` の該当行を差し替えてください。")
        else:
            st.success("すべてのトークンが有効です。")


def _render_feed_list(existing: core.ExistingConfig) -> tuple[list[str], list[str]]:
    """通常フィードの取捨選択と追加を受け付ける。"""
    st.subheader("通常のフィード")
    st.caption(f"現在 {len(existing.feed_urls)} 件。チェックを外すと削除されます。")
    keep = st.multiselect("収集するフィード", existing.feed_urls,
                          default=existing.feed_urls, key="url_keep",
                          label_visibility="collapsed")
    added = st.text_area("追加するURL（1行に1つ）", key="url_add", height=110,
                         placeholder="https://example.com/feed").strip()  # noqa: W02  入力例
    add_list = [line.strip() for line in added.splitlines() if line.strip()]
    checked = [(u, core.validate_feed_url(u)) for u in add_list]
    for url, problem in checked:
        if problem:
            st.warning(f"{url}: {problem}", icon=":material/warning:")
    add_list = [u for u, problem in checked if not problem]
    duplicated = [u for u in add_list if u in keep]
    if duplicated:
        st.warning(f"すでにある URL は追加されません: {len(duplicated)} 件", icon=":material/info:")
    add_list = [u for u in add_list if u not in keep]

    removed = [u for u in existing.feed_urls if u not in keep]
    st.write(f"保存後: **{len(keep) + len(add_list)}** 件"
             + (f"（追加 {len(add_list)} / 削除 {len(removed)}）" if add_list or removed else "（変更なし）"))
    return keep, add_list


def render_url_manager() -> None:
    """URL設定タブ: 収集するフィードの確認・追加・削除と、グループの編集。"""
    st.header("URL の設定")
    st.caption("ニュースを集めてくる RSS フィードの一覧です。既存の設定を読み込んで、追加・削除できます。")

    existing = core.load_existing_config()
    if existing is None:
        st.info("まだ `urls.yml` がありません。セットアップタブから作成してください。", icon=":material/info:")
        return

    groups, others = core.split_special_feeds(existing.special_feeds)

    keep, add_list = _render_feed_list(existing)

    st.divider()
    st.subheader("名前付きグループ")
    if groups:
        updated_groups = _render_group_editor(groups, existing.feed_urls, others)
    else:
        st.caption("グループはまだありません。")
        updated_groups = []

    with st.expander("新しいグループを作る"):
        st.caption("特定のフィードだけを専用スペースへ隔離したいときに使います。")
        new_name = st.text_input("グループ名", key="new_group_name",
                                 help="`channels.yml` の `source_groups` にこの名前を書いて参照します。")
        new_urls = st.text_area("このグループに入れるURL（1行に1つ）", key="new_group_urls", height=90).strip()
        new_list = [line.strip() for line in new_urls.splitlines() if line.strip()]
        if new_name and new_list:
            updated_groups = updated_groups + [core.build_group_entry(new_name, new_list)]
            st.caption(f"「{new_name}」を {len(new_list)} 件で作成します。")

    if others:
        st.divider()
        st.caption("天気の観測地点は「ダイジェスト」タブで設定できます"
                   "（この画面では変更せずそのまま保存します）。")

    st.divider()
    agreed = _render_change_review({}, [core.URLS_FILE.name], "urls")
    if st.button("URL の設定を保存", type="primary", key="save_urls", disabled=not agreed):
        _save_urls(keep + add_list, updated_groups + others)


def _render_category_editor(key: str) -> None:
    """カテゴリ1件のキーワードを編集して保存する。"""
    text = core.read_text_safely(core.CATEGORIES_FILE)
    if not text:
        st.error("categories.yml を読めません。ファイルの権限を確認してください。")
        return
    current = core.read_category_keywords(text, key)

    private_count = core.private_category_counts().get(key, 0)
    if private_count:
        st.warning(
            f"このカテゴリは **`categories-private.yml` にも {private_count} 語** 定義されています"
            "（実行時に自動で合算されます）。\n\n"
            "この画面で編集できるのは **`categories.yml` 側だけ**です。"
            "非公開ファイルは社名などを含むため、ウィザードからは読み書きしません。"
            "非公開側の語を変えたいときは、`categories-private.yml` を直接編集してください。",
            icon=":material/lock:")
    if "${" in key:
        expanded = core.expand_category_name(key)
        st.caption(f":material/settings: この名前は `.env` の変数で決まります（現在の値: **{expanded}**）。")
    must = [k for k in current if k.startswith("!")]
    normal = [k for k in current if not k.startswith("!")]

    keep_must = st.multiselect("必須語（`!` 付き。どれか1つも含まれない記事は配信されません）",
                               must, default=must, key=f"m_{key}")
    keep_normal = st.multiselect("通常語", normal, default=normal, key=f"n_{key}")
    added = st.text_area("追加する語（1行に1つ。必須語は先頭に `!`）",
                         key=f"a_{key}", height=90).strip()
    add_list = [line.strip() for line in added.splitlines() if line.strip()]
    keywords = keep_must + keep_normal + add_list

    removed = [k for k in current if k not in keywords]
    st.caption(f"保存後: {len(keywords)} 語"
               + (f"（追加 {len(add_list)} / 削除 {len(removed)}）" if add_list or removed else "（変更なし）"))
    if add_list or removed:
        st.caption(f":material/edit_note: `categories.yml` の「{core.expand_category_name(key)}」を"
                   f"書き換えます（追加 {len(add_list)} 語・削除 {len(removed)} 語）。"
                   "元のファイルは `.bak-日時` に残します。")
    agreed = st.checkbox("この内容で書き換えてよい", key=f"agree_cat_{key}",
                         disabled=not (add_list or removed))
    if st.button("このカテゴリを保存", key=f"save_{key}", type="primary",
                 disabled=not (add_list or removed) or not agreed):
        updated = core.update_category_keywords(text, key, keep=keywords, add=keywords)
        try:
            result = core.backup_and_write(core.CATEGORIES_FILE, updated)
        except OSError as exc:
            st.error(f"`categories.yml` を保存できませんでした: {exc}")
            return
        st.success(f"`{result.path.name}` を更新しました"
                   + (f"（元の内容は `{result.backup.name}` に退避）" if result.backup else ""))


def _render_region_editor() -> tuple[dict[str, int], list[str], list[str]]:
    """時事ダイジェストの地域バランスを編集する。"""
    st.subheader("時事ダイジェストの地域バランス")
    st.markdown(
        "**なぜ必要か** — まとめに載せる一般ニュースは、放っておくと**米国発の記事に偏りがち**です"
        "（英語圏のフィードが多く、記事数も多いため）。ここで「日本・米国・その他」の件数を決めておくと、"
        "毎日おおよそ同じ配分で選ばれ、国内の話題が埋もれません。\n\n"
        "件数が足りないときは**日本→その他**の順に補い、**米国は指定件数を超えて増やしません**。"
        "この設定を消すと、従来の「日本のニュースを最低5件」という枠だけになります。"
    )
    regions = core.load_regions()
    quota = regions["quota"]

    col_jp, col_us, col_other = st.columns(3)
    with col_jp:
        japan = st.number_input("日本（国内）", min_value=0, max_value=30,
                                value=int(quota.get("japan", 7)), key="q_japan",
                                help="不足分の補充はここを最優先します。")
    with col_us:
        us = st.number_input("米国", min_value=0, max_value=30,
                             value=int(quota.get("us", 3)), key="q_us",
                             help="この件数を超えて補充しません（偏りを抑える上限）。")
    with col_other:
        other = st.number_input("その他の国", min_value=0, max_value=30,
                                value=int(quota.get("other", 5)), key="q_other",
                                help="米国以外の外国の記事。")
    st.caption(f"1回のダイジェストに載る時事ニュースは、おおよそ **{japan + us + other} 件**になります。")

    st.write("**地域を判定する語**")
    st.caption("記事の見出しにこれらの語が含まれていれば、その地域の記事とみなします。"
               "どれにも当たらない日本語の記事は「日本」として扱われます。")
    us_words = st.text_area("米国と判定する語（1行に1つ）",
                            value="\n".join(regions["keywords"]["us"]),
                            key="kw_us", height=120)
    other_words = st.text_area("その他の国と判定する語（1行に1つ）",
                               value="\n".join(regions["keywords"]["other"]),
                               key="kw_other", height=120)
    us_list = [w.strip() for w in us_words.splitlines() if w.strip()]
    other_list = [w.strip() for w in other_words.splitlines() if w.strip()]
    if not us_list and not other_list:
        st.warning("判定する語が1つもないと地域バランスは働かず、従来の日本枠に戻ります。",
                   icon=":material/warning:")

    return {"japan": japan, "us": us, "other": other}, us_list, other_list


def render_digest_manager() -> None:
    """ダイジェストタブ: 天気の地点と、時事ダイジェストの地域バランス。"""
    st.header("ダイジェストの設定")
    st.caption("**ダイジェスト（天気＋まとめ）チャンネル**の中身を調整します。"
               "ダイジェストを使っていない場合、この設定は配信に影響しません。")

    existing = core.load_existing_config()
    others = [e for e in (existing.special_feeds if existing else []) if "group" not in e]
    weather_entry = _render_weather_editor(others)

    st.divider()
    quota, us_list, other_list = _render_region_editor()

    st.divider()
    files = [core.REGIONS_FILE.name]
    if existing is not None:
        files.insert(0, core.URLS_FILE.name)
    agreed = _render_change_review({}, files, "digest")
    if st.button("ダイジェストの設定を保存", type="primary", key="save_digest",
                 disabled=not agreed):
        results = []
        try:
            if existing is not None:
                groups = [e for e in existing.special_feeds if "group" in e]
                rest = [e for e in others if "weather" not in e]
                specials = groups + ([weather_entry] if weather_entry else []) + rest
                results.append(core.backup_and_write(
                    core.URLS_FILE, core.build_urls_text(existing.feed_urls, special_feeds=specials)))
            results.append(core.backup_and_write(
                core.REGIONS_FILE,
                core.build_regions_text(quota, us_list, other_list)))
        except OSError as exc:
            st.error(f"保存できませんでした: {exc}\n\nフォルダの書き込み権限を確認してください。")
            return
        for result in results:
            st.success(f"`{result.path.name}` を更新しました"
                       + (f"（元の内容は `{result.backup.name}` に退避）" if result.backup else ""))


def _render_model_input(label: str, key: str, provider: str, current: str,
                        example: str) -> str:
    """モデル名を自由記述で受け取り、書き方がおかしければその場で指摘する。"""
    value = st.text_input(label, value=current or example, key=key,
                          placeholder=example,
                          help=f"自由に入力できます。例: {example}").strip()
    problem = core.check_model_name(provider, value)
    if problem:
        st.warning(f"{problem}", icon=":material/warning:")
    return value


def render_llm_manager() -> None:
    """要約に使う LLM の設定タブ。Claude / OpenAI / Gemini から選べる。"""
    st.header("要約に使う AI の設定")
    st.caption("記事の要約と、配信記事の選定に AI を使えます。"
               "**設定しなくても配信は動きます**（その場合は RSS の紹介文をそのまま使います）。")

    from dotenv import dotenv_values
    current = dotenv_values(core.ENV_FILE) if core.ENV_FILE.exists() else {}
    saved = (current.get("LLM_PROVIDER") or core.DEFAULT_PROVIDER).strip().lower()
    keys = list(core.LLM_PROVIDERS)
    labels = [core.LLM_PROVIDERS[k]["label"] for k in keys]
    index = keys.index(saved) if saved in keys else 0

    picked_label = st.segmented_control("使う AI", labels, default=labels[index],
                                        key="llm_provider") or labels[index]
    provider = keys[labels.index(picked_label)]
    info = core.LLM_PROVIDERS[provider]

    with st.container(border=True):
        st.write("**API キー**")
        key_env = info["key_env"]
        has_key = bool((current.get(key_env) or "").strip())
        st.caption(f"`.env` の `{key_env}` に保存します。")
        if has_key:
            st.success("設定済みです（値は表示しません）。", icon=":material/key:")
        else:
            st.info("未設定です。要約を使う場合は入力してください。", icon=":material/info:")
        st.link_button(f"{info['label']} のキー発行ページ", info["console"],
                       icon=":material/open_in_new:")
        api_key = st.text_input("API キー", type="password", key="llm_key",
                                help="入力値は画面にもログにも残りません。"
                                     "空のままなら現在の設定を保ちます。").strip()
        clear_key = st.checkbox("キーを削除して要約を使わない", key="llm_clear") if has_key else False

    with st.container(border=True):
        st.write("**モデル**")
        st.caption("モデル名は**自由に入力**できます（新しいモデルが出てもそのまま書けます）。"
                   f"{info['label']} では{info['hint']}を指定します。")
        summary_model = _render_model_input(
            "要約に使うモデル", "llm_model", provider,
            (current.get("ANTHROPIC_MODEL") or "").strip(), info["example"])
        rerank_model = _render_model_input(
            "記事の選定に使うモデル", "llm_rerank", provider,
            (current.get("ANTHROPIC_RERANK_MODEL") or "").strip(), info["example"])

    _render_connection_test(provider, info, api_key, current, summary_model)

    _render_ssl_toggle(current)
    _save_llm_settings(provider, info, api_key, clear_key, summary_model, rerank_model)


def _render_connection_test(provider: str, info: dict, api_key: str,
                            current: dict, model: str) -> None:
    """入力したキーとモデル名で、実際に1回問い合わせて確かめる。"""
    with st.container(border=True):
        st.write("**接続を試す**")
        st.caption("実際に短い問い合わせを1回送って、キーとモデル名が使えるか確かめます。")
        if st.button("接続を試す", key="llm_try"):
            token = api_key or (current.get(info["key_env"]) or "").strip()
            with st.spinner("問い合わせています..."):
                ok, message = core.try_llm(provider, token, model)
            st.success(message) if ok else st.error(message)


def _render_ssl_toggle(current: dict) -> None:
    """SSL 検証の切り替え欄を描く。"""
    with st.container(border=True):
        st.write("**通信設定**")
        ssl_now = (current.get("SSL_VERIFY") or "false").strip().lower() != "false"
        st.session_state["_llm_ssl"] = st.checkbox(
            "SSL 証明書を検証する", value=ssl_now, key="llm_ssl",
            help="社内プロキシや macOS の証明書問題がある環境ではオフのままにします。")
        st.caption("既定はオフ（`SSL_VERIFY=false`）です。")


def _save_llm_settings(provider: str, info: dict, api_key: str, clear_key: bool,
                       summary_model: str, rerank_model: str) -> None:
    """入力内容を .env に保存する。書き方がおかしいモデル名は保存前に止める。"""
    problems = [core.check_model_name(provider, m) for m in (summary_model, rerank_model)]
    problems = [x for x in problems if x]

    values = {"LLM_PROVIDER": provider,
              "ANTHROPIC_MODEL": summary_model,
              "ANTHROPIC_RERANK_MODEL": rerank_model,
              "SSL_VERIFY": "true" if st.session_state.get("_llm_ssl") else "false"}
    if clear_key:
        values[info["key_env"]] = ""
    elif api_key:
        values[info["key_env"]] = api_key

    others = core.other_provider_keys(provider)
    if others:
        st.warning(
            f"いま **{'、'.join(others)}** のキーが設定されています。"
            f"このまま保存すると、**要約は {info['label']} で行われます**"
            "（他社のキーは消しませんが、使われなくなります）。",
            icon=":material/swap_horiz:")
    agreed = _render_change_review(values, [], "llm")

    if st.button("この設定を保存", type="primary", key="save_llm",
                 disabled=bool(problems) or not agreed):
        try:
            result = core.backup_and_write(core.ENV_FILE, core.build_env_text(values))
        except OSError as exc:
            st.error(f"`.env` を保存できませんでした: {exc}")
            return
        st.success(f"`{result.path.name}` を更新しました"
                   + (f"（元の内容は `{result.backup.name}` に退避）" if result.backup else ""))
    if problems:
        st.caption(":material/block: モデル名を直すと保存できます。")


def render_category_manager() -> None:
    """カテゴリ管理タブ: 既存カテゴリの編集と、新規カテゴリの作成。"""
    st.header("カテゴリの管理")
    st.caption("記事をどのカテゴリに振り分けるかを決めるキーワードです。"
               "チャンネル設定とは独立していて、いつでも編集できます。")

    if not core.CATEGORIES_FILE.exists():
        st.error("categories.yml が見つかりません。")
        return

    keys = core.category_keys()
    st.subheader("既存のカテゴリを編集する")
    if keys:
        target = st.selectbox("編集するカテゴリ", keys, key="edit_category")
        with st.container(border=True):
            _render_category_editor(target)
    else:
        st.info("まだカテゴリがありません。下から作成してください。", icon=":material/info:")

    st.divider()
    st.subheader("新しいカテゴリを作る")
    with st.container(border=True):
        new_name = st.text_input("カテゴリ名", key="new_category_name",
                                 help="チャンネル名と同じにすると、配信設定で categories: を省略できます。")
        new_kw = st.text_area("キーワード（1行に1つ。必須語は先頭に `!`）", key="new_category_kw",
                              height=120,
                              placeholder="!キーワード\n関連語1\n関連語2")
        words = [line.strip() for line in new_kw.splitlines() if line.strip()]
        if new_name and new_name in keys:
            st.warning(f"「{new_name}」は既にあります。上の編集欄から変更してください。",
                       icon=":material/warning:")
        elif st.checkbox("`categories.yml` に追加してよい", key="agree_new_cat",
                         disabled=not (new_name and words)) and st.button(
                "カテゴリを追加", type="primary", disabled=not (new_name and words)):
            text = core.read_text_safely(core.CATEGORIES_FILE)
            try:
                result = core.backup_and_write(
                    core.CATEGORIES_FILE, core.append_category(text, new_name.strip(), words))
            except OSError as exc:
                st.error(f"`categories.yml` を保存できませんでした: {exc}")
                return
            st.success(f"「{new_name}」を追加しました（{len(words)} 語）。"
                       "配信するには、セットアップタブでチャンネルに割り当ててください。")
            st.caption(f"元の内容は `{result.backup.name}` に退避しました。" if result.backup else "")


def main() -> None:
    """セットアップとカテゴリ管理の2つのタブを描画する。"""
    (tab_overview, tab_setup, tab_urls, tab_categories,
     tab_digest, tab_llm, tab_sched, tab_check) = st.tabs(
        ["設定の全体像", "セットアップ", "URL の設定", "カテゴリの管理", "ダイジェスト",
         "要約AI", "自動実行", "bot とスペース"])
    with tab_sched:
        render_scheduler()
    with tab_overview:
        render_overview()
    with tab_check:
        render_space_inspector()
    with tab_digest:
        render_digest_manager()
    with tab_llm:
        render_llm_manager()
    with tab_urls:
        render_url_manager()
    with tab_categories:
        render_category_manager()
    with tab_setup:
        render_diagnostics()
        categories = core.available_categories()
        if not categories:
            st.error("categories.yml を読めません。リポジトリが壊れていないか確認してください。")
            st.stop()
        existing = core.load_existing_config()
        if existing:
            st.success(f"既存の設定を読み込みました（{existing.summary}）。"
                       "各ステップに現在の内容が初期値として入っています。", icon=":material/history:")
        token = render_bot()
        token = render_token(token)
        if not token:
            st.stop()
        plans = render_channels(categories, existing)
        if not plans:
            st.warning("配信するスペースを1つ以上選んでください。")
            st.stop()
        feeds = render_feeds(existing)
        render_write(token, plans, feeds, existing)
        render_dry_run()


main()
