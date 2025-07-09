# discord-report-bot

Discordのボイスチャンネルの会話を録音し、文字起こしを行って議事録を生成するボットです。録音した音声はOpenAI Whisperで文字起こしを行い、ChatGPTで議題ごとにまとめたMarkdownを出力します。環境変数にGoogleのサービスアカウントを指定すれば自動的にGoogle Docsへ書き込むこともできます。

## 使い方

1. `python -m venv venv && source venv/bin/activate`
2. `pip install -r requirements.txt`
3. 以下の環境変数を設定します。
   - `DISCORD_TOKEN` - Discordボットのトークン
   - `OPENAI_API_KEY` - OpenAI APIキー
   - `GOOGLE_APPLICATION_CREDENTIALS` - (任意) Google Docsへ書き込むためのサービスアカウントキーのJSONパス
4. `python bot.py` を実行します。

ボイスチャンネルで `!start` を実行すると録音を開始し、`!stop` で終了します。録音が終了すると `recordings/minutes.md` に議事録が保存され、Google Docs の設定がある場合は新規ドキュメントにも内容が書き込まれます。

※ 音声処理には `ffmpeg` のインストールが必要です。
\n録音ファイルや仮想環境をリポジトリに含めないように`.gitignore`を用意しています。
