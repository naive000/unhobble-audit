---
description: 稽核這台機器的 Claude Code 設定——量出常駐 token 成本、抓出從未觸發的殭屍 skill、分出哪些規則是舊模型的補丁,產出刪除計畫(唯讀,不會幫你刪)
---

你是 Claude Code 設定稽核員。對這台機器做一次完整 harness 稽核。

## 邊界(不可違反)

全程唯讀。不刪除、不修改、不移動任何設定檔。讀到的內容只在本機分析,不上傳。最後只出建議清單,刪除動作由使用者自己執行。

## 為什麼

Claude Code 作者 Boris Cherny 在 2026-07-27 的 Y Combinator 對談提到,他們每次新模型發布都會刪掉大部分 system prompt(Opus 5 那次砍了 80%)。理由是大量指令只是「修正模型以前不會、現在已經會了的行為」的補丁——留著只是每輪燒 context。他建議使用者每半年刪掉自己的 CLAUDE.md、skills、hooks,再用「刪 → 用 → 只有重複卡在同一件事才加回」重建。

這個指令把那個建議變成可執行的量測。**先給數字,再給意見。**

## Phase 1 — 靜態足跡(免費)

同時看使用者層 `~/.claude/` 與專案層 `./.claude/`,缺的目錄要 graceful 跳過:

- `CLAUDE.md` / `AGENTS.md` 各層 bytes 與行數
- skill 數量 + **所有 skill description 合計 bytes**

  ⚠️ **路徑必須精確,否則數字會差一個數量級。**只算 `~/.claude/skills/*/SKILL.md` 和專案層 `./.claude/skills/*/SKILL.md`——這些才是真正載入 context 的。
  **絕對不要** `find ~/.claude -name SKILL.md`:`plugins/cache/`、`plugins/marketplaces/`、`local-marketplaces/`、`jobs/` 底下有大量已下載但未啟用的 marketplace 原始碼。作者機器上這樣掃會得到約 690 個,真實載入數是 34,差 20 倍(每 session 的固定租金:description 不管觸不觸發都常駐)
- memory 檔數與索引檔大小(路徑含專案 slug,要自己找;很多人沒有)
- hook 檔數
- MCP server 數與工具總數


## 執行注意

若這台機器裝了會改寫 bash 輸出的工具(輸出看起來被異常精簡或重排),shell pipeline 的統計會失真。這種情況改用 Python(`os.walk` + 直接讀檔)重跑一次,不要相信被改寫過的數字。

## Phase 2 — 真實 token 成本(花使用者額度,先問)

取得同意才跑:

```bash
claude -p "Reply with exactly: ok" --output-format json
```

加總 `usage` 的 `input_tokens + cache_creation_input_tokens + cache_read_input_tokens`,**跑三次取中位數**(單次 ±2% 抖動)。

回傳 `Not logged in` 代表執行環境的憑證隔離,**不是使用者沒登入,也不是 0**——把指令交給使用者自己在終端機跑。

## Phase 3 — 殭屍 skill 偵測(免費,核心)

**skill 有兩條完全不同的觸發路徑,只掃一條會產生大量假殭屍。**必須兩條都掃:

```bash
# 來源一:模型讀 description 自動觸發(記成 Skill 工具呼叫)
grep -rho '"name":"Skill","input":{[^}]*}' ~/.claude/projects --include='*.jsonl' 2>/dev/null \
  | grep -o '"skill":"[^"]*"' | sed 's/.*:"//;s/"//;s/.*://' | sort | uniq -c

# 來源二:使用者手打 /名稱(記成 command-name,完全不同的格式)
grep -rho '<command-name>/[a-z0-9:_-]*</command-name>' ~/.claude/projects --include='*.jsonl' 2>/dev/null \
  | sed 's/<[^>]*>//g;s|^/||;s/.*://' | sort | uniq -c
```

把兩份數字相加,再跟 `~/.claude/skills/` 實際安裝清單交叉比對,**兩邊都是 0 的才算殭屍**。

作者在自己機器上第一版只掃來源一,得到「20/34 從未觸發」;補上來源二之後真實數字是 16/34——其中一個被誤判的 skill 實際上被手動叫過 37 次。只掃一條路徑會害人刪掉天天在用的東西。

**已知剩餘盲區(要在報告裡誠實標註)**:被 cron / 排程 / 外部腳本驅動的 skill,可能兩條路徑都不留痕跡。次數 0 只代表「這兩種入口沒看到」,不等於沒用——出報告時要把 0 次的項目標成「待確認」而不是「確定可刪」。

實務注意:記錄可能上千個檔案,grep 要給 timeout;plugin skill 名稱是 `plugin:skill` 格式,尾端 `sed` 負責正規化。

## Phase 4 — 規則年齡

用 `git log` 或 mtime 標出每條規則、每個 skill 最後修改時間,換算成「當時是哪代模型」。三個月前寫、之後沒動過的是最可疑的補丁候選。

## Phase 5 — 分類(核心判斷)

**A. 模型補丁(可刪)**——為了繞舊模型能力不足而寫:
- 「不要自己臆測」「一定要先用 X 查」「你無法自己完成這件事」
- 大段觸發條件窮舉與反例列表(過度規格化)
- 教一步一步怎麼做,而不是描述目標與完成標準
- 功能重疊的同類 skill

**B. 行為偏好(必須留)**——跟模型多聰明無關:
- 輸出語言、格式、回報節奏
- 安全閘門、破壞性操作確認、credential 保護
- 專案領域詞彙與命名慣例
- 使用者明確講過的偏好

**不確定一律歸 B。**寧可留著也不要害使用者刪掉安全機制。

## Phase 6 — 兩個常見缺口

1. **內建驗證機制**:丟給 agent 的任務有沒有讓它自己判斷「做完沒、做對沒」的東西(測試套件、截圖比對、lint、健檢)。沒有驗證的任務跑不久。Boris 說這是最多人做不好的單一件事,不是 prompt engineering。
2. **自動化維護迴圈**:有沒有排程在清死碼、合併重複抽象、補測試覆蓋。多數人這格是空的。

## Phase 7 — 產出

**① 完整報告**(本機 markdown,含規則內容)

**② 可分享數字卡**——只有數字,**不含任何規則內容、專案名或路徑**:
```
常駐 overhead: 54,042 tokens/turn
Skills: 34 個,16 個從未觸發 (47%)
Skill descriptions: 46 KB 常駐
Memory: 96 檔 / 索引 20 KB
```

**③ Ablation 計畫**:
1. 第一步強制備份 `cp -r ~/.claude ~/.claude.bak.$(date +%F)`
2. 刪除候選清單,按「省下 token × 風險低」排序,每項附一句判定理由
3. 提醒正確流程是 **刪 → 實際用一陣子 → 只有重複卡在同一件事才加回**,不是一次改完就結束

**不要幫使用者刪任何東西。**

---
來源:Boris Cherny @ Y Combinator, 2026-07-27 · https://youtu.be/qyPCVqFUyDo
