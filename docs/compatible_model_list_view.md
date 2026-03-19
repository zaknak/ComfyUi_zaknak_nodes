# Compatible Model List View

## 機能概要

`Compatible Model List View` は、`Compatible Endpoint` が出力した `models_json` を確認しやすい一覧文字列へ整形するための ComfyUI ノードです。接続先問い合わせは行わず、取得済みのモデル一覧 JSON を参照して、`index: model_name` 形式の複数行文字列を返します。

`Compatible Model Selector` がモデル名選択を担当し、このノードが一覧確認を担当することで、選択 UI を単純に保ちながら index 対応を把握しやすくします。

## 入力

| 名前 | 型 | 説明 |
| --- | --- | --- |
| `models_json` | `STRING` | `Compatible Endpoint` が返したモデル一覧 JSON |

## 出力

| 名前 | 型 | 説明 |
| --- | --- | --- |
| `models_list_text` | `STRING` | `index: model_name` 形式で並べたモデル一覧 |

## 処理仕様

- `models_json` は OpenAI 互換の `/models` 応答相当を想定します
- `data[].id` を優先し、`id` がなければ `name` を参照します
- `models_json` 自体が文字列配列である場合もモデル一覧として扱います
- 有効なモデル一覧があれば `0: model-a` のような複数行文字列を返します
- `models_json` が空、不正 JSON、または有効なモデル一覧を含まない場合は空文字を返します
- このノードは接続設定や HTTP リクエストを持たず、一覧表示だけを責務にします

## 使用例

### 一覧確認後に別ノードで選ぶ例

`Compatible Endpoint` の `models_json` を `Compatible Model List View` に接続すると、モデル一覧を `index: model_name` 形式で確認できます。同じ `models_json` を `Compatible Model Selector` にも渡し、見つけた index を `model_index` に指定して `model_name` を取り出します。

## 注意点 / 制約

- ComfyUI 標準 UI の制約上、このノードは一覧文字列を返すだけで、動的ドロップダウンは提供しません
- 一覧順序は接続先サーバーの応答順に依存します
- このノード単体では接続先情報を保持しません
