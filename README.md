# zmk-usb-bridge-gui

`zmk-usb-bridge-gui` は、`zmk-usb-bridge` とは別 project として進める
`Windows 優先の GUI 付き ZMK BLE keyboard receiver` 構想です。

現時点では、`LaLapadGen2` を参照キーボードとする `PoC` の実装と前提整理を進めています。
既存の `NoGUI` bridge に GUI を積み増すのではなく、`候補一覧表示 + 手動選択 pairing + 状態可視化`
を前提とした別 project として実装を進めます。

`zmk-usb-bridge-gui` は `ZMK keyboard firmware project` ではなく、
`receiver 側 firmware + desktop app` を扱う **独立した Zephyr project** です。
`既存 ZMK キーボード無改造` を前提とするため、`CDC ACM` や debug log 用 endpoint の追加は
**receiver 側 USB device** の話であり、keyboard 側 firmware に要求する仕様ではありません。

## いま重視すること

- `Windows` 優先で PoC を最短成立させる
- `既存 ZMK キーボード無改造` を必須条件にする
- `CDC ACM` を GUI と receiver の双方向制御チャネルとして使う
- `接続状態 / keyboard 名 / battery / modifier / 直近キー / mouse button` を GUI 表示する
- `候補一覧取得 / 選択デバイスへの pairing / bond erase` を GUI 操作から行えるようにする

## ドキュメント

- 設計文書の入口: [docs/README.md](docs/README.md)
- 基本構想: [docs/foundation/project-concept.md](docs/foundation/project-concept.md)

## Desktop App Skeleton

この repository には、現在の PoC 実装の土台として使っている最小 desktop app skeleton を含めています。

標準のローカル開発手順:

1. `uv sync --group dev`
2. `uv run python -m zmk_usb_bridge_gui`
3. `uv run python -m zmk_usb_bridge_gui discover --probe`
4. `uv run python -m unittest discover -s tests -v`

Windows 配布用 build:

1. `uv sync --group build`
2. `uv run pyinstaller packaging/zmk-usb-bridge-gui.spec`

`PySide6` と `pyserial` は desktop app の通常依存として `uv sync` で入る前提です。
追加の build tool だけを `build` group に分けています。
