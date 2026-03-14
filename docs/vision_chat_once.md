# Vision Chat Once

## 機能概要

`Vision Chat Once` は、ComfyUI の `IMAGE` 入力とテキスト prompt を OpenAI 互換 API サーバーへ送り、画像付きの単発チャットを実行するためのノードです。VLM での説明、分類、タグ付け、判定などの用途を想定します。

テキスト専用ノードと分離し、画像エンコードや画像対応モデル制約をこのノード側の責務として扱います。

## 入力

| 名前 | 型 | 説明 |
| --- | --- | --- |
| `endpoint` | `COMPATIBLE_ENDPOINT` | 接続先設定ノードが出力した接続情報 |
| `image` | `IMAGE` | ComfyUI から渡される画像入力。現状はバッチ先頭 1 枚を使用 |
| `system_prompt` | `STRING` | system role 用の prompt |
| `user_prompt` | `STRING` | 画像と併せて送る user prompt |
| `image_detail` | `STRING` | API が対応している場合の画像 detail 指定。`auto` / `low` / `high` |
| `temperature` | `FLOAT` | 生成の揺らぎを制御する値 |
| `max_tokens` | `INT` | 出力トークン上限。`0` の場合は body へ含めない |
| `timeout_seconds` | `FLOAT` | リクエストのタイムアウト秒数 |

## 出力

| 名前 | 型 | 説明 |
| --- | --- | --- |
| `text` | `STRING` | 応答テキスト |
| `response_json` | `STRING` | API 応答全体を JSON 文字列で返したもの |
| `finish_reason` | `STRING` | 応答終了理由 |
| `usage_json` | `STRING` | token usage などのメタ情報 |

## 処理仕様

- `IMAGE` 入力は先頭 1 枚だけを使用し、標準ライブラリで PNG 化して data URL として送ります
- メッセージ形式は OpenAI 互換の `image_url` 形式を想定します
- `user_prompt` は画像と一緒に送る補助テキストとして扱います
- `system_prompt` が空でも送信できます
- 応答本文は `choices[0].message.content` を優先して取り出します

## 使用例

### 画像説明の例

ComfyUI で生成した画像をそのまま `image` へ渡し、「この画像の内容を簡潔に説明して」と問い合わせます。応答テキストは後続ノードでログや別処理へ回せます。

### タグ抽出の例

画像入力に対して `Prompt Preset` からタグ抽出用 prompt を与え、VLM にタグやキャプションを生成させます。

## 注意点 / 制約

- すべての OpenAI 互換 API サーバーが画像入力形式に対応しているわけではありません
- 画像対応モデルと非対応モデルがあるため、モデル選択だけでは成功可否を保証できない場合があります
- 現在の実装は複数画像、動画、フレーム列に対応しません
- 画像バッチが複数枚でも、先頭 1 枚だけを使用します
- 画像非対応モデルや接続先仕様差異による失敗時は例外になります
