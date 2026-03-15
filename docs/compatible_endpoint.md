# Compatible Endpoint

## 機能概要

`Compatible Endpoint` は、外部で起動している OpenAI 互換 API サーバーへの接続設定をまとめて扱うための ComfyUI ノードです。ベース URL、API キー、モデル一覧取得、既定モデルの決定を担当し、後続のチャット送信ノードから再利用できる接続情報を提供します。

このノードは、実際のチャット送信を行いません。接続先に関する責務を分離し、送信ノード側の UI と責務を軽く保つことを目的とします。

## 入力

| 名前 | 型 | 説明 |
| --- | --- | --- |
| `base_url` | `STRING` | OpenAI 互換 API サーバーのベース URL。例: `http://127.0.0.1:1234/v1` |
| `api_key` | `STRING` | API キー。ローカル用途では空欄許容を基本とするが、必要なサーバーでは利用する |
| `model_name` | `STRING` | 利用するモデル名。空欄時は取得したモデル一覧から既定値を決定する |
| `refresh_models` | `BOOLEAN` | `true` の場合、`/models` 取得を試みる |
| `timeout_seconds` | `FLOAT` | モデル一覧取得に用いるタイムアウト秒数 |

初期実装では、認証方式は Bearer Token 相当の API キー入力に限定します。複数認証方式は将来拡張とします。

## 出力

| 名前 | 型 | 説明 |
| --- | --- | --- |
| `endpoint` | `COMPATIBLE_ENDPOINT` | 後続ノードへ渡す接続設定 |
| `model_name` | `STRING` | 最終的に選択または採用されたモデル名 |
| `models_json` | `STRING` | 取得できたモデル一覧の JSON 文字列。取得失敗時はエラー要約を含む |
| `status_text` | `STRING` | 接続確認や取得結果を要約した表示用文字列 |

## 処理仕様

- `base_url` はチャット系 API とモデル一覧取得 API の共通ベースとして扱います
- `refresh_models=true` の場合、`/models` 取得を試みます
- モデル一覧取得に成功し、`model_name` が空なら、取得一覧の先頭モデルを既定値として採用します
- モデル一覧取得に成功しても一覧が空なら、自動選択は行いません
- モデル一覧取得に失敗または非対応の場合でも、`model_name` の手動入力で利用を継続できます
- `api_key` が空でも接続先が受け付ける場合はそのまま利用できます
- `status_text` には取得件数、既定値の自動採用有無、手入力モデルの妥当性などを要約します
- より明示的に別モデルを選びたい場合は、`models_json` を `Compatible Model List View` と `Compatible Model Selector` へ渡し、一覧確認と選択を分離できます

## 使用例

### 既定モデルをそのまま使う例

`base_url=http://127.0.0.1:1234/v1` を指定し、`refresh_models=true` で一覧取得を試します。`model_name` が空なら、取得できたモデル一覧の先頭要素が自動的に採用されます。

### 一覧取得後に別モデルを選ぶ例

`Compatible Endpoint` の `models_json` を `Compatible Model List View` へ渡すと、`index: model_name` の一覧文字列を確認できます。同じ `models_json` を `Compatible Model Selector` へも渡し、必要な `model_index` を指定して `model_name` を取り出します。取得した名前は別の入力経路で再利用し、ワークフロー側で採用モデルを切り替えます。

### API キー不要サーバーの例

ローカルサーバーが認証不要であれば `api_key` を空のまま使います。この場合も、後続ノードは同じ `endpoint` 出力を受け取って送信できます。

## 注意点 / 制約

- モデル一覧取得 API は、すべての OpenAI 互換サーバーで同一挙動とは限りません
- モデル一覧取得失敗は致命エラーにしない方針ですが、実際の送信時には指定モデル名が無効な場合があります
- ベース URL の末尾スラッシュは内部で除去します
- 初期仕様ではプロキシ設定やカスタムヘッダーは扱いません
- 接続可否の確認と実際の推論成功は必ずしも一致しません
