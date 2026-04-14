# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Project Overview

**承認表 (Shonin-hyo)** is a healthcare scheduling and visit approval system built with vanilla HTML/JavaScript and Firebase. It manages nursing home care schedules, patient/staff rosters, and course assignments with a Linear.app-inspired UI.

The project has two core parts:
1. **Frontend**: Single-page app (`public/index.html`) with vanilla JavaScript, no build step
2. **Backend Sync**: Python script (`scripts/sync_to_firestore.py`) that syncs SQL Server master data (offices, patients, staff) to Firestore nightly

---

## Tech Stack

- **Frontend**: HTML5 + vanilla JavaScript (Tailwind CSS via CDN)
- **Database**: Firebase Firestore (2 projects: staging & production)
- **Hosting**: Firebase Hosting
- **Backend Sync**: Python 3 with `pyodbc`, `firebase-admin`, `python-dotenv`
- **Security Rules**: Firestore (see `firestore.rules`)
- **Data Source**: SQL Server (Azure, HelpCare system)

---

## Key Architectural Patterns

### Frontend State Management
The app uses a **global `state` object** with the following top-level keys:
- `activeOffice`, `activeDay`, `activeCourse` – navigation context
- `officeMaster`, `staffMaster`, `patientMaster` – read-only rosters synced from Firestore
- `officeDetails` – office metadata keyed by name (added for detail views)
- `scheduleRows` – daily schedule data (each row has `_docId` for Firestore ID)
- `courseAssignees` – staff assignments to courses (keyed `{office}|{day}|{tab}|{course}`)
- `modalState`, `staffPicker`, `patientModal`, etc. – UI state for overlays

**Render Pattern**: One `renderApp()` function re-renders the entire app whenever state changes. No component system; HTML is built as template strings in render functions.

### Firestore Collections
- `offices`: `{name, center_cd, updatedAt}`
- `patients`: `{center_cd, user_id, name, office, full_name, office_name, updatedAt, ...}`
- `staffs`: `{center_cd, user_id, name, office, role, full_name, updatedAt, ...}` (role can be empty)
- `schedules`: `{office, day, course, startTime, endTime, room, patient, content, isMultiple, secondaryStaff, _docId}`
- `settings/config`: `{courseNames, courseAssignees, lastUpdate}`

**Key Design Decision**: Uses document IDs like `{center_cd}_{user_id}` for patients/staff to avoid duplicates across offices.

### SQL Server Sync Script
- Connects via ODBC to Azure SQL Server (`kenhlcsql02.database.windows.net / kenhlcsdb02`)
- Extracts data from `center`, `HLC_MST_USR`, `user_by_office`, `HLC_MST_EMP` tables
- Office sync via `center` where `temp_flg='0'`
- Patient sync via `user_by_office.deleted_at IS NULL` (note: `activate` condition was removed to get all users)
- Staff sync via `HLC_MST_EMP.DEPT_CD = center.dept_cd` with `EMPLOYED_FLG=1`
- Includes optional `--dry-run`, `--office`, `--no-delete` flags
- **Critical**: Always reads-only (SELECT only); never modifies SQL Server

---

## Development & Deployment

### Local Frontend Development
```bash
# Serve locally at http://localhost:5000
npx firebase use staging
npx firebase serve --only hosting
```

No build step needed. Edit `public/index.html` directly, refresh browser.

### Firebase CLI & Authentication
```bash
# Login (interactive browser)
npx firebase login --reauth

# Switch between projects
npx firebase use staging
npx firebase use production

# Deploy to current project
npx firebase deploy --only hosting
npx firebase deploy --only firestore:rules
```

### Python Sync Script (Staging Validation)
```bash
# Install dependencies
pip install -r scripts/requirements.txt

# Dry-run (reads only, no writes)
cd scripts
DB_PASSWORD="..." FIREBASE_CREDENTIALS="serviceAccountKey.staging.json" \
  python sync_to_firestore.py --office A000010558 --dry-run

# Full sync for specific office
DB_PASSWORD="..." FIREBASE_CREDENTIALS="serviceAccountKey.staging.json" \
  python sync_to_firestore.py --office A000010558

# Full sync all offices
DB_PASSWORD="..." FIREBASE_CREDENTIALS="serviceAccountKey.json" \
  python sync_to_firestore.py
```

**Firestore Credentials**:
- `scripts/serviceAccountKey.staging.json` – staging
- `scripts/serviceAccountKey.json` – production (never commit these files)

### Deployment Checklist
1. **Staging validation**: Run sync with `--dry-run`, deploy to staging, test UI
2. **Firestore rules**: Before production, update `firestore.rules` to remove `allow read, write: if true;` (see comments in file)
3. **Production**: `firebase use production && firebase deploy`
4. **Secrets**: DB password is never committed; set via shell `DB_PASSWORD=...` or `.env` file (not tracked)

---

## UI/Design Reference

See `DESIGN.md` for:
- Linear.app aesthetic (clean, precision-focused)
- Warm Parchment (#F7F4EE) background + Terracotta (#BE4B20) accent
- Tailwind CSS classes used (no CSS files; all in `public/index.html`)
- Button styles, modal shadows, responsive breakpoints

Key classes used:
- `text-uber-accent`, `bg-uber-accent`, `border-uber` (custom Tailwind theme)
- `italic uppercase` for labels and headings
- `font-black` for weight emphasis
- `hover:bg-uber-secondary` for interactive feedback

---

## Important Files & Their Roles

| File | Purpose |
|------|---------|
| `public/index.html` | Single-page app; all HTML, CSS (Tailwind), and JS in one file (83KB) |
| `public/envConfig.js` | Firebase config (API keys, project IDs). Must be updated from Firebase Console before deployment |
| `firestore.rules` | Firestore security rules; currently allows all reads/writes in dev; must be updated for production |
| `scripts/sync_to_firestore.py` | Master data sync from SQL Server to Firestore; run via cron or CI |
| `scripts/requirements.txt` | Python dependencies: firebase-admin, pyodbc, python-dotenv |
| `firebase.json` | Firebase project config; specifies hosting dir (`public`) and rules files |
| `.firebaserc` | Aliases: `staging → shonin-staging-89db3`, `production → shonin-prod` |

---

## Common Tasks

### Add a New Field to Firestore Synced Data
1. Update SQL query in `sync_to_firestore.py` (e.g., `QUERY_PATIENTS`)
2. Add field to document dict in `sync_staff()`, `sync_patients()`, or `sync_offices()`
3. Test with `--dry-run` and inspect Firestore console
4. Deploy to staging, validate in UI
5. Update production sync script and run against prod Firebase

### Update Firestore Collection Schema
- Edit the Python sync script and test locally with `--office A000010558 --dry-run`
- Deploy updated script
- For breaking changes, consider running a migration script separately

### Deploy a UI Change
1. Edit `public/index.html` (no build needed)
2. Test locally: `npx firebase serve --only hosting`
3. Deploy: `npx firebase deploy --only hosting`
4. Verify at https://shonin-staging-89db3.web.app or production URL

### Troubleshoot Firestore Sync
- Check `scripts/sync.log` for error messages
- Verify DB credentials: `DB_PASSWORD=... python sync_to_firestore.py --office A000010558 --dry-run`
- Check Firestore console for data presence/structure
- Ensure service account key has Firestore write permissions (check Firebase Console → IAM)

---

## Known Limitations & Constraints

1. **Single HTML file**: Entire app is in `public/index.html` (~83KB). Consider splitting if it grows beyond 100KB.
2. **No build step**: All CSS/JS is inline. Minification tools cannot be used; keep performance in mind.
3. **Firestore limits**: Spark plan has 20K writes/day; monitor if sync grows. Consider batching if needed.
4. **SQL Server connectivity**: Requires ODBC driver + network access. Sync must run from a machine with SQL Server access (e.g., Appサーバー).
5. **Activate condition**: `activate='0'` users are now included in sync (condition removed on 2026-04-09). If behavior changes, check `QUERY_PATIENTS` in Python script.
6. **Staff role mapping**: SQL-synced staff have a `role` field that may be empty (no qualifications registered). UI handles this by grouping as "全職員" or "未分類".

---

## Security & Environment

- **Never commit**: `.env`, `serviceAccountKey*.json`, or database passwords
- **Production secrets**: Use environment variables or secure CI/CD secret management
- **Firestore rules**: Current dev rules allow all access. For production, enforce `request.auth != null`
- **Database access**: Read-only SQL user recommended; script never writes to SQL Server
- **API keys**: `envConfig.js` contains Firebase public keys (safe to commit; they're read-only)

---

## References

- **Firebase Docs**: https://firebase.google.com/docs
- **Tailwind CSS**: Classes used in project (theme customized in `<style>` tag inside `public/index.html`)
- **Python Firestore SDK**: https://firebase.google.com/docs/firestore/client/start-python
- **Firestore Constraints**: Max 20K writes/day on Spark plan; document size < 1 MB
- **SQL Server ODBC**: Requires `ODBC Driver 18 for SQL Server` (or 17) on sync machine

---

## Future Enhancements

- Extract `public/index.html` into modular JS files if it exceeds 100KB
- Add unit tests for sync script (pytest)
- Implement Firestore backup/restore procedures
- Monitor Spark plan usage; scale to Blaze if needed
- Automate sync via Cloud Scheduler + Cloud Functions (will require upgrade from Spark)
