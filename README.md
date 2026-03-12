# comfyui_zaknak_nodes

ComfyUI で使うカスタムノードを追加していくためのリポジトリです。

このリポジトリでは ComfyUI 用カスタムノードを提供します。ノードの概要はこの README に、各ノードの詳細仕様は `docs/` 配下にまとめます。

## 特徴

- ComfyUI 向けカスタムノードをまとめて管理します
- README から利用者向けの導線を提供します
- 各ノードの詳細仕様は `docs/` 配下で個別に管理します

## インストール

ComfyUI の `custom_nodes` ディレクトリ配下にこのリポジトリを配置してください。

```bash
cd ComfyUI/custom_nodes
git clone <this-repository-url> comfyui_zaknak_nodes
```

その後、ComfyUI を再起動してください。

## 使い方

1. このリポジトリを `custom_nodes` 配下に配置します。
2. ComfyUI を起動または再起動します。
3. 追加済みのノードがある場合は、ノード検索から対象ノード名で探します。
4. 詳細な入出力や使用例は `docs/` 配下のドキュメントを参照します。

現在は最初のノードとして、マスク領域にだけモザイクを適用するノードを提供しています。

## ノード一覧

| Node | 概要 | 詳細 | 状態 |
| --- | --- | --- | --- |
| Mosaic By Mask | 画像とマスクを入力し、白側マスク領域にモザイクを適用する | [docs/mosaic_by_mask.md](docs/mosaic_by_mask.md) | 実装済み |

## ドキュメント

- ノード仕様一覧: [docs/NODES.md](docs/NODES.md)

## 補足

- ノードごとの詳細仕様は `docs/` 配下の Markdown を参照してください
- リポジトリ運用方針は `AGENTS.md` に記載します

