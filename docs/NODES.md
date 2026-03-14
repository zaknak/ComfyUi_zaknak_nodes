# Docs

このディレクトリには、各 ComfyUI カスタムノードの仕様書を配置します。

## ルール

- 1 ノードにつき 1 つの Markdown ファイルを作成します
- ノード追加時は、このディレクトリに対応する仕様書を追加します
- `README.md` のノード一覧から、各仕様書へリンクします
- 複数ノードにまたがる共通方針がある場合は、系列全体の概要ドキュメントを別途追加してよいものとします

## ノード仕様一覧

### Image

- [Mosaic By Mask](mosaic_by_mask.md): 白側マスク領域にだけモザイクを適用し、mask バッチの内部結合モードにも対応する
- [Censor Bars By Mask](censor_bars_by_mask.md): マスク領域を参考に複数の平行帯を並べ、mask バッチの内部結合モードにも対応する

### Compatible LLM / VLM

- [Compatible LLM / VLM Overview](llm_vlm_overview.md): OpenAI 互換 API を使うノード群の目的、責務分離、MVP 範囲、共通方針
- [Compatible Endpoint](compatible_endpoint.md): 接続先設定、モデル一覧取得、既定モデルの決定を扱う
- [Compatible Model Selector](compatible_model_selector.md): `models_json` から index 指定で `model_name` を選ぶ
- [Prompt Preset](prompt_preset.md): 外部 JSON ベース、または PyYAML 利用時の YAML ベースで prompt プリセットを扱う
- [Chat Once](chat_once.md): 単発のテキストチャット送信を扱う
- [Vision Chat Once](vision_chat_once.md): 画像付きの単発チャット送信を扱う
- [Chat History Future](chat_history_future.md): 履歴付きチャットの将来拡張方針を整理する設計メモ

ノード追加後は、少なくとも以下を含むドキュメントを作成してください。

- ノード名
- 機能概要
- 入力
- 出力
- 使用例
- 注意点または制約
