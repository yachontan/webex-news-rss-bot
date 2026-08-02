#!/usr/bin/env python3
"""
check_rooms_ui.py
-----------------
check_rooms.py のブラウザUI版。Webex スペース（ルーム）の一覧・検索と、
`.env` に貼り付ける `WEBEX_SPACE_ID_*` 行の生成を画面上で行う。
Streamlit UI for check_rooms.py — browse/search Webex spaces and generate
the `WEBEX_SPACE_ID_*` lines for your `.env`.

起動 / Launch:
    ./bin/streamlit run check_rooms_ui.py
    （または / or: ./bin/python -m streamlit run check_rooms_ui.py）

ロジックは check_rooms.py の関数をそのまま呼ぶ（CLI と UI で挙動を揃えるため）。
This UI reuses check_rooms.py's functions so CLI and UI behave identically.
"""

import os
from pathlib import Path

import requests
import streamlit as st
from dotenv import load_dotenv

from check_rooms import find_rooms_by_title, list_rooms

_ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(_ENV_PATH, override=True)

MANUAL_ENTRY = "（手入力する / enter manually）"


@st.cache_data(show_spinner=False)
def env_token_names() -> list[str]:
    """
    `.env` にある Bot トークン変数の**名前だけ**を返す（値は画面に出さない）。
    Returns the names of token variables defined in `.env` (values are never displayed).

    実装はウィザードと共通（wizard/core.py）。共通の WEBEX_BOT_TOKEN と、
    チャンネル別の WEBEX_BOT_TOKEN_* の両方に対応する。
    """
    from wizard import core

    return core.detect_env_tokens(_ENV_PATH)


# .env の WEBEX_SPACE_ID_* によく使われる用途名（生成する変数名の候補）
SUFFIX_CHOICES = [
    "GENERAL", "AI", "SECURITY", "NETWORKING", "ECONOMY",
    "CISCO", "CISCO_ADVISORY", "DIGEST",
]

st.set_page_config(page_title="Webex スペースID 確認ツール", page_icon="🛰️", layout="wide")

st.title("🛰️ Webex スペースID 確認ツール")
st.caption(
    "Bot が参加しているスペースの一覧と Room ID を確認し、`.env` に貼り付ける行を生成します。"
    "／ Browse Webex spaces and generate `.env` lines."
)

# ------------------------------------------------------------------
# トークン入力 / Token
# ------------------------------------------------------------------
with st.sidebar:
    st.header("接続設定 / Connection")

    names = env_token_names()

    if names:
        st.success(f"`.env` から {len(names)} 個の Bot トークンを検出しました。")
        choice = st.selectbox(
            "使うトークン / Token to use",
            names + [MANUAL_ENTRY],
            help="Bot は自分が参加しているスペースしか見えません。目的のスペースを持つ Bot を選んでください。"
                 "（変数名だけを表示し、値は画面に出しません）",
        )
    else:
        st.info("`.env` に Bot トークンが見つかりません。下の欄に貼り付けてください。")
        choice = MANUAL_ENTRY

    if choice == MANUAL_ENTRY:
        token = st.text_input(
            "Webex Bot トークン / Bot token",
            type="password",
            help="Webex Developer Portal で発行した Bot トークン、またはパーソナルアクセストークン。"
                 "入力値は画面に表示されず、保存もされません。",
        ).strip()
    else:
        token = (os.environ.get(choice) or "").strip()
        st.caption(f"`{choice}` を使用します。")

    fetch = st.button("スペース一覧を取得 / Fetch spaces", type="primary", width="stretch")

    st.divider()
    st.markdown(
        "**スペースが出てこないときは**\n\n"
        "Bot がそのスペースのメンバーになっていないと一覧に出ません。"
        "Webex 側でスペースに Bot を追加してから、もう一度取得してください。"
    )

# ------------------------------------------------------------------
# 取得 / Fetch
# ------------------------------------------------------------------
if fetch:
    if not token:
        st.error("トークンが未入力です。サイドバーに入力してください。")
    else:
        with st.spinner("Webex API に接続しています..."):
            try:
                st.session_state["rooms"] = list_rooms(token)
                st.session_state["fetch_error"] = None
            except requests.exceptions.RequestException as e:
                status = getattr(e.response, "status_code", "N/A")
                body = getattr(e.response, "text", str(e))
                st.session_state["rooms"] = None
                st.session_state["fetch_error"] = (status, body)

if st.session_state.get("fetch_error"):
    status, body = st.session_state["fetch_error"]
    st.error(f"取得に失敗しました（ステータスコード: {status}）。トークンが無効か期限切れの可能性があります。")
    with st.expander("エラー詳細 / Details"):
        st.code(body)

rooms = st.session_state.get("rooms")

if rooms is None:
    st.info("サイドバーの「スペース一覧を取得」を押してください。")
    st.stop()

st.success(f"✅ トークンは有効です。{len(rooms)} 件のスペースが見つかりました。")

# ------------------------------------------------------------------
# 検索 / Filter
# ------------------------------------------------------------------
col_q, col_exact = st.columns([4, 1])
with col_q:
    query = st.text_input(
        "スペース名で絞り込み / Filter by name",
        placeholder="例: Cisco Security Advisories",
        help="部分一致・大文字小文字を区別しません（CLI の --find と同じ挙動）。",
    )
with col_exact:
    exact = st.checkbox("完全一致", help="CLI の --exact と同じ")

if query:
    if exact:
        matches = [r for r in rooms if (r.get("title") or "") == query]
    else:
        matches = find_rooms_by_title(rooms, query)
else:
    matches = rooms

st.write(f"表示中: **{len(matches)}** 件 / {len(rooms)} 件")

if not matches:
    st.warning("該当するスペースがありません。Bot がそのスペースのメンバーか確認してください。")
    st.stop()

# ------------------------------------------------------------------
# 一覧 / Table
# ------------------------------------------------------------------
table = [
    {
        "スペース名 / Title": r.get("title") or "",
        "Room ID": r.get("id") or "",
        "種別 / Type": r.get("type") or "",
        "最終更新 / Last activity": (r.get("lastActivity") or "")[:19].replace("T", " "),
    }
    for r in matches
]
st.dataframe(table, width="stretch", hide_index=True)

st.caption("表のセルは選択してコピーできます。右上のアイコンから全体のダウンロードも可能です。")

# ------------------------------------------------------------------
# .env 行の生成 / Generate .env line
# ------------------------------------------------------------------
st.divider()
st.subheader("`.env` に貼り付ける行を作る / Generate a `.env` line")

titles = [r.get("title") or "(名前なし)" for r in matches]
idx = st.selectbox(
    "スペースを選ぶ / Pick a space",
    range(len(matches)),
    format_func=lambda i: titles[i],
)
selected = matches[idx]

col_a, col_b = st.columns(2)
with col_a:
    suffix = st.selectbox(
        "用途（変数名の末尾）/ Variable suffix",
        SUFFIX_CHOICES + ["（自由入力 / custom）"],
        help="`bots.yml` の `${WEBEX_SPACE_ID_...}` と揃えてください。",
    )
with col_b:
    if suffix == "（自由入力 / custom）":
        suffix = st.text_input("変数名の末尾 / Custom suffix", value="MY_SPACE").strip().upper()

var_name = f"WEBEX_SPACE_ID_{suffix}" if suffix else "WEBEX_SPACE_ID"
st.code(f"{var_name}={selected.get('id')}", language="bash")

safe_title = (selected.get("title") or "").replace('"', '\\"')
st.markdown(
    f"この行を `.env` に追記し、`config.yml` のチャンネル側で `${{{var_name}}}` として参照します。"
)
st.code(
    "channels:\n"
    f'  - name: "{safe_title}"\n'
    f"    webex_space_id: ${{{var_name}}}\n"
    "    categories:\n"
    "      - セキュリティ        # ← 送りたいカテゴリ名に置き換える\n",
    language="yaml",
)
st.caption(
    "name を categories.yml のカテゴリ名そのもの（例: `セキュリティ`）にすれば、"
    "`categories:` の2行は省略できます。"
)
