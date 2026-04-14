#!/usr/bin/env python3
"""
SQL Server → Firestore 同期スクリプト
対象: 事業所マスタ (offices) および 利用者マスタ (patients)

使用方法:
    python sync_to_firestore.py [--office A000010558] [--dry-run]

環境変数 (.env または シェル):
    DB_SERVER    SQL Server ホスト名
    DB_NAME      データベース名
    DB_USER      ユーザー名
    DB_PASSWORD  パスワード
    FIREBASE_CREDENTIALS  サービスアカウントキーのパス (デフォルト: serviceAccountKey.json)
    FIREBASE_PROJECT      Firebase プロジェクトID (省略時はキーファイルから自動取得)
"""

import os
import sys
import json
import logging
import argparse
from datetime import datetime, timezone
from pathlib import Path

# --- サードパーティライブラリ (requirements.txt 参照) ---
try:
    import pyodbc
except ImportError:
    sys.exit("ERROR: pyodbc が未インストールです。pip install pyodbc を実行してください。")

try:
    import firebase_admin
    from firebase_admin import credentials, firestore
except ImportError:
    sys.exit("ERROR: firebase-admin が未インストールです。pip install firebase-admin を実行してください。")

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv は任意

# ─────────────────────────────────────────────
# ログ設定
# ─────────────────────────────────────────────
LOG_FILE = Path(__file__).parent / "sync.log"
_handlers = [logging.StreamHandler(sys.stdout)]
try:
    _handlers.insert(0, logging.FileHandler(LOG_FILE, encoding="utf-8"))
except OSError as e:
    print(f"[WARN] sync.log を開けないため標準出力のみで継続します: {e}", file=sys.stderr)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=_handlers,
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# 設定
# ─────────────────────────────────────────────
DB_CONFIG = {
    "server":   os.environ.get("DB_SERVER",   "kenhlcsql02.database.windows.net"),
    "database": os.environ.get("DB_NAME",     "kenhlcsdb02"),
    "username": os.environ.get("DB_USER",     "sqladmin"),
    "password": os.environ.get("DB_PASSWORD", ""),  # 環境変数から取得推奨
}

FIREBASE_CRED_PATH = os.environ.get("FIREBASE_CREDENTIALS", "serviceAccountKey.json")
FIREBASE_PROJECT   = os.environ.get("FIREBASE_PROJECT", None)

# Firestore バッチ書き込みの上限 (500件/バッチ)
BATCH_SIZE = 400

# ─────────────────────────────────────────────
# SQL クエリ
# ─────────────────────────────────────────────
QUERY_OFFICES = """
SELECT
    c.center_cd,
    c.name AS office_name
FROM center c
WHERE c.temp_flg = '0'
{office_filter}
ORDER BY c.center_cd
"""

QUERY_PATIENTS = """
SELECT
    c.center_cd,
    c.name       AS office_name,
    u.USER_ID,
    {patient_member_no_select},
    u.FAMILY_NAME,
    u.FIRST_NAME,
    u.FAMILY_NAME_KANA,
    u.FIRST_NAME_KANA
FROM center c
JOIN user_by_office ubo
    ON  c.center_cd  = ubo.center_cd
    AND ubo.deleted_at IS NULL
JOIN HLC_MST_USR u
    ON  ubo.user_id = u.USER_ID
    AND (u.DELETE_FLG = 0 OR u.DELETE_FLG IS NULL)
WHERE c.temp_flg = '0'
{office_filter}
ORDER BY c.center_cd, u.USER_ID
"""

QUERY_STAFF = """
SELECT
    c.center_cd,
    c.name         AS office_name,
    e.USER_ID,
    {staff_member_no_select},
    u.FAMILY_NAME,
    u.FIRST_NAME,
    u.FAMILY_NAME_KANA,
    u.FIRST_NAME_KANA,
    lic.LICENSE_NAME
FROM center c
JOIN HLC_MST_EMP e
    ON  c.dept_cd = e.DEPT_CD
    AND e.DELETE_FLG = 0
    AND e.EMPLOYED_FLG = 1
JOIN HLC_MST_USR u
    ON  e.USER_ID = u.USER_ID
    AND (u.DELETE_FLG = 0 OR u.DELETE_FLG IS NULL)
LEFT JOIN (
    SELECT q.USER_ID,
           MIN(lic2.LICENSE_NAME) AS LICENSE_NAME
    FROM HLC_TBL_QUALIFICATION q
    JOIN HLC_MST_LICENSE lic2 ON q.LICENSE_CD = lic2.LICENSE_CD
    GROUP BY q.USER_ID
) lic ON e.USER_ID = lic.USER_ID
WHERE c.temp_flg = '0'
{office_filter}
ORDER BY c.center_cd, u.FAMILY_NAME
"""


# ─────────────────────────────────────────────
# SQL Server 接続
# ─────────────────────────────────────────────
def get_db_connection():
    """pyodbc で SQL Server に接続して返す。"""
    # Linux: ODBC Driver 17 or 18 for SQL Server が必要
    drivers = [
        "ODBC Driver 18 for SQL Server",
        "ODBC Driver 17 for SQL Server",
        "FreeTDS",
    ]
    driver = None
    available = [d for d in pyodbc.drivers()]
    for d in drivers:
        if d in available:
            driver = d
            break

    if driver is None:
        raise RuntimeError(
            f"SQL Server 用 ODBC ドライバが見つかりません。利用可能: {available}\n"
            "インストール方法: https://learn.microsoft.com/ja-jp/sql/connect/odbc/linux-mac/installing-the-microsoft-odbc-driver-for-sql-server"
        )

    conn_str = (
        f"DRIVER={{{driver}}};"
        f"SERVER={DB_CONFIG['server']};"
        f"DATABASE={DB_CONFIG['database']};"
        f"UID={DB_CONFIG['username']};"
        f"PWD={DB_CONFIG['password']};"
        "Encrypt=yes;"
        "TrustServerCertificate=no;"
        "Connection Timeout=30;"
    )
    logger.info(f"SQL Server 接続中: {DB_CONFIG['server']} / {DB_CONFIG['database']}")
    return pyodbc.connect(conn_str)


def get_table_columns(cursor, table_name: str) -> set[str]:
    """指定テーブルのカラム名セットを返す。"""
    cursor.execute(
        """
        SELECT COLUMN_NAME
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = ?
        """,
        (table_name,),
    )
    return {str(row.COLUMN_NAME).upper() for row in cursor.fetchall()}


def build_optional_column_select(alias: str, output_name: str, available_columns: set[str], candidates: list[str]) -> str:
    """存在する候補カラムから SELECT 句を組み立てる。"""
    existing = [f"CAST({alias}.{name} AS NVARCHAR(255))" for name in candidates if name.upper() in available_columns]
    if not existing:
        return f"CAST(NULL AS NVARCHAR(255)) AS {output_name}"
    if len(existing) == 1:
        return f"{existing[0]} AS {output_name}"
    return f"COALESCE({', '.join(existing)}) AS {output_name}"


def normalize_member_no(value) -> str:
    """会員番号の揺れを吸収して文字列化する。"""
    if value is None:
        return ""
    return str(value).strip()


def normalize_office_name(value) -> str:
    """事業所名の先頭装飾を除去して比較可能な形にする。"""
    s = str(value or "").strip()
    while s[:1] in {"※", "＊", "*"}:
        s = s[1:].lstrip()
    return s


def build_sync_key(center_cd: str, user_id: str) -> str:
    """システム間で不変な同期キー。"""
    return f"{center_cd}_{user_id}"


def load_existing_docs(col) -> tuple[dict[str, dict], dict[tuple[str, str], str], dict[tuple[str, str], str]]:
    """
    既存ドキュメントを読み込み、doc_id と user_id/member_no インデックスを返す。
    戻り値:
      - docs_by_id: doc_id -> dict
      - docs_by_user_key: (center_cd, user_id) -> doc_id
      - docs_by_member_key: (center_cd, member_no) -> doc_id
    """
    docs_by_id = {}
    docs_by_user_key = {}
    docs_by_member_key = {}
    docs_by_office_name_key = {}
    docs_by_sync_key = {}

    for snap in col.stream():
        data = snap.to_dict() or {}
        docs_by_id[snap.id] = data

        center_cd = str(data.get("center_cd") or "").strip()
        user_id = str(data.get("user_id") or "").strip()
        member_no = normalize_member_no(data.get("member_no"))
        office = normalize_office_name(data.get("office"))
        name = str(data.get("name") or "").strip()
        sync_key = str(data.get("sync_key") or "").strip()

        if center_cd and user_id:
            docs_by_user_key[(center_cd, user_id)] = snap.id
            docs_by_sync_key[build_sync_key(center_cd, user_id)] = snap.id
        if center_cd and member_no:
            docs_by_member_key[(center_cd, member_no)] = snap.id
        if office and name:
            docs_by_office_name_key[(office, name)] = snap.id
        if sync_key:
            docs_by_sync_key[sync_key] = snap.id

    return docs_by_id, docs_by_user_key, docs_by_member_key, docs_by_office_name_key, docs_by_sync_key


def pick_patient_doc_id(center_cd: str, user_id: str, member_no: str,
                        docs_by_user_key: dict[tuple[str, str], str],
                        docs_by_member_key: dict[tuple[str, str], str],
                        office_name: str,
                        full_name: str,
                        docs_by_office_name_key: dict[tuple[str, str], str],
                        docs_by_sync_key: dict[str, str]) -> str:
    """利用者の安定キーから Firestore doc_id を選ぶ。"""
    sync_key = build_sync_key(center_cd, user_id)
    existing_sync_doc = docs_by_sync_key.get(sync_key)
    if existing_sync_doc:
        return existing_sync_doc

    existing_user_doc = docs_by_user_key.get((center_cd, user_id))
    if existing_user_doc:
        return existing_user_doc

    if member_no:
        existing_member_doc = docs_by_member_key.get((center_cd, member_no))
        if existing_member_doc:
            return existing_member_doc

    existing_legacy_doc = docs_by_office_name_key.get((normalize_office_name(office_name), full_name))
    if existing_legacy_doc:
        return existing_legacy_doc
    return sync_key


def merge_patient_preserved_fields(existing_doc: dict | None, synced_doc: dict) -> dict:
    """承認アプリ側で管理している項目は同期時に引き継ぐ。"""
    if not existing_doc:
        return synced_doc

    preserved_fields = (
        "room",
        "floor",
        "patterns",
    )
    merged = dict(synced_doc)
    for field in preserved_fields:
        if field in existing_doc and existing_doc[field] not in (None, ""):
            merged[field] = existing_doc[field]

    # 承認アプリで編集中(kana_modified=true)の間だけ、ふりがなを保護する。
    # 通常は SQL Server を正として同期結果を反映する。
    if existing_doc.get("kana_modified"):
        merged["kana_modified"] = True
        for field in ("family_name_kana", "first_name_kana", "full_name_kana"):
            if field in existing_doc and existing_doc[field] not in (None, ""):
                merged[field] = existing_doc[field]
    return merged


def docs_equal_ignoring_updated_at(existing_doc: dict | None, new_doc: dict) -> bool:
    """updatedAt を除いて同値なら True。"""
    if not existing_doc:
        return False

    def strip_updated_at(doc: dict) -> dict:
        return {k: v for k, v in doc.items() if k != "updatedAt"}

    return strip_updated_at(existing_doc) == strip_updated_at(new_doc)


# ─────────────────────────────────────────────
# Firebase 初期化
# ─────────────────────────────────────────────
def init_firebase(cred_path: str, project_id: str | None = None):
    """Firebase Admin SDK を初期化して Firestore クライアントを返す。"""
    cred_file = Path(cred_path)
    if not cred_file.exists():
        raise FileNotFoundError(
            f"サービスアカウントキーが見つかりません: {cred_file.resolve()}\n"
            "Firebase コンソール → プロジェクトの設定 → サービスアカウント → 新しい秘密鍵の生成"
        )

    cred = credentials.Certificate(str(cred_file))
    kwargs = {}
    if project_id:
        kwargs["project"] = project_id

    firebase_admin.initialize_app(cred, kwargs)
    logger.info(f"Firebase 初期化完了: {cred_file.name}")
    return firestore.client()


# ─────────────────────────────────────────────
# 同期ロジック
# ─────────────────────────────────────────────
def sync_offices(cursor, db: firestore.Client, office_filter: str, dry_run: bool) -> set:
    """事業所マスタを offices コレクションへ同期。同期済みの center_cd セットを返す。"""
    query = QUERY_OFFICES.format(office_filter=office_filter)
    cursor.execute(query)
    rows = cursor.fetchall()
    logger.info(f"事業所マスタ取得: {len(rows)} 件")

    now = datetime.now(timezone.utc)
    synced_ids = set()
    col = db.collection("offices")
    existing_docs = {snap.id: (snap.to_dict() or {}) for snap in col.stream()}
    write_count = 0
    skip_count = 0

    for i in range(0, len(rows), BATCH_SIZE):
        batch = db.batch()
        chunk = rows[i : i + BATCH_SIZE]
        batch_writes = 0
        for row in chunk:
            center_cd   = str(row.center_cd).strip()
            office_name = normalize_office_name(row.office_name)
            doc_id = center_cd

            doc = {
                "center_cd":   center_cd,
                "name":        office_name,
            }
            synced_ids.add(doc_id)
            if docs_equal_ignoring_updated_at(existing_docs.get(doc_id), doc):
                skip_count += 1
                continue

            doc["updatedAt"] = now
            if not dry_run:
                batch.set(col.document(doc_id), doc)
                batch_writes += 1
            write_count += 1

        if not dry_run and batch_writes > 0:
            batch.commit()
        logger.info(f"  offices バッチ書き込み: {i + 1}〜{i + len(chunk)} 件")

    logger.info(f"  offices 変更あり: {write_count} 件 / 変更なし: {skip_count} 件")

    return synced_ids


def sync_patients(cursor, db: firestore.Client, office_filter: str, dry_run: bool) -> set:
    """利用者マスタを patients コレクションへ同期。同期済みのドキュメントID セットを返す。"""
    user_columns = get_table_columns(cursor, "HLC_MST_USR")
    patient_member_no_select = build_optional_column_select(
        "u",
        "MEMBER_NO",
        user_columns,
        ["MEMBER_NO", "KAIIN_NO", "MEMBER_NUMBER"],
    )
    query = QUERY_PATIENTS.format(
        office_filter=office_filter,
        patient_member_no_select=patient_member_no_select,
    )
    cursor.execute(query)
    rows = cursor.fetchall()
    logger.info(f"利用者マスタ取得: {len(rows)} 件")

    now = datetime.now(timezone.utc)
    synced_ids = set()
    col = db.collection("patients")
    docs_by_id, docs_by_user_key, docs_by_member_key, docs_by_office_name_key, docs_by_sync_key = load_existing_docs(col)
    write_count = 0
    skip_count = 0

    for i in range(0, len(rows), BATCH_SIZE):
        batch = db.batch()
        chunk = rows[i : i + BATCH_SIZE]
        batch_writes = 0
        for row in chunk:
            center_cd        = str(row.center_cd).strip()
            user_id          = str(row.USER_ID).strip()
            member_no        = normalize_member_no(getattr(row, "MEMBER_NO", None))
            family_name      = str(row.FAMILY_NAME or "").strip()
            first_name       = str(row.FIRST_NAME or "").strip()
            family_name_kana = str(row.FAMILY_NAME_KANA or "").strip()
            first_name_kana  = str(row.FIRST_NAME_KANA or "").strip()
            office_name_raw  = str(row.office_name or "").strip()
            office_name      = normalize_office_name(office_name_raw)
            full_name        = f"{family_name} {first_name}".strip()
            sync_key         = build_sync_key(center_cd, user_id)

            doc_id = pick_patient_doc_id(
                center_cd, user_id, member_no,
                docs_by_user_key, docs_by_member_key,
                office_name, full_name, docs_by_office_name_key, docs_by_sync_key
            )

            doc = {
                "center_cd":        center_cd,
                "user_id":          user_id,
                "member_no":        member_no,
                "sync_key":         sync_key,
                "master_key":       sync_key,
                "family_name":      family_name,
                "first_name":       first_name,
                "family_name_kana": family_name_kana,
                "first_name_kana":  first_name_kana,
                "full_name":        full_name,
                "full_name_kana":   f"{family_name_kana} {first_name_kana}".strip(),
                "office_name":      office_name,
                "name":             full_name,
                "office":           office_name,
            }
            doc = merge_patient_preserved_fields(docs_by_id.get(doc_id), doc)
            synced_ids.add(doc_id)

            if docs_equal_ignoring_updated_at(docs_by_id.get(doc_id), doc):
                skip_count += 1
            else:
                doc["updatedAt"] = now
                if not dry_run:
                    batch.set(col.document(doc_id), doc)
                    batch_writes += 1
                write_count += 1

            docs_by_id[doc_id] = doc
            docs_by_user_key[(center_cd, user_id)] = doc_id
            docs_by_sync_key[sync_key] = doc_id
            if member_no:
                docs_by_member_key[(center_cd, member_no)] = doc_id
            if office_name and full_name:
                docs_by_office_name_key[(office_name, full_name)] = doc_id

        if not dry_run and batch_writes > 0:
            batch.commit()
        logger.info(f"  patients バッチ書き込み: {i + 1}〜{i + len(chunk)} 件")

    logger.info(f"  patients 変更あり: {write_count} 件 / 変更なし: {skip_count} 件")

    return synced_ids


def sync_staff(cursor, db: firestore.Client, office_filter: str, dry_run: bool) -> set:
    """職員マスタを staffs コレクションへ同期。同期済みのドキュメントID セットを返す。"""
    user_columns = get_table_columns(cursor, "HLC_MST_USR")
    staff_member_no_select = build_optional_column_select(
        "u",
        "MEMBER_NO",
        user_columns,
        ["MEMBER_NO", "KAIIN_NO", "MEMBER_NUMBER"],
    )
    query = QUERY_STAFF.format(
        office_filter=office_filter,
        staff_member_no_select=staff_member_no_select,
    )
    cursor.execute(query)
    rows = cursor.fetchall()
    logger.info(f"職員マスタ取得: {len(rows)} 件")

    now = datetime.now(timezone.utc)
    synced_ids = set()
    col = db.collection("staffs")
    existing_docs = {snap.id: (snap.to_dict() or {}) for snap in col.stream()}
    write_count = 0
    skip_count = 0

    for i in range(0, len(rows), BATCH_SIZE):
        batch = db.batch()
        chunk = rows[i : i + BATCH_SIZE]
        batch_writes = 0
        for row in chunk:
            center_cd        = str(row.center_cd).strip()
            user_id          = str(row.USER_ID).strip()
            member_no        = normalize_member_no(getattr(row, "MEMBER_NO", None))
            sync_key         = build_sync_key(center_cd, user_id)
            family_name      = str(row.FAMILY_NAME or "").strip()
            first_name       = str(row.FIRST_NAME or "").strip()
            family_name_kana = str(row.FAMILY_NAME_KANA or "").strip()
            first_name_kana  = str(row.FIRST_NAME_KANA or "").strip()
            office_name      = normalize_office_name(row.office_name)
            license_name     = str(row.LICENSE_NAME or "").strip()

            doc_id = f"{center_cd}_{user_id}"

            doc = {
                "center_cd":        center_cd,
                "user_id":          user_id,
                "member_no":        member_no,
                "sync_key":         sync_key,
                "master_key":       sync_key,
                "family_name":      family_name,
                "first_name":       first_name,
                "family_name_kana": family_name_kana,
                "first_name_kana":  first_name_kana,
                "full_name":        f"{family_name} {first_name}".strip(),
                "name":             f"{family_name} {first_name}".strip(),
                "office":           office_name,
                "office_name":      office_name,
                "role":             license_name,
            }
            synced_ids.add(doc_id)
            if docs_equal_ignoring_updated_at(existing_docs.get(doc_id), doc):
                skip_count += 1
                continue

            doc["updatedAt"] = now
            if not dry_run:
                batch.set(col.document(doc_id), doc)
                batch_writes += 1
            write_count += 1

        if not dry_run and batch_writes > 0:
            batch.commit()
        logger.info(f"  staffs バッチ書き込み: {i + 1}〜{i + len(chunk)} 件")

    logger.info(f"  staffs 変更あり: {write_count} 件 / 変更なし: {skip_count} 件")

    return synced_ids


def delete_stale(db: firestore.Client, collection: str, synced_ids: set, dry_run: bool):
    """Firestoreに存在するが今回の同期対象に含まれないドキュメントを削除する。"""
    col = db.collection(collection)
    docs = col.stream()
    stale = [d for d in docs if d.id not in synced_ids]

    if not stale:
        logger.info(f"{collection}: 削除対象なし")
        return

    logger.info(f"{collection}: 削除対象 {len(stale)} 件")
    for i in range(0, len(stale), BATCH_SIZE):
        batch = db.batch()
        chunk = stale[i : i + BATCH_SIZE]
        for doc in chunk:
            if not dry_run:
                batch.delete(col.document(doc.id))
            logger.info(f"  削除: {collection}/{doc.id}")
        if not dry_run:
            batch.commit()


# ─────────────────────────────────────────────
# エントリポイント
# ─────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="SQL Server → Firestore 同期")
    parser.add_argument("--office", metavar="CENTER_CD",
                        help="特定の事業所のみ同期 (例: A000010558)。省略時は全事業所。")
    parser.add_argument("--dry-run", action="store_true",
                        help="DBからの読み取りのみ実施し、Firestoreへの書き込み/削除を行わない。")
    parser.add_argument("--no-delete", action="store_true",
                        help="Firestoreの既存ドキュメントを削除しない (upsertのみ)。")
    parser.add_argument("--cred", default=FIREBASE_CRED_PATH,
                        help=f"サービスアカウントキーのパス (デフォルト: {FIREBASE_CRED_PATH})")
    args = parser.parse_args()

    if args.dry_run:
        logger.info("=== DRY RUN モード: Firestore への書き込みは行いません ===")

    # SQL のフィルタ句
    if args.office:
        office_filter = f"AND c.center_cd = '{args.office}'"
        logger.info(f"対象事業所を絞り込み: {args.office}")
    else:
        office_filter = ""
        logger.info("対象事業所: 全事業所")

    start = datetime.now()
    logger.info(f"同期開始: {start.strftime('%Y-%m-%d %H:%M:%S')}")

    conn = None
    try:
        # Firebase 初期化
        db = init_firebase(args.cred, FIREBASE_PROJECT)

        # SQL Server 接続
        conn = get_db_connection()
        cursor = conn.cursor()

        # 事業所同期
        synced_offices = sync_offices(cursor, db, office_filter, args.dry_run)
        logger.info(f"事業所同期完了: {len(synced_offices)} 件")

        # 利用者同期
        synced_patients = sync_patients(cursor, db, office_filter, args.dry_run)
        logger.info(f"利用者同期完了: {len(synced_patients)} 件")

        # 職員同期
        synced_staff = sync_staff(cursor, db, office_filter, args.dry_run)
        logger.info(f"職員同期完了: {len(synced_staff)} 件")

        # 廃止レコードの削除 (全事業所同期時のみ実施)
        if not args.no_delete and not args.office:
            delete_stale(db, "offices",  synced_offices,  args.dry_run)
            delete_stale(db, "patients", synced_patients, args.dry_run)
            delete_stale(db, "staffs",   synced_staff,    args.dry_run)
        elif args.office:
            logger.info("特定事業所指定のため、廃止レコード削除をスキップ")

    except Exception as e:
        logger.exception(f"同期中にエラーが発生しました: {e}")
        sys.exit(1)
    finally:
        if conn:
            conn.close()

    elapsed = datetime.now() - start
    logger.info(f"同期完了: 所要時間 {elapsed.total_seconds():.1f}秒")


if __name__ == "__main__":
    main()

