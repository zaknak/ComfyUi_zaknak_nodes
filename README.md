# comfyui_zaknak_nodes

ComfyUI で使う私的なカスタムノードを追加していくためのリポジトリです。ノードの概要はこの README に、各ノードの詳細仕様は `docs/` 配下のドキュメントを参照してください。

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

## ドキュメント

- ノード仕様一覧: [docs/NODES.md](docs/NODES.md)

## License

Copyright (c) 2026 zaknak

This project is licensed under the MIT License. 