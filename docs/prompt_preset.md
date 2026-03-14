# Prompt Preset

## 機能概要

`Prompt Preset` は、外部ファイルで管理された prompt プリセット定義を読み出し、ComfyUI ワークフローで再利用しやすい形に整えるためのノードです。固定文のコピペを減らし、用途ごとの prompt を差し替えやすくすることを目的とします。

現在の基準形式は JSON で、YAML は `PyYAML` が利用可能な環境でのみ任意対応です。

## 入力

| 名前 | 型 | 説明 |
| --- | --- | --- |
| `preset_path` | `STRING` | プリセット定義ファイルのパス。`.json`、または `PyYAML` 利用時の `.yaml` / `.yml` |
| `preset_id` | `STRING` | ファイル内から選択するプリセット識別子 |
| `variables_json` | `STRING` | テンプレート展開に使う変数を JSON 文字列で与える入力 |
| `fallback_user_prompt` | `STRING` | `user_template` が無い場合に使う補助入力 |

## 出力

| 名前 | 型 | 説明 |
| --- | --- | --- |
| `system_prompt` | `STRING` | system 用の prompt |
| `user_prompt` | `STRING` | 展開済み user prompt |
| `preset_meta_json` | `STRING` | ラベル、タグ、説明、version などを含むメタ情報 |
| `preset_name` | `STRING` | 表示用のプリセット名 |

## 対応する論理構造

少なくとも以下のような情報を扱えます。

- `id`
- `label`
- `name`
- `description`
- `system_prompt`
- `user_template`
- `user_prompt`
- `variables`
- `tags`
- `version`

トップレベルは、以下のいずれかを解釈します。

- `id` を持つオブジェクトの配列
- `presets` キー配下の配列または辞書
- `preset_id` をキーにした辞書

## 処理仕様

- ノードは外部ファイルを読み、`preset_id` に対応する定義を解決します
- `user_prompt` があればそれを優先して返します
- `user_template` がある場合は `variables_json` を JSON として読み、`str.format_map` で展開します
- `user_template` に必要な変数が足りない場合はエラーにします
- `user_template` が無い場合は `fallback_user_prompt` を返します
- `preset_meta_json` には prompt 本文以外のメタ情報を含めます

## 使用例

### タグ抽出用プリセットの例

画像や文章からタグを抽出したい場合、system prompt と user template を 1 つのプリセットとして保存しておきます。ワークフロー側では `preset_id` だけを差し替えることで、用途別の問い合わせを切り替えられます。

### 要約用プリセットの例

同じ送信ノードに対して、要約用、校正用、分類用など複数の prompt プリセットを用意しておけば、ComfyUI ワークフローを大きく変えずに用途を切り替えられます。

## 注意点 / 制約

- 初期仕様ではプリセットの永続保存 UI は扱わず、外部ファイル読み出しを前提とします
- YAML 読み込みは `PyYAML` が使える環境でのみ有効です
- `variables_json` は JSON オブジェクトである必要があります
- 変数不足時は補完せずエラーにします
- ワークフロー再現性の観点では、プリセットファイルのパス管理をどうするか別途検討が必要です
