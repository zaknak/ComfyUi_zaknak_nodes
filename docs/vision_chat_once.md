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
| `max_tokens` | `INT` | 出力トークン上限。既定値は `10240`。`0` の場合は body へ含めない |
| `seed` | `INT` | サーバーが対応している場合に送る乱数シード |
| `extra_body_toml` | `STRING` | POST body へ追加マージする TOML 文字列。空文字は追加なし |
| `strict_finish_reason` | `BOOLEAN` | `true` の場合、`finish_reason` が厳密に `stop` でなければエラーにする |
| `strip_think_tags` | `BOOLEAN` | `true` の場合、`text` 出力から `<think>` 推論ログ部分を除去する |
| `timeout_seconds` | `FLOAT` | リクエストのタイムアウト秒数 |

## 出力

| 名前 | 型 | 説明 |
| --- | --- | --- |
| `text` | `STRING` | 応答テキスト。`strip_think_tags=true` の場合は後処理後の文字列 |
| `response_json` | `STRING` | API 応答全体を JSON 文字列で返したもの |
| `finish_reason` | `STRING` | 応答終了理由 |
| `usage_json` | `STRING` | token usage などのメタ情報 |

## 処理仕様

- `IMAGE` 入力は先頭 1 枚だけを使用し、標準ライブラリで PNG 化して data URL として送ります
- メッセージ形式は OpenAI 互換の `image_url` 形式を想定します
- `user_prompt` は画像と一緒に送る補助テキストとして扱います
- `system_prompt` が空でも送信できます
- リクエスト body は OpenAI 互換 chat completions 相当の形式を基本とし、通常は `max_tokens` と `seed` を含めて送ります
- `extra_body_toml` が空でなければ TOML として解釈し、root table の場合だけ既存 payload へ浅く追加マージします
- `extra_body_toml` が TOML として解釈できない場合はエラーにします
- `extra_body_toml` に `model`、`messages`、`max_tokens`、`seed` など既存 payload と衝突するキーが含まれていた場合はエラーにします
- `extra_body_toml` では `temperature` を追加指定できます
- 値は JSON payload へ変換可能な TOML 型だけを扱い、string / int / float / bool / array / table / inline table を許可します
- TOML の date / time / datetime は JSON への暗黙変換を行わず、明示的エラーにします
- TOML 内の文字列値は `Prompt Preset` の `variables_toml` と同様に LF へ正規化してから payload へ入れます
- 応答本文は `choices[0].message.content` を優先して取り出します
- `strict_finish_reason=true` の場合、`finish_reason` が厳密に `stop` のときだけ成功とし、それ以外はエラーとして実行を中断します
- `strict_finish_reason=false` の場合、`finish_reason` は検証せずそのまま出力します
- `strip_think_tags=true` の場合、`text` 出力に対して `<think>...</think>` 区間を削除します
- 推論開始タグ `<think>` が無く、`</think>` だけが出力される不正系では、先頭から最初の `</think>` までを推論ログとして削除し、その直後の改行・空白も削除します
- `response_json` はデバッグ用の生レスポンスとして残し、`strip_think_tags` の影響を受けません

## 使用例

### 画像説明の例

ComfyUI で生成した画像をそのまま `image` へ渡し、「この画像の内容を簡潔に説明して」と問い合わせます。応答テキストは後続ノードでログや別処理へ回せます。

### タグ抽出の例

画像入力に対して `Prompt Preset` からタグ抽出用 prompt を与え、VLM にタグやキャプションを生成させます。

### 再現性を狙う例

同じ画像、同じ prompt、同じ generation パラメータで比較したい場合は `seed` を固定し、接続先が対応していれば再現性のある応答傾向を狙えます。

### 追加オプション付与の例

`extra_body_toml` に以下のような TOML を入れると、画像付き payload に追加パラメータを付けて送信できます。

```toml
temperature = 0.7

[response_format]
type = "json_object"
```

### 推論ログ除去の例

推論ログを `<think>...</think>` で返すモデルを使う場合、`strip_think_tags=true` にすると `text` 出力だけを整形し、本文だけを後続ノードへ渡せます。

## 注意点 / 制約

- すべての OpenAI 互換 API サーバーが画像入力形式に対応しているわけではありません
- 画像対応モデルと非対応モデルがあるため、モデル選択だけでは成功可否を保証できない場合があります
- 現在の実装は複数画像、動画、フレーム列に対応しません
- 画像バッチが複数枚でも、先頭 1 枚だけを使用します
- `seed` はサーバー非対応の可能性があります
- `extra_body_toml` は root table を持つ TOML のみを受け付けます
- `extra_body_toml` で `model`、`messages`、`max_tokens`、`seed` を上書きすることはできません
- `temperature` はノード入力にはありませんが、必要なら `extra_body_toml` で追加指定できます
- `extra_body_toml` では TOML の date / time / datetime を使えません
- `strict_finish_reason` の既定値は `true` です
- `strict_finish_reason=true` の場合、`finish_reason` が `stop` 以外、空文字、未設定ならエラーになります
- `strip_think_tags` の既定値は `false` です
- `strip_think_tags` は `text` 出力だけに適用され、`response_json` は変更しません
- 画像非対応モデルや接続先仕様差異による失敗時は例外になります
