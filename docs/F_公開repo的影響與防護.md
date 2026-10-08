# F. 用 GitHub Pages（公開 repo＋公開網站）有什麼影響、要怎麼防

- 2026-10-08。使用者 決定部署照他其他 App：GitHub Pages、公開 repo。他問「有什麼不良影響嗎」，這份正面回答。
- 來源標記同前：〔原文〕〔摘要〕、→推論；「實測」＝這一輪在本機實際跑過。

---

## 結論先講

可以用，**但防護要設在 commit 之前，不是 push 之前，更不是事後**。原因是：公開 repo 公開的不只是現在的檔案，而是**整段 commit 歷史**；一個檔 commit 過再刪掉，它還在歷史裡，push 上去就公開了，事後要清只能改寫歷史（而且別人可能已經 clone）。

這一輪已經設好並實測：`.gitignore`＋commit 前自查（`scripts/selfcheck.py`，pre-commit hook）＋push 前掃整段歷史（pre-push hook）。細節見 §2。

---

## 1. 逐項影響

### 1.1 repo 公開後，什麼會被看到

| 會被看到的東西 | 說明 | 防護 |
|---|---|---|
| 現在的原始碼與文件 | 任何人都能看、下載、fork | 文件裡不寫個資；本 App 的 `docs/` 會整包公開（見 §3 的待決定事項） |
| **整段 commit 歷史** | 每一個 commit 的每一個檔，**包括後來刪掉的** | commit 前擋（pre-commit）；push 前再掃一次整段歷史（pre-push） |
| commit 的作者名稱與 email | 每個 commit 都帶 | 本機 repo 已設成跟 JLPT_App 相同的 GitHub noreply email（實測：`git config user.email` 是 `…@users.noreply.github.com`）；這台電腦沒有全域 git 身分 |
| commit 訊息 | 公開 | 不寫個資、不寫本機路徑 |
| 網站的所有檔案 | 網站公開，題庫 JSON 誰都能直接下載 | 網站上只放練習功能與原創題 |

GitHub 官方文件原文：「GitHub Pages sites are publicly available on the internet, even if the repository for the site is private」；個人帳號沒有私人發布（「To publish a GitHub Pages site privately, you need to have an organization account.」）。

### 1.2 TABF 官方題目：維持不進 repo

- 存放位置：`refs/`（官方 PDF）、`data/local/`（之後轉出來的題庫）。都在 `.gitignore`，另外 `*.pdf`、`*.docx`、`*.xlsx`、`*.pptx` 不論放在哪都擋。
- **`.gitignore` 不夠**：它只擋一般的 `git add`。`git add -f` 擋不住，副檔名改掉的 PDF 也擋不住——**擋不住的東西跟沒放東西，在 `git status` 上長得一樣**。所以另設 commit 前自查，它不看 `.gitignore`，直接看要進 commit 的內容。
- 實測（本 repo，2026-10-08，結束後 HEAD 仍是「還沒有 commit」、暫存區清空、假檔已刪、18 份真 PDF 沒動）：

| 嘗試 | 結果 |
|---|---|
| A. `git add refs/tabf/_gate_test_fake.pdf` | `.gitignore` 擋下：回傳 1，暫存區是空的 |
| B. `git add -f` 強行加入，再 `git commit` | 進了暫存區；**commit 被自查擋下**：R1（目錄）、R1（副檔名）、R2（內容是 PDF），回傳 1 |
| C. 內容是 PDF、副檔名改成 `.txt`，放在 `docs/`（`.gitignore` 擋不到） | 進了暫存區；**commit 被自查擋下**：R2（內容是 PDF），回傳 1 |

- TABF 題怎麼到使用者手機上：本機轉檔產生一個「匯入包」檔（放 `data/local/`），他用 LINE／雲端硬碟等自己傳到手機，在 App 裡選檔匯入。題目只存在他手機的瀏覽器裡（見 1.4）。

### 1.3 微軟的內容：一行都不能進

- 依微軟考生協議第 1 條，連「摘要（summarize）」考題都禁止〔原文，見 B §2.2〕；Learn 的官方練習題也限個人非商業使用〔原文〕。
- 所以 AZ-900 題目**只能原創**，寫法規則：
  - 依官方 study guide 的考點出題，`source` 一律是 `original-ai` 或 `original-human`；解析的依據欄（`basis`）放 Microsoft Learn 文件的**連結**，不貼文件原文段落。
  - 不參考、不改寫任何官方練習題、考後回憶、dump 或第三方題庫的題目。
  - App 畫面每一題標「練習題，不是考題」；首頁與關於頁寫明「非 Microsoft 官方、與 Microsoft 無關」，不使用微軟的 logo（考試代號、產品名稱照常用來說明是哪一科）。
  - 建置檢查（第二階段做）：AZ-900 的題目 `source` 不是 `original-*` 就拒絕建置。
- 自查能擋的是「檔案類型、來源欄位、路徑」；**擋不了「某一題是不是抄來的」**——那靠出題流程本身，這一點要誠實講清楚。

### 1.4 使用者的作答紀錄：只在他手機本機

- **現況**：App 還沒寫，所以這是**設計上**的確認，不是程式的實測。
  - 設計（`D_架構草案.md` §3）：作答紀錄、錯題、模擬考成績、匯入的題目全部存在手機瀏覽器的 IndexedDB；備份是匯出成檔案，由使用者自己保管。沒有任何後端、帳號或雲端同步。
  - 前例（JLPT_App，唯讀查核）：程式裡的網路請求只有 `js/data.js` 讀題庫、`sw.js` 快取外殼與題庫，全部是讀取自己網站的檔案；沒有 POST、`sendBeacon`、分析工具。
- **第二階段要做成「程式保證」而不是「設計上沒寫」**：
  1. 網頁加 Content-Security-Policy，`connect-src 'self'`：瀏覽器層級就禁止連到任何外部網址。
  2. 靜態檢查：程式裡不得出現 POST／PUT、`sendBeacon`、`WebSocket`、外部網址；有就擋 commit。
  3. 瀏覽器實測：跑完一整輪練習，記錄所有網路請求，必須全部是同網站的 GET。並用一個「偷偷送出作答」的假樣本證明這個測試會紅。
- **GitHub 看得到的**：GitHub 文件寫 Pages 會記錄訪客 IP（「the visitor's IP address is logged and stored for security purposes」〔原文〕）。也就是 GitHub 知道「有人開了這個網站」，但**看不到他答了什麼**——答案從來不離開手機。

### 1.5 公開網站會被搜尋引擎索引

- 原創的 AZ-900 練習題、內控的原創題會被別人搜到、看到、引用或複製。不違法，但他要知道。
- 可以減少但**不能保證**：
  - 網站加 `robots.txt`（Disallow）與 `<meta name="robots" content="noindex">`，守規矩的搜尋引擎不會收錄網站。
  - **repo 本身在 github.com 上照樣公開、照樣可被搜尋**，這一層擋不掉。
- 網站上看得到的也只有原創題；TABF 題不在網站上，所以不會被索引。

### 1.6 跟 Cloudflare 比，放棄了什麼

| | GitHub Pages（他的選擇） | Cloudflare（不加門禁） | Cloudflare＋Access |
|---|---|---|---|
| 網站網址誰能開 | 任何人 | 任何人 | **只有登入的他** |
| 原始碼、文件、commit 歷史 | **公開** | 可以不公開（私有 repo 或只在本機） | 可以不公開 |
| 費用 | 0 | 0 | 0（免費方案上限 50 人〔摘要〕） |
| 部署 | `git push`（跟其他 App 一樣） | 本機一行指令 | 同左＋設定 Access |

放棄的就是兩層：**原始碼與歷史的隱私**，以及（相對於加 Access）**「網址本身只有他能開」**。代價是：所有防護都得放在 commit 之前，而且一旦漏網就是公開的、難以收回。照他的選擇做：GitHub Pages。

---

## 2. 常設閘門（已設、已驗）

### 2.1 組成

| 層 | 檔案 | 何時跑 | 擋什麼 |
|---|---|---|---|
| 1 | `.gitignore` | `git add` | `refs/`、`data/local/`、PDF／Office 檔 |
| 2 | `scripts/selfcheck.py`（pre-commit：`.githooks/pre-commit`） | 每次 commit | 看暫存區每一個檔的**路徑與內容**，不靠 `.gitignore` |
| 3 | `scripts/selfcheck.py --history`（pre-push：`.githooks/pre-push`） | 每次 push | 所有分支、所有 commit 裡出現過的每一個檔（包含已刪除的） |

規則：
- R1 路徑：`refs/`、`data/local/` 底下；`.pdf .docx .xlsx .pptx`（不分大小寫）
- R2 內容：檔頭是 PDF；Office 文件
- R3 題目檔：有 `source: tabf-official` 或 `source: user-import` 的欄位行
- R4 本機路徑：Windows／Git Bash／macOS／Linux 的使用者目錄、Claude session 目錄、本機 Windows 使用者名稱
- R5 email：GitHub noreply 與 noreply@anthropic.com 以外的 email

結束碼 0 通過、1 擋下、2 程式出錯（**出錯不算通過**）。

### 2.2 驗證

- `python scripts/selfcheck.py --selftest`：在暫存 repo 裡逐一放假樣本，每一個都必須被**恰好那幾條**規則擋下、乾淨樣本必須通過。實測全部符合：
  - `.gitignore` 3 個情境（refs/ 的 PDF、data/local/ 的檔、docs/ 的 PDF）：一般 `git add` 都被拒絕。
  - 14 個樣本：3 個乾淨樣本通過（原創題檔、文件裡用反引號提到來源值、範例網域 email）；11 個違規樣本各自被預期的規則擋下。
  - 1 個歷史情境：用 `--no-verify` 繞過 commit 自查、再刪掉檔案，`--history` 仍然抓到。
- **突變證明**（在暫存複本裡改壞，真檔沒動）——每一個都讓 selftest 變紅：
  1. 拿掉 PDF 檔頭檢查 → 3 項不符
  2. 暫存區掃描永遠回空 → 11 項不符
  3. 歷史掃描只看最新一個 commit → 歷史情境不符
  4. `.gitignore` 拿掉 PDF 規則 → `.gitignore` 情境不符（注意：只拿掉 `*.pdf` 不會紅，因為 Windows 的 git 預設不分大小寫，`*.PDF` 照樣擋住；要兩行都拿掉才是真的洞）
- 真實檔：`docs/`、`scripts/`、hooks 等 11 個檔放進暫存區跑一次 → 通過（之後已取消暫存，沒有 commit）。途中 `selfcheck.py` 自己被 R4 擋過一次（註解裡寫了路徑範例），改成文字描述，沒有開例外。

### 2.3 已知限制（要誠實寫）

- `git commit --no-verify`、`git push --no-verify` 可以繞過 hook。JLPT_App 的做法是「推送一律走閘門腳本，不直接下 `git push`」；第二階段照做一支 `scripts/pushsafe.sh`（先跑 `--selftest`、`--history`，全過才 push）。
- hook 靠 `git config core.hooksPath .githooks` 啟用，這是本機設定、**不跟著 repo 走**。新 clone 要重下一次（寫在 STATUS）。
- 自查擋不了「內容是抄來的」（見 1.3）。

---

## 3. 個人資訊（2026-10-08 已處理）

`docs/` 會整包公開。第一次 commit 前已把所有入庫檔案改成中性寫法：
- 不寫使用者的姓名（一律寫「使用者」）、任職機構、學校。
- 不寫「正在準備考試」「單位要求」這類能指向特定個人處境的敘述；只寫 App 的範圍（例如「App 收錄一般金融組」）。
- commit 前自查加上 R6（見 §2.1）：內建一組個人處境用語，另讀本機的私人清單 `.selfcheck-private.txt`（`.gitignore` 擋、不入庫），由使用者自己填真實姓名、任職機構、學校等字串。
