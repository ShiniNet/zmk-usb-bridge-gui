# Desktop App Foundation

## Purpose

- desktop app の技術スタックと `COM port` 自動検出方式を固定する
- `Windows 優先 PoC` を最短で成立させるための実装前提を明文化する
- 実機デバッグ時に desktop app が担う `log capture` の責務境界を明確にする

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
- `hello` probe の待ち時間は `PoC Phase 1` では `0.4 秒` を既定値とし、応答が無ければその probe では非 GUI port とみなしてよい
- receiver 側が port open 直後に `hello` を送る前提を置き、`0.4 秒` で不足する観測が出た場合だけ firmware / app のどちらを調整するかを再評価する
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

## Debug Capture Boundary

- desktop app は必要に応じて `GUI app event`、`receiver GUI protocol`、`receiver debug serial`、`keyboard debug serial` を同時収集してよい
- ただし `GUI protocol port` を log capture のために別 open してはならない
- `receiver debug port` と `keyboard debug port` は GUI 制御 port とは別 reader として扱う
- log record の schema、保存形式、session 単位の運用は [`debug-log-foundation.md`](debug-log-foundation.md) を正本とする

## Current Phase 1 Desktop App Contract

### Implementation Boundary

- desktop app の責務は `serial_discovery`、`session`、`controller`、`runtime`、`ui/main_window` に分離する
- `protocol v1` の message 定義と parse / serialize は [`protocol-v1.md`](protocol-v1.md) を正本とする
- candidate の公開条件、上限、並び順は [`candidate-listing-policy.md`](candidate-listing-policy.md) を正本とする
- `tests/` は `protocol`、`state`、`controller`、`runtime`、`session` の stable contract を守る最小集合として維持する

### Discovery And Attach Contract

- discovery と attach の基本方針は上記 `COM Port Detection Policy` を正本とする
- `Phase 1` の GUI 実装は、`multiple receivers detected` を手動選択 UI ではなく `1 台に絞って再接続` を促す状態として扱う
- attach 後は `serial_number` と安定した device path を優先候補として保持し、再接続時の discovery に引き継いでよい

### Runtime And Recovery Contract

- attach 後の初期同期と command / event sequence の基本形は [`protocol-v1.md`](protocol-v1.md) を正本とする
- `Refresh` は `get_status` を基本としつつ、`Phase 1` の GUI 実装では `get_candidates` も続けて送る belt-and-suspenders の再同期操作として扱ってよい
- `get_status` だけでも `candidate_snapshot` を含むが、追加の `get_candidates` による重複 `candidate_snapshot` は許容する
- `scan_complete(result=stopped)` を `scanning` 中に受けた場合は `idle` ではなく `connecting` へ遷移してよい
- `scan_complete` が来ない場合の watchdog timeout は、`PoC Phase 1` では `12 秒` を既定値とし、`5-10 秒` の bounded scan window を少し上回る余裕として扱う
- watchdog timeout 時は GUI 側の scan 状態を解除して `Refresh` による再同期を要求する
- `Connect` は選択中候補の `candidate_generation` と `candidate_id` を付けて `connect_candidate` を送る
- `Bond Erase` は確認後に `bond_erase` を送り、`idle` と空 candidate 一覧への復帰を待つ
- serial 切断や session open failure 時は attach 状態を破棄し、自動 discovery へ戻る

### GUI Surface Contract

- summary には `Connection`、`Receiver Port`、`Protocol Version`、`Peer Name`、`Receiver State` を表示する
- `Phase 2+` では summary を拡張し、`Battery`、`Modifiers`、`Last Key`、`Mouse Buttons` を追加表示してよい
- candidate table には `Display Name`、`Address`、`RSSI`、`Tier` を表示する
- `display_name` が無い candidate は `Unnamed HID device` と表示する
- `Tier B` は `keyboard appearance unverified` が分かる文言で表示する
- 操作ボタンは `Scan`、`Refresh`、`Connect`、`Bond Erase`、`Retry` を持つ
- `Scan`、`Refresh`、`Bond Erase` は `attach 済み` かつ `non-busy` の間だけ有効化する
- `Connect` は `attach 済み`、`non-busy`、候補選択済み、かつ `receiver_state != connected` のときだけ有効化する
- `Retry` は未 attach 時だけ有効化する
- `Last Error` を常設し、複数 receiver 検知時は status bar に port 一覧を表示してよい
- telemetry 表示は少なくとも `Disconnected`、`Unsupported`、`Pending / Not reported yet` を区別できるようにする

### Validation Evidence

- `Phase 1` の手動確認結果と packaging / Windows 実機観測は [`../validation/phase1-validation-log.md`](../validation/phase1-validation-log.md) に集約する
- 実装タスクの進行管理 checklist は、`Phase 1` の主要実装と確認が済んだ時点で恒久 document から外してよい

## Windows Distribution Flow

- Windows 実機または Windows CI runner 上で `uv sync --group build` を実行する
- 配布 build は `uv run pyinstaller packaging/zmk-usb-bridge-gui.spec` を標準入口とする
- 配布物は `dist/<platform>/zmk-usb-bridge-gui/` または単体 `EXE` を第一候補とし、PoC では installer 作成までは必須にしない
- `PyInstaller` の成果物は `dist/<platform>/` と `build/pyinstaller/<platform>/` に分離し、Linux と Windows の build 成果物を混在させない

## Non-Goals For Phase 1

- `macOS` と `Linux` の正式パッケージ化
- 自動更新機構
