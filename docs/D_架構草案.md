# D. 架構草案

> 這是草案，**還沒寫任何 App 程式**。依據：JLPT_App 的 `CLAUDE.md`、`docs/STATUS.md`（§5 資料慣例、§6 關鍵決定、§7 被否決的方案、§9 架構速查）與 `scripts/build_data.py`（唯讀，未改動）。
> 預設採 `C_方案比較.md` 的方案四；使用者 選別的方案時，要改的地方在最後一節列出。

---

## 0. 沿用 JLPT_App 的，與刻意不沿用的

**沿用**
- 純前端 PWA：原生 JS ES Modules＋IndexedDB＋Service Worker，無框架、無打包。
- 題庫寫在人好編輯的純文字原始檔，用 Python 腳本（只用標準函式庫）建成 JSON＋`manifest.json`。
- `dataVersion`（全題庫雜湊）當 SW 快取標記，題庫一改就自動失效（JLPT §6，v1.5.0 忘了升版號的教訓）。
- 建置「先全部檢查、再全部寫成 .tmp、最後一起換上」，失敗不留半新半舊（`build_data.py` 的 `commit_outputs`）。
- 載入函式走 `once()` 快取進行中的 Promise；路由加世代碼；`[hidden]{display:none!important}`；資源一律相對路徑（GitHub Pages 子路徑）。
- 作答紀錄只存在本機 IndexedDB，有匯出／匯入備份（匯入是「取代」語意，備份帶 `idScheme` 與 `dataVersion`）。

**刻意不沿用**
- **不用「依行序自動編號」的 id**。JLPT 的 id 依有效資料列順序產生，是後來所有資料決策的根源（§7 第 1 條：刪 27 行會讓 37.7% 的 id 靜默指向別的詞）。本 App 每一題的 id **寫死在原始檔裡**，建置只檢查、不產生。
- **不用一行一筆的 pipe 格式**。法規題的題幹常常一大段、選項長、解析多段，AI-901 還有程式碼，擠在一行裡沒辦法編輯。改用「一題一個區塊」的格式（見 §2）。
- **刪題不從原始檔刪**：改標 `status: retired`，建置照樣輸出（隱藏不出題），使用者在該題的紀錄仍解析得到（JLPT `loadSetRaw` 的教訓）。

---

## 1. 多證照怎麼切：證照 → 科目 → 章節 → 題目

```
證照 cert        bic（銀行內控）  az900           ai901
  └ 科目 subject   law（法規）     （只有一科）     （只有一科）
                   prac-gen（實務・一般金融）
                   prac-con（實務・消費金融）
      └ 章節 chapter  依官方大綱；TABF 沒有官方逐章大綱 → 先用法規名稱分章，簡章取得後再對齊
          └ 題目 question
```

- 每張證照一份定義檔 `data/src/<cert>/cert.txt`，寫：名稱、主辦、語言、科目清單、每科的章節樹、模擬考規則（題數、時間、及格線、計分方式）、大綱版本與日期。
- **章節 id 也寫死**（例：`az900.B2`＝Azure architecture／運算與網路），大綱改版時新增章節、舊章節標 `retired` 並寫對應到哪個新章節，舊題的統計不會斷。
- 使用者流程：首頁選證照 → 選科目 → 選練習方式（章節練習／隨機／錯題／模擬考）→ 出題。選過的證照記在 `meta.lastCert`，下次直接進。

## 2. 題庫原始檔格式（草案）

一題一個區塊，`===` 開頭帶 id；欄位 `key: value`；值要換行就縮排續行。只用 Python 標準函式庫解析。

```
=== bic-law-o-0001
type: single
chapter: bic.law.ch02
stem: 依「金融控股公司及銀行業內部控制及稽核制度實施辦法」，下列敘述何者正確？
A: …
B: …
C: …
D: …
answer: B
explain: …（解析，可多行）
basis: 金融控股公司及銀行業內部控制及稽核制度實施辦法 第24條
law_as_of: 2026-10-01
source: original-ai
reviewed: 2026-10-15
```

### 欄位

| 欄位 | 必填 | 說明 |
|---|---|---|
| id（`===` 後） | 是 | 全庫唯一，**一旦發布永不改、永不重用**。建議格式：`<cert>-<subject>-<來源碼>-<序號>`。TABF 官方題用期別＋題號（`bic-law-t49-012`），天生穩定 |
| `type` | 是 | `single`（單選）、`multi`（複選）、`tf`（是非）、`yn-set`（Yes/No 題組：共用題幹＋多個敘述各判是非，對應微軟常見題型）。拖放、Hot area、排序先不做，見 §6 |
| `chapter` | 是 | 章節 id，必須存在於 `cert.txt` |
| `stem` | 是 | 題幹；可含 ```` ``` ```` 程式碼區塊（AI-901 用） |
| `A`～`F` | single／multi 必填 | 選項。key 固定，答案寫 key，出題時可洗牌、顯示重新編號 |
| `answer` | 是 | single：`B`；multi：`A,C`；tf：`T`／`F`；yn-set：`Y,N,Y` |
| `select` | multi 選填 | 「選兩個」這類題要寫幾個 |
| `fixed_order` | 選填 | 有「以上皆是」這類選項時不洗牌 |
| `explain` | 建議 | 解析。TABF 官方題原本沒有解析，空著也能建置，畫面顯示「尚無解析」 |
| `basis` | 法規題建議必填 | 依據的法規與條號，或 Learn 文件網址 |
| `law_as_of` | 法規題必填 | 法規基準日。TABF 官方題填該期測驗日 |
| `source` | 是 | `tabf-official`（附 `period: 49`、`qno: 12`）、`original-ai`、`original-human`、`user-import` |
| `lang` | 選填 | 預設跟證照的語言 |
| `status` | 選填 | `active`（預設）、`outdated`（法規已修、答案可能錯，仍可看但不出題）、`retired`（隱藏） |
| `reviewed` | 選填 | 人工查核日期；沒填的題在統計頁標示「未查核」 |

### 建置檢查（`build_data.py` 要擋下的）

- id 重複、id 格式不對、同一個 id 的題目內容跟上一次發布的版本「變成完全不同的題」（比對題幹相似度，防止有人把 id 拿去重用）。
- `chapter` 不存在、`answer` 指到不存在的選項、multi 的答案數不等於 `select`、yn-set 的答案數不等於敘述數。
- 法規題缺 `law_as_of`。
- **原始檔來源分兩區**：`data/src/`（進 repo，只放原創題）與 `data/local/`（列入 `.gitignore`，放 TABF 轉檔與使用者自己匯入的題）。建置時兩區合併給本機用；**部署用的建置只吃 `data/src/`**，並檢查輸出裡不得出現 `source: tabf-official` 或 `user-import` 的題（版權防線，見 §5）。

### 建置輸出

```
data/manifest.json                 證照清單、各科題數、dataVersion、大綱版本
data/<cert>/cert.json              章節樹、模擬考規則
data/<cert>/<subject>.json         題目
```
manifest 裡題數分「全部」與「可出題（active）」兩套，回報一律用可出題那套（JLPT §5 的慣例）。

## 3. 作答紀錄（本機 IndexedDB）

資料庫 `certquiz`，版本 1。

| store | key | 內容 |
|---|---|---|
| `attempts` | 自動遞增 | 每一次作答：`qid`、`cert`、時間、選了什麼、對錯、練習方式、所屬場次 id。**原始紀錄全留**，統計都從這裡算，將來改統計方式不用遷移 |
| `progress` | `qid` | 每題的彙總：作答次數、答對次數、最近一次結果、SRS 盒號與下次複習日 |
| `mistakes` | `qid` | 錯題本：最近答錯時間、累計錯幾次、是否已手動移出 |
| `flags` | `qid` |使用者自己的標記：「這題法規過期」「答案有疑問」「收藏」＋備註 |
| `exams` | 自動遞增 | 模擬考成績：證照、科目、題數、得分、用時、是否及格 |
| `userQuestions` | `qid` | 在 App 裡匯入的題目（方案一、2A）。不進 repo、不上網 |
| `meta` | `k` | 設定：上次選的證照、每輪題數、主題等 |

- **錯題複習**：答錯就進錯題本；在錯題模式連續答對 2 次才自動移出（次數待使用者定）。也沿用 JLPT 的 SRS（Leitner 盒 0–6），但每張證照分開排程。
- **備份**：匯出一個 JSON（含 `attempts`、`progress`、`mistakes`、`flags`、`exams`、`userQuestions`、`meta`，帶 `idScheme: "explicit-v1"` 與 `dataVersion`）；匯入是取代。換手機就靠它。
- 題目改了內容（例如法規修訂後修正答案）：`progress` 記下作答當時的 `dataVersion`，題目有變動時在畫面上提示「這題在你上次作答後改過」。

## 4. 練習方式與計分

| 模式 | 說明 |
|---|---|
| 章節練習 | 選一個或多個章節，依 SRS 排序出題（到期題優先，沿用 JLPT `DUE_QUOTA` 的做法） |
| 隨機練習 | 可篩來源：只出官方題／只出原創／全部 |
| 錯題複習 | 只出錯題本裡的題 |
| 模擬考 | 照 `cert.txt` 的規則：銀行內控法規 50 題／60 分鐘、實務 80 題／90 分鐘、每科 70 分及格；微軟兩張是量尺分數、官方不公布換算，**App 只顯示答對率，並在畫面寫明「不等於 700 分」** |

- 複選題計分：預設全對才給分（跟微軟官方練習題相同）。
- 每題作答後顯示：正解、解析、依據、來源標籤（官方／原創 AI／匯入）、法規基準日。
- 統計頁：各章節答對率、弱點章節、官方題與原創題分開統計（原創題答對率高不代表考得過）。

## 5. 版權防線（寫進程式，不靠記得）

1. `data/local/` 列入 `.gitignore`；推送前的自查掃描輸出與暫存區，看到 `tabf-official`、`user-import` 就擋。
2. 部署建置只吃 `data/src/`，輸出再檢查一次來源欄位。
3. 每一題畫面上都顯示來源標籤；原創題標「練習題，非考題」。
4. 任何微軟題目的 `source` 只能是 `original-*`；不收任何考後回憶。

## 6. 先不做、留待以後的

- 微軟的拖放、Hot area、排序（Build list）、Case study 題型：要另外設計互動畫面，第一版用 `single`／`multi`／`yn-set` 改寫考點即可。
- TABF 簡章的官方章節：取得後對齊 `cert.txt` 的章節樹。
- 多語切換：每題的 `lang` 欄位先留著，介面先只做繁中。

## 6.5 部署（2026-10-08 補）

三條路的比較見 `E_第二輪查證.md` §5。建議走 Cloudflare Workers 靜態資產（照 RentCheck 的 `wrangler.jsonc`＋`deploy.sh` 做法），只上傳建置輸出；`data/local/` 的 TABF 題永遠不進部署，靠 App 內「匯入」放進手機。部署腳本在上傳前再掃一次輸出裡有沒有 `tabf-official`／`user-import`。

## 7.使用者選別的方案時要改的地方

- **只選方案一**：不做 TABF 轉檔腳本、不寫原創題；首頁加「還沒有題目，請匯入」的引導。
- ~~選方案二B（公開部署 TABF 題）~~：使用者 2026-10-08 取消（不寫信問 TABF、不公開散布）。
- **不做 AI-901、改做 AI-900**：`cert.txt` 照 AI-900 最後版大綱建，首頁標「已退役，僅供概念複習」。
