# Prompt Preset

## 機能概要

`Prompt Preset` は、外部 TOML ファイルで管理された prompt プリセット定義を読み出し、ComfyUI ワークフローで再利用しやすい形に整えるためのノードです。固定文のコピペを減らし、用途ごとの prompt を差し替えやすくすることを目的とします。

外部形式は TOML のみを正式対応とし、JSON / YAML は読み込みません。

## 入力

| 名前 | 型 | 説明 |
| --- | --- | --- |
| `preset_path` | `STRING` | プリセット定義ファイルのパス。`.toml` のみ対応 |
| `preset_id` | `STRING` | ファイル内から選択するプリセット識別子 |
| `variables_json` | `STRING` | `{{name}}` 置換に使う変数を JSON object 文字列で与える入力 |
| `fallback_user_prompt` | `STRING` | `preset_id` 不一致、または対象プリセットの `user` が無いときに使う補助入力 |

## 出力

| 名前 | 型 | 説明 |
| --- | --- | --- |
| `system_prompt` | `STRING` | system 用の prompt |
| `user_prompt` | `STRING` | 展開済み user prompt |
| `preset_meta_json` | `STRING` | prompt 本文以外のメタ情報を JSON 文字列で返したもの |
| `preset_name` | `STRING` | 表示用のプリセット名。`label` があればそれを使い、無ければ `preset_id` を使う |

## TOML スキーマ

- ルート `version = 1` は必須です
- ルート `presets` テーブルは必須です
- 各プリセットは `[presets.<id>]` 形式で定義します
- `label` は任意です
- `system` と `user` は少なくともどちらか一方が必要です
- 未知のキーは許容しますが、このノードでは無視します
- `system` / `user` は複数行文字列の利用を前提とします

```toml
version = 1

[presets.summary]
label = "Summary"
system = """
You are a helpful assistant.
Answer in Japanese.
"""
user = """
以下を要約してください。

{{input}}
"""

[presets.translate]
label = "Translate"
system = """
You are a translation assistant.
"""
user = """
Translate the following text into Japanese:

{{input}}
"""
```

## 処理仕様

- ノードは UTF-8 の `.toml` ファイルだけを読み込みます
- 改行コードは LF / CRLF のどちらでも受理し、内部では LF (`\n`) に正規化します
- `system` と `user` は読み込み後に LF へ正規化します
- `variables_json` 内の文字列値も LF へ正規化してから置換します
- 最終出力の `system_prompt` / `user_prompt` も LF に統一します
- 末尾改行や中間改行は、不要に削除・圧縮せず、記述内容をできるだけ保持します

## 変数展開

- 記法は `{{name}}` です
- 展開対象は `system` と `user` の両方です
- 展開は単純文字列置換のみです
- 式評価、関数呼び出し、ネスト構文、テンプレート言語化は行いません
- 未定義変数はエラーにせず、そのまま残します
- `variables_json` は空文字または JSON object である必要があります

例:

```toml
version = 1

[presets.example]
label = "Example"
system = """
You are a helpful assistant.
"""
user = """
Summarize the following text:
{{input}}
"""
```

`variables_json`:

```json
{
  "input": "黒猫が窓辺で眠っている"
}
```

生成される `user_prompt`:

```text
Summarize the following text:
黒猫が窓辺で眠っている
```

## fallback の扱い

### fallback を使わず明示的エラーにするケース

- file not found
- file read failed
- unsupported extension
- invalid utf-8
- toml parse error
- unsupported version
- invalid preset structure

### fallback を許容するケース

- `preset_id` 不一致
- 対象プリセットの `user` 欠落

`preset_id` が見つからない場合、`fallback_user_prompt` が非空ならそれを `user_prompt` として返します。対象プリセットに `user` が無い場合も同様です。`fallback_user_prompt` が空なら明示的に失敗します。

## 使用例

ファイル `prompt_presets.toml`:

```toml
version = 1

[presets.summary]
label = "Summary"
system = """
You are a helpful assistant.
Answer in Japanese.
"""
user = """
以下を要約してください。

{{input}}
"""

[presets.translate]
label = "Translate"
system = """
You are a translation assistant.
"""
user = """
Translate the following text into Japanese:

{{input}}
"""
```

ノード入力:

```text
preset_id = "summary"
variables_json = {"input":"黒猫が窓辺で眠っている"}
```

生成される `user_prompt`:

```text
以下を要約してください。

黒猫が窓辺で眠っている
```

## 注意点 / 制約

- `preset_path` は `.toml` のみを受け付けます
- `version` は `1` 固定です
- `presets` はテーブルである必要があります
- 対象プリセットはテーブルである必要があります
- `system` / `user` の少なくとも一方が必要です
- `variables_json` が不正 JSON、または object 以外の JSON 値だった場合はエラーになります
- `Prompt Preset` は `tomli` を使用して TOML を読み込みます
- JSON / YAML 互換維持、自動移行、TOML 書き戻し、messages 形式対応は扱いません
