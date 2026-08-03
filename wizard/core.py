"""初期設定ウィザードの共通ロジック / Shared logic for the rss-bot setup wizard.

CLI 版（cli.py）と ブラウザUI版（app.py）の両方がこのモジュールを使う。
UI に依存する処理は持たず、診断・検証・生成だけを担う。

依存の注意: このモジュール自身は標準ライブラリだけで import できる。
requests / PyYAML は使う関数の中で遅延 import する（仮想環境を作る前の
ブートストラップ（setup.py）からも読み込めるようにするため）。
"""

from __future__ import annotations

import hashlib
import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, time as dt_time
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parent.parent

URLS_FILE = REPO_ROOT / "urls.yml"
CHANNELS_FILE = REPO_ROOT / "channels.yml"
LEGACY_CONFIG_FILE = REPO_ROOT / "config.yml"
URLS_EXAMPLE = REPO_ROOT / "urls.yml.example"
ENV_FILE = REPO_ROOT / ".env"
ENV_EXAMPLE = REPO_ROOT / ".env.example"
CATEGORIES_FILE = REPO_ROOT / "categories.yml"
CATEGORIES_PRIVATE_FILE = REPO_ROOT / "categories-private.yml"
REQUIREMENTS = REPO_ROOT / "requirements.txt"
REQUIREMENTS_UI = REPO_ROOT / "requirements-ui.txt"

MIN_PYTHON = (3, 10)

# Webex 開発者ポータルの固定URL（環境ごとに変わる設定値ではないため定数で持つ）
BOT_CREATE_URL = "https://developer.webex.com/my-apps/new/bot"  # noqa: W02  外部サービスの固定URL
BOT_DOCS_URL = "https://developer.webex.com/docs/bots"  # noqa: W02  外部サービスの固定URL
BOT_LIST_URL = "https://developer.webex.com/my-apps"  # noqa: W02  外部サービスの固定URL
WEBEX_ME_URL = "https://webexapis.com/v1/people/me"  # noqa: W02  外部サービスの固定URL


# ===========================================================
# ステップ0: 環境診断 / Step 0: Environment checks
# ===========================================================

@dataclass
class Check:
    """診断1件の結果。ok=False でも fatal でなければ続行できる。"""

    name: str
    ok: bool
    detail: str
    hint: str = ""
    fatal: bool = False


def check_python_version() -> Check:
    """実行中の Python が要件を満たすかを確認する。"""
    current = sys.version_info[:2]
    ok = current >= MIN_PYTHON
    return Check(
        name="Python のバージョン",
        ok=ok,
        detail=f"{current[0]}.{current[1]}（必要: {MIN_PYTHON[0]}.{MIN_PYTHON[1]} 以上）",
        hint="" if ok else "python.org から新しい Python を入れ直してください。",
        fatal=not ok,
    )


def _mac_protected_dirs() -> list[tuple[Path, str]]:
    """macOS で TCC に保護され、launchd から読めないディレクトリ。"""
    home = Path.home()
    return [
        (home / "Documents", "書類フォルダ"),
        (home / "Desktop", "デスクトップ"),
        (home / "Downloads", "ダウンロード"),
        (home / "Library" / "Mobile Documents", "iCloud Drive"),
    ]


def _check_location_macos(root: Path) -> Check:
    """macOS: TCC 保護対象の配下にいないかを判定する。"""
    for protected, label in _mac_protected_dirs():
        if root == protected or protected in root.parents:
            return Check(
                name="リポジトリの置き場所",
                ok=False,
                detail=f"{label}の配下にあります（{root}）",
                hint="定時実行（launchd）から設定ファイルを読めません。"
                     "~/Developer/rss-bot などへ移動してください（手動実行だけは成功するため気づきにくい問題です）。",
            )
    return Check(name="リポジトリの置き場所", ok=True, detail=f"{root}（TCC 保護対象外）")


def _check_location_windows(root: Path) -> Check:
    """Windows: OneDrive 同期フォルダーの配下にいないかを判定する。"""
    text = str(root)
    onedrive = os.environ.get("OneDrive") or os.environ.get("OneDriveConsumer") or ""
    in_onedrive = "onedrive" in text.lower() or (onedrive and text.lower().startswith(onedrive.lower()))
    if in_onedrive:
        return Check(
            name="リポジトリの置き場所",
            ok=False,
            detail=f"OneDrive 同期フォルダーの配下にあります（{root}）",
            hint="ファイル オンデマンドでプレースホルダー化されると、タスクスケジューラからの実行が失敗することがあります。"
                 r"C:\tools\rss-bot などへ移動してください。",
        )
    if text.startswith("\\\\"):
        return Check(
            name="リポジトリの置き場所",
            ok=False,
            detail=f"ネットワークドライブ上にあります（{root}）",
            hint="「ユーザーがログオンしていなくても実行」時にパスを解決できません。ローカルドライブへ移動してください。",
        )
    return Check(name="リポジトリの置き場所", ok=True, detail=f"{root}（同期フォルダーの外）")


def check_location(root: Path | None = None) -> Check:
    """定時実行に適した置き場所かを OS ごとに判定する。"""
    root = (root or REPO_ROOT).resolve()
    system = platform.system()
    if system == "Darwin":
        return _check_location_macos(root)
    if system == "Windows":
        return _check_location_windows(root)
    return Check(name="リポジトリの置き場所", ok=True, detail=f"{root}")


def check_writable(root: Path | None = None) -> Check:
    """ログや設定を書き込めるかを実際に書いて確かめる。"""
    root = root or REPO_ROOT
    probe = root / ".wizard_write_test"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        return Check(
            name="書き込み権限",
            ok=False,
            detail=f"{root} に書き込めません（{exc}）",
            hint="フォルダの権限を確認するか、書き込める場所へ移動してください。",
            fatal=True,
        )
    return Check(name="書き込み権限", ok=True, detail="設定ファイルとログを書き込めます")


def run_diagnostics(root: Path | None = None) -> list[Check]:
    """ステップ0の診断をまとめて実行する。"""
    return [check_python_version(), check_location(root), check_writable(root)]


# ===========================================================
# 設定ファイルの用意 / Creating missing config files
# ===========================================================

# (作るファイル, ひな形, 必須か) の対応表。ひな形が無いものは作らない。
CONFIG_TEMPLATES = [
    (ENV_FILE, ENV_EXAMPLE, True),
    (URLS_FILE, REPO_ROOT / "urls.yml.example", True),
    (CHANNELS_FILE, REPO_ROOT / "channels.yml.example", True),
    (CATEGORIES_FILE, REPO_ROOT / "categories.yml.example", True),
    (REPO_ROOT / "regions.yml", REPO_ROOT / "regions.yml.example", False),
    (REPO_ROOT / "morning_messages.txt", REPO_ROOT / "morning_messages.txt.example", False),
]


def missing_config_files() -> list[str]:
    """まだ作られていない設定ファイルの名前を返す。"""
    return [target.name for target, template, _ in CONFIG_TEMPLATES
            if not target.exists() and template.exists()]


def ensure_config_files() -> list[str]:
    """足りない設定ファイルを、ひな形から作る。

    **既にあるファイルには一切触れない**（上書きも追記もしない）。
    戻り値は新しく作ったファイル名の一覧。作るものが無ければ空。
    Windows / macOS のどちらでも同じように動く。
    """
    created: list[str] = []
    for target, template, _required in CONFIG_TEMPLATES:
        if target.exists() or not template.exists():
            continue
        try:
            shutil.copyfile(template, target)
        except OSError:
            continue      # 権限などで作れない場合は、呼び出し側の診断に任せる
        created.append(target.name)
    return created


# ===========================================================
# ステップ1: 仮想環境と依存 / Step 1: venv and dependencies
# ===========================================================

def venv_python(root: Path | None = None) -> Path | None:
    """リポジトリ内の仮想環境の python を探す。無ければ None。"""
    root = root or REPO_ROOT
    names = ["Scripts/python.exe", "bin/python"] if os.name == "nt" else ["bin/python", "venv/bin/python"]
    for name in names:
        candidate = root / name
        if candidate.exists():
            return candidate
    for name in ["venv/Scripts/python.exe", "venv/bin/python"]:
        candidate = root / name
        if candidate.exists():
            return candidate
    return None


def create_venv(root: Path | None = None) -> Path:
    """リポジトリ直下に仮想環境を作り、その python のパスを返す。"""
    root = root or REPO_ROOT
    subprocess.run([sys.executable, "-m", "venv", str(root)], check=True)
    created = venv_python(root)
    if created is None:
        raise RuntimeError("仮想環境を作成しましたが python が見つかりません")
    return created


def install_requirements(python_path: Path, include_ui: bool = True) -> None:
    """requirements.txt（必要なら UI 用も）を導入する。"""
    targets = [REQUIREMENTS]
    if include_ui and REQUIREMENTS_UI.exists():
        targets.append(REQUIREMENTS_UI)
    for req in targets:
        subprocess.run([str(python_path), "-m", "pip", "install", "-q", "-r", str(req)], check=True)


def missing_packages(python_path: Path) -> list[str]:
    """本体の実行に必要なパッケージのうち、入っていないものを返す。"""
    code = (
        "import importlib.util as u, json, sys;"
        "mods = ['feedparser', 'requests', 'dotenv', 'yaml'];"
        "print(json.dumps([m for m in mods if u.find_spec(m) is None]))"
    )
    try:
        done = subprocess.run([str(python_path), "-c", code], capture_output=True, text=True, check=True)
    except (subprocess.CalledProcessError, OSError):
        return ["feedparser", "requests", "dotenv", "yaml"]
    import json

    return json.loads(done.stdout.strip() or "[]")


# ===========================================================
# ステップ2: Webex 接続 / Step 2: Webex connection
# ===========================================================

def _load_check_rooms() -> ModuleType:
    """リポジトリ直下の check_rooms.py を読み込む（API の実装を一本化するため）。"""
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    import check_rooms  # 仮想環境の作成後にしか使えないため遅延 import

    return check_rooms


def detect_env_tokens(path: Path | None = None) -> list[str]:
    """.env にある Bot トークン変数の**名前だけ**を返す（値は返さない）。

    共通の WEBEX_BOT_TOKEN と、チャンネル別の WEBEX_BOT_TOKEN_* の両方に対応する。
    Returns the names of token variables defined in .env (never the values).
    """
    from dotenv import dotenv_values

    path = path or ENV_FILE
    if not path.exists():
        return []
    values = dotenv_values(path)
    names = [k for k, v in values.items() if k.startswith("WEBEX_BOT_TOKEN") and (v or "").strip()]
    names.sort(key=lambda k: (k != "WEBEX_BOT_TOKEN", k))  # 共通トークンを先頭に
    return names


def get_env_token(name: str, path: Path | None = None) -> str:
    """.env から指定した変数名のトークン値を取り出す。"""
    from dotenv import dotenv_values

    path = path or ENV_FILE
    if not path.exists():
        return ""
    return (dotenv_values(path).get(name) or "").strip()


def validate_token(token: str) -> tuple[bool, str]:
    """Webex トークンが有効かを確認する。戻り値は (成否, 説明)。"""
    import requests

    token = (token or "").strip()
    if not token:
        return False, "トークンが空です"
    try:
        _load_check_rooms().list_rooms(token, max_rooms=1)
    except requests.exceptions.HTTPError as exc:
        status = getattr(exc.response, "status_code", None)
        if status == 401:
            return False, "トークンが無効か期限切れです（401）"
        return False, f"Webex API がエラーを返しました（{status}）"
    except requests.exceptions.RequestException as exc:
        return False, f"Webex へ接続できません（{exc.__class__.__name__}）"
    return True, "トークンは有効です"


def token_identity(token: str) -> tuple[str, str]:
    """トークンが属する bot の (表示名, アドレス) を返す。取得できなければ ("", "")。

    表示名は「貼ったトークンが本当にその bot のものか」の確認に、
    アドレス（@webex.bot）は「このアドレスをスペースに招待してください」の案内に使う。
    Returns (display name, bot address) so the user can verify and invite the bot.
    """
    import requests

    token = (token or "").strip()
    if not token:
        return "", ""
    try:
        response = requests.get(WEBEX_ME_URL, timeout=15,
                                headers={"Authorization": f"Bearer {token}"})
        response.raise_for_status()
    except requests.exceptions.RequestException:
        return "", ""
    data = response.json()
    emails = data.get("emails") or []
    return str(data.get("displayName") or ""), str(emails[0] if emails else "")


def env_vars_sharing_token(token: str, exclude: str = "",
                           path: Path | None = None) -> list[str]:
    """同じトークン値が既に入っている .env の変数名を返す（貼り間違いの検出用）。

    値そのものは返さない。1つの bot のトークンを複数の変数へ入れてしまうと、
    別スペース宛の配信が同じ宛先へ流れる事故になるため、保存前に警告する材料にする。
    """
    from dotenv import dotenv_values

    token = (token or "").strip()
    path = path or ENV_FILE
    if not token or not path.exists():
        return []
    values = dotenv_values(path)
    return sorted(k for k, v in values.items()
                  if k and k != exclude and (v or "").strip() == token)


def replace_env_token(name: str, token: str) -> tuple[bool, str]:
    """.env のトークン変数を1つだけ差し替える。戻り値は (成否, 説明)。

    **有効性を確認できたときだけ書き込む。** 無効な値で上書きすると、
    元のトークンも失って状況が悪くなるため。説明に値は含めない。
    """
    name = (name or "").strip()
    if not name.startswith("WEBEX_BOT_TOKEN"):
        return False, f"Bot トークンの変数名ではありません: {name}"
    ok, message = validate_token(token)
    if not ok:
        return False, f"{message} — 変更していません"
    try:
        result = backup_and_write(ENV_FILE, build_env_text({name: (token or "").strip()}))
    except OSError as exc:
        return False, f".env に書き込めませんでした（{exc}）"
    where = f"（控え: {result.backup.name}）" if result.backup else ""
    return True, f"{name} を差し替えました{where}"


def space_rows(spaces: list[dict], configured: dict[str, str] | None = None) -> list[dict]:
    """スペース一覧を画面表示用の行に整える。"""
    used = configured or {}
    rows = []
    for space in spaces:
        space_id = space.get("id", "")
        rows.append({
            "スペース名": space.get("title") or "(名前なし)",
            "種別": {"group": "グループ", "direct": "1対1"}.get(space.get("type", ""), space.get("type", "")),
            "最終更新": (space.get("lastActivity") or "")[:16].replace("T", " "),
            "配信設定": used.get(space_id, "未設定"),
            "Room ID": space_id,
        })
    return rows


def check_all_tokens() -> list[dict]:
    """.env にある全 Bot トークンの有効性と、見えるスペース数を調べる。

    値は返さない。結果は {変数名, 有効か, 説明, スペース数} の一覧。
    """
    rows = []
    for name in detect_env_tokens():
        token = get_env_token(name)
        ok, message = validate_token(token)
        count = ""
        if ok:
            try:
                count = str(len(list_spaces(token)))
            except OSError:
                count = "?"
            except Exception:  # noqa: W01  API 側の想定外応答でも一覧表示は続ける
                count = "?"
        rows.append({"変数名": name, "状態": "有効" if ok else "エラー",
                     "内容": message, "参加スペース数": count})
    return rows


def list_spaces(token: str) -> list[dict]:
    """トークンで見えるスペースの一覧を返す（check_rooms.py と同じ実装を使う）。"""
    return _load_check_rooms().list_rooms(token)


# ===========================================================
# ステップ3: カテゴリと配信先 / Step 3: categories and channels
# ===========================================================

def available_categories(path: Path | None = None) -> list[str]:
    """categories.yml に定義されたカテゴリ名を返す（${VAR} は環境変数で展開）。"""
    import yaml

    path = path or CATEGORIES_FILE
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    names = []
    for key in data:
        # _expand_env は .env を読み込んでから展開する。
        # .env を読まずに展開すると ${MYFAB_KEYWORD} が解決できず、
        # 変数で名前を決めているカテゴリが選択肢から漏れてしまう。
        name = _expand_env(str(key))
        if "${" not in name:
            names.append(name)
    return names


def category_name_map(path: Path | None = None) -> dict[str, str]:
    """{展開後のカテゴリ名: categories.yml に書かれている原文} を返す。

    画面には展開後の名前を出しつつ、保存時は元の ${VAR} の書き方に戻すために使う。
    """
    return {_expand_env(key): key for key in category_keys(path)
            if "${" not in _expand_env(key)}


@dataclass
class ChannelPlan:
    """ウィザードが組み立てる配信チャンネル1件。

    name は Webex 投稿の見出しになるため、利用者が自由に決められる。
    categories は複数指定でき、name と単一カテゴリが一致する場合だけ
    categories: を省略できる（本体が name をカテゴリ名として解決するため）。
    """

    name: str
    categories: list[str] = field(default_factory=list)
    space_id: str = ""
    space_title: str = ""
    env_suffix: str = ""
    # 既存設定にチャンネル別の webex_bot_token があれば、その参照を保持する
    bot_token_ref: str = ""
    # 既存の webex_space_id の書き方（${WEBEX_SPACE_ID_XXX} など）を保持する。
    # 名前から変数名を作り直すと、既存の .env と食い違って配信が止まる。
    space_ref: str = ""
    # True なら name を ${CATEGORY_*} で書く（カテゴリ名の正本を .env に置く）
    use_category_var: bool = False
    # True なら「天気＋各チャンネルの投稿まとめ」を配信するダイジェストにする。
    # 自分ではニュースを集めないため categories は使わない。
    is_digest: bool = False
    # このチャンネルにも該当する記事を、指定したチャンネルへ譲る（重複配信を防ぐ）
    defers_to: list[str] = field(default_factory=list)
    # 日本語記事の下限。None なら指定なし（本体の既定にまかせる）
    min_japanese: int | None = None
    # True ならこのチャンネルが該当記事を独占し、他チャンネルからは除外する
    priority: bool = False
    # urls.yml の名前付きグループ。指定するとそのフィード由来の記事だけを専有配信する
    source_groups: list[str] = field(default_factory=list)

    @property
    def suffix(self) -> str:
        """このチャンネルの変数サフィックス（配列の添字にあたる）。"""
        return self.env_suffix or _slug(self.name)

    @property
    def env_var(self) -> str:
        """このチャンネルが .env で使う Space ID の変数名。"""
        return f"WEBEX_SPACE_ID_{self.suffix}"

    @property
    def token_var(self) -> str:
        """このチャンネルが使う Bot トークンの変数名（他チャンネルと同じ命名にする）。"""
        return f"WEBEX_BOT_TOKEN_{self.suffix}"

    @property
    def token_ref(self) -> str:
        """channels.yml の webex_bot_token に書く値。"""
        return self.bot_token_ref or f"${{{self.token_var}}}"

    @property
    def space_id_ref(self) -> str:
        """channels.yml の webex_space_id に書く値（既存の書き方を優先する）。"""
        return self.space_ref or f"${{{self.env_var}}}"

    @property
    def category_var(self) -> str:
        """チャンネル名を宣言する .env の変数名。"""
        return f"CATEGORY_{self.suffix}"

    @property
    def name_ref(self) -> str:
        """config 上の name に書く値（変数方式なら ${CATEGORY_*}）。"""
        return f"${{{self.category_var}}}" if self.use_category_var else self.name

    @property
    def omits_categories(self) -> bool:
        """categories: を省略できるか（name と単一カテゴリが一致するとき）。"""
        return not self.is_digest and self.categories == [self.name]


# 日本語の名前から .env の変数サフィックスへの対応（既定のカテゴリ）
KNOWN_SUFFIXES = {
    "一般": "GENERAL",
    "経済": "ECONOMY",
    "セキュリティ": "SECURITY",
    "ネットワーク": "NETWORKING",
    "クラウド": "CLOUD",
    "AI・機械学習": "AI",
}


def _slug(text: str) -> str:
    """カテゴリ名から .env の変数名に使える英数字の識別子を作る。

    同じカテゴリ名からは常に同じ識別子が出る必要がある
    （実行のたびに変わると .env と config.yml の対応が壊れるため）。
    """
    if text in KNOWN_SUFFIXES:
        return KNOWN_SUFFIXES[text]
    ascii_only = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").upper()
    if ascii_only:
        return ascii_only
    # 英数字が残らない名前は、内容から決まる安定した識別子にする
    digest = hashlib.md5(text.encode("utf-8")).hexdigest()[:6].upper()
    return f"CH_{digest}"


# ===========================================================
# 既存設定の読み込み / Reading an existing config
# ===========================================================

# ウィザードが画面上で組み立てられるキー。これ以外を持つチャンネルは
# 中身を理解できないため、編集せず原文のまま引き継ぐ。
SIMPLE_CHANNEL_KEYS = {"name", "webex_space_id", "webex_bot_token", "categories",
                       "digest", "defers_to", "min_japanese", "priority", "source_groups"}


@dataclass
class ExistingConfig:
    """既存 config.yml から読み取った内容。"""

    feed_urls: list[str] = field(default_factory=list)
    special_feeds: list[dict] = field(default_factory=list)
    assigned: dict[str, str] = field(default_factory=dict)
    channel_categories: dict[str, list[str]] = field(default_factory=dict)
    # 読み込んだ全チャンネルの原文。画面に出ないスペース（別の bot でしか
    # 見えないチャンネル）を書き出しで失わないために保持する。
    all_channels: list[dict] = field(default_factory=list)
    digest_spaces: set[str] = field(default_factory=set)
    bot_tokens: dict[str, str] = field(default_factory=dict)
    space_refs: dict[str, str] = field(default_factory=dict)
    channel_options: dict[str, dict] = field(default_factory=dict)
    kept_channels: list[dict] = field(default_factory=list)

    @property
    def summary(self) -> str:
        """画面に出す1行の要約。"""
        parts = [f"フィード {len(self.feed_urls)} 件"]
        if self.special_feeds:
            parts.append(f"特殊エントリ {len(self.special_feeds)} 件")
        parts.append(f"配信先 {len(self.assigned) + len(self.kept_channels)} 件")
        return "、".join(parts)


def _expand_env(value: object) -> str:
    """${VAR} を .env の値で展開する（未定義ならそのまま返す）。"""
    from dotenv import load_dotenv

    load_dotenv(ENV_FILE, override=True)
    return os.path.expandvars(str(value or ""))  # noqa: W07  環境変数展開は pathlib に無い


def load_existing_config(path: Path | None = None) -> ExistingConfig | None:
    """既存の設定（urls.yml + channels.yml、無ければ config.yml）を読んで分解する。

    ウィザードが再現できないチャンネル（priority / defers_to / digest /
    source_groups / min_japanese などを持つもの）は kept_channels に入れ、
    書き出すときに原文のまま引き継ぐ。
    """
    import yaml

    data: dict = {}
    if path is not None:
        sources = [path]
    elif URLS_FILE.exists() or CHANNELS_FILE.exists():
        sources = [URLS_FILE, CHANNELS_FILE]
    elif LEGACY_CONFIG_FILE.exists():
        sources = [LEGACY_CONFIG_FILE]
    else:
        return None

    for source in sources:
        if not source.exists():
            continue
        try:
            loaded = yaml.safe_load(source.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            return None
        if isinstance(loaded, list):
            data["feeds"] = loaded          # v1.x のリスト形式
        elif isinstance(loaded, dict):
            data.update(loaded)
    if not data:
        return None

    result = ExistingConfig()
    for item in data.get("feeds") or []:
        if isinstance(item, str):
            result.feed_urls.append(item)
        elif isinstance(item, dict):
            result.special_feeds.append(item)

    for channel in data.get("channels") or []:
        if isinstance(channel, dict):
            _absorb_channel(result, channel)
    return result


def _absorb_channel(result: ExistingConfig, channel: dict) -> None:
    """チャンネル1件を ExistingConfig に取り込む。"""
    result.all_channels.append(channel)
    if set(channel) - SIMPLE_CHANNEL_KEYS:
        result.kept_channels.append(channel)
        return
    name = str(channel.get("name") or "")
    space_id = _expand_env(channel.get("webex_space_id"))
    result.assigned[space_id] = name
    result.channel_categories[space_id] = list(channel.get("categories") or [name])
    if channel.get("digest"):
        result.digest_spaces.add(space_id)
    result.space_refs[space_id] = str(channel.get("webex_space_id") or "")
    result.channel_options[space_id] = {
        "source_groups": [str(x) for x in (channel.get("source_groups") or [])],
        "defers_to": [str(x) for x in (channel.get("defers_to") or [])],
        "min_japanese": channel.get("min_japanese"),
        "priority": bool(channel.get("priority")),
    }
    token_ref = str(channel.get("webex_bot_token") or "")
    if token_ref:
        result.bot_tokens[space_id] = token_ref


# ===========================================================
# ステップ6: ファイル生成 / Step 6: file generation
# ===========================================================

@dataclass
class WriteResult:
    """書き込み1件の結果。backup は退避先（無ければ None）。"""

    path: Path
    backup: Path | None = None
    created: bool = False


def backup_and_write(path: Path, text: str) -> WriteResult:
    """既存ファイルを退避してから書き込む。上書きの前に必ず控えを残す。

    書き込みに失敗した場合は OSError を送出する（呼び出し側で利用者へ知らせる）。
    Raises OSError so the caller can report the failure to the user.
    """
    backup = None
    created = not path.exists()
    if path.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = path.with_name(f"{path.name}.bak-{stamp}")
        shutil.copy2(path, backup)
    path.write_text(text, encoding="utf-8")
    return WriteResult(path=path, backup=backup, created=created)


def diff_env_changes(values: dict[str, str]) -> list[dict]:
    """これから .env に書く内容と、いまの内容を比べて一覧にする。

    値そのものは返さない（トークンを画面に出さないため）。
    操作は「追加」「上書き」「変更なし」「削除」のいずれか。
    """
    from dotenv import dotenv_values

    current = dotenv_values(ENV_FILE) if ENV_FILE.exists() else {}
    rows = []
    for key, new_value in values.items():
        old = (current.get(key) or "").strip()
        new = (new_value or "").strip()
        secret = "TOKEN" in key or "API_KEY" in key
        if not new and old:
            action = "削除"
        elif not old:
            action = "追加"
        elif old == new:
            action = "変更なし"
        else:
            action = "上書き"
        shown = "（値は表示しません）" if secret else (new or "（空）")
        rows.append({"設定": key, "操作": action, "新しい値": shown})
    return rows


def summarize_env_changes(rows: list[dict]) -> str:
    """差分の要約を1行で返す（「追加2件・上書き1件」など）。"""
    counts: dict[str, int] = {}
    for row in rows:
        if row["操作"] != "変更なし":
            counts[row["操作"]] = counts.get(row["操作"], 0) + 1
    if not counts:
        return "変更はありません"
    return "・".join(f"{action} {n} 件" for action, n in counts.items())


def other_provider_keys(provider: str) -> list[str]:
    """選んだプロバイダ以外で、すでにキーが設定されているものを返す。"""
    from dotenv import dotenv_values

    if not ENV_FILE.exists():
        return []
    current = dotenv_values(ENV_FILE)
    found = []
    for name, spec in LLM_PROVIDERS.items():
        if name == provider:
            continue
        if (current.get(spec["key_env"]) or "").strip():
            found.append(spec["label"])
    return found


def build_env_text(values: dict[str, str], base: str | None = None) -> str:
    """.env の内容を組み立てる。既存の行があれば値だけ差し替える。

    ベースは**既存の .env**。既存の変数（他 bot のトークンなど）を消さないため、
    .env が無いときに限りテンプレート（.env.example）から作る。
    Existing .env is the base so other bots' tokens are never dropped.
    """
    if base is not None:
        source = base
    elif ENV_FILE.exists():
        source = read_text_safely(ENV_FILE)
    elif ENV_EXAMPLE.exists():
        source = read_text_safely(ENV_EXAMPLE)
    else:
        source = ""
    lines = source.splitlines()
    remaining = dict(values)
    out: list[str] = []
    for line in lines:
        match = re.match(r"^#?\s*([A-Z_][A-Z0-9_]*)=", line)
        key = match.group(1) if match else None
        if key and key in remaining:
            out.append(f"{key}={remaining.pop(key)}")
        else:
            out.append(line)
    if remaining:
        out.append("")
        out.append("# ── セットアップウィザードが追加 / Added by the setup wizard ──")
        out.extend(f"{key}={value}" for key, value in remaining.items())
    return "\n".join(out).rstrip() + "\n"


def _yaml_scalar(value: object) -> str:
    """YAML のスカラーとして安全な表記にする（必要なときだけ引用する）。

    `News Today : 天気とサマリー` のように `: `（コロン+空白）を含む名前を素で書くと
    マッピングと解釈され、**ファイル全体が読めなくなる**。他にも `#` や先頭の記号など
    引用が要る文字がある。判定は PyYAML に任せるのが確実。
    `${VAR}` 参照は引用不要と判定されるため、これまでどおりの見た目で残る。
    Quote only when needed, so ${VAR} references stay readable.
    """
    import yaml

    text = yaml.safe_dump(str(value), allow_unicode=True,
                          default_flow_style=True, width=10 ** 6).strip()
    if text.endswith("..."):
        text = text[:-3].strip()
    return text


def _dump_entry(entry: dict, indent: str = "  ") -> list[str]:
    """dict をリスト要素の YAML 行に整形する（既存設定を原文の意味のまま出すため）。"""
    import yaml

    text = yaml.safe_dump(entry, allow_unicode=True, sort_keys=False, default_flow_style=False)
    lines = text.rstrip().splitlines()
    if not lines:
        return []
    out = [f"{indent}- {lines[0]}"]
    out.extend(f"{indent}  {line}" for line in lines[1:])
    return out


def _feeds_block(feed_urls: list[str],
                 weather_labels: list[tuple[str, float, float]],
                 special_feeds: list[dict] | None = None) -> list[str]:
    """config.yml の feeds: セクションを組み立てる。"""
    lines = ["feeds:"]
    for entry in special_feeds or []:
        lines.append("")
        if "weather" in entry:
            label = "天気API"
        elif "cisco_advisory" in entry:
            label = "Cisco Security Advisory の CVSS 取得API"
        else:
            label = f"グループ: {entry.get('group', '')}"
        lines.append(f"  # {label}（既存の設定をそのまま引き継ぎ）")
        lines.extend(_dump_entry(entry))
    if weather_labels and not any("weather" in e for e in (special_feeds or [])):
        lines.append("")
        lines.append("  # 天気API（デイリーダイジェスト用、APIキー不要）")
        lines.append("  - weather:")
        lines.append("      api_url: https://api.open-meteo.com/v1/forecast")
        lines.append("      locations:")
        for label, lat, lon in weather_labels:
            lines.append(f"        - {{ label: {_yaml_scalar(label)}, lat: {lat}, lon: {lon} }}")
    lines.append("")
    lines.append("  # 収集するRSSフィード")
    lines.extend(f"  - {url}" for url in feed_urls)
    return lines


def channels_using_space(existing: ExistingConfig | None, space_id: str) -> list[dict]:
    """指定スペースを使っている既存チャンネルを返す（上書き警告に使う）。"""
    if existing is None or not space_id:
        return []
    return [ch for ch in existing.all_channels
            if _expand_env(ch.get("webex_space_id")) == space_id]


def channels_to_preserve(existing: ExistingConfig | None,
                        edited_names: set[str],
                        removed_names: set[str] | None = None) -> list[dict]:
    """今回編集しなかった既存チャンネルを、原文のまま返す。

    判定は**チャンネル名**で行う。スペースIDで判定すると、同じスペースに
    複数のチャンネル（例: ニュース配信とダイジェスト）を向けている場合に、
    片方を編集しただけでもう片方が消えてしまう。
    名前は ${VAR} で書かれていることがあるため、原文と展開後の両方で照合する。

    removed_names は**画面で明示的に削除された**チャンネル名。削除されたものは
    書き出す一覧（plans）から外れるため、指定が無いと「編集しなかった」と
    区別が付かず、そのまま復活してしまう。
    Explicitly removed channels must be named here, otherwise they look untouched
    and get preserved verbatim.
    """
    if existing is None:
        return []
    removed = removed_names or set()
    preserved = []
    for channel in existing.all_channels:
        raw = str(channel.get("name") or "")
        expanded = _expand_env(raw)
        if raw in edited_names or expanded in edited_names:
            continue
        if raw in removed or expanded in removed:
            continue
        preserved.append(channel)
    return preserved


def edited_channel_names(plans: list[ChannelPlan]) -> set[str]:
    """ウィザードが書き出すチャンネル名の集合（原文と展開後の両方）。"""
    names: set[str] = set()
    for plan in plans:
        names.add(plan.name)
        names.add(plan.name_ref)
        names.add(_expand_env(plan.name_ref))
    return names


def build_urls_text(feed_urls: list[str],
                    weather: list[tuple[str, float, float]] | None = None,
                    special_feeds: list[dict] | None = None) -> str:
    """urls.yml の内容を組み立てる（収集するフィードだけ）。"""
    header = [
        "# ============================================================",
        "# urls.yml  —  収集するRSSフィード",
        f"#   セットアップウィザードが生成（{datetime.now().strftime('%Y-%m-%d %H:%M')}）",
        "#   天気API（weather）と名前付きグループ（group）もここに書く。",
        "# ============================================================",
        "",
    ]
    body = _feeds_block(feed_urls, weather or [], special_feeds)
    return "\n".join(header + body).rstrip() + "\n"


def build_channels_text(channels: list[ChannelPlan],
                        kept_channels: list[dict] | None = None) -> str:
    """config.yml の内容を組み立てる。

    name はカテゴリ名そのものにするため、categories: は書かない
    （完全一致で解決されるので設定が短くなる）。

    special_feeds（天気・名前付きグループ）と kept_channels（priority や
    defers_to などを持つチャンネル）は、ウィザードが解釈せず原文のまま書き出す。
    """
    header = [
        "# ============================================================",
        "# channels.yml  —  配信先チャンネル",
        f"#   セットアップウィザードが生成（{datetime.now().strftime('%Y-%m-%d %H:%M')}）",
        "#   name がカテゴリ名と完全一致するため categories: は書かない。",
        "# ============================================================",
        "",
    ]
    body = ["channels:"]
    for plan in channels:
        body.append("")
        if plan.space_title and plan.space_title != plan.name:
            body.append(f"  # 投稿先: {plan.space_title}")
        body.append(f"  - name: {_yaml_scalar(plan.name_ref)}")
        body.append(f"    webex_space_id: {_yaml_scalar(plan.space_id_ref)}")
        body.append(f"    webex_bot_token: {_yaml_scalar(plan.token_ref)}")
        if plan.priority:
            body.append("    priority: true       # 該当記事を独占し、他チャンネルからは除外する")
        if plan.defers_to:
            body.append("    defers_to:           # 下記チャンネルにも該当する記事は、そちらに譲る")
            body.extend(f"      - {_yaml_scalar(target)}" for target in plan.defers_to)
        if plan.min_japanese is not None:
            body.append(f"    min_japanese: {plan.min_japanese}"
                        "      # 日本語記事がこの件数を下回ったら新着順に補充する")
        if plan.source_groups:
            body.append("    source_groups:       # urls.yml のグループ由来の記事だけを専有配信")
            body.extend(f"      - {_yaml_scalar(group)}" for group in plan.source_groups)
        if plan.is_digest:
            body.append("    digest: true         # 天気＋各チャンネルの投稿まとめを1通に集約")
            body.append("    categories: []       # 自分ではニュースを集めない")
        elif plan.source_groups and not plan.categories:
            body.append("    categories: []       # グループ指定のみで振り分ける")
        elif not plan.omits_categories:
            body.append("    categories:")
            body.extend(f"      - {_yaml_scalar(category)}" for category in plan.categories)
    for channel in kept_channels or []:
        body.append("")
        body.append("  # 既存の設定をそのまま引き継ぎ（優先配信・譲渡・ダイジェスト等）")
        body.extend(_dump_entry(channel))
    return "\n".join(header + body).rstrip() + "\n"


def default_feed_urls(path: Path | None = None) -> list[str]:
    """config.yml.example の feeds: から、通常フィードのURLだけを取り出す。"""
    import yaml

    path = path or URLS_EXAMPLE
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    feeds = data if isinstance(data, list) else (data.get("feeds") or [])
    return [item for item in feeds if isinstance(item, str)]


# ===========================================================
# フィード設定（urls.yml）/ Feed definitions
# ===========================================================

# 受け付けるURLのスキーム（検査用の定数であり、接続先の設定ではない）
_URL_SCHEMES = ("http://", "https://")  # noqa: W02  URLの検査に使う定数（接続先ではない）
# 天気API（APIキー不要）。既定値であり、urls.yml で上書きできる。
WEATHER_API_URL = "https://api.open-meteo.com/v1/forecast"  # noqa: W02  既定値（urls.yml で変更可）
# 地名から緯度経度を引くAPI（Open-Meteo、APIキー不要）
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"  # noqa: W02  外部サービスの固定URL


def available_groups(path: Path | None = None) -> list[str]:
    """urls.yml に定義された名前付きグループの一覧を返す。"""
    config = load_existing_config(path)
    if config is None:
        return []
    groups, _ = split_special_feeds(config.special_feeds)
    return [str(g.get("group")) for g in groups if g.get("group")]


def build_group_entry(name: str, urls: list[str]) -> dict:
    """名前付きグループのエントリを作る。"""
    return {"group": name.strip(), "urls": [u.strip() for u in urls if u.strip()]}


def split_special_feeds(special: list[dict]) -> tuple[list[dict], list[dict]]:
    """特殊エントリを (グループ, その他=天気など) に分ける。"""
    groups = [e for e in special if "group" in e]
    others = [e for e in special if "group" not in e]
    return groups, others


def read_weather_locations(special: list[dict]) -> list[dict]:
    """天気エントリから観測地点の一覧を返す（無ければ空リスト）。"""
    for entry in special:
        weather = entry.get("weather") if isinstance(entry, dict) else None
        if weather:
            return [dict(loc) for loc in (weather.get("locations") or []) if isinstance(loc, dict)]
    return []


def geocode_place(name: str, count: int = 5) -> list[dict]:
    """地名から緯度経度の候補を返す（Open-Meteo の地名検索、APIキー不要）。

    戻り値は {label, lat, lon, detail} の一覧。見つからなければ空リスト。
    """
    import requests

    query = (name or "").strip()
    if not query:
        return []
    try:
        res = requests.get(GEOCODING_URL, timeout=15, params={
            "name": query, "count": count, "language": "ja", "format": "json"})
        res.raise_for_status()
        items = res.json().get("results") or []
    except requests.exceptions.RequestException:
        return []
    except ValueError:      # JSON として読めない応答
        return []

    results = []
    for item in items:
        lat, lon = item.get("latitude"), item.get("longitude")
        if lat is None or lon is None:
            continue
        detail = " / ".join(x for x in [item.get("admin1"), item.get("country")] if x)
        results.append({"label": str(item.get("name") or query),
                        "lat": float(lat), "lon": float(lon), "detail": detail})
    return results


def build_weather_entry(locations: list[dict], api_url: str = "") -> dict:
    """天気エントリを組み立てる（ダイジェストの天気ブロックで使う）。"""
    cleaned = []
    for loc in locations:
        label = str(loc.get("label") or "").strip()
        try:
            lat, lon = float(loc.get("lat")), float(loc.get("lon"))
        except (TypeError, ValueError):
            continue
        if label:
            cleaned.append({"label": label, "lat": lat, "lon": lon})
    return {"weather": {"api_url": api_url or WEATHER_API_URL, "locations": cleaned}}


def validate_feed_url(url: str) -> str:
    """フィードURLの明らかな誤りを指摘する。問題なければ空文字を返す。"""
    text = url.strip()
    if not text:
        return "空です"
    if not text.startswith(_URL_SCHEMES):
        return "http:// または https:// で始まる必要があります"  # noqa: W02  利用者向けの説明文
    if " " in text:
        return "空白が含まれています"
    return ""


# ===========================================================
# カテゴリ定義（categories.yml）/ Category definitions
# ===========================================================

def detect_category_vars(path: Path | None = None) -> dict[str, str]:
    """.env で宣言されているカテゴリ変数を {変数名: カテゴリ名} で返す。"""
    from dotenv import dotenv_values

    path = path or ENV_FILE
    if not path.exists():
        return {}
    values = dotenv_values(path)
    return {k: v for k, v in values.items()
            if k.startswith("CATEGORY_") and (v or "").strip()}


def category_keys(path: Path | None = None) -> list[str]:
    """categories.yml のトップレベルキーを、書かれているまま（未展開で）返す。"""
    path = path or CATEGORIES_FILE
    if not path.exists():
        return []
    keys = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([^\s#][^:]*):\s*$", line)
        if match:
            keys.append(match.group(1).strip())
    return keys


def rename_category_key(text: str, old_key: str, new_key: str) -> str:
    """categories.yml のトップレベルキーだけを書き換える（コメントと語彙は保持）。"""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.rstrip() == f"{old_key}:":
            lines[i] = f"{new_key}:"
            break
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def append_category(text: str, key: str, keywords: list[str]) -> str:
    """categories.yml に新しいカテゴリを追記する。"""
    block = ["", f"{key}:"]
    block.extend(f"  - {kw}" for kw in keywords)
    return text.rstrip() + "\n" + "\n".join(block) + "\n"


_KEYWORD_RE = re.compile(r"^\s*-\s*(.+?)\s*$")


def _keyword_value(line: str) -> str | None:
    """キーワード行から値を取り出す。キーワード行でなければ None。"""
    if not line.startswith((" ", "\t")) or "- " not in line:
        return None
    match = _KEYWORD_RE.match(line)
    if not match:
        return None
    value = match.group(1)
    # 行末のコメントを落とす（クォートの中の # は残す）
    if not value.startswith(('"', "'")):
        value = value.split("#")[0].strip()
    return value.strip().strip('"').strip("'")


def _section_bounds(lines: list[str], key: str) -> tuple[int, int] | None:
    """categories.yml の指定キーのセクション範囲（開始行の次, 終了行）を返す。"""
    start = None
    for i, line in enumerate(lines):
        if line.rstrip() == f"{key}:":
            start = i
            break
    if start is None:
        return None
    for j in range(start + 1, len(lines)):
        if lines[j] and not lines[j].startswith((" ", "\t", "#")) and lines[j].rstrip().endswith(":"):
            return start + 1, j
    return start + 1, len(lines)


def read_text_safely(path: Path) -> str:
    """設定ファイルを読む。存在しない・読めない場合は空文字を返す。"""
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def private_category_counts() -> dict[str, int]:
    """categories-private.yml に定義されたカテゴリと語数を返す（中身は返さない）。

    非公開ファイルは実行時に categories.yml へマージされる。ウィザードはこの
    ファイルを編集しないため、語数だけを見せて誤解を防ぐ。
    """
    import yaml

    text = read_text_safely(CATEGORIES_PRIVATE_FILE)
    if not text:
        return {}
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): len(v or []) for k, v in data.items()}


# .env に既定で入れる値（社内プロキシや macOS の証明書問題を避けるため）
DEFAULT_ENV_VALUES = {"SSL_VERIFY": "false"}

# LLM（Claude）の設定に使う変数
LLM_KEYS = ("ANTHROPIC_API_KEY", "ANTHROPIC_MODEL", "ANTHROPIC_RERANK_MODEL")

# 使える LLM プロバイダ。キーの変数名・モデル名の目安・キー発行ページをまとめて持つ。
LLM_PROVIDERS = {
    "anthropic": {
        "label": "Claude（Anthropic）",
        "key_env": "ANTHROPIC_API_KEY",
        "example": "claude-haiku-4-5-20251001",
        "hint": "`claude-` で始まるモデル名",
        "prefix": ("claude-",),
        "console": "https://console.anthropic.com/settings/keys",  # noqa: W02  固定URL
    },
    "openai": {
        "label": "OpenAI",
        "key_env": "OPENAI_API_KEY",
        "example": "gpt-4o-mini",
        "hint": "`gpt-` や `o1`/`o3`/`o4` で始まるモデル名",
        "prefix": ("gpt", "o1", "o3", "o4"),
        "console": "https://platform.openai.com/api-keys",  # noqa: W02  固定URL
    },
    "gemini": {
        "label": "Gemini（Google）",
        "key_env": "GEMINI_API_KEY",
        "example": "gemini-2.0-flash",
        "hint": "`gemini-` で始まるモデル名",
        "prefix": ("gemini-",),
        "console": "https://aistudio.google.com/apikey",  # noqa: W02  固定URL
    },
}
DEFAULT_PROVIDER = "anthropic"
DEFAULT_SUMMARY_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_RERANK_MODEL = "claude-haiku-4-5-20251001"
ANTHROPIC_CONSOLE_URL = "https://console.anthropic.com/settings/keys"  # noqa: W02  外部サービスの固定URL


def check_model_name(provider: str, model: str) -> str:
    """モデル名の書き方を確かめる。問題なければ空文字、あれば指摘を返す。

    実在するかまでは判定できないため、綴りの明らかな取り違え（別の会社の
    モデル名を入れている等）を拾う。最終確認は「接続を試す」で行う。
    """
    text = (model or "").strip()
    if not text:
        return "モデル名が空です"
    if " " in text:
        return "モデル名に空白が含まれています"
    info = LLM_PROVIDERS.get(provider)
    if not info:
        return f"知らないプロバイダです: {provider}"
    for other, spec in LLM_PROVIDERS.items():
        if other != provider and text.startswith(tuple(spec["prefix"])):
            return (f"{spec['label']} のモデル名に見えます。"
                    f"{info['label']} を選んでいるので、{info['hint']}を入れてください")
    if not text.startswith(tuple(info["prefix"])):
        return f"{info['label']} では{info['hint']}が一般的です（例: {info['example']}）"
    return ""


def try_llm(provider: str, api_key: str, model: str) -> tuple[bool, str]:
    """実際に短い問い合わせを1回送って、キーとモデル名が使えるか確かめる。"""
    import requests

    if not api_key:
        return False, "API キーが未設定です"
    sys.path.insert(0, str(REPO_ROOT))
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("rssbot", REPO_ROOT / "webex-news-rss-bot.py")
        bot = importlib.util.module_from_spec(spec)
        saved, sys.argv = sys.argv, ["wizard"]
        spec.loader.exec_module(bot)
        sys.argv = saved
        answer = bot.call_llm("OK とだけ返してください。", api_key, model.strip(),
                              max_tokens=16, provider=provider)
    except requests.exceptions.HTTPError as exc:
        status = getattr(exc.response, "status_code", None)
        detail = {401: "API キーが違うようです", 403: "この API キーでは使えません",
                  404: "そのモデル名は見つかりません"}.get(status, f"エラー（{status}）")
        return False, detail
    except requests.exceptions.RequestException as exc:
        return False, f"接続できません（{exc.__class__.__name__}）"
    except (KeyError, IndexError, ValueError):
        return False, "応答の形が想定と違います（モデル名を確認してください）"
    return True, f"応答を確認しました: {answer[:40]}"


def expand_category_name(key: str) -> str:
    """${VAR} を含むカテゴリ名を .env の値で展開して返す。"""
    expanded = _expand_env(key)
    return expanded if "${" not in expanded else f"{key}（未設定）"


def read_category_keywords(text: str, key: str) -> list[str]:
    """categories.yml の指定カテゴリのキーワードを、書かれている順で返す。"""
    lines = text.splitlines()
    bounds = _section_bounds(lines, key)
    if bounds is None:
        return []
    start, end = bounds
    values = [_keyword_value(line) for line in lines[start:end]]
    return [v for v in values if v]


def _format_keyword(keyword: str) -> str:
    """キーワードを YAML の1行に整える（記号で始まる語はクォートする）。"""
    if keyword.startswith(("!", "#", "&", "*", "-", "?", "@", "`")) or ":" in keyword:
        escaped = keyword.replace('"', '\\"')
        return f'  - "{escaped}"'
    return f"  - {keyword}"


def update_category_keywords(text: str, key: str,
                             keep: list[str], add: list[str] | None = None) -> str:
    """カテゴリのキーワードを更新する（keep に無い行を消し、add を末尾に足す）。

    コメント行と空行はそのまま残すため、分類の説明が失われない。
    """
    lines = text.splitlines()
    bounds = _section_bounds(lines, key)
    if bounds is None:
        return text
    start, end = bounds
    keep_set = set(keep)
    body: list[str] = []
    for line in lines[start:end]:
        value = _keyword_value(line)
        if value is None:
            body.append(line)      # コメント・空行は保持
        elif value in keep_set:
            body.append(line)      # 残す語は元の書き方のまま
    while body and not body[-1].strip():
        body.pop()
    existing = set(read_category_keywords(text, key))
    for keyword in add or []:
        if keyword and keyword not in existing:
            body.append(_format_keyword(keyword))
    body.append("")
    return "\n".join(lines[:start] + body + lines[end:]) + ("\n" if text.endswith("\n") else "")


def sync_category_names(plans: list[ChannelPlan], path: Path | None = None) -> tuple[str, list[str]]:
    """チャンネルの name と categories.yml のキーを揃えたテキストを返す。

    変数方式（use_category_var）のチャンネルについて、categories.yml のキーを
    `${CATEGORY_*}` へ書き換える。定義が無いカテゴリは空の枠を追加する。
    戻り値は (書き換え後のテキスト, 変更内容の説明).
    """
    path = path or CATEGORIES_FILE
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    existing = category_keys(path)
    notes: list[str] = []
    for plan in plans:
        if not plan.use_category_var:
            continue
        if plan.name_ref in existing:
            continue
        if plan.name in existing:
            text = rename_category_key(text, plan.name, plan.name_ref)
            notes.append(f"{plan.name} → {plan.name_ref} に変数化")
    return text, notes


# ===========================================================
# 設定の全体像 / Configuration overview
# ===========================================================

def channel_summary(existing: ExistingConfig | None) -> list[dict]:
    """チャンネル一覧を画面表示用に整える。"""
    if existing is None:
        return []
    rows = []
    for channel in existing.all_channels:
        name = str(channel.get("name") or "")
        if channel.get("digest"):
            kind = "ダイジェスト"
            target = "天気＋各チャンネルのまとめ"
        elif channel.get("source_groups"):
            kind = "フィード指定"
            target = "、".join(str(g) for g in channel["source_groups"])
        else:
            cats = channel.get("categories") or [name]
            kind = "カテゴリ配信"
            target = "、".join(_expand_env(str(c)) for c in cats)
        extras = []
        if channel.get("priority"):
            extras.append("独占")
        if channel.get("defers_to"):
            extras.append("譲る→" + "、".join(str(x) for x in channel["defers_to"]))
        if channel.get("min_japanese") is not None:
            extras.append(f"日本語下限{channel['min_japanese']}")
        rows.append({
            "チャンネル名": _expand_env(name),
            "種類": kind,
            "送るもの": target,
            "追加の設定": "、".join(extras) or "—",
            "スペース変数": str(channel.get("webex_space_id") or ""),
        })
    return rows


_GRAPH_NODE_STYLE = ('  node [shape=box style="rounded,filled" fontname="Helvetica" '
                     'fillcolor="#2b2b2b" fontcolor="#eeeeee" color="#666666"];')
_GRAPH_EDGE_STYLE = ('  edge [color="#888888" fontcolor="#aaaaaa" '
                     'fontname="Helvetica" fontsize=10];')


def routing_graph(existing: ExistingConfig | None) -> str:
    """チャンネル間の記事の流れを DOT 形式で返す（優先独占と譲渡）。"""
    if existing is None:
        return ""
    lines = ["digraph routing {", "  rankdir=LR;", "  bgcolor=transparent;",
             _GRAPH_NODE_STYLE, _GRAPH_EDGE_STYLE]
    for channel in existing.all_channels:
        name = _expand_env(str(channel.get("name") or ""))
        label = name
        if channel.get("digest"):
            label += "\\n(ダイジェスト)"
        elif channel.get("priority"):
            label += "\\n(独占)"
        lines.append(f'  "{name}" [label="{label}"];')
    for channel in existing.all_channels:
        source = _expand_env(str(channel.get("name") or ""))
        for target in (channel.get("defers_to") or []):
            lines.append(f'  "{source}" -> "{_expand_env(str(target))}" [label="譲る"];')
    lines.append("}")
    return "\n".join(lines)


def category_summary() -> list[dict]:
    """カテゴリごとのキーワード数を返す（非公開ファイル分も合算して示す）。"""
    text = read_text_safely(CATEGORIES_FILE)
    private = private_category_counts()
    rows = []
    for key in category_keys():
        words = read_category_keywords(text, key)
        must = [w for w in words if w.startswith("!")]
        # 表の列で型が混ざると描画に失敗するため、すべて文字列で返す
        rows.append({
            "カテゴリ": _expand_env(key),
            "必須語": str(len(must)),
            "通常語": str(len(words) - len(must)),
            "非公開ファイル": str(private[key]) if private.get(key) else "—",
        })
    return rows


# ===========================================================
# 地域バランス（regions.yml）/ Region balance for the digest
# ===========================================================

REGIONS_FILE = REPO_ROOT / "regions.yml"
DEFAULT_QUOTA = {"japan": 7, "us": 3, "other": 5}


def load_regions() -> dict:
    """regions.yml を読み込む。無い・壊れている場合は既定値を返す。"""
    import yaml

    empty = {"quota": dict(DEFAULT_QUOTA), "keywords": {"us": [], "other": []}}
    text = read_text_safely(REGIONS_FILE)
    if not text:
        return empty
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError:
        return empty
    if not isinstance(data, dict):
        return empty
    quota = {**DEFAULT_QUOTA, **(data.get("quota") or {})}
    keywords = data.get("keywords") or {}
    return {
        "quota": {k: int(v) for k, v in quota.items() if str(v).lstrip("-").isdigit()},
        "keywords": {"us": [str(x) for x in (keywords.get("us") or [])],
                     "other": [str(x) for x in (keywords.get("other") or [])]},
    }


def build_regions_text(quota: dict[str, int], us: list[str], other: list[str]) -> str:
    """regions.yml の内容を組み立てる。"""
    lines = [
        "# ============================================================",
        "# regions.yml  —  時事ダイジェストの地域バランス",
        "#",
        "# デイリーダイジェストの「時事ダイジェスト」枠で、一般ニュースが",
        "# 特定の地域（特に米国発）に偏らないよう件数を配分するための設定。",
        "# このファイルが無い場合は、従来の「日本のニュース（最低5件）」枠になる。",
        "# ============================================================",
        "",
        "quota:",
        f"  japan: {quota.get('japan', 7)}    # 日本国内。不足分の補充はここを最優先",
        f"  us: {quota.get('us', 3)}       # 米国。ここで指定した件数を超えて補充しない",
        f"  other: {quota.get('other', 5)}    # 米国以外の外国",
        "",
        "keywords:",
        "  # 記事がどの地域かを判定する語。どれにも当たらない日本語記事は「日本」とみなす。",
        "  us:",
    ]
    lines.extend(f"    - {word}" for word in us)
    lines.append("  other:")
    lines.extend(f"    - {word}" for word in other)
    return "\n".join(lines).rstrip() + "\n"


# ===========================================================
# 自動実行 / Scheduling the daily run
# ===========================================================

SCHEDULE_LABEL = "com.webex-news.rssbot"      # macOS の launchd ラベル
SCHEDULE_TASK_NAME = "rss-bot daily"          # Windows のタスク名
WEEKDAY_LABELS = ["月", "火", "水", "木", "金", "土", "日"]
_MAC_WEEKDAY = {0: 1, 1: 2, 2: 3, 3: 4, 4: 5, 5: 6, 6: 0}   # 月=1 … 日=0
_WIN_WEEKDAY = {0: "MON", 1: "TUE", 2: "WED", 3: "THU", 4: "FRI", 5: "SAT", 6: "SUN"}


def _plist_path() -> Path:
    """macOS で plist を置く場所。"""
    return Path.home() / "Library" / "LaunchAgents" / f"{SCHEDULE_LABEL}.plist"


def runner_path() -> Path:
    """定時実行から呼ぶラッパーのパス（OS ごとに違う）。"""
    return REPO_ROOT / ("run_rssbot.bat" if platform.system() == "Windows" else "run_rssbot.sh")


def ensure_runner() -> tuple[bool, str]:
    """ラッパーを用意する。無ければ雛形から作り、実行できるようにする。"""
    runner = runner_path()
    if runner.exists():
        if platform.system() != "Windows":
            runner.chmod(runner.stat().st_mode | 0o111)
        return True, f"{runner.name} を使います"
    template = REPO_ROOT / "run_rssbot.sh.example"
    if platform.system() == "Windows" or not template.exists():
        return False, f"{runner.name} が見つかりません（リポジトリが壊れている可能性があります）"
    try:
        shutil.copyfile(template, runner)
        runner.chmod(0o755)
    except OSError as exc:
        return False, f"{runner.name} を作成できません: {exc}"
    return True, f"{runner.name} を雛形から作成しました"


def build_plist(hour: int, minute: int, weekdays: list[int]) -> str:
    """launchd 用の plist を組み立てる。"""
    entries = "\n".join(
        f"        <dict><key>Weekday</key><integer>{_MAC_WEEKDAY[d]}</integer>"
        f"<key>Hour</key><integer>{hour}</integer>"
        f"<key>Minute</key><integer>{minute}</integer></dict>"
        for d in sorted(weekdays))
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{SCHEDULE_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>{runner_path()}</string>
    </array>
    <key>StartCalendarInterval</key>
    <array>
{entries}
    </array>
    <key>WorkingDirectory</key>
    <string>{REPO_ROOT}</string>
    <key>StandardErrorPath</key>
    <string>{REPO_ROOT / "log" / "launchd_boot_err.log"}</string>
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
"""


def _run(command: list[str]) -> tuple[bool, str]:
    """外部コマンドを実行し、(成否, 出力) を返す。"""
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    output = (done.stdout + done.stderr).strip()
    return done.returncode == 0, output


def install_schedule(hour: int, minute: int, weekdays: list[int]) -> tuple[bool, str]:
    """毎朝の自動実行を登録する（macOS: launchd / Windows: タスクスケジューラ）。"""
    if not weekdays:
        return False, "実行する曜日を1つ以上選んでください"
    ok, message = ensure_runner()
    if not ok:
        return False, message

    if platform.system() == "Windows":
        days = ",".join(_WIN_WEEKDAY[d] for d in sorted(weekdays))
        ok, output = _run(["schtasks", "/Create", "/TN", SCHEDULE_TASK_NAME,
                           "/TR", f'"{runner_path()}"', "/SC", "WEEKLY",
                           "/D", days, "/ST", f"{hour:02d}:{minute:02d}", "/F"])
        return ok, output or ("登録しました" if ok else "登録に失敗しました")

    path = _plist_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(build_plist(hour, minute, weekdays), encoding="utf-8")
    except OSError as exc:
        return False, f"plist を書き込めません: {exc}"
    _run(["launchctl", "unload", str(path)])
    ok, output = _run(["launchctl", "load", str(path)])
    return ok, output or ("登録しました" if ok else "launchctl load に失敗しました")


def remove_schedule() -> tuple[bool, str]:
    """登録した自動実行を解除する。"""
    if platform.system() == "Windows":
        ok, output = _run(["schtasks", "/Delete", "/TN", SCHEDULE_TASK_NAME, "/F"])
        return ok, output or ("解除しました" if ok else "解除できませんでした")
    path = _plist_path()
    _run(["launchctl", "unload", str(path)])
    try:
        if path.exists():
            path.unlink()
    except OSError as exc:
        return False, f"plist を削除できません: {exc}"
    return True, "解除しました"


def schedule_status() -> tuple[bool, str]:
    """いま自動実行が登録されているかを調べる。"""
    if platform.system() == "Windows":
        ok, output = _run(["schtasks", "/Query", "/TN", SCHEDULE_TASK_NAME])
        return ok, output if ok else "登録されていません"
    path = _plist_path()
    if not path.exists():
        return False, "登録されていません"
    ok, output = _run(["launchctl", "list", SCHEDULE_LABEL])
    if ok:
        return True, f"登録済みです（{path.name}）"
    return False, f"plist はありますが、読み込まれていません（{path}）"


def run_schedule_now() -> tuple[bool, str]:
    """登録した処理をいますぐ1回実行する（動作確認用）。"""
    if platform.system() == "Windows":
        return _run(["schtasks", "/Run", "/TN", SCHEDULE_TASK_NAME])
    return _run(["launchctl", "start", SCHEDULE_LABEL])


def describe_schedule(hour: int, minute: int, weekdays: list[int]) -> str:
    """設定内容を日本語1行で説明する。"""
    if not weekdays:
        return "曜日が選ばれていません"
    if sorted(weekdays) == [0, 1, 2, 3, 4]:
        days = "平日（月〜金）"
    elif len(weekdays) == 7:
        days = "毎日"
    else:
        days = "・".join(WEEKDAY_LABELS[d] for d in sorted(weekdays))
    return f"{days} の {hour:02d}:{minute:02d} に実行します"


# ===========================================================
# ステップ7: 動作確認 / Step 7: dry run
# ===========================================================

def run_dry_run(python_path: Path, hours: int = 24, timeout: int = 900) -> tuple[bool, str]:
    """--dry-run を実行し、(成否, 出力) を返す。"""
    script = REPO_ROOT / "webex-news-rss-bot.py"
    try:
        done = subprocess.run(
            [str(python_path), str(script), "--dry-run", "--hours", str(hours)],
            capture_output=True, text=True, timeout=timeout, cwd=str(REPO_ROOT),
        )
    except subprocess.TimeoutExpired:
        return False, f"{timeout} 秒以内に終わりませんでした。"
    except OSError as exc:
        return False, f"実行できませんでした: {exc}"
    output = done.stdout + ("\n" + done.stderr if done.stderr else "")
    return done.returncode == 0, output
