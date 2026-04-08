# Firebase セットアップ手順書

## 前提条件
- Node.js がインストール済み
- Google アカウントがある

---

## 1. Firebase CLI のインストール

```bash
npm install -g firebase-tools
firebase login
```

---

## 2. Firebase プロジェクトを 2 つ作成

[Firebase コンソール](https://console.firebase.google.com) で以下の 2 プロジェクトを作成する。

| エイリアス    | プロジェクト名の例             |
|-------------|-------------------------------|
| staging     | `shonin-staging-89db3`        |
| production  | `shonin-prod`                 |

各プロジェクトで **Firestore Database** と **Hosting** を有効化する。
（Firebase Functions は **選択しない**）

---

## 3. envConfig.js の設定値を入力

`public/envConfig.js` の `REPLACE_***` プレースホルダーを
Firebase コンソール → プロジェクト設定 → マイアプリ → SDK の設定と構成 の値で置き換える。

```
staging  → REPLACE_STAGING_*  の 6 項目
production → REPLACE_PRODUCTION_* の 6 項目
```

---

## 4. firebase init（プロジェクトルートで実行）

```bash
cd "G:\マイドライブ\承認表"
firebase init
```

選択項目（スペースキーで選択、Enter で確定）:

```
? Which Firebase features do you want to set up?
  ◉ Firestore: Configure security rules and indexes files
  ◉ Hosting: Configure files for Firebase Hosting

# Functions は絶対に選択しない（Sparkプランを死守するため）
```

続く質問:

```
? Please select an option: Use an existing project
? Select a default Firebase project: shonin-staging-89db3   ← まず staging を選択

? What file should be used for Firestore Rules? firestore.rules   ← そのまま Enter
? What file should be used for Firestore indexes? firestore.indexes.json   ← そのまま Enter

? What do you want to use as your public directory? public   ← そのまま Enter
? Configure as a single-page app? No
? Set up automatic builds and deploys with GitHub? No
```

---

## 5. エイリアス（staging / production）の登録

```bash
# staging を登録（初期化時に選択したプロジェクトが .firebaserc に書き込まれる）
firebase use --add
# → プロジェクト一覧から shonin-staging-89db3 を選択
# → エイリアス名: staging

firebase use --add
# → shonin-prod を選択
# → エイリアス名: production
```

`.firebaserc` が以下のようになれば OK:

```json
{
  "projects": {
    "staging": "shonin-staging-89db3",
    "production": "shonin-prod"
  }
}
```

---

## 6. デプロイコマンド

### ステージングへデプロイ
```bash
firebase use staging
firebase deploy --only hosting,firestore:rules
```

### 本番へデプロイ
```bash
firebase use production
firebase deploy --only hosting,firestore:rules
```

### 本番の Firestore ルールだけ更新
```bash
firebase use production
firebase deploy --only firestore:rules
```

---

## 7. Firestore セキュリティルールの切り替え

`firestore.rules` のコメントを参照して、本番デプロイ前に切り替える。

**開発中（全許可）**
→ そのままでOK

**本番運用時（認証必須）**
→ `firestore.rules` のコメントを参考に `allow read, write: if true;` を削除し
  認証ルールを有効化 → `firebase deploy --only firestore:rules`

---

## 8. Firestore にマスタデータを初期投入（任意）

Firebase コンソール → Firestore Database → データ タブ から手動で入力、
または下記スクリプトで一括投入できる。

コレクション構造:

| コレクション | フィールド例 |
|-------------|-------------|
| `offices`   | `name: "NH南千住"` |
| `staffs`    | `office: "NH南千住", name: "田中花子", role: "看護師"` |
| `patients`  | `office: "NH南千住", room: "101", floor: 1, name: "山田太郎"` |
| `schedules` | `office, day, course, startTime, endTime, room, patient, content, isMultiple, secondaryStaff` |
| `settings`  | ドキュメントID: `config` → `courseNames, courseAssignees, lastUpdate` |

---

## 9. ローカル開発

```bash
firebase use staging
firebase serve --only hosting
# → http://localhost:5000 で確認
```

---

## Spark プランの主な無料枠（2024年時点）

| 項目 | 無料枠 |
|------|--------|
| Firestore 読み取り | 50,000 回/日 |
| Firestore 書き込み | 20,000 回/日 |
| Firestore 削除 | 20,000 回/日 |
| Hosting 帯域幅 | 10 GB/月 |
| Hosting ストレージ | 1 GB |

Firebase Functions は **一切使用しない** ため、クレジットカード登録は不要。
