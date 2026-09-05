# unhobble-audit

**量出你的 Claude Code 設定到底有多肥,然後告訴你哪些可以刪。**

這是一個 slash command,不是 skill。

## 為什麼不是 skill

Skill 的 description 每個 session 都常駐在 context 裡,**不管有沒有被觸發**。發一個叫你清 context 的工具,結果它自己永久佔你的 context——裝的人越多反效果越大。

所以這個工具是 slash command:呼叫才載入,平常在清單裡只佔一行。這也是它自己的稽核結論之一。

## 它會告訴你什麼

不是「你的 skill 太多了」這種誰都會講的話,是實數:

```
常駐 overhead: 54,042 tokens/turn
Skills: 34 個,16 個從未觸發;扣掉太新的,6 個確定閒置 (18%)
Skill descriptions: 23 KB 常駐
Memory: 99 檔 / 索引 21 KB
```

上面是作者自己機器的實際數字。每個 skill 的 description 不管有沒有觸發都常駐在 context,每一輪對話都在付租金。

所有數字由 [`scripts/measure.py`](./scripts/measure.py) 產出——確定性腳本,不用 `find`/`grep`,所以不受 shell 輸出改寫工具影響,路徑也寫死。

這不是潔癖。實測散文版指令的結果:記錄檔數 2088 被算成 4、skill 數 34 被算成 37。而 `find ~/.claude -name SKILL.md` 會掃到 `plugins/cache/`、`plugins/marketplaces/` 底下幾百個未啟用的原始碼,得到約 690——真實載入數是 34,差 20 倍。

殭屍判定經過兩道防偽:

**兩條觸發路徑都掃**(模型自動觸發 + 使用者手打 `/名稱`)。只掃其中一條會多算四個假殭屍,其中一個實際上被手動叫過 37 次。

**剛裝的不算數。**距上次修改未滿 30 天的 skill 還沒有足夠時間觸發,單獨列成「太新無法判斷」而不是刪除候選。作者機器上 16 個從未觸發的 skill 裡有 10 個屬於這類,其中一個才裝了半天——不排除的話數字會難看三倍,而且是假的。

七個階段:靜態足跡 → 真實 token 成本 → 殭屍 skill 偵測 → 規則年齡 → 補丁 vs 偏好分類 → 驗證機制與維護迴圈缺口 → 刪除計畫。

## 兩種用法

**零安裝**——複製 [`PROMPT.md`](./PROMPT.md) 裡那段貼進 Claude Code 就跑。

**裝起來**——`/plugin install`(或把 `commands/unhobble.md` 丟進 `~/.claude/commands/`),之後打 `/unhobble`。

## 安全性

- **全程唯讀**,不刪除、不修改、不移動任何設定檔
- **不外傳**,讀到的內容只在本機分析
- **絕不自動刪東西**,只出建議清單,第一步強制要你備份
- 分類時把「安全閘門、credential 保護、輸出偏好」歸為**必須留**,不確定的一律歸必須留——不會害你刪掉防護

Phase 2 量 token 成本會花掉你一次 API 額度,執行前會先問你。

## 方法論出處

概念來自 Claude Code 作者 Boris Cherny 在 Y Combinator 的對談([影片](https://youtu.be/qyPCVqFUyDo),2026-07-27)——他們每次新模型發布都會刪掉大部分 system prompt,Opus 5 那次砍了 80%,理由是舊指令多半只是「修正模型以前不會、現在已經會了的行為」的補丁。他建議使用者每半年也刪一次自己的 CLAUDE.md、skills、hooks。

這個工具把那個建議變成可量測的稽核。內容為作者重新撰寫,非影片轉錄。

## License

MIT
