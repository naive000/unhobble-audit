#!/usr/bin/env python3
"""unhobble-audit 量測器 — 確定性統計,輸出 JSON。

不用 find/grep,所以不受任何 shell 輸出改寫工具影響。
唯讀:只讀檔,不寫入、不刪除、不外傳。
"""
import json, os, re, sys, time
from pathlib import Path

HOME = Path.home()
UD = HOME / ".claude"          # 使用者層
PD = Path.cwd() / ".claude"    # 專案層

# 只有這兩個位置的 skill 會載入 context。plugins/cache、plugins/marketplaces、
# local-marketplaces、jobs 底下也有大量 SKILL.md,那些是已下載但未啟用的原始碼。
# cwd 就是 home 時 PD 會等於 UD,不能重複計算
_SAME = PD.resolve() == UD.resolve() if PD.exists() else False
SKILL_ROOTS = [("user", UD / "skills")] + ([] if _SAME else [("project", PD / "skills")])

RE_SKILL_TOOL = re.compile(rb'"name":"Skill","input":\{[^}]*"skill":"([^"]+)"')
RE_SLASH_CMD = re.compile(rb'<command-name>/([a-zA-Z0-9:_-]+)</command-name>')


def frontmatter_description(p: Path) -> int:
    """回傳 description 欄位的 byte 長度(含多行續行)。抓不到回 0。"""
    try:
        raw = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0
    if not raw.startswith("---"):
        return 0
    end = raw.find("\n---", 3)
    if end == -1:
        return 0
    fm, out, grabbing = raw[3:end], [], False
    for line in fm.splitlines():
        if re.match(r"^description\s*:", line):
            grabbing = True
            out.append(line)
        elif grabbing:
            # 續行:縮排或非 key 開頭
            if re.match(r"^[A-Za-z_][A-Za-z0-9_-]*\s*:", line):
                break
            out.append(line)
    return len("\n".join(out).encode("utf-8"))


def scan_skills():
    skills, warns = {}, []
    for layer, root in SKILL_ROOTS:
        if not root.is_dir():
            continue
        for entry in sorted(root.iterdir()):
            # symlink 指向 repo 外的 skill 目錄也要算(例:yt-radar)
            try:
                is_dir = entry.is_dir()  # 會跟隨 symlink
            except OSError:
                warns.append(f"無法讀取 {entry}")
                continue
            if not is_dir:
                continue
            sf = entry / "SKILL.md"
            if not sf.is_file():
                warns.append(f"{layer}/{entry.name}: 目錄存在但沒有 SKILL.md,未計入")
                continue
            skills[entry.name] = {
                "layer": layer,
                "symlink": entry.is_symlink(),
                "desc_bytes": frontmatter_description(sf),
                "mtime": int(sf.stat().st_mtime),
                "days_since_touch": round((time.time() - sf.stat().st_mtime) / 86400, 1),
            }
    return skills, warns


def scan_transcripts(skill_names):
    """兩條觸發路徑都要掃:模型自動觸發(Skill 工具)+ 使用者手打 /名稱。"""
    proj = UD / "projects"
    tool, cmd, files, nbytes = {}, {}, 0, 0
    if proj.is_dir():
        for dirpath, _, names in os.walk(proj):
            for n in names:
                if not n.endswith(".jsonl"):
                    continue
                p = Path(dirpath) / n
                files += 1
                try:
                    data = p.read_bytes()
                except OSError:
                    continue
                nbytes += len(data)
                for m in RE_SKILL_TOOL.finditer(data):
                    k = m.group(1).decode().split(":")[-1]
                    tool[k] = tool.get(k, 0) + 1
                for m in RE_SLASH_CMD.finditer(data):
                    k = m.group(1).decode().split(":")[-1]
                    cmd[k] = cmd.get(k, 0) + 1
    fired = {}
    for s in skill_names:
        t, c = tool.get(s, 0), cmd.get(s, 0)
        fired[s] = {"via_tool": t, "via_slash": c, "total": t + c}
    return fired, files, nbytes


def count_files(d: Path, pattern="*"):
    return len([p for p in d.glob(pattern) if p.is_file()]) if d.is_dir() else 0


def main():
    t0 = time.time()
    skills, warns = scan_skills()
    fired, njsonl, nbytes = scan_transcripts(skills.keys())
    NEW_DAYS = 30  # 距上次修改未滿這個天數的,沒觸發不代表沒用
    never = [k for k, v in fired.items() if v["total"] == 0]
    zombies = sorted(k for k in never if skills[k]["days_since_touch"] >= NEW_DAYS)
    too_new = sorted(k for k in never if skills[k]["days_since_touch"] < NEW_DAYS)

    rules = {}
    for label, p in [("user CLAUDE.md", UD / "CLAUDE.md"), ("user AGENTS.md", HOME / "AGENTS.md"),
                     ("project CLAUDE.md", Path.cwd() / "CLAUDE.md"),
                     ("project AGENTS.md", Path.cwd() / "AGENTS.md")]:
        if p.is_file():
            st = p.stat()
            rules[label] = {"bytes": st.st_size, "mtime": int(st.st_mtime)}

    # 只有「當前專案」的 MEMORY.md 會載入 context;其他專案的不會。
    # 也只算頂層 *.md——memory/archive/ 之類子目錄是歸檔,不進 context。
    def _mem(m: Path):
        if not m.is_dir():
            return {"files": 0, "index_bytes": 0, "archived": 0}
        idx = m / "MEMORY.md"
        arch = len([q for q in m.rglob("*.md") if q.parent != m])
        return {"files": count_files(m, "*.md"),
                "index_bytes": idx.stat().st_size if idx.is_file() else 0,
                "archived": arch}

    slug = "-" + str(Path.cwd()).strip("/").replace("/", "-")
    cur = _mem(UD / "projects" / slug / "memory")
    allp = {"files": 0, "index_bytes": 0, "archived": 0, "projects_with_memory": 0}
    projroot = UD / "projects"
    if projroot.is_dir():
        for d in projroot.iterdir():
            r = _mem(d / "memory")
            if r["files"]:
                allp["projects_with_memory"] += 1
            for k in ("files", "index_bytes", "archived"):
                allp[k] += r[k]

    mcp = 0
    for cfg in [UD / ".config.json", UD / ".claude.json"]:
        if cfg.is_file():
            try:
                mcp = max(mcp, len(json.loads(cfg.read_text()).get("mcpServers", {})))
            except Exception:
                pass

    out = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "elapsed_sec": round(time.time() - t0, 1),
        "skills": {
            "count": len(skills),
            "desc_bytes_total": sum(v["desc_bytes"] for v in skills.values()),
            "never_fired_count": len(never),
            "zombie_count": len(zombies),
            "zombie_pct": round(100 * len(zombies) / len(skills)) if skills else 0,
            "zombies": zombies,
            "too_new_to_judge": too_new,
            "new_threshold_days": NEW_DAYS,
            "detail": {k: {**skills[k], **fired[k]} for k in sorted(skills)},
        },
        "transcripts": {"jsonl_files": njsonl, "total_bytes": nbytes},
        "rules": rules,
        "memory": {"current_project": cur, "all_projects": allp,
                   "note": "只有 current_project.index_bytes 會載入 context"},
        "hooks": count_files(UD / "hooks"),
        "mcp_servers": mcp,
        "warnings": warns,
        "caveat": ("(1) 觸發次數 0 只代表『Skill 工具』與『手打 /名稱』兩條路徑沒看到;"
                   "被 cron/排程/外部腳本驅動的 skill 兩邊都不留痕跡,0 次要標成『待確認』"
                   "而非『確定可刪』。 (2) too_new_to_judge 裡的 skill 還沒有足夠時間觸發,"
                   "不算候選。 (3) days_since_touch 是『距上次修改』不是『安裝至今』——"
                   "改過舊 skill 會讓它看起來很新。"),
    }
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    print()


if __name__ == "__main__":
    main()
