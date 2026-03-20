# Compatible LLM / VLM Overview

## 目的

このドキュメントは、このリポジトリへ追加した Compatible LLM / VLM 系 ComfyUI ノード群の共通方針を整理するためのものです。個別ノードの詳細仕様は別ファイルへ分離し、この文書では目的、責務分離、MVP、共通制約、実装で確定した仕様を扱います。

## 前提

- LLM / VLM は ComfyUI 内部で起動しません
- 外部で起動した OpenAI 互換 API サーバーへリクエストを送る方式を前提とします
- 当面はローカル利用を主目的とします
- 使いやすさを優先しつつ、将来拡張を阻害しない責務分離を目指します

想定する接続先は LM Studio などの OpenAI 互換エンドポイントですが、特定実装へ強く依存しない形で設計します。

## 実装済み MVP

現在の実装対象は以下です。

- 接続先設定と既定モデル決定
- 利用可能モデル一覧の取得と、取得済み一覧からのモデル名選択
- 単発のテキストチャット送信
- ComfyUI の画像入力先頭 1 枚を添えた単発の VLM 送信
- 外部ファイルベースの prompt プリセット読み出し

以下は未実装で、将来拡張で扱います。

- 履歴付きチャット
- ストリーミング応答
- 複数ターンの会話状態管理
- モデル能力の自動判定や高度なキャッシュ
- 認証方式の追加対応
- 複数画像入力
- 動的ドロップダウン UI によるモデル選択

## ノード責務の分離方針

### 接続設定ノード

接続先設定、API キー、モデル一覧取得、既定モデルの決定は `Compatible Endpoint` に集約します。`model_name` が空のまま一覧取得に成功した場合は、取得結果の先頭モデルを既定値として採用します。

### モデル選択ノード

取得済みの `models_json` から明示的に別モデルを選びたい場合は、一覧確認用の `Compatible Model List View` と選択用の `Compatible Model Selector` を組み合わせます。ComfyUI 標準 UI の制約上、現在は動的ドロップダウンではなく index 指定でモデル名を取り出します。

### プリセットノード

prompt プリセットは送信ノードへ内蔵せず、外部 TOML ファイルから読み出す専用ノードで扱います。

### 単発送信ノード

単発のテキストチャットは独立した 1 回のリクエストとして扱います。履歴状態を持たせず、ComfyUI のワークフロー内で明快に使えることを優先します。ノード入力としては `max_tokens` と `seed` を扱い、`max_tokens` の既定値は `10240` とします。`temperature` や `top_p` のような追加 generation パラメータは `extra_body_json` で任意に指定できます。さらに `strict_finish_reason` により、`finish_reason` が `stop` 以外だった応答をエラーとして扱えるようにします。`text` 出力には任意の後処理オプションを持てるものとし、`strip_think_tags` は `<think>` 推論ログを除去する整形機能として扱います。

### 画像付き送信ノード

VLM 向けの画像付き送信は、テキスト専用ノードと分離します。画像は ComfyUI `IMAGE` バッチの先頭 1 枚を PNG 化して data URL として送ります。ノード入力としては `max_tokens` と `seed` を扱い、`max_tokens` の既定値は `10240` とします。追加 generation パラメータは `extra_body_json` で任意に指定できます。`strict_finish_reason` は `text` 応答の正常終了判定に使い、`strip_think_tags` は `text` 出力だけを整形し、API 生レスポンスは保持します。

### 履歴付きチャット

履歴付きチャットは将来拡張とし、単発送信ノードへモード切り替えで混在させません。将来的に導入する場合は、履歴専用ノードまたは messages 構築ノードを追加し、会話状態の責務を分離します。

## UI / 入出力方針

- UI は ComfyUI 標準のノード UI を前提とします
- `Compatible Endpoint` はベース URL、API キー、`model_name`、モデル一覧再取得フラグを中心に構成します
- `Compatible Model List View` は `models_json` から index とモデル名の対応一覧を文字列で返します
- `Compatible Model Selector` は `models_json` と index 入力から `model_name` を返します
- 送信ノードは prompt 入力を主役にし、接続設定を重複させません
- `extra_body_json` は JSON object 文字列のみ受け付け、空文字は追加なしとして扱います
- `extra_body_json` で既存 payload キーと衝突する指定はエラーにします
- `extra_body_json` により、UI に出さない generation パラメータを追加指定できます
- `strict_finish_reason` は `BOOLEAN` 入力で、既定値は `true` とします
- `strict_finish_reason=true` の場合、`finish_reason` が `stop` 以外ならエラーにします
- `strip_think_tags` は `BOOLEAN` 入力で、既定値は `false` とします
- `strip_think_tags` は `text` 出力だけに適用し、`response_json` は生レスポンスとして保持します
- テキスト応答は `STRING` を主出力とします
- メタ情報は JSON 文字列として追加出力します
- 画像入力は ComfyUI の `IMAGE` 型を受け、標準ライブラリで PNG 化して API 送信用に変換します

## モデル一覧取得の考え方

- 接続先がモデル一覧取得 API に対応している場合は、利用可能モデル一覧を取得します
- `Compatible Endpoint` はその結果を `models_json` と `status_text` で返します
- `model_name` が空でモデル一覧取得に成功した場合は、先頭モデルを既定値として採用します
- 接続先が非対応、失敗、または一時的に取得できない場合でも、手動で `model_name` を入力して利用できます
- 取得済み一覧から明示的に選びたい場合は `Compatible Model List View` で index 対応を確認し、`Compatible Model Selector` で選択します

## プリセット方針

- プリセットは外部 `.toml` ファイルのみを読み込みます
- ルートには `version = 1` と `presets` テーブルが必須です
- 各プリセットは `[presets.<id>]` 形式で定義します
- 変数入力は `input_text` と `variables_toml` の 2 系統で受けます
- `input_text` は `input` 変数として扱い、同名競合時は `variables_toml` より優先します
- `system` と `user` は少なくともどちらか一方を持てます
- `system` / `user` の変数展開は `{{name}}` の単純文字列置換で行います
- 未解決変数はコンソールへ出力し、`keep_unresolved_variables` でそのまま残すか空文字にするかを切り替えます
- `variables_toml` はフラットな TOML key-value のみを受け付け、array / table / inline table はエラーにします
- 改行は内部で LF に正規化し、不要なトリムや圧縮は行いません
- `preset_id` 不一致と `user` 欠落時だけ `fallback_user_prompt` を使えます
- 送信ノードはプリセット内部構造へ強く依存せず、読み出し済みの prompt 情報を受け取って利用します

## エラーハンドリング方針

以下は少なくとも区別して扱います。

- ベース URL の不正または接続不能
- タイムアウト
- HTTP エラー
- モデル一覧取得失敗
- 指定モデルが利用不可
- 画像非対応モデルへの画像入力
- 空応答または不正 JSON
- API キー不足
- プリセットファイル読込失敗
- `variables_toml` の TOML 構文エラー
- `variables_toml` の配列型不正
- `variables_toml` の table / inline table 型不正
- `extra_body_json` の不正 JSON
- `extra_body_json` の型不正
- `extra_body_json` と既存 payload のキー衝突
- `strict_finish_reason=true` における `finish_reason != "stop"`

モデル一覧取得失敗は手動モデル指定へのフォールバックを基本とします。一方、送信ノード実行時に `model_name` が空ならエラーにします。`strip_think_tags` はレスポンス整形であり、推論ログが存在しない場合でもエラーにはしません。

## 依存関係方針

Compatible LLM / VLM 系の実装は HTTP 通信と画像 PNG 化を標準ライブラリで行います。`Prompt Preset` の TOML 読み込みには `tomli` を使用します。

## 想定ユースケース

- ローカルで起動した OpenAI 互換 API に対して、ComfyUI ワークフローから単発でテキスト問い合わせを行う
- 生成画像や入力画像を VLM へ渡し、説明、タグ抽出、判定、要約などを行う
- 用途別の prompt プリセットを切り替えて、同じワークフローから異なる問い合わせを行う
- 取得済みモデル一覧からワークフロー側でモデルを切り替える
- 追加 body パラメータをノード入力から与えて、接続先固有オプションを試す
- `<think>` 推論ログ付きモデルの応答を整形し、本文だけを後続処理へ渡す
- 将来的に、単発ノード群を土台として履歴付きチャットや messages 構築へ拡張する

## 関連ドキュメント

- [Compatible Endpoint](compatible_endpoint.md)
- [Compatible Model List View](compatible_model_list_view.md)
- [Compatible Model Selector](compatible_model_selector.md)
- [Prompt Preset](prompt_preset.md)
- [Chat Once](chat_once.md)
- [Vision Chat Once](vision_chat_once.md)
- [Chat History Future](chat_history_future.md)
