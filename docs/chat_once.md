# Chat Once

## 機能概要

`Chat Once` は、OpenAI 互換 API サーバーへ単発のテキストチャットリクエストを送るための ComfyUI ノードです。1 回ごとに独立したリクエストとして扱い、会話履歴は内部保持しません。

接続先設定は `Compatible Endpoint` から受け取り、prompt の構築は `Prompt Preset` などから受け取れるようにします。

## 入力

| 名前 | 型 | 説明 |
| --- | --- | --- |
| `endpoint` | `COMPATIBLE_ENDPOINT` | 接続先設定ノードが出力した接続情報 |
| `system_prompt` | `STRING` | system role 用の prompt |
| `user_prompt` | `STRING` | user role 用の prompt |
| `temperature` | `FLOAT` | 生成の揺らぎを制御する値 |
| `max_tokens` | `INT` | 出力トークン上限。`0` の場合は body へ含めない |
| `top_p` | `FLOAT` | nucleus sampling 用パラメータ |
| `seed` | `INT` | サーバーが対応している場合に送る乱数シード |
| `timeout_seconds` | `FLOAT` | リクエストのタイムアウト秒数 |

## 出力

| 名前 | 型 | 説明 |
| --- | --- | --- |
| `text` | `STRING` | 応答テキスト |
| `response_json` | `STRING` | API 応答全体を JSON 文字列で返したもの |
| `finish_reason` | `STRING` | 応答終了理由 |
| `usage_json` | `STRING` | token usage などのメタ情報 |

## 処理仕様

- このノードは毎回独立した単発リクエストを送ります
- `endpoint` からベース URL、API キー、選択モデルを受け取ります
- request body は OpenAI 互換 chat completions 相当の形式を基本とします
- `system_prompt` と `user_prompt` の両方が空ならエラーにします
- 応答本文は `choices[0].message.content` を優先して取り出し、配列形式の content もテキスト連結して扱います
- `response_json` はデバッグや後続ノード利用向けに生に近い情報を残します

## 使用例

### 単発問い合わせの例

ローカルの OpenAI 互換 API へ「この文章を要約して」と送る場合、`Compatible Endpoint` と接続し、`user_prompt` に対象文を入れて 1 回だけ応答を得ます。

### プリセット併用の例

`Prompt Preset` から要約用の system prompt と template 展開済み user prompt を受け取り、そのまま `Chat Once` へ接続して利用します。

## 注意点 / 制約

- 初期仕様では会話履歴を内部保持しません
- ストリーミング応答は対象外です
- すべての OpenAI 互換サーバーが同じ generation パラメータを受け付けるとは限りません
- `seed` はサーバー非対応の可能性があります
- `model_name` が空の endpoint を渡すとエラーにします
- レスポンス形状の差異があるため、空応答時は例外になります
