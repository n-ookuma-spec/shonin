# 職員マスタ・利用者マスタ UIブラッシュアップ 実装プラン

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `renderStaffMaster()` と `renderPatientMaster()` を、検索バー・インラインバッジ付きハイブリッドリストに書き換える

**Architecture:** 単一ファイル `public/index.html` 内の2関数を全面書き換え。検索/フィルターは `filterMasterList()` がDOMを直接操作してリアルタイムに絞り込む（全再レンダリングを避けてカーソル位置を保持）。週パターン判定は `hasWeeklyPattern(patient)` ヘルパーが担当。

**Tech Stack:** Vanilla JS / Tailwind CSS CDN（ビルドステップなし）。ローカルテスト: `npx firebase serve --only hosting`

---

## ファイルマップ

| ファイル | 変更 |
|---|---|
| `public/index.html` | `hasWeeklyPattern()` 追加、`getPatientPrimaryCourse()` 追加、`filterMasterList()` 追加、`renderPatientMaster()` 全面書き換え、`renderStaffMaster()` 全面書き換え |

---

## Task 1: ヘルパー関数を追加する

**Files:**
- Modify: `public/index.html` — `function renderStaffPicker()` の直前に追加（line 298 付近）

- [ ] **Step 1: `hasWeeklyPattern` と `getPatientPrimaryCourse` を挿入する**

`function renderStaffPicker()` の直前の行を探し、その前に以下を追加する。

```js
    function hasWeeklyPattern(patient) {
      if (!patient || !patient.patterns) return false;
      return state.daysOfWeek.some(day => {
        const entries = patient.patterns[day];
        return Array.isArray(entries) && entries.some(e => e.enabled && e.course);
      });
    }

    function getPatientPrimaryCourse(patient) {
      if (!patient || !patient.patterns) return '';
      const counts = {};
      state.daysOfWeek.forEach(day => {
        const entries = patient.patterns[day] || [];
        entries.forEach(e => {
          if (e.enabled && e.course) counts[e.course] = (counts[e.course] || 0) + 1;
        });
      });
      const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]);
      return sorted.length ? sorted[0][0] : '';
    }

    function filterMasterList() {
      const searchEl = document.getElementById('master-search');
      const filterEl = document.getElementById('master-filter');
      const q = (searchEl ? searchEl.value : '').toLowerCase();
      const filterVal = filterEl ? filterEl.value : 'all';
      const rows = document.querySelectorAll('.master-row');
      let visibleCount = 0;
      rows.forEach(row => {
        const name = (row.dataset.name || '').toLowerCase();
        const room = (row.dataset.room || '').toLowerCase();
        const pattern = row.dataset.pattern || '';
        const matchesSearch = !q || name.includes(q) || room.includes(q);
        const matchesFilter =
          filterVal === 'all' ||
          (filterVal === 'unset' && pattern === 'unset') ||
          (filterVal === 'set'   && pattern === 'set');
        const visible = matchesSearch && matchesFilter;
        row.style.display = visible ? '' : 'none';
        if (visible) visibleCount++;
      });
      const counter = document.getElementById('master-count');
      if (counter) counter.textContent = visibleCount + ' / ' + rows.length + '名 表示中';
    }
```

- [ ] **Step 2: ブラウザで構文エラーがないことを確認する**

```
npx firebase serve --only hosting
```

ブラウザのコンソール（F12）を開き、赤いエラーがないことを確認する。

- [ ] **Step 3: コミット**

```bash
cd "G:/マイドライブ/承認表"
git add public/index.html
git commit -m "feat: add hasWeeklyPattern, getPatientPrimaryCourse, filterMasterList helpers"
```

---

## Task 2: `renderPatientMaster()` を書き換える

**Files:**
- Modify: `public/index.html` — `function renderPatientMaster()` (line 908–911)

- [ ] **Step 1: `renderPatientMaster()` を以下のコードで全面置換する**

既存の `function renderPatientMaster() {` から次の `}` までを、以下のコードで置き換える。

```js
    function renderPatientMaster() {
      const allPatients = state.patientMaster
        .filter(p => p.office === state.activeOffice && p.name)
        .sort((a, b) => {
          const ra = parseInt(a.room || '9999', 10);
          const rb = parseInt(b.room || '9999', 10);
          return ra !== rb ? ra - rb : (a.name || '').localeCompare(b.name || '', 'ja');
        });

      const rows = allPatients.map(p => {
        const settled = hasWeeklyPattern(p);
        const course   = getPatientPrimaryCourse(p);
        const patternLabel = settled ? '✓ 設定済' : '⚠ 未設定';
        const patternData  = settled ? 'set' : 'unset';
        const rowBg        = settled ? '' : 'style="background:#fffbeb;"';
        const badgeCls     = settled
          ? 'style="background:#dcfce7;color:#16a34a;padding:2px 8px;font-size:9px;font-weight:900;white-space:nowrap;"'
          : 'style="background:#fef9c3;color:#a16207;padding:2px 8px;font-size:9px;font-weight:900;white-space:nowrap;"';
        const patientJson  = JSON.stringify(p).replace(/"/g, '&quot;');
        return `<div class="master-row" data-name="${(p.name||'').replace(/"/g,'')}" data-room="${p.room||''}" data-pattern="${patternData}" ${rowBg}
          style="display:grid;grid-template-columns:1fr 52px 96px 72px;align-items:center;padding:0 12px;min-height:44px;border-bottom:1px solid #E8E8E8;cursor:pointer;${settled ? '' : 'background:#fffbeb;'}"
          onclick="openPatientModal(${patientJson})"
          onmouseover="if(this.style.background!=='rgb(255,251,235)')this.style.background='#F8F8F8'"
          onmouseout="this.style.background='${settled ? 'white' : '#fffbeb'}'">
          <span style="font-size:13px;font-weight:900;font-style:italic;text-transform:uppercase;">${p.name}</span>
          <span style="font-size:11px;font-family:'DM Mono',monospace;font-weight:700;">${p.room || '—'}</span>
          <span ${badgeCls}>${patternLabel}</span>
          <span style="font-size:10px;opacity:0.55;">${course}</span>
        </div>`;
      }).join('');

      return `<div class="p-16 flex-1 overflow-auto bg-white text-uber-accent font-black uppercase italic">
        <button onclick="openMasterDetail(null)" class="mb-12 flex items-center gap-3 border border-uber px-6 py-3 w-fit hover:bg-uber-secondary transition-all"><i data-lucide="arrow-left" class="w-4 h-4"></i> 戻る</button>
        <div class="flex flex-wrap items-end justify-between gap-6 mb-12">
          <div>
            <h3 class="text-4xl mb-4 tracking-tighter uppercase italic font-black">利用者マスタ</h3>
            <div class="text-[12px] opacity-40">${state.activeOffice}</div>
          </div>
          <button onclick="expandPatientPatternsToSchedules()" class="flex items-center gap-2 px-6 py-3 border border-uber bg-white hover:bg-uber-accent hover:text-white transition-all text-[11px] font-black uppercase"><i data-lucide="rows-3" class="w-4 h-4"></i>週間パターンを予定へ展開</button>
        </div>

        <div class="flex gap-3 mb-4 max-w-4xl">
          <div class="flex-1 flex items-center gap-2 border border-uber bg-uber-secondary px-4 py-2">
            <i data-lucide="search" class="w-4 h-4 opacity-40 shrink-0"></i>
            <input id="master-search" type="text" placeholder="名前・部屋番号で検索..."
              oninput="filterMasterList()"
              class="flex-1 bg-transparent outline-none text-[12px] font-black italic text-uber-accent placeholder:opacity-30 placeholder:not-italic">
          </div>
          <select id="master-filter" onchange="filterMasterList()"
            class="border border-uber bg-white px-4 py-2 text-[11px] font-black uppercase italic text-uber-accent outline-none cursor-pointer">
            <option value="all">全員</option>
            <option value="unset">⚠ 未設定のみ</option>
            <option value="set">✓ 設定済のみ</option>
          </select>
        </div>

        <div class="max-w-4xl">
          <div style="display:grid;grid-template-columns:1fr 52px 96px 72px;padding:6px 12px;background:#F8F8F8;border:1px solid #2C2C2C;font-size:9px;font-weight:900;text-transform:uppercase;letter-spacing:0.08em;opacity:0.6;">
            <span>名前</span><span>部屋</span><span>週パターン</span><span>コース</span>
          </div>
          <div style="border:1px solid #E8E8E8;border-top:none;">
            ${allPatients.length ? rows : '<div class="p-8 text-center opacity-40 text-[13px]">この事業所には利用者がいません</div>'}
          </div>
          <div id="master-count" style="padding:6px 12px;font-size:9px;opacity:0.4;text-align:right;border:1px solid #E8E8E8;border-top:none;">${allPatients.length} / ${allPatients.length}名 表示中</div>
        </div>
      </div>`;
    }
```

- [ ] **Step 2: ブラウザで利用者マスタを開いて確認する**

1. `npx firebase serve --only hosting` でサーブ
2. サイドバーの「マスタ管理」→「利用者マスタ」を開く
3. 以下を確認する:
   - リストが部屋番号順に並んでいる
   - 週パターン未設定の行が黄背景（`#fffbeb`）になっている
   - 緑バッジ「✓ 設定済」/ 黄バッジ「⚠ 未設定」が正しく表示される
   - 検索バーに名前や部屋番号を入力すると絞り込まれる
   - フィルタードロップダウンで「⚠ 未設定のみ」が機能する
   - 行クリックで従来の利用者編集モーダルが開く
   - 「週間パターンを予定へ展開」ボタンが機能する

- [ ] **Step 3: コミット**

```bash
cd "G:/マイドライブ/承認表"
git add public/index.html
git commit -m "feat: rewrite renderPatientMaster with hybrid list, search, pattern badge"
```

---

## Task 3: `renderStaffMaster()` を書き換える

**Files:**
- Modify: `public/index.html` — `function renderStaffMaster()` (line 901–907)

- [ ] **Step 1: `renderStaffMaster()` を以下のコードで全面置換する**

既存の `function renderStaffMaster() {` から次の `}` までを、以下のコードで置き換える。

```js
    function renderStaffMaster() {
      const allStaff = state.staffMaster
        .filter(s => s.office === state.activeOffice)
        .sort((a, b) => (a.name || '').localeCompare(b.name || '', 'ja'));

      const rows = allStaff.map(s => {
        const roleBadge = s.role
          ? `<span style="background:#F8F8F8;border:1px solid #E8E8E8;padding:2px 8px;font-size:9px;font-weight:900;">${s.role}</span>`
          : `<span style="opacity:0.3;font-size:12px;">—</span>`;
        return `<div class="master-row" data-name="${(s.name||'').replace(/"/g,'')}" data-room="" data-pattern=""
          style="display:grid;grid-template-columns:1fr 120px;align-items:center;padding:0 12px;min-height:44px;border-bottom:1px solid #E8E8E8;cursor:default;"
          onmouseover="this.style.background='#F8F8F8'"
          onmouseout="this.style.background='white'">
          <span style="font-size:13px;font-weight:900;font-style:italic;text-transform:uppercase;">${s.name}</span>
          ${roleBadge}
        </div>`;
      }).join('');

      return `<div class="p-16 flex-1 overflow-auto bg-white text-uber-accent font-black uppercase italic">
        <button onclick="openMasterDetail(null)" class="mb-12 flex items-center gap-3 border border-uber px-6 py-3 w-fit hover:bg-uber-secondary transition-all"><i data-lucide="arrow-left" class="w-4 h-4"></i> 戻る</button>
        <div class="mb-12 border-l-[10px] border-uber-accent pl-8">
          <h3 class="text-4xl font-black tracking-tighter mb-4 uppercase">職員マスタ</h3>
          <div class="text-[12px] opacity-40">${state.activeOffice} — ${allStaff.length}名</div>
        </div>

        <div class="flex items-center gap-2 border border-uber bg-uber-secondary px-4 py-2 mb-4 max-w-xl">
          <i data-lucide="search" class="w-4 h-4 opacity-40 shrink-0"></i>
          <input id="master-search" type="text" placeholder="名前で検索..."
            oninput="filterMasterList()"
            class="flex-1 bg-transparent outline-none text-[12px] font-black italic text-uber-accent placeholder:opacity-30 placeholder:not-italic">
        </div>

        <div class="max-w-xl">
          <div style="display:grid;grid-template-columns:1fr 120px;padding:6px 12px;background:#F8F8F8;border:1px solid #2C2C2C;font-size:9px;font-weight:900;text-transform:uppercase;letter-spacing:0.08em;opacity:0.6;">
            <span>名前（五十音順）</span><span>職種</span>
          </div>
          <div style="border:1px solid #E8E8E8;border-top:none;">
            ${allStaff.length ? rows : '<div class="p-8 text-center opacity-40 text-[13px]">この事業所には職員がいません</div>'}
          </div>
          <div id="master-count" style="padding:6px 12px;font-size:9px;opacity:0.4;text-align:right;border:1px solid #E8E8E8;border-top:none;">${allStaff.length} / ${allStaff.length}名 表示中</div>
        </div>
      </div>`;
    }
```

- [ ] **Step 2: ブラウザで職員マスタを開いて確認する**

1. サイドバーの「マスタ管理」→「職員マスタ」を開く
2. 以下を確認する:
   - 全職員が五十音順フラットリストで表示される
   - 職種バッジ（PT / OT など）が右列に表示される
   - 職種未登録スタッフは「—」で表示される
   - 検索バーに名前を入力すると絞り込まれる
   - カウンター「N / M名 表示中」が更新される
   - 旧来のロール別カードグループが消えている

- [ ] **Step 3: コミット**

```bash
cd "G:/マイドライブ/承認表"
git add public/index.html
git commit -m "feat: rewrite renderStaffMaster with flat alphabetical list and search"
```

---

## Task 4: 最終動作確認

- [ ] **Step 1: 両画面を通しで確認する**

1. 利用者マスタ → 部屋番号検索（例: `201`）が機能すること
2. 利用者マスタ → 「⚠ 未設定のみ」フィルター → 黄背景行だけ残ること
3. 利用者マスタ → 行クリック → 利用者編集モーダルが正常に開くこと
4. 利用者マスタ → 「週間パターンを予定へ展開」ボタンが機能すること
5. 職員マスタ → 名前検索が機能すること
6. サイドバーの「マスタ管理トップ」→「利用者マスタ」→「戻る」のナビゲーションが壊れていないこと
7. ブラウザコンソールにエラーがないこと

- [ ] **Step 2: `.gitignore` に `.superpowers/` を追加する（未追加の場合）**

```bash
cd "G:/マイドライブ/承認表"
grep -q ".superpowers" .gitignore || echo ".superpowers/" >> .gitignore
git add .gitignore
git commit -m "chore: ignore .superpowers brainstorm artifacts"
```

---

## 注意事項

- **`onmouseover` のインラインスタイル競合:** 未設定行（黄背景）のホバーは `onmouseover` で `#F8F8F8` に、`onmouseout` で `#fffbeb` に戻す。既に `white` と `#fffbeb` のどちらかをインラインに持つので、`onmouseout` で正しい色を返すよう実装済み。
- **`lucide` アイコンの再初期化:** `renderApp()` は最後に `lucide.createIcons()` を呼ぶ既存の仕組みがあるので追加不要。検索バー内の `<i data-lucide="search">` は初回レンダリング時に展開される。
- **Firestore への影響なし:** 今回は表示ロジックのみ変更。`savePatientMaster()` / Firestore 書き込みパスは一切触らない。
