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

## 現在の進捗

- desktop app の USB dongle attach / reconnect は、最新 Windows 実機ログで安定化を確認済みです。
- `GUI 起動 -> dongle 接続 -> attached -> dongle 抜去 -> 再接続 -> attached` まで通過しています。
- 次の主タスクは receiver firmware 側の `connect_candidate / pairing / bond_erase` を stub から実 BLE lifecycle へ置き換えることです。
- 進行中の詳細計画は [docs/plans/phase2-and-beyond-implementation-plan.md](docs/plans/phase2-and-beyond-implementation-plan.md) を参照します。

## ドキュメント

- 設計文書の入口: [docs/README.md](docs/README.md)
- 基本構想: [docs/foundation/project-concept.md](docs/foundation/project-concept.md)
- Phase2以降の実装計画: [docs/plans/phase2-and-beyond-implementation-plan.md](docs/plans/phase2-and-beyond-implementation-plan.md)
- テスト方針: [docs/foundation/testing-policy.md](docs/foundation/testing-policy.md)

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

`PyInstaller` の成果物は platform ごとに分離されます。
たとえば Windows 実行時は `dist/windows-x86_64/zmk-usb-bridge-gui/`、
Linux 実行時は `dist/linux-x86_64/zmk-usb-bridge-gui/` が出力先です。
これにより、`\\wsl.localhost\...` 配下で Windows build を回したときに
既存の Linux build 成果物を掃除しようとして失敗する問題を避けます。

## Receiver Firmware Build

receiver firmware は、この workspace にある `zephyr/` と `toolchains/zephyr-sdk-*` を使って build できます。

標準の build 手順:

1. workspace root に `zephyr/`、`.west/`、`toolchains/zephyr-sdk-*` があることを確認する
2. `./scripts/build_receiver_firmware.sh`
3. `artifacts/builds/<timestamp>_receiver_seeeduino_xiao_ble/zephyr.uf2` または `artifacts/builds/latest/receiver_seeeduino_xiao_ble/zephyr.uf2` を使う

明示的に command を打つ場合は次でもよいです。

```bash
ZEPHYR_SDK_INSTALL_DIR=/home/dev/00_Dev_BLE_Reciever/toolchains/zephyr-sdk-0.16.3 \
west build -b seeeduino_xiao_ble . -d build/firmware/seeeduino_xiao_ble
```

補足:

- helper script は `ZEPHYR_SDK_INSTALL_DIR` 未設定時に `<workspace>/toolchains` から最新の `zephyr-sdk-*` を自動検出する
- build 出力の主対象は `zephyr.elf` と `zephyr.uf2`
- helper script は build 成功後に `UF2` と debug artifact を `artifacts/builds/` へ履歴付きでコピーする
- 現在の参照 board は `Seeed XIAO nRF52840` なので、まずは `zephyr.uf2` を使う運用を前提にする

## Receiver Firmware Flash

`Seeed XIAO nRF52840` へ書き込む最短手順:

1. board の reset を素早く 2 回押して bootloader mode に入る
2. host 側に現れた mass storage volume へ `zephyr.uf2` をコピーする
3. board が再起動したら GUI app から attach を確認する

この repository では flash 自体はまだ自動化していません。
理由は、mount point が Windows / WSL / Linux のどこから見えるかが環境依存だからです。
