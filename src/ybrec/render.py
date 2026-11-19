"""Turn API payloads into readable Markdown."""
from __future__ import annotations

import datetime as dt
import re


def ts(ms: int | None) -> str:
    if not ms:
        return ""
    return dt.datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M")


def clock(ms: int | None) -> str:
    s = int((ms or 0) // 1000)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def duration(ms: int | None) -> str:
    return clock(ms)


def safe_name(s: str, limit: int = 40) -> str:
    s = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", s or "").strip(" ._")
    return s[:limit] or "untitled"


def _speaker_map(data: dict) -> dict:
    roles = data.get("voiceIdRoles") or {}
    out = {}
    for key, r in roles.items():
        vid = str(r.get("voiceId", key))
        out[vid] = r.get("nickname") or ""
    return out


def transcript_md(meta: dict, data: dict) -> str:
    names = _speaker_map(data)
    lines = [f"# {meta.get('title', '')}", "", f"- 时间：{ts(meta.get('startTime'))}",
             f"- 时长：{duration(meta.get('durationMs'))}", ""]
    prev = None
    for s in data.get("voiceSentence") or []:
        text = (s.get("sourceText") or "").strip()
        if not text:
            continue
        vid = str(s.get("voiceId", ""))
        who = names.get(vid) or (f"说话人{int(vid) + 1}" if vid.isdigit() else vid or "说话人")
        if who != prev:
            lines += ["", f"**{who}** [{clock(s.get('startTime'))}]"]
            prev = who
        lines.append(text)
    return "\n".join(lines).strip() + "\n"


def summary_md(meta: dict, summary: dict, minutes: list) -> str:
    out = [f"# {meta.get('title', '')}", "", f"- 时间：{ts(meta.get('startTime'))}",
           f"- 时长：{duration(meta.get('durationMs'))}", ""]
    if summary.get("summary"):
        out += [summary["summary"].strip(), ""]
    chapters = [m for m in minutes if not m.get("isDeleted") and (m.get("content") or "").strip()]
    if chapters:
        out += ["---", "", "## 章节纪要", ""]
        for m in sorted(chapters, key=lambda m: m.get("startTime") or 0):
            out += [m["content"].strip(), ""]
    return "\n".join(out).strip() + "\n"
