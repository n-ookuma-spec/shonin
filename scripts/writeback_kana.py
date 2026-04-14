#!/usr/bin/env python3
"""
Firestore → SQL Server 振り仮名書き戻しスクリプト

承認表アプリで編集された振り仮名（kana_modified: true のレコード）を
Firestore から読み取り、SQL Server の HLC_MST_USR に書き戻す。

使用方法:
    python writeback_kana.py [--dry-run] [--office A000010558]

環境変数 (.env または シェル):
    DB_SERVER    SQL Server ホスト名          (デフォルト: kenhlcsql02.database.windows.net)
    DB_NAME      データベース名                (デフォルト: kenhlcsdb02)
    DB_USER      ユーザー名                   (デフォルト: sqladmin)
    DB_PASSWORD  パスワード
    FIREBASE_CREDENTIALS  サービスアカウントキーのパス (デフォルト: serviceAccountKey.json)
    FIREBASE_PROJECT      Firebase プロジェクトID (省略時はキーファイルから自動取得)
"""

import os
import sys
import logging
import argparse
from datetime import datetime, timezone
from pathlib import Path

# --- サードパーティライブラリ ---
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
    pass

# ─────────────────────────────────────────────
# ログ設定
# ─────────────────────────────────────────────
LOG_FILE = Path(__file__).parent / "writeback_kana.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# 設定
# ─────────────────────────────────────────────
DB_CONFIG = {
    "server":   os.environ.get("DB_SERVER",   "kenhlcsql02.database.windows.net"),
    "database": os.environ.get("DB_NAME",     "kenhlcsdb02"),
    "username": os.environ.get("DB_USER",     "sqladmin"),
    "password": os.environ.get("DB_PASSWORD", ""),
}

FIREBASE_CRED_PATH = os.environ.get("FIREBASE_CREDENTIALS", "serviceAccountKey.json")
FIREBASE_PROJECT   = os.environ.get("FIREBASE_PROJECT", None)


# ─────────────────────────────────────────────
# DB接続
# ─────────────────────────────────────────────
def get_db_connection():
    conn_str = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={DB_CONFIG['server']};"
        f"DATABASE={DB_CONFIG['database']};"
        f"UID={DB_CONFIG['username']};"
        f"PWD={DB_CONFIG['password']};"
        f"Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
    )
    return pyodbc.connect(conn_str)


# ─────────────────────────────────────────────
# バックアップ
# ─────────────────────────────────────────────
def backup_kana_table(cursor, dry_run=False):
    """書き戻し対象レコードのバックアップテーブルを作成する。"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_table = f"HLC_MST_USR_KANA_WRITEBACK_{ts}"
    sql = f"""
        SELECT USER_ID, FAMILY_NAME, FIRST_NAME,
               FAMILY_NAME_KANA, FIRST_NAME_KANA, UPDATE_DATE
        INTO {backup_table}
        FROM HLC_MST_USR
        WHERE FAMILY_NAME_KANA IS NOT NULL OR FIRST_NAME_KANA IS NOT NULL
    """
    if dry_run:
        logger.info(f"[DRY-RUN] バックアップ会スキップ: {backup_table}")
        return backup_table
    cursor.execute(sql)
    logger.info(f"バックアップ作成: {backup_table}")
    return backup_table


# ─────────────────────────────────────────────
# Firestore 初期化
# ─────────────────────────────────────────────
def init_firestore():
    cred_path = Path(__file__).parent / FIREBASE_CRED_PATH
    if not cred_path.exists():
        sys.exit(f"ERROR: Firebase認証ファイルが見つかりません: {cred_path}")

    if not firebase_admin._apps:
        cred = credentials.Certificate(str(cred_path))
        kwargs = {"credential": cred}
        if FIREBASE_PROJECT:
            kwargs["options"] = {"projectId": FIREBASE_PROJECT}
        firebase_admin.initialize_app(**kwargs)

    return firestore.client()


# ─────────────────────────────────────────────
# Firestore から kana_modified レコードを取得
# ─────────────────────────────────────────────
def fetch_modified_patients(db_fs, office_filter=None):
    """kana_modified: true の利用者レコードを返す。"""
    query = db_fs.collection("patients").where("kana_modified", "==", True)
    docs = query.stream()
    results = []
    for doc in docs:
        d = doc.to_dict()
        d["_doc_ref"] = doc.reference
        if office_filter and d.get("office") != office_filter:
            continue
        results.append(d)
    return results


def fetch_modified_staffs(db_fs, office_filter=None):
    """kana_modified: true の職員レコードを返す。"""
    query = db_fs.collection("staffs").where("kana_modified", "==", True)
    docs = query.stream()
    results = []
    for doc in docs:
        d = doc.to_dict()
        d["_doc_ref"] = doc.reference
        if office_filter and d.get("office") != office_filter:
            continue
        results.append(d)
    return results


# ─────────────────────────────────────────────
# SQL Server への書き戻し
# ─────────────────────────────────────────────
UPDATE_SQL = """
    UPDATE HLC_MST_USR
    SET FAMILY_NAME_KANA = ?,
        FIRST_NAME_KANA  = ?,
        UPDATE_DATE      = GETDATE()
    WHERE USER_ID = ?
"""


def writeback_record(cursor, user_id, family_kana, first_kana, dry_run=False):
    if dry_run:
        logger.info(
            f"[DRY-RUN] UPDATE USER_ID={user_id}  "
            f"FAMILY_NAME_KANA='{family_kana}'  FIRST_NAME_KANA='{first_kana}'"
        )
        return True
    cursor.execute(UPDATE_SQL, (family_kana or "", first_kana or "", user_id))
    rows = cursor.rowcount
    if rows == 0:
        logger.warning(f"  USER_ID={user_id} がHLC_MST_USRに見つかりません — スキップ")
        return False
    logger.info(f"  更新: USER_ID={user_id}  姓カナ='{family_kana}'  名カナ='{first_kana}'")
    return True


# ─────────────────────────────────────────────
# Firestore フラグ解除
# ─────────────────────────────────────────────
def clear_kana_modified(doc_ref, dry_run=False):
    if dry_run:
        logger.info(f"[DRY-RUN] kana_modified フラグ解除: {doc_ref.path}")
        return
    doc_ref.update({"kana_modified": firestore.DELETE_FIELD})


# ─────────────────────────────────────────────
# メイン
# ─────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="振り仮名 Firestore→SQL 書き戻しスクリプト")
    parser.add_argument("--dry-run", action="store_true", help="書き込みを行わずに動作確認")
    parser.add_argument("--office", help="特定の事業所コードのみ処理 (例: A000010558)")
    args = parser.parse_args()

    if not DB_CONFIG["password"]:
        sys.exit("ERROR: DB_PASSWORD 環境変数が設定されていません。")

    logger.info("=== 振り仮名書き戻し開始 ===")
    if args.dry_run:
        logger.info("*** DRY-RUN モード: DBへの書き込みはスキップされます ***")

    # Firestore 初期化
    db_fs = init_firestore()

    # 修正済みレコードを取得
    patients = fetch_modified_patients(db_fs, office_filter=args.office)
    staffs   = fetch_modified_staffs(db_fs,   office_filter=args.office)

    logger.info(f"修正済みレコード: 利用者 {len(patients)} 件 / 職員 {len(staffs)} 件")

    if not patients and not staffs:
        logger.info("書き戻し対象レコードなし。終了します。")
        return

    # SQL Server 接続
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # バックアップ作成（利用者・職員両方がいる場合は1回だけ）
        backup_table = backup_kana_table(cursor, dry_run=args.dry_run)
        if not args.dry_run:
            conn.commit()

        # 利用者の書き戻し
        patient_ok = patient_ng = 0
        for p in patients:
            user_id = p.get("user_id") or p.get("USER_ID")
            if not user_id:
                logger.warning(f"利用者 {p.get('name')} に user_id なし — スキップ")
                patient_ng += 1
                continue
            ok = writeback_record(
                cursor,
                user_id,
                p.get("family_name_kana", ""),
                p.get("first_name_kana",  ""),
                dry_run=args.dry_run,
            )
            if ok:
                patient_ok += 1
                clear_kana_modified(p["_doc_ref"], dry_run=args.dry_run)
            else:
                patient_ng += 1

        # 職員の書き戻し
        staff_ok = staff_ng = 0
        for s in staffs:
            user_id = s.get("user_id") or s.get("USER_ID")
            if not user_id:
                logger.warning(f"職員 {s.get('name')} に user_id なし — スキップ")
                staff_ng += 1
                continue
            ok = writeback_record(
                cursor,
                user_id,
                s.get("family_name_kana", ""),
                s.get("first_name_kana",  ""),
                dry_run=args.dry_run,
            )
            if ok:
                staff_ok += 1
                clear_kana_modified(s["_doc_ref"], dry_run=args.dry_run)
            else:
                staff_ng += 1

        if not args.dry_run:
            conn.commit()
            logger.info("コミット完了")

        logger.info(
            f"結果: 利用者 {patient_ok}件更新 / {patient_ng}件スキップ  "
            f"職員 {staff_ok}件更新 / {staff_ng}件スキップ"
        )
        logger.info(f"バックアップテーブル: {backup_table}")

    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
        if not args.dry_run:
            conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

    logger.info("=== 振り仮名書き戻し完了 ===")


if __name__ == "__main__":
    main()
