# Discord Meeting Minutes Bot

Discordの特定ボイスチャンネルで会議を自動録音し、Markdown議事録を生成するBotです。

## 仕様
- 対象VC参加者が2人以上で録音開始
- 対象VCの参加者が0人で録音終了
- 音声をユーザー単位でWAV保存
- 10分ごとにチャンク分割
- Whisper APIで文字起こし
- LLMで「決定事項 / TODO / 各メンバー報告内容」を抽出
- `minutes/YYYYMMDD.md` に追記保存
- Discordテキストチャンネルへ投稿
- `audio/` `transcripts/` は7日後自動削除

## セットアップ
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
cp .env.example .env
```

`.env` に必要値を設定してください。

### LLM切替
- 文字起こしは常に Whisper(OpenAI) を使用
- 要約モデルは `.env` の `LLM_PROVIDER` で切替
  - `LLM_PROVIDER=openai`: `OPENAI_SUMMARY_MODEL` を使用
  - `LLM_PROVIDER=gemini`: `GEMINI_API_KEY` と `GEMINI_SUMMARY_MODEL` を使用

## 実行
```bash
python -m src.main
```

## Docker実行（1コマンド）
```bash
cp .env.example .env
# .env を編集
docker compose up --build
```

## Discord権限
Botに以下が必要です。
- View Channels
- Connect
- Speak
- Use Voice Activity
- Send Messages
- Read Message History

## コマンド
- `/meeting_status`
- `/meeting_force_stop`
- `/meeting_health`

## 注意
- 音声受信は `discord-ext-voice-recv` を利用します。
- Google Docs自動作成は行わず、`minutes/YYYYMMDD.md` を手動貼り付け運用です。
