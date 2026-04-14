@echo off
chcp 65001 >nul 2>&1
cd /d "G:\マイドライブ\承認表\scripts"
set DB_SERVER=kenhlcsql02.database.windows.net
set DB_NAME=kenhlcsdb02
set DB_USER=sqladmin
set "DB_PASSWORD=Q+4Rbj)g.cV#"
set FIREBASE_CREDENTIALS=serviceAccountKey.json
python writeback_kana.py --watch >> writeback_kana_watch.log 2>&1
