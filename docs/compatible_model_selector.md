# Compatible Model Selector

## 機能概要

`Compatible Model Selector` は、`Compatible Endpoint` が出力した `models_json` からモデル名を取り出すための ComfyUI ノードです。接続先問い合わせは行わず、取得済みのモデル一覧 JSON を参照して、指定 index のモデル名だけを `model_name` として返します。

`Compatible Endpoint` が接続設定と一覧取得を担当し、このノードが一覧からの選択を担当することで、Compatible LLM 系ノードの責務を分離します。

## 入力

| 名前 | 型 | 説明 |
| --- | --- | --- |
| `models_json` | `STRING` | `Compatible Endpoint` が返したモデル一覧 JSON |
| `model_index` | `INT` | 先頭を `0` とする選択 index |

## 出力

| 名前 | 型 | 説明 |
| --- | --- | --- |
| `model_name` | `STRING` | 指定 index に対応するモデル名。選択不能時は空文字 |

## 処理仕様

- `models_json` は OpenAI 互換の `/models` 応答相当を想定します
- `data[].id` を優先し、`id` がなければ `name` を参照します
- `models_json` 自体が文字列配列である場合もモデル一覧として扱います
- `model_index` が範囲外の場合は空文字を返します
- `models_json` が空、不正 JSON、または有効なモデル一覧を含まない場合は空文字を返します
- このノードは接続設定や HTTP リクエストを持たず、モデル名選択だけを責務にします

## 使用例

### 取得済み一覧から 2 件目を選ぶ例

`Compatible Endpoint` の `models_json` を接続し、`model_index=1` を指定すると、一覧の 2 件目のモデル名を `model_name` として取得できます。

### 一覧が取得できない接続先の例

`models_json` が空またはエラー内容のみを含む場合、このノードは空文字を返します。その場合は `Compatible Endpoint` 側の手動 `model_name` 入力や既定モデル採用を利用します。

## 注意点 / 制約

- ComfyUI 標準 UI の制約上、このノードは現時点で動的ドロップダウンではなく index 指定で選択します
- 一覧順序は接続先サーバーの応答順に依存します
- このノード単体では接続先情報を保持しません
