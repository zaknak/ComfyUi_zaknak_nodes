# Prompt Preset

## 機能概要

`Prompt Preset` は、外部ファイルで管理された prompt プリセット定義を読み出し、ComfyUI ワークフローで再利用しやすい形に整えるためのノードです。固定文のコピペを減らし、用途ごとの prompt を差し替えやすくすることを目的とします。

現在の基準形式は JSON で、YAML は `PyYAML` が利用可能な環境でのみ任意対応です。YAML を使う場合も、解釈される論理構造は JSON と同じです。

## 入力

| 名前 | 型 | 説明 |
| --- | --- | --- |
| `preset_path` | `STRING` | プリセット定義ファイルのパス。`.json`、または `PyYAML` 利用時の `.yaml` / `.yml` |
| `preset_id` | `STRING` | ファイル内から選択するプリセット識別子 |
| `variables_json` | `STRING` | `user_template` のテンプレート展開に使う変数を JSON 文字列で与える入力 |
| `fallback_user_prompt` | `STRING` | `user_prompt` と `user_template` が無い場合に使う補助入力 |

## 出力

| 名前 | 型 | 説明 |
| --- | --- | --- |
| `system_prompt` | `STRING` | system 用の prompt |
| `user_prompt` | `STRING` | 展開済み user prompt |
| `preset_meta_json` | `STRING` | prompt 本文以外のメタ情報を JSON 文字列で返したもの |
| `preset_name` | `STRING` | 表示用のプリセット名。`label` → `name` → `id` → `preset_id` の順で採用 |

## プリセットオブジェクトの項目

1 件のプリセット定義は JSON object で、主に以下のキーを扱います。

| キー | 必須 | 説明 |
| --- | --- | --- |
| `id` | 形式による | プリセット識別子。配列形式では実質必須 |
| `label` | 任意 | UI 表示向けの名前 |
| `name` | 任意 | `label` が無い場合の表示名候補 |
| `description` | 任意 | 説明文 |
| `system_prompt` | 任意 | system prompt |
| `user_prompt` | 任意 | 固定の user prompt。非空文字列なら最優先 |
| `user_template` | 任意 | `variables_json` で展開するテンプレート |
| `tags` | 任意 | 任意のタグ配列など |
| `version` | 任意 | 任意のバージョン情報 |
| `variables` | 任意 | メタ情報としては保持可能。ただし現在の実装ではテンプレート展開には未使用 |

`preset_meta_json` には、`system_prompt`、`user_template`、`user_prompt` を除いた残りのキーが入ります。

## 想定している JSON フォーマット

実装は、トップレベルとして以下の形を解釈します。

### 1. 単一プリセット object

```json
{
  "id": "tag_extract",
  "label": "タグ抽出",
  "system_prompt": "あなたはタグ抽出アシスタントです。",
  "user_template": "次の文章からタグを列挙してください: {text}",
  "tags": ["tag", "text"],
  "version": "1.0"
}
```

この場合、`preset_id` は `tag_extract` を指定します。

### 2. `preset_id` をキーにした辞書

```json
{
  "tag_extract": {
    "label": "タグ抽出",
    "system_prompt": "あなたはタグ抽出アシスタントです。",
    "user_template": "次の文章からタグを列挙してください: {text}"
  },
  "summary": {
    "label": "要約",
    "system_prompt": "あなたは要約アシスタントです。",
    "user_template": "次の文章を{tone}に要約してください: {text}"
  }
}
```

この形式では、各値の object に `id` が無くても、辞書キーが `id` として補われます。

### 3. `presets` 配下に辞書を持つ object

```json
{
  "presets": {
    "tag_extract": {
      "label": "タグ抽出",
      "description": "文章からタグ候補を作る",
      "system_prompt": "あなたはタグ抽出アシスタントです。",
      "user_template": "次の文章からタグを列挙してください: {text}"
    },
    "summary": {
      "label": "要約",
      "system_prompt": "あなたは要約アシスタントです。",
      "user_template": "次の文章を{tone}に要約してください: {text}"
    }
  }
}
```

この形式でも、`presets` 配下のキー名が `preset_id` として使われます。

### 4. `presets` 配下に配列を持つ object

```json
{
  "presets": [
    {
      "id": "tag_extract",
      "label": "タグ抽出",
      "system_prompt": "あなたはタグ抽出アシスタントです。",
      "user_template": "次の文章からタグを列挙してください: {text}"
    },
    {
      "id": "summary",
      "label": "要約",
      "system_prompt": "あなたは要約アシスタントです。",
      "user_template": "次の文章を{tone}に要約してください: {text}"
    }
  ]
}
```

この形式では、各要素に `id` が必要です。

### 5. `id` を持つ object の配列

```json
[
  {
    "id": "tag_extract",
    "label": "タグ抽出",
    "system_prompt": "あなたはタグ抽出アシスタントです。",
    "user_template": "次の文章からタグを列挙してください: {text}"
  },
  {
    "id": "summary",
    "label": "要約",
    "system_prompt": "あなたは要約アシスタントです。",
    "user_template": "次の文章を{tone}に要約してください: {text}"
  }
]
```

## 処理仕様

- ノードは外部ファイルを読み、`preset_id` に対応する定義を解決します
- `user_prompt` が非空文字列であれば、それを最優先で返します
- `user_prompt` が無く、`user_template` がある場合は `variables_json` を JSON object として読み、`str.format_map` で展開します
- `user_prompt` と `user_template` がどちらも無い場合は `fallback_user_prompt` を返します
- `variables_json` が空文字なら空 object `{}` として扱います
- `preset_meta_json` には prompt 本文以外のメタ情報を含めます

優先順位は次のとおりです。

1. `user_prompt`
2. `user_template` + `variables_json`
3. `fallback_user_prompt`

## 使用例

### 辞書マップ形式の例

ファイル `prompt_presets.json`:

```json
{
  "tag_extract": {
    "label": "タグ抽出",
    "system_prompt": "あなたはタグ抽出アシスタントです。",
    "user_template": "次の文章からタグを列挙してください: {text}"
  }
}
```

ノード入力:

```json
preset_id = "tag_extract"
variables_json = {"text":"黒猫が窓辺で眠っている"}
```

生成される `user_prompt`:

```text
次の文章からタグを列挙してください: 黒猫が窓辺で眠っている
```

### 固定 `user_prompt` を使う例

```json
{
  "summary_fixed": {
    "label": "固定要約",
    "system_prompt": "あなたは要約アシスタントです。",
    "user_prompt": "以下の文章を3行で要約してください。"
  }
}
```

この場合、`variables_json` の内容に関係なく `user_prompt` がそのまま返ります。

### 複数変数を使う例

```json
{
  "summary": {
    "label": "要約",
    "system_prompt": "あなたは要約アシスタントです。",
    "user_template": "次の文章を{tone}に要約してください: {text}"
  }
}
```

```json
{
  "tone": "簡潔",
  "text": "この文章は長い説明文です。"
}
```

生成される `user_prompt`:

```text
次の文章を簡潔に要約してください: この文章は長い説明文です。
```

## 注意点 / 制約

- 初期仕様ではプリセットの永続保存 UI は扱わず、外部ファイル読み出しを前提とします
- YAML 読み込みは `PyYAML` が使える環境でのみ有効です
- `preset_path` は `.json`、`.yaml`、`.yml` のみを受け付けます
- `preset_id` は必須です
- 対象の `preset_id` が見つからない場合はエラーになります
- `variables_json` は空文字または JSON object である必要があります
- `variables_json` が不正 JSON、または object 以外の JSON 値だった場合はエラーになります
- `user_template` の必須変数が `variables_json` に不足している場合はエラーになります
- プリセット定義内の `variables` は、現在の実装ではテンプレート展開に使われません
- ワークフロー再現性の観点では、プリセットファイルのパス管理をどうするか別途検討が必要です
