# Prompt Preset

## 機能概要

`Prompt Preset` は、外部 TOML ファイルで管理された prompt プリセット定義を読み出し、ComfyUI ワークフローで再利用しやすい形に整えるためのノードです。固定文のコピペを減らし、用途ごとの prompt を差し替えやすくすることを目的とします。

このノードは外部 `.toml` 指定版です。リポジトリ同梱の既定プリセットを表示名で選ぶ用途には `Bundled Prompt Preset` を使います。

外部形式は TOML のみを正式対応とし、JSON / YAML は読み込みません。追加変数入力も `variables_toml` に統一し、プリセット本体と同じ TOML 文化で扱います。

## 入力

| 名前 | 型 | 説明 |
| --- | --- | --- |
| `preset_path` | `STRING` | プリセット定義ファイルのパス。`.toml` のみ対応 |
| `preset_id` | `STRING` | ファイル内から選択するプリセット識別子 |
| `input_text` | `STRING` | 複数行本文入力。自動的に `input` 変数として扱う |
| `variables_toml` | `STRING` | 追加変数を与えるフラットな TOML key-value 文字列 |
| `fallback_user_prompt` | `STRING` | `preset_id` 不一致、または対象プリセットの `user` が無いときに使う補助入力 |
| `keep_unresolved_variables` | `BOOLEAN` | 未解決変数を出力に残すかどうか。`true` ならそのまま残し、`false` なら空文字に置換する |

## 出力

| 名前 | 型 | 説明 |
| --- | --- | --- |
| `system_prompt` | `STRING` | system 用の prompt |
| `user_prompt` | `STRING` | 展開済み user prompt |
| `preset_meta_json` | `STRING` | prompt 本文以外のメタ情報を JSON 文字列で返したもの。`_prompt_preset` に変数解決の要約を含む |
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
Style: {{style}}
Instruction:
{{instruction}}
"""
user = """
以下を要約してください。

{{input}}
"""
```

## 変数入力仕様

### 入力方式

- `input_text` は `input` 変数に対応します
- `variables_toml` は任意の追加変数を TOML で与えます
- `system` と `user` の両方に同じ変数辞書を使って展開します
- `keep_unresolved_variables` の既定値は `true` です

### 変数辞書の構築順

1. 空の変数辞書を作る
2. `variables_toml` を parse して追加する
3. `input_text` が非空なら LF 正規化し、`input` として追加する

同名キーが競合した場合は個別入力欄を優先します。つまり、`variables_toml` に `input = "..."` があっても、`input_text` の値が `input` として使われます。`input_text` が空なら `input` キーは作りません。

### `variables_toml` の制約

- ルートはフラットな TOML key-value 群のみ受け付けます
- string / int / float / bool を許可します
- TOML の複数行文字列も string として許可します
- array はエラーです
- table / inline table / array of tables はエラーです
- その他ネスト構造はエラーです
- 構文エラーは明示的エラーにします

有効例:

```toml
style = "concise"
target_language = "Japanese"
temperature = 0.7
use_markdown = true
instruction = """
Please keep the tone formal.
Use short paragraphs.
"""
```

無効例:

```toml
tags = ["a", "b"]
```

```toml
[style]
name = "concise"
```

```toml
meta = { a = 1 }
```

## 処理仕様

- ノードは UTF-8 の `.toml` ファイルだけを読み込みます
- 改行コードは LF / CRLF のどちらでも受理し、内部では LF (`\n`) に正規化します
- `input_text`、`variables_toml` 内の文字列値、TOML の `system` / `user`、最終出力はすべて LF に正規化します
- 中間改行は保持し、不要な空白圧縮や整形は行いません
- `{{name}}` は単純文字列置換のみで展開します
- 未解決変数はエラーにせず、コンソールへ出力します
- `keep_unresolved_variables=true` なら未解決変数はそのまま残します
- `keep_unresolved_variables=false` なら未解決変数は空文字へ置換します
- ネスト参照、フィルタ、条件分岐、ループ、関数呼び出し、式評価は行いません

## 使用例

### プリセット TOML

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

### UI 入力

`input_text`:

```text
ここに要約対象の本文
```

`variables_toml`:

```toml
style = "concise"
instruction = """
Use short paragraphs.
Avoid bullet points unless necessary.
"""
```

### 展開結果

`system_prompt`:

```text
You are a helpful assistant.
Answer in Japanese.
Style: concise
Instruction:
Use short paragraphs.
Avoid bullet points unless necessary.
```

`user_prompt`:

```text
以下を要約してください。

ここに要約対象の本文
```

### 未定義変数の扱い

テンプレート:

```text
Hello {{name}}
{{unknown_value}}
```

変数:

```toml
name = "Kentaroh"
```

結果:

```text
Hello Kentaroh
{{unknown_value}}
```

`keep_unresolved_variables=false` の場合:

```text
Hello Kentaroh
```

未解決変数が存在した場合は、`system` / `user` / fallback のどこで発生したか分かる形でコンソールへ変数名一覧を出力します。

## fallback の扱い

### fallback を使わず明示的エラーにするケース

- file not found
- file read failed
- unsupported extension
- invalid utf-8
- toml parse error
- unsupported version
- invalid preset structure
- `variables_toml` が TOML として parse できない
- `variables_toml` に array が含まれる
- `variables_toml` に table / inline table / array of tables が含まれる
- `variables_toml` にその他ネスト構造が含まれる

### fallback を許容するケース

- `preset_id` 不一致
- 対象プリセットの `user` 欠落

`preset_id` が見つからない場合、`fallback_user_prompt` が非空ならそれを `user_prompt` として返します。対象プリセットに `user` が無い場合も同様です。`fallback_user_prompt` が空なら明示的に失敗します。

## `preset_meta_json` の補足

`preset_meta_json` には、プリセット内のメタ情報に加えて `_prompt_preset` を含めます。ここには少なくとも以下が入ります。

- `preset_id`
- `resolved_variable_names`
- `input_text_used`
- `fallback_used`
- `keep_unresolved_variables`
- `unresolved_variable_names`
- `unresolved_in_system`
- `unresolved_in_user`
- `unresolved_in_fallback`

## 注意点 / 制約

- `preset_path` は `.toml` のみを受け付けます
- `version` は `1` 固定です
- `presets` はテーブルである必要があります
- 対象プリセットはテーブルである必要があります
- `system` / `user` の少なくとも一方が必要です
- `variables_toml` は空文字を許容します
- `input_text` は空でも許容します
- `Prompt Preset` は `tomli` を使用して TOML を読み込みます
- 未解決変数はエラーにしませんが、コンソールには出力されます
- 旧 JSON 追加変数互換、可変 GUI フィールド生成、Jinja 風テンプレート機能は扱いません
