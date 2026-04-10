# Desktop App Foundation

## Purpose

- desktop app の技術スタックと `COM port` 自動検出方式を固定する
- `Windows 優先 PoC` を最短で成立させるための実装前提を明文化する

## Technology Stack

- 実装言語は `Python 3.11+` とする
- GUI toolkit は `PySide6` とする
- serial 通信ライブラリは `pyserial` とする
- package manager / 仮想環境管理は `uv` とする
- Windows 向け bundler は `PyInstaller` とする

## Why This Stack

- `protocol v1` は `line-delimited JSON over serial` なので、PoC 速度では `Python + pyserial` が最短
- `PySide6` は Windows ネイティブ app として十分な UI を組みやすい
- `PyInstaller` で単体 `EXE` 化しやすい
- `uv` を使うと Linux 側の開発と Windows 側の依存再現が揃えやすい

## COM Port Detection Policy

### Primary Strategy

- 検出方式は `VID/PID prefilter + hello 応答確認` の併用とする
- まず `pyserial` の port 列挙で receiver 想定 `VID/PID` を持つ USB serial port を候補にする
- PoC で使う receiver の `VID/PID` は `0x2FE3:0x0012` とする
- desktop app 側の `VID/PID` prefilter は receiver firmware の `prj.conf` と同じ値を参照する
- 次に各候補 port を短時間 open し、`protocol v1` の `hello` を待つ
- `hello.channel=gui` を返した port だけを GUI 制御用 port として採用する

### GUI CDC と Log CDC の識別

- receiver は `GUI 用 CDC` と `log 用 CDC` を同一 USB device 上に持ってよい
- GUI app は `COM port` の並び順や `COM 番号` に依存しない
- `hello.channel=gui` を返す instance を GUI 用、返さない instance を非 GUI 用として扱う
- log 用 CDC は human-readable log 専用であり、GUI app の接続先にしない

### Receiver 未接続時

- matching `VID/PID` port が見つからなければ `receiver not found` と表示する
- app 起動中は `2 秒周期` の軽い再探索を許容する
- 利用者が明示的に `再試行` を押した場合も同じ探索を走らせる

### 複数 receiver 接続時

- `hello.channel=gui` を返す receiver が `1 台だけ` なら自動接続する
- `2 台以上` 見つかった場合は自動接続しない
- PoC では `multiple receivers detected` と表示し、`1 台に絞って再接続` を促す
- 複数 receiver の手動選択 UI は Phase 1 のスコープ外とする

### 再接続時

- 接続済み receiver が抜かれた場合は切断扱いにして自動探索へ戻る
- 同じ receiver が再列挙されたら、再度 `hello.channel=gui` を確認して再接続する
- 可能なら `USB serial number` または安定した device path を記憶し、再接続時の優先候補にしてよい

## USB Assumption For PoC

- PoC では `USB HID + CDC ACM(2 instance)` の composite device を前提にする
- GUI app は `shared VID/PID` の複数 interface を前提に実装する
- GUI 用 / log 用 interface の区別は `hello` で確定し、interface index の固定には依存しない

## Local Development Flow

- repository 直下に desktop app 用 `pyproject.toml` を置き、`uv sync` で依存を入れる
- ローカル起動は `uv run python -m zmk_usb_bridge_gui` を標準入口とする
- 開発中の receiver 接続確認は `hello -> status_snapshot -> candidate_snapshot` の成立を最初のチェックにする

## Windows Distribution Flow

- Windows 実機または Windows CI runner 上で `uv sync --group build` を実行する
- 配布 build は `uv run pyinstaller packaging/zmk-usb-bridge-gui.spec` を標準入口とする
- 配布物は `dist/zmk-usb-bridge-gui/` または単体 `EXE` を第一候補とし、PoC では installer 作成までは必須にしない

## Non-Goals For Phase 1

- `macOS` と `Linux` の正式パッケージ化
- 自動更新機構
