# zmk-usb-bridge-gui

`zmk-usb-bridge-gui` は、`zmk-usb-bridge` とは別 project として進める
`Windows 優先の GUI 付き ZMK BLE keyboard receiver` 構想です。

現時点では、`LaLapadGen2` を参照キーボードとする `PoC` の前提整理を主目的とします。
既存の `NoGUI` bridge に GUI を積み増すのではなく、`候補一覧表示 + 手動選択 pairing + 状態可視化`
を前提とした別 project として検討します。

## いま重視すること

- `Windows` 優先で PoC を最短成立させる
- `既存 ZMK キーボード無改造` を必須条件にする
- `CDC ACM` を GUI と receiver の双方向制御チャネルとして使う
- `接続状態 / keyboard 名 / battery / modifier / 直近キー / mouse button` を GUI 表示する
- `候補一覧取得 / 選択デバイスへの pairing / bond erase` を GUI 操作から行えるようにする

## ドキュメント

- 設計文書の入口: [docs/README.md](docs/README.md)
- 基本構想: [docs/foundation/project-concept.md](docs/foundation/project-concept.md)

