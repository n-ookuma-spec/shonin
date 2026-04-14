#!/usr/bin/env python3
"""
Firestore → SQL Server 振り仮名書き戻しスクリプト

承認表アプリで編集された振り仮名（kana_modified: true のレコード）を
Firestore から読み取り、SQL Server の HLC_MST_USR に書き戻す。

使用方法:
    python writeback_kana.py [--dry-run] [--office A000010558]   # 一括実行
    python writeback_kana.py --watch                              # リアルタイム監視

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
import signal
import logging
import argparse
import threading
import time
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

# Windows cp932 で emダッシュ等が出力エラーになるのを防ぐ
_stream_handler = logging.StreamHandler(sys.stdout)
_stream_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
if sys.platform == "win32":
    import io
    _stream_handler.stream = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        _stream_handler,
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
    query = db_fs.collection("patients").where(filter=firestore.FieldFilter("kana_modified", "==", True))
    docs = query.stream()
    results = []
    for doc in docs:
        d = doc.to_dict()
        d["_doc_ref"] = doc.reference
        if office_filter and not office_matches(d, office_filter):
            continue
        results.append(d)
    return results


def fetch_modified_staffs(db_fs, office_filter=None):
    """kana_modified: true の職員レコードを返す。"""
    query = db_fs.collection("staffs").where(filter=firestore.FieldFilter("kana_modified", "==", True))
    docs = query.stream()
    results = []
    for doc in docs:
        d = doc.to_dict()
        d["_doc_ref"] = doc.reference
        if office_filter and not office_matches(d, office_filter):
            continue
        results.append(d)
    return results


def office_matches(data: dict, office_filter: str | None) -> bool:
    """office(事業所名) または center_cd のどちらでも絞り込めるようにする。"""
    if not office_filter:
        return True
    office = str(data.get("office") or "").strip()
    center_cd = str(data.get("center_cd") or "").strip()
    return office == office_filter or center_cd == office_filter


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
        logger.warning(f"  USER_ID={user_id} がHLC_MST_USRに見つかりません -スキップ")
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
# レコード単位バックアップ（watchモード用）
# ─────────────────────────────────────────────
BACKUP_SELECT_SQL = """
    SELECT USER_ID, FAMILY_NAME_KANA, FIRST_NAME_KANA
    FROM HLC_MST_USR WHERE USER_ID = ?
"""


def backup_single_record(cursor, user_id):
    """1レコード分の変更前データをログに記録する（watchモード用）。"""
    cursor.execute(BACKUP_SELECT_SQL, (user_id,))
    row = cursor.fetchone()
    if row:
        logger.info(
            f"  変更前: USER_ID={row[0]}  "
            f"姓カナ='{row[1] or ''}'  名カナ='{row[2] or ''}'"
        )


# ─────────────────────────────────────────────
# Watch モード: Firestore on_snapshot リアルタイム監視
# ─────────────────────────────────────────────
class KanaWatcher:
    """Firestoreリスナーで kana_modified: true を即座にSQL Serverへ書き戻す。"""

    def __init__(self, db_fs, office_filter=None):
        self.db_fs = db_fs
        self.office_filter = office_filter
        self._conn = None
        self._lock = threading.Lock()
        self._processed = set()  # 重複処理防止
        self._stop_event = threading.Event()

    def _get_connection(self):
        """SQL Server 接続を取得（切断時は再接続）。"""
        if self._conn is None:
            self._conn = get_db_connection()
            logger.info("SQL Server 接続確立")
        try:
            # 接続が生きているか確認
            self._conn.execute("SELECT 1")
        except Exception:
            logger.warning("SQL Server 接続が切断 -再接続中...")
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = get_db_connection()
            logger.info("SQL Server 再接続完了")
        return self._conn

    def _process_snapshot(self, collection_name, doc_snapshots, changes, read_time):
        """on_snapshot コールバック。変更があったドキュメントを即座に書き戻す。"""
        for change in changes:
            if change.type.name in ("ADDED", "MODIFIED"):
                doc = change.document
                data = doc.to_dict()

                # kana_modified でないものはスキップ
                if not data.get("kana_modified"):
                    continue

                # 事業所フィルター
                if self.office_filter and not office_matches(data, self.office_filter):
                    continue

                doc_id = doc.id
                # 重複処理防止（フラグ削除後の再通知を無視）
                if doc_id in self._processed:
                    continue

                user_id = data.get("user_id") or data.get("USER_ID")
                if not user_id:
                    logger.warning(f"[{collection_name}] {data.get('name')} に user_id なし -スキップ")
                    continue

                family_kana = data.get("family_name_kana", "")
                first_kana = data.get("first_name_kana", "")

                logger.info(
                    f"[WATCH] {collection_name} 変更検知: "
                    f"{data.get('name', '?')} → 姓カナ='{family_kana}' 名カナ='{first_kana}'"
                )

                with self._lock:
                    try:
                        conn = self._get_connection()
                        cursor = conn.cursor()

                        # 変更前データをログに記録（レコード単位バックアップ）
                        backup_single_record(cursor, user_id)

                        # SQL Server 更新
                        ok = writeback_record(cursor, user_id, family_kana, first_kana)
                        if ok:
                            conn.commit()
                            # Firestore のフラグ解除
                            self._processed.add(doc_id)
                            clear_kana_modified(doc.reference)
                            logger.info(f"[WATCH] SQL Server 反映完了: {data.get('name', '?')}")
                        else:
                            conn.rollback()

                        cursor.close()
                    except Exception as e:
                        logger.error(f"[WATCH] 書き戻しエラー: {e}")
                        try:
                            self._conn.rollback()
                        except Exception:
                            pass
                        # 接続を破棄して次回再接続
                        self._conn = None

                # 処理済みセットのクリーンアップ（メモリリーク防止）
                if len(self._processed) > 1000:
                    self._processed.clear()

    def start(self):
        """patients と staffs の on_snapshot リスナーを開始する。"""
        logger.info("=== リアルタイム監視モード開始 ===")
        logger.info("承認表アプリで振り仮名を保存すると即座にSQL Serverへ反映します。")
        logger.info("停止: Ctrl+C")

        if self.office_filter:
            logger.info(f"事業所フィルター: {self.office_filter}")

        # SQL Server 接続を事前確認
        conn = self._get_connection()
        logger.info("SQL Server 接続OK -リスナー開始")

        # Firestore リスナー登録
        patient_query = self.db_fs.collection("patients").where(filter=firestore.FieldFilter("kana_modified", "==", True))
        staff_query = self.db_fs.collection("staffs").where(filter=firestore.FieldFilter("kana_modified", "==", True))

        patient_watch = patient_query.on_snapshot(
            lambda docs, changes, read_time: self._process_snapshot("patients", docs, changes, read_time)
        )
        staff_watch = staff_query.on_snapshot(
            lambda docs, changes, read_time: self._process_snapshot("staffs", docs, changes, read_time)
        )

        # Ctrl+C まで待機
        try:
            while not self._stop_event.is_set():
                self._stop_event.wait(timeout=1)
        except KeyboardInterrupt:
            pass
        finally:
            logger.info("リスナー停止中...")
            patient_watch.unsubscribe()
            staff_watch.unsubscribe()
            if self._conn:
                self._conn.close()
            logger.info("=== リアルタイム監視モード終了 ===")

    def stop(self):
        self._stop_event.set()


# ─────────────────────────────────────────────
# 一括実行モード
# ─────────────────────────────────────────────
def run_batch(db_fs, args):
    """従来の一括書き戻し処理。"""
    patients = fetch_modified_patients(db_fs, office_filter=args.office)
    staffs   = fetch_modified_staffs(db_fs,   office_filter=args.office)

    logger.info(f"修正済みレコード: 利用者 {len(patients)} 件 / 職員 {len(staffs)} 件")

    if not patients and not staffs:
        logger.info("書き戻し対象レコードなし。終了します。")
        return

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        backup_table = backup_kana_table(cursor, dry_run=args.dry_run)
        if not args.dry_run:
            conn.commit()

        patient_ok = patient_ng = 0
        for p in patients:
            user_id = p.get("user_id") or p.get("USER_ID")
            if not user_id:
                logger.warning(f"利用者 {p.get('name')} に user_id なし -スキップ")
                patient_ng += 1
                continue
            ok = writeback_record(
                cursor, user_id,
                p.get("family_name_kana", ""),
                p.get("first_name_kana",  ""),
                dry_run=args.dry_run,
            )
            if ok:
                patient_ok += 1
                clear_kana_modified(p["_doc_ref"], dry_run=args.dry_run)
            else:
                patient_ng += 1

        staff_ok = staff_ng = 0
        for s in staffs:
            user_id = s.get("user_id") or s.get("USER_ID")
            if not user_id:
                logger.warning(f"職員 {s.get('name')} に user_id なし -スキップ")
                staff_ng += 1
                continue
            ok = writeback_record(
                cursor, user_id,
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


# ─────────────────────────────────────────────
# メイン
# ─────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="振り仮名 Firestore→SQL 書き戻しスクリプト")
    parser.add_argument("--dry-run", action="store_true", help="書き込みを行わずに動作確認")
    parser.add_argument("--office", help="特定の事業所コードのみ処理 (例: A000010558)")
    parser.add_argument("--watch", action="store_true",
                        help="リアルタイム監視モード: Firestore変更を即座にSQL Serverへ反映")
    args = parser.parse_args()

    if not DB_CONFIG["password"]:
        sys.exit("ERROR: DB_PASSWORD 環境変数が設定されていません。")

    db_fs = init_firestore()

    if args.watch:
        if args.dry_run:
            sys.exit("ERROR: --watch と --dry-run は同時に使用できません。")
        watcher = KanaWatcher(db_fs, office_filter=args.office)
        signal.signal(signal.SIGINT, lambda *_: watcher.stop())
        signal.signal(signal.SIGTERM, lambda *_: watcher.stop())
        watcher.start()
    else:
        logger.info("=== 振り仮名書き戻し開始 ===")
        if args.dry_run:
            logger.info("*** DRY-RUN モード: DBへの書き込みはスキップされます ***")
        run_batch(db_fs, args)
        logger.info("=== 振り仮名書き戻し完了 ===")


if __name__ == "__main__":
    main()
