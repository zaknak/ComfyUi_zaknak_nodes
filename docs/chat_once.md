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

- このノードは毎回独立した単発リクエストを送ります
- `endpoint` からベース URL、API キー、選択モデルを受け取ります
- request body は OpenAI 互換 chat completions 相当の形式を基本とします
- 通常の request body には `max_tokens` と `seed` を含めます
- `system_prompt` と `user_prompt` の両方が空ならエラーにします
- `extra_body_toml` が空でなければ TOML として解釈し、root table の場合だけ既存 payload へ浅く追加マージします
- `extra_body_toml` が TOML として解釈できない場合はエラーにします
- `extra_body_toml` に `model`、`messages`、`max_tokens`、`seed` など既存 payload と衝突するキーが含まれていた場合はエラーにします
- `extra_body_toml` では `temperature` と `top_p` を追加指定できます
- 値は JSON payload へ変換可能な TOML 型だけを扱い、string / int / float / bool / array / table / inline table を許可します
- TOML の date / time / datetime は JSON への暗黙変換を行わず、明示的エラーにします
- TOML 内の文字列値は `Prompt Preset` の `variables_toml` と同様に LF へ正規化してから payload へ入れます
- 応答本文は `choices[0].message.content` を優先して取り出し、配列形式の content もテキスト連結して扱います
- `strict_finish_reason=true` の場合、`finish_reason` が厳密に `stop` のときだけ成功とし、それ以外はエラーとして実行を中断します
- `strict_finish_reason=false` の場合、`finish_reason` は検証せずそのまま出力します
- `strip_think_tags=true` の場合、`text` 出力に対して `<think>...</think>` 区間を削除します
- 推論開始タグ `<think>` が無く、`</think>` だけが出力される不正系では、先頭から最初の `</think>` までを推論ログとして削除し、その直後の改行・空白も削除します
- `response_json` はデバッグや後続ノード利用向けに生に近い情報を残し、`strip_think_tags` の影響を受けません

## 使用例

### 単発問い合わせの例

ローカルの OpenAI 互換 API へ「この文章を要約して」と送る場合、`Compatible Endpoint` と接続し、`user_prompt` に対象文を入れて 1 回だけ応答を得ます。

### プリセット併用の例

`Prompt Preset` から要約用の system prompt と template 展開済み user prompt を受け取り、そのまま `Chat Once` へ接続して利用します。

### 追加オプション付与の例

`extra_body_toml` に以下のような TOML を入れると、標準入力で構成した payload に追加パラメータを付けて送信できます。

```toml
temperature = 0.7
top_p = 0.9

[response_format]
type = "json_object"
```

### 推論ログ除去の例

モデルが `<think>...</think>` を含む応答を返す場合、`strip_think_tags=true` にすると `text` 出力からその部分だけを除去できます。`response_json` には元の API 応答がそのまま残ります。

## 注意点 / 制約

- 初期仕様では会話履歴を内部保持しません
- ストリーミング応答は対象外です
- すべての OpenAI 互換サーバーが同じ generation パラメータを受け付けるとは限りません
- `seed` はサーバー非対応の可能性があります
- `extra_body_toml` は root table を持つ TOML のみを受け付けます
- `extra_body_toml` で `model`、`messages`、`max_tokens`、`seed` を上書きすることはできません
- `temperature` と `top_p` はノード入力にはありませんが、必要なら `extra_body_toml` で追加指定できます
- `extra_body_toml` では TOML の date / time / datetime を使えません
- `strict_finish_reason` の既定値は `true` です
- `strict_finish_reason=true` の場合、`finish_reason` が `stop` 以外、空文字、未設定ならエラーになります
- `strip_think_tags` の既定値は `false` です
- `strip_think_tags` は `text` 出力だけに適用され、`response_json` は変更しません
- `Compatible Endpoint` の既定モデル採用や手動入力の結果として `endpoint.model_name` が空でなければ送信できます
- `endpoint.model_name` が空のまま渡された場合はエラーにします
- レスポンス形状の差異があるため、空応答時は例外になります
