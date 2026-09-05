#!/usr/bin/env python3
"""從 scripts/measure.py 產生 PROMPT.md 與 commands/unhobble.md,避免兩份不同步。"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = (ROOT / "scripts" / "measure.py").read_text()

BODY = """## 邊界(先讀,不可違反)

- **全程唯讀。**不刪除、不修改、不移動任何設定檔。
- **不外傳。**讀到的內容只在本機分析。
- **不派 subagent。**整份稽核在同一個 session 內完成,確保結果可重現。
- **報告寫到 `~/unhobble-report-<今天日期>.md`**,不要寫進當前目錄——那可能是一個 git repo,報告含機器資訊,不該被 commit。
- **最後只出建議清單,刪除動作由使用者自己執行。**

## 背景

Claude Code 作者 Boris Cherny 在 2026-07-27 的 Y Combinator 對談提到,他們每次新模型發布都會刪掉大部分 system prompt(Opus 5 那次砍了 80%)。理由是大量指令只是「修正模型以前不會、現在已經會了的行為」的補丁,新模型不需要,留著只是每輪燒 context。他建議使用者每半年也刪一次自己的 CLAUDE.md、skills、hooks,用「刪 → 用 → 只有重複卡在同一件事才加回」重建。

這份稽核把那個建議變成可執行的量測。**先給數字,再給意見。**

## Phase 0 — 跑量測腳本(所有數字的唯一來源)

把下面這支腳本存成 `/tmp/unhobble_measure.py` 然後執行它。

**為什麼要用腳本而不是直接下指令**:實測過散文版指令,產出的數字錯得離譜(記錄檔數 2088 被算成 4、skill 數 34 被算成 37)。原因有二——`find ~/.claude -name SKILL.md` 會掃到 `plugins/cache/`、`plugins/marketplaces/` 底下幾百個未啟用的原始碼;以及有些機器裝了會改寫 shell 輸出的工具,統計會失真。這支腳本路徑寫死、不用 find/grep,兩個問題都繞開。

**不要自己用 shell 指令重算這些數字。**跑腳本,讀它吐出來的 JSON。

```python
%SCRIPT%
```

執行:`python3 /tmp/unhobble_measure.py`

它會輸出 JSON,包含:skill 數與 description 總 bytes、殭屍 skill 名單(兩條觸發路徑都掃)、記錄檔統計、規則檔大小與 mtime、memory 檔數、hook 數、MCP server 數。

**讀 JSON 時注意三件事**:
- `skills.desc_bytes_total` 是每個 session 的固定租金——skill 的 description 不管有沒有觸發都常駐在 context。
- `memory.current_project.index_bytes` 才是會載入 context 的;`all_projects` 只是參考。
- `skills.zombies` 是「兩條路徑都沒看到」,不是「確定沒用」。被 cron/排程/外部腳本驅動的 skill 兩邊都不留痕跡,**一律標成「待確認」**。
- **`skills.too_new_to_judge` 不是刪除候選。**那些 skill 距上次修改未滿 30 天,還沒有足夠時間觸發。只有 `zombies` 才進候選清單。作者機器上 16 個從未觸發的 skill 裡有 10 個屬於這類,其中一個才裝了半天——把它們算進去會讓數字難看兩倍,而且是假的。
- `days_since_touch` 是「距上次修改」不是「安裝至今」。改過的舊 skill 會看起來很新,這是已知限制,報告裡要講。

## Phase 1 — 規則年齡

用 JSON 裡的 `mtime`(以及 `git log`,若規則檔在版控裡)標出每條規則、每個 skill 最後修改時間,換算成「當時是哪一代模型」。三個月前寫、之後沒動過的是最可疑的補丁候選。

## Phase 2 — 分類(核心判斷,只有你做得到)

把每一條規則、每一個 skill 判進兩籃:

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

## Phase 3 — 兩個常見缺口

1. **內建驗證機制**:丟給 agent 的任務有沒有讓它自己判斷「做完沒、做對沒」的東西(測試套件、截圖比對、lint、健檢)。沒有驗證的任務跑不久。Boris 說這是最多人做不好的單一件事,不是 prompt engineering。
2. **自動化維護迴圈**:有沒有排程在清死碼、合併重複抽象、補測試覆蓋。多數人這格是空的。

## Phase 4 — 產出報告(第一交付物)

**① 完整報告**,寫到 `~/unhobble-report-<今天日期>.md`。**這是第一交付物,先寫檔再說。**常駐 token 成本那一格先填「未量測(見 Phase 5)」。

**② 可分享數字卡**——只有數字,**不含任何規則內容、專案名或路徑**:
```
常駐 overhead: 未量測(見 Phase 5)
Skills: 34 個,16 個從未觸發 (47%)
Skill descriptions: 23 KB 常駐
Memory: 99 檔 / 索引 21 KB
```

**③ Ablation 計畫**:
1. 第一步強制備份 `cp -r ~/.claude ~/.claude.bak.$(date +%F)`
2. 刪除候選清單,按「省下 token × 風險低」排序,每項附一句判定理由,殭屍項標「待確認」
3. 提醒正確流程是 **刪 → 實際用一陣子 → 只有重複卡在同一件事才加回**,不是一次改完就結束

**不要幫使用者刪任何東西。**

## Phase 5 — 真實 token 成本(選配,報告寫完才問)

**這一步必須放在報告寫完之後。**在交付物落地之前,不要問任何需要使用者回覆的問題——非互動或批次執行時沒有人會回你,問了就等於整份稽核作廢。

報告存檔後,再問使用者要不要量常駐成本(會花掉一點 API 額度)。同意才執行:

```bash
claude -p "Reply with exactly: ok" --output-format json
```

加總 `usage` 的 `input_tokens + cache_creation_input_tokens + cache_read_input_tokens`,**跑三次取中位數**(單次 ±2% 抖動)。這是問一句廢話就要付的常駐成本。拿到數字後回頭把報告裡「未量測」那格補上。

若回傳 `Not logged in`,那是執行環境的憑證隔離,**不是使用者沒登入,也不是 0**——把指令交給使用者自己在終端機跑。

沒有得到回覆就到此為止,報告已經是完整的。

---
方法論出處:Boris Cherny @ Y Combinator, 2026-07-27 · https://youtu.be/qyPCVqFUyDo
"""

body = BODY.replace("%SCRIPT%", SCRIPT.rstrip())

(ROOT / "PROMPT.md").write_text(
    "# Unhobble Audit — 貼進 Claude Code 就跑\n\n"
    "複製底下整段(從 `---` 開始到結尾),貼進你的 Claude Code。不用安裝任何東西。\n\n---\n\n"
    "你是我的 Claude Code 設定稽核員。請對我這台機器做一次完整的 harness 稽核。\n\n" + body)

(ROOT / "commands" / "unhobble.md").write_text(
    "---\ndescription: 稽核這台機器的 Claude Code 設定——量出常駐 token 成本、"
    "抓出從未觸發的殭屍 skill、分出哪些規則只是舊模型的補丁,產出刪除計畫(唯讀,不會幫你刪)\n---\n\n"
    "你是 Claude Code 設定稽核員。對這台機器做一次完整 harness 稽核。\n\n" + body)

print("PROMPT.md", (ROOT / "PROMPT.md").stat().st_size, "bytes")
print("commands/unhobble.md", (ROOT / "commands" / "unhobble.md").stat().st_size, "bytes")
