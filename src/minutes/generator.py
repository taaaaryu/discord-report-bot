from __future__ import annotations

import json
from datetime import datetime

from google import genai
from openai import OpenAI

from models import MemberReport, MeetingDecision, MeetingMinutes, MeetingTodo, Utterance


class MinutesGenerator:
    def __init__(
        self,
        llm_provider: str,
        openai_api_key: str,
        openai_model: str,
        gemini_api_key: str | None = None,
        gemini_model: str = "gemini-1.5-flash",
    ) -> None:
        self.llm_provider = llm_provider
        self.openai_model = openai_model
        self.gemini_model = gemini_model
        self.openai_client: OpenAI | None = None
        self.gemini_client: genai.Client | None = None

        if llm_provider == "openai":
            self.openai_client = OpenAI(api_key=openai_api_key)
        elif llm_provider == "gemini":
            if not gemini_api_key:
                raise ValueError("GEMINI_API_KEY is required when LLM_PROVIDER=gemini")
            self.gemini_client = genai.Client(api_key=gemini_api_key)
        else:
            raise ValueError("llm_provider must be 'openai' or 'gemini'")

    def generate(self, title: str, dt: datetime, participant_names: list[str], utterances: list[Utterance]) -> MeetingMinutes:
        transcript_lines = []
        for u in sorted(utterances, key=lambda x: x.started_at_sec):
            transcript_lines.append(f"[{u.started_at_sec:0.1f}-{u.ended_at_sec:0.1f}] {u.speaker_name}: {u.text}")
        transcript = "\n".join(transcript_lines)

        schema = {
            "decisions": [{"text": "string"}],
            "todos": [{"task": "string", "owner": "string", "due": "YYYY-MM-DD or 未定"}],
            "reports": [{
                "speaker_name": "string",
                "progress": "string",
                "concerns": "string",
                "discussion": "string",
                "action": "string"
            }],
        }

        prompt = (
            "あなたは会議議事録作成アシスタントです。\n"
            "出力はJSONのみ。日本語で簡潔に。\n"
            "全体要約は不要。以下の順序に使うデータを抽出してください: 決定事項, TODO, 各メンバー報告。\n"
            "TODOのowner/dueが不明なら'未定'。\n"
            "reportsには発言者ごとに進捗・悩み/課題・相談内容・議論結果/次アクションを整理。\n"
            f"期待スキーマ: {json.dumps(schema, ensure_ascii=False)}\n\n"
            f"会議タイトル: {title}\n"
            f"参加者: {', '.join(participant_names)}\n"
            "会議ログ:\n"
            f"{transcript}"
        )

        raw = self._run_llm(prompt).strip()
        payload = self._parse_json(raw)

        decisions = [MeetingDecision(text=item.get("text", "")) for item in payload.get("decisions", []) if item.get("text")]
        todos = [
            MeetingTodo(
                task=item.get("task", ""),
                owner=item.get("owner", "未定") or "未定",
                due=item.get("due", "未定") or "未定",
            )
            for item in payload.get("todos", [])
            if item.get("task")
        ]
        reports = [
            MemberReport(
                speaker_name=item.get("speaker_name", "不明"),
                progress=item.get("progress", "なし"),
                concerns=item.get("concerns", "なし"),
                discussion=item.get("discussion", "なし"),
                action=item.get("action", "なし"),
            )
            for item in payload.get("reports", [])
        ]

        return MeetingMinutes(
            title=title,
            date_text=dt.strftime("%Y-%m-%d"),
            participants=participant_names,
            decisions=decisions,
            todos=todos,
            reports=reports,
        )

    def _run_llm(self, prompt: str) -> str:
        if self.llm_provider == "openai":
            if self.openai_client is None:
                raise RuntimeError("OpenAI client is not initialized")
            response = self.openai_client.responses.create(
                model=self.openai_model,
                input=prompt,
                temperature=0.2,
            )
            return response.output_text or ""

        if self.llm_provider == "gemini":
            if self.gemini_client is None:
                raise RuntimeError("Gemini client is not initialized")
            response = self.gemini_client.models.generate_content(
                model=self.gemini_model,
                contents=prompt,
                config={"temperature": 0.2},
            )
            return self._extract_gemini_text(response)

        raise RuntimeError(f"Unsupported llm_provider: {self.llm_provider}")

    @staticmethod
    def _parse_json(text: str) -> dict:
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:]
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start == -1 or end == -1:
                return {}
            return json.loads(text[start : end + 1])

    @staticmethod
    def _extract_gemini_text(response: object) -> str:
        text = getattr(response, "text", None)
        if isinstance(text, str) and text.strip():
            return text

        candidates = getattr(response, "candidates", None) or []
        collected: list[str] = []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            parts = getattr(content, "parts", None) or []
            for part in parts:
                part_text = getattr(part, "text", None)
                if isinstance(part_text, str) and part_text.strip():
                    collected.append(part_text)
        return "\n".join(collected)
