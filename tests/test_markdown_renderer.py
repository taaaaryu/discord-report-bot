from minutes.markdown_renderer import MarkdownRenderer
from models import MemberReport, MeetingDecision, MeetingMinutes, MeetingTodo


def test_markdown_section_order_and_member_report() -> None:
    minutes = MeetingMinutes(
        title="日次会議",
        date_text="2026-02-09",
        participants=["alice", "bob"],
        decisions=[MeetingDecision(text="A案で進める")],
        todos=[MeetingTodo(task="API実装", owner="alice", due="未定")],
        reports=[
            MemberReport(
                speaker_name="alice",
                progress="実装中",
                concerns="認証仕様が曖昧",
                discussion="認証方式を比較",
                action="明日までに提案",
            )
        ],
    )

    md = MarkdownRenderer().render(minutes)

    idx_decisions = md.index("## 決定事項")
    idx_todo = md.index("## TODO")
    idx_reports = md.index("## 各メンバー報告内容")

    assert idx_decisions < idx_todo < idx_reports
    assert "### alice" in md
    assert "- 進捗: 実装中" in md
    assert "- 悩み/課題: 認証仕様が曖昧" in md
