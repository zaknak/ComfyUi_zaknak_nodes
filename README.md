# comfyui_zaknak_nodes

ComfyUI で使う私的なカスタムノードを追加していくためのリポジトリです。ノードの概要はこの README に、各ノードの詳細仕様は `docs/` 配下のドキュメントを参照してください。

このリポジトリでは、画像処理ノードに加えて、ローカルで起動している OpenAI 互換 API サーバーを利用する Compatible LLM / VLM 系ノード群も追加しています。これらのノードは ComfyUI 内でモデルを起動するものではなく、外部で起動した API サーバーへリクエストを送るためのものです。

## インストール

ComfyUI の `custom_nodes` ディレクトリ配下にこのリポジトリを配置してください。

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/zaknak/ComfyUi_zaknak_nodes.git
```

その後、ComfyUI を再起動してください。

## ノード一覧

| Node | 概要 | 詳細 | 状態 |
| --- | --- | --- | --- |
| Mosaic By Mask | 画像とマスクを入力し、白側マスク領域にモザイクを適用する。mask バッチの内部結合モードあり | [docs/mosaic_by_mask.md](docs/mosaic_by_mask.md) | 実装済み |
| Censor Bars By Mask | 画像とマスクを入力し、マスク領域を複数の平行帯で隠す。mask バッチの内部結合モードあり | [docs/censor_bars_by_mask.md](docs/censor_bars_by_mask.md) | 実装済み |
| Compatible Endpoint | OpenAI 互換 API サーバーへの接続設定、モデル一覧取得、既定モデルの決定を扱う | [docs/compatible_endpoint.md](docs/compatible_endpoint.md) | 実装済み |
| Compatible Model List View | `Compatible Endpoint` の `models_json` を `index: model_name` の一覧文字列へ整形して表示確認しやすくする | [docs/compatible_model_list_view.md](docs/compatible_model_list_view.md) | 実装済み |
| Compatible Model Selector | `Compatible Endpoint` の `models_json` から index 指定でモデル名を選び、`model_name` のみを出力する | [docs/compatible_model_selector.md](docs/compatible_model_selector.md) | 実装済み |
| Prompt Preset | 外部 TOML ファイルから prompt プリセット定義を読み出し、再利用しやすい prompt 設定を提供する | [docs/prompt_preset.md](docs/prompt_preset.md) | 実装済み |
| Bundled Prompt Preset | リポジトリ同梱の既定 TOML から prompt プリセットを読み出し、表示名で選択して使う | [docs/bundled_prompt_preset.md](docs/bundled_prompt_preset.md) | 実装済み |
| Chat Once | OpenAI 互換 API へ単発のテキストチャットを送信し、応答文字列とメタ情報を得る | [docs/chat_once.md](docs/chat_once.md) | 実装済み |
| Vision Chat Once | ComfyUI の画像入力先頭 1 枚とテキストを OpenAI 互換 API へ送り、画像付き応答を得る | [docs/vision_chat_once.md](docs/vision_chat_once.md) | 実装済み |

## ドキュメント

- ノード仕様一覧: [docs/NODES.md](docs/NODES.md)
- Compatible LLM / VLM 系ノード概要: [docs/llm_vlm_overview.md](docs/llm_vlm_overview.md)

## 実装メモ

- Compatible LLM / VLM 系は追加依存なしの実装を優先し、HTTP 通信と画像 PNG 化は標準ライブラリで処理します
- `Compatible Endpoint` はモデル一覧を `models_json` と `status_text` で返し、`model_name` が空かつ一覧取得成功時は先頭モデルを既定値として採用します
- モデル一覧から別のモデルを選びたい場合は `Compatible Model List View` で index 対応を確認し、`Compatible Model Selector` で `model_name` を取り出します
- `Prompt Preset` は `tomli` を使って `.toml` のみを読み込み、`input_text` を `input` 変数として扱います
- `Prompt Preset` の追加変数は `variables_toml` で与え、同名なら個別欄の `input_text` が優先されます
- `variables_toml` はフラットな TOML key-value のみを受け付け、array / table / inline table は扱いません
- `Prompt Preset` は未解決変数をコンソールへ出力し、`keep_unresolved_variables` で出力へ残すか空文字にするかを切り替えられます
- `Bundled Prompt Preset` はリポジトリ同梱の既定 `.toml` を固定で読み込み、`label` を使ってプリセットを選択します
- `Chat Once` / `Vision Chat Once` の追加 body パラメータは `extra_body_toml` で与え、`Prompt Preset` と同じく TOML ベースで統一します

## Prompt Preset TOML 例

```toml
version = 1

[presets.summary]
label = "Summary"
system = """
You are a helpful assistant.
Answer in Japanese.
Style: {{style}}
Instruction:
{{instruction}}
"""
user = """
以下を要約してください。

{{input}}
"""
```

UI 入力例:

```text
input_text = 要約対象の本文
```

```toml
style = "concise"
instruction = """
Use short paragraphs.
Avoid bullet points unless necessary.
"""
```

## License

Copyright (c) 2026 zaknak

This project is licensed under the MIT License.
