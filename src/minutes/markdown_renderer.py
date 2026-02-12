from __future__ import annotations

from models import MeetingMinutes


class MarkdownRenderer:
    def render(self, minutes: MeetingMinutes) -> str:
        lines: list[str] = []
        lines.append(f"# 日次会議議事録（{minutes.date_text}）")
        lines.append("")
        lines.append(f"- 会議名: {minutes.title}")
        lines.append(f"- 参加者: {', '.join(minutes.participants) if minutes.participants else '不明'}")
        lines.append("")

        lines.append("## 決定事項")
        if minutes.decisions:
            for d in minutes.decisions:
                lines.append(f"- {d.text}")
        else:
            lines.append("- なし")
        lines.append("")

        lines.append("## TODO")
        if minutes.todos:
            for t in minutes.todos:
                owner = t.owner if t.owner else "未定"
                due = t.due if t.due else "未定"
                lines.append(f"- [ ] {t.task}（担当: {owner} / 期限: {due}）")
        else:
            lines.append("- [ ] なし（担当: 未定 / 期限: 未定）")
        lines.append("")

        lines.append("## 各メンバー報告内容")
        if minutes.reports:
            for r in minutes.reports:
                lines.append(f"### {r.speaker_name}")
                lines.append(f"- 進捗: {r.progress}")
                lines.append(f"- 悩み/課題: {r.concerns}")
                lines.append(f"- 相談内容: {r.discussion}")
                lines.append(f"- 議論結果/次アクション: {r.action}")
                lines.append("")
        else:
            lines.append("- 報告なし")

        return "\n".join(lines).rstrip()
