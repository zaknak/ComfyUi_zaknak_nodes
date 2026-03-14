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
| Compatible Endpoint | OpenAI 互換 API サーバーへの接続設定、モデル一覧取得、モデル選択用メタ情報を扱う | [docs/compatible_endpoint.md](docs/compatible_endpoint.md) | 実装済み |
| Prompt Preset | 外部 JSON ベース、または PyYAML 利用時の YAML ベースでプリセット定義を読み出し、再利用しやすい prompt 設定を提供する | [docs/prompt_preset.md](docs/prompt_preset.md) | 実装済み |
| Chat Once | OpenAI 互換 API へ単発のテキストチャットを送信し、応答文字列とメタ情報を得る | [docs/chat_once.md](docs/chat_once.md) | 実装済み |
| Vision Chat Once | ComfyUI の画像入力先頭 1 枚とテキストを OpenAI 互換 API へ送り、画像付き応答を得る | [docs/vision_chat_once.md](docs/vision_chat_once.md) | 実装済み |

## ドキュメント

- ノード仕様一覧: [docs/NODES.md](docs/NODES.md)
- Compatible LLM / VLM 系ノード概要: [docs/llm_vlm_overview.md](docs/llm_vlm_overview.md)

## 実装メモ

- Compatible LLM / VLM 系は追加依存なしの実装を優先し、HTTP 通信と画像 PNG 化は標準ライブラリで処理します
- `Compatible Endpoint` はモデル一覧を `models_json` と `status_text` で返し、現状は動的ドロップダウンではなく `model_name` 手入力中心です
- `Prompt Preset` の YAML 読み込みは `PyYAML` が利用可能な環境でのみ有効です

## License

Copyright (c) 2026 zaknak

This project is licensed under the MIT License.
