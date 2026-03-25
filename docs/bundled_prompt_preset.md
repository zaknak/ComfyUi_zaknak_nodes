# Bundled Prompt Preset

## 機能概要

`Bundled Prompt Preset` は、このリポジトリに同梱された既定の TOML プリセットファイルを読み出し、表示名で選択して prompt を展開するためのノードです。外部ファイルのパス入力を省略しつつ、画像説明やタグ生成向けの prompt をすぐに使えるようにすることを目的とします。

既存の `Prompt Preset` が外部 `.toml` 指定版であるのに対し、このノードは同梱ファイル固定版です。変数展開、fallback、未解決変数の扱いは `Prompt Preset` と同じ仕様に揃えます。

## 入力

| 名前 | 型 | 説明 |
| --- | --- | --- |
| `preset_label` | `STRING` | 同梱プリセットファイル内の `label` から選ぶ表示名 |
| `input_text` | `STRING` | 複数行本文入力。自動的に `input` 変数として扱う |
| `variables_toml` | `STRING` | 追加変数を与えるフラットな TOML key-value 文字列 |
| `fallback_user_prompt` | `STRING` | 選択されたプリセットに `user` が無いときに使う補助入力 |
| `keep_unresolved_variables` | `BOOLEAN` | 未解決変数を出力に残すかどうか。`true` ならそのまま残し、`false` なら空文字に置換する |

## 出力

| 名前 | 型 | 説明 |
| --- | --- | --- |
| `system_prompt` | `STRING` | system 用の prompt |
| `user_prompt` | `STRING` | 展開済み user prompt |
| `preset_meta_json` | `STRING` | prompt 本文以外のメタ情報を JSON 文字列で返したもの。`_prompt_preset` に変数解決の要約を含む |
| `preset_name` | `STRING` | 表示用のプリセット名。選択した `label` を返す |

## 同梱プリセットファイル

- 読み込み対象は `presets/default_prompt_presets.toml` です
- ファイル形式は `Prompt Preset` と同じく TOML のみです
- ルート `version = 1` と `presets` テーブルが必須です
- 各プリセットは `[presets.<id>]` 形式で定義します
- 各プリセットは `label` を必須とし、同梱ファイル内で一意である必要があります
- `system` と `user` は少なくともどちらか一方が必要です

現在の同梱プリセット:

- `🖼️ Tags(EN)`: 画像から英語タグ列を生成する
- `🖼️ Simple Description(EN)`: 画像の主題と状況を英語 1 文で簡潔に説明する
- `🖼️ Detailed Description(EN)`: 画像の見た目を英語の詳細段落で説明する
- `🖼️ Tag and Detailed Description(EN)`: Danbooru 風タグ列と詳細説明の両方を生成する

## 選択仕様

- UI では `preset_label` 候補として `label` 一覧を表示します
- 内部では `preset_label` から対応する `preset_id` を解決して処理します
- `preset_meta_json._prompt_preset.preset_id` には内部の `preset_id` を保持します
- `preset_name` は選択された `label` を返します
- `label` に絵文字や記号を含んでいても、その文字列をそのまま選択候補として扱います

## 変数入力仕様

- `input_text` は `input` 変数に対応します
- `variables_toml` は任意の追加変数を TOML で与えます
- `system` と `user` の両方に同じ変数辞書を使って展開します
- `keep_unresolved_variables` の既定値は `true` です
- 同名キーが競合した場合は `input_text` が優先されます

`variables_toml` の制約は `Prompt Preset` と同じです。

- ルートはフラットな TOML key-value 群のみ受け付けます
- string / int / float / bool を許可します
- array はエラーです
- table / inline table / array of tables はエラーです

## fallback の扱い

- 選択されたプリセットに `user` が無い場合、`fallback_user_prompt` が非空ならそれを `user_prompt` として返します
- `fallback_user_prompt` が空なら明示的に失敗します
- `preset_label` が候補一覧に存在しない場合は明示的に失敗します
- 同梱ファイルの読み込み失敗、構造不正、`label` 重複は fallback せず明示的エラーにします

## 使用例

### UI 入力

`preset_label`:

```text
🖼️ Simple Description(EN)
```

`input_text`:

```text
A bright cafe interior with a woman reading by the window.
```

### 展開結果のイメージ

`system_prompt`:

```text
Analyze the image and write a single concise sentence that describes the main subject and setting. Keep it grounded in visible details only.
```

`user_prompt`:

```text
A bright cafe interior with a woman reading by the window.
```

## 注意点 / 制約

- 外部ファイルパスは入力しません。読み込み先は同梱ファイル固定です
- 同梱プリセットは `label` 必須かつ一意である必要があります
- 未解決変数はエラーにしませんが、コンソールには出力されます
- 現在の同梱内容は英語の画像説明・タグ生成向けプリセット群です
- 変数展開、改行正規化、`variables_toml` の制約は `Prompt Preset` と同じです
