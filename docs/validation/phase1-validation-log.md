# Phase 1 Validation Log

## Purpose

- `DesktopApp Phase 1` の確認結果を、`PoC Evaluation` に沿って簡潔に残す
- `stub bring-up`、`Windows 実機 validation`、`packaging` の進捗を 1 か所で追えるようにする
- 実装追加が必要か、観測待ちか、`hold` かを切り分けやすくする

## Current Snapshot

- 文書作成時点で `Priority 1: Stub Bring-up` はローカル GUI 手動確認ベースで概ね完了
- 自動 test: `uv run python -m unittest discover -s tests -v` 通過
- local firmware build: `west build -b seeeduino_xiao_ble . -d build/firmware-check` が `ZEPHYR_SDK_INSTALL_DIR` 指定付きで通過し、`zephyr.uf2` を生成できることを確認
- local firmware helper: `scripts/build_receiver_firmware.sh` が build 後に `artifacts/builds/` へ `UF2` と debug artifact を履歴付きで退避できることを確認
- `PyInstaller` build は current Linux 開発環境で smoke 確認済み
- Windows packaged `EXE` の起動、`receiver attached`、`candidate list` 初期表示、`Connect`、`Bond Erase`、`receiver` 抜き差し後の再接続は実機で確認済み
- `DesktopApp Phase 1` の Windows 実機 validation では、USB 側 attach / candidate 表示 / connect / bond erase / receiver 抜き差し後の再接続まで確認済み
- `Phase 1.5` の local closeout として、desktop app は telemetry 表示と `Disconnected / Unsupported / Pending` の区別まで実装済み
- stub firmware も protocol 上は `telemetry_update`、非同期 `scan -> candidate_upsert -> scan_complete`、`scan_busy / connect_busy / invalid_state / unsupported_command` の error surface を返せる状態まで拡張済み

## Phase 1.5 Closeout

### Closed In Phase 1 / 1.5

- `DesktopApp Phase 1` の attach / candidate list / connect / bond erase / receiver 再接続の主導線
- `COM Port Detection Stability` の最新 Windows attach / reconnect 再検証
- packaged app の build / launch / Windows 上の基本動作確認
- `protocol v1` の desktop app 実装、candidate policy、testing policy、foundation document の正本化
- local test による `protocol / controller / runtime / session / state` の stable contract 保護
- `Phase 4` 先行着手としての telemetry contract と GUI 表示の土台

### Carry Over To Phase 2+

- `Reconnect Stability` の pass / hold 判定
- 実 BLE scan / candidate cache / pairing / bond storage / bonded reconnect
- `USB HID bridge` の本実装ベースでの回帰確認
- 実機 `connect_candidate` failure code 集合の確定

### Carry-Over Reasoning

- `Reconnect Stability` は `PoC Evaluation` の pass 条件に含まれるが、current firmware は stub のため `BLE bonded reconnect` 自体をまだ観測できない
- `USB` 抜き差し後の GUI 再接続は確認済みだが、これは `receiver discovery` の確認であり、`keyboard` との bond 復帰試験とは切り分ける
- よって `Phase 1` で close するのは `stub firmware で観測できる contract` までとし、real firmware 前提の項目は `Phase 2+` へ明示的に carry over する

### Supplemental Observations Still Worth Collecting

- `receiver not found`
- `multiple receivers detected`
- `connect_candidate` failure code と GUI 表示文言の対応
- candidate noise と `12 件上限` 周りの実機観測

## Validation Entries

### 1. Stub Bring-up

- Status: `pass`
- Environment: `local desktop app + stub protocol`
- Confirmed:
  - `hello -> status_snapshot -> candidate_snapshot` の初期同期
  - `Scan`、`Refresh`、`Connect`、`Bond Erase` の基本操作導線
  - `telemetry_update`、非同期 `scan_started -> candidate_upsert -> scan_complete`、主要 stub error code の local contract を追加実装した
- Notes:
  - 細かな表示文言や error surface は、実機応答に合わせて必要なら微修正する

### 2. Candidate Discovery

- Status: `pass (initial Windows observation)`
- Target:
  - `LaLapadGen2` が `10 秒以内` に候補一覧へ出る
- Evidence:
  - Windows packaged `EXE` 起動後、GUI 上で `Connection=receiver attached`、`Receiver Port=COM8`、`Protocol Version=v1`、`Receiver State=idle` を確認
  - `Candidates` 一覧に `LaLapadGen2` が表示されることを確認
- Notes:
  - 今回は `候補が表示されること` まで確認済みであり、`10 秒以内` の計測値は未採取
  - `candidate_snapshot` 内容、一覧上位表示、`12 件上限` の追加観測は継続する

### 3. Manual Pairing / Connect

- Status: `pass (Windows observation)`
- Target:
  - `connect_candidate` 実行後に `connecting -> connected` へ到達し、接続先名が GUI に出る
- Evidence:
  - `LaLapadGen2` を選択した状態で `Connect` 実行後、GUI 上で `Peer Name=LaLapadGen2`、`Receiver State=connected` を確認
  - `Connection=receiver attached`、`Receiver Port=COM8`、`Protocol Version=v1` は接続成立後も維持された
  - `Last Error=None` のまま接続成立した
- Notes:
  - 今回は成功系のみ観測した
  - 失敗時は `error.code` と GUI 表示文言の対応も記録する

### 4. Bond Erase Recovery

- Status: `pass (Windows observation)`
- Target:
  - `bond_erase` 後に `idle` と空 snapshot へ戻り、再度 scan / connect に進める
- Evidence:
  - `Bond Erase` 操作時に `Erase receiver bonds and return to idle state?` 確認ダイアログが表示された
  - 実行後、GUI 上で `Peer Name=n/a`、`Receiver State=idle`、空 `Candidates` 一覧への復帰を確認
  - `Connection=receiver attached`、`Receiver Port=COM8` は維持され、`Last Error=None` のまま復帰した
- Notes:
  - `status_snapshot` と `candidate_snapshot` の再同期順、再 scan 後の候補再出現タイミングは継続観測する

### 5. COM Port Detection Stability

- Status: `pass (latest Windows attach/reconnect revalidation)`
- Target:
  - `app 起動時` と `receiver 抜き差し後` の両方で `hello.channel=gui` port へ再接続できる
- Evidence:
  - Windows packaged `EXE` 起動時に `COM8` へ attach し、GUI の summary に反映された
  - `receiver` 抜き差し後に GUI 用 `COM port` へ正しく再接続し、その後も挙動に異常が見られなかったとの user observation を確認
  - `20260419_152258_78ec.jsonl` で `GUI 起動 -> dongle 接続 -> attached -> dongle 抜去 -> 再接続 -> attached -> dongle 抜去` の一連の再接続シナリオが成功した
- Notes:
  - `single receiver` 条件での再接続は確認済み
  - `receiver not found`、`multiple receivers detected` の各状態がどう見えたかは引き続き補助観測対象とする
  - 2026-04-11 の Windows 実機再検証では、一時 `receiver attached` へ戻らない問題を観測したが、原因は `attach 前 discovery` の sibling diagnostic と `hello.channel=gui` probe 成功後の `COM8` reopen による `PermissionError(13)` だったと切り分け済みである
  - 上記に対して、通常 discovery では sibling diagnostic を既定無効化し、probe 成功済み port は close/reopen せずそのまま session へ引き継ぐよう修正した
  - 続く `20260411_190957_0aa6.jsonl` では attach 復旧後に `status_snapshot` 分割受信由来の `protocol_parse_error` を観測したため、session reader を `newline` まで再組み立てしてから parse するよう追加修正した
  - 最新の `20260411_191511_7db6.jsonl` では `COM8` の `hello.channel=gui` 検出後に `attached` へ遷移し、その後 `Protocol parse error` や予期せぬ `Receiver port disconnected` を出さず正常終了まで維持できたため、上記の問題は現時点では再現していない
  - ただし 2026-04-11 夜から 2026-04-12 未明の再検証では、`attach` 安定化のための追加変更が逆に不安定要因になった
  - `20260411_192328_ccf4.jsonl`: `COM8` への attach 自体は成功したが、`scan_start` 後に `ack / event` が 1 件も返らず watchdog timeout になった。候補一覧に何も出なかった直接原因は `candidate filter` ではなく、receiver session が command に応答していないことだった
  - `20260411_193400_ac94.jsonl`: retained probe port へ `DTR` を再 assert する試行後、`hello` 検出から `attached` まで約 23 秒遅延したため、この案は revert した
  - `20260411_194222_b1e8.jsonl`: probe 成功後に `COM8` を close/reopen する試行では `FileNotFoundError(2)` で attach 失敗となったため、この案も revert した
  - `20260411_212920_9edc.jsonl` と `20260411_213319_c34c.jsonl`: retained probe port を `attach_open_port` で再利用する経路のまま再準備を加えると、`receiver_attach_open_started` で GUI がハングした
  - 上記に対して、attach 自体は background worker 化し、`Receiver attach timed out` で UI が固まらないようにはした
  - その後の `20260412_002257_014a.jsonl` では attach まで進む前に discovery probe が不安定化し、`COM7` を先に 1 秒 probe したあと `COM8` も `hello_verified=false` となり、以後は `COM7 / COM8` 両方が `elapsed_ms=0` で即失敗する `receiver_not_found` loop を観測した
  - historical hypothesis:
    `COM7` と `COM8` の sibling port のうち、GUI 側と思われる `COM8(location=1-1:x.2)` より先に `COM7` を probe すると、GUI port 側の受信機会または port readiness を乱している可能性がある
  - mitigation:
    discovery 時は `location` を持つ port を優先して probe するよう変更し、実機ログ上で実績のある `COM8` を `COM7` より先に見るよう調整した
  - 2026-04-19 local mitigation:
    `probe_gui_protocol` worker の open/read exception を `discovery_probe_finished.probe_failure_*` として明示ログ化した
  - 2026-04-19 local mitigation:
    GUI runtime の discovery では、`hello` / protocol verified になった probe port を close/reopen せず `attach_open_port` へ引き継ぐ方針へ戻した
  - 2026-04-19 local mitigation:
    retained probe port の session attach では `DTR` 再 assert と input/output buffer reset を行わず、既に開けている port の reader / writer thread 起動だけに寄せた
  - observation target:
    `probe_failure_exception_class / probe_failure_detail` は今後 `hello_verified=false` が再発した場合に `pyserial open failure` と `hello timeout` の切り分けに使う
  - `20260419_150621_f3c0.jsonl`:
    `COM8(location=1-1.2.3.1:x.2)` が最初に probe され、`hello.channel=gui` は `62 ms` で検出できた
  - `20260419_150621_f3c0.jsonl`:
    その後 `receiver_attach_open_started(mode=attach_open_port)` までは進んだが、`3 秒` の attach timeout に到達し `Receiver attach timed out` になった
  - `20260419_150621_f3c0.jsonl`:
    timeout 後も stale attach worker が `COM8` を掴み続け、後続 discovery は `COM8 / COM7` の `PermissionError(13)` を記録した
  - `20260419_150621_f3c0.jsonl`:
    stale worker は約 `14.5 秒` 後に `receiver_attach_open_finished(mode=attach_open_port)` を出したが、すでに active token は timeout 済みで attach state には復帰しなかった
  - 2026-04-19 follow-up mitigation:
    attach timeout 時に active candidate の retained probe port と active session を明示 close / release するよう修正した
  - 2026-04-19 follow-up mitigation:
    timeout 後に stale attach result が返った場合は attach thread slot を解放し、古い session を閉じるようにした
  - follow-up observation:
    以後の実機ログでは timeout 後の即時 `PermissionError(13)` loop は再現していない
  - `20260419_151128_a3a9.jsonl`:
    dongle 接続後、`COM8(location=1-1.2.3.1:x.2)` が最初に probe され、`hello.channel=gui` は `32 ms` で検出できた
  - `20260419_151128_a3a9.jsonl`:
    `receiver_attach_open_started(mode=attach_open_port)` の後、`receiver_attach_open_finished` は `30,000 ms` 後に出ており、retained probe port の session attach 中に長時間ブロックしている
  - `20260419_151128_a3a9.jsonl`:
    `Receiver attach timed out` は attach 開始から約 `45 秒` 後、かつ `receiver_attach_open_finished` から約 `15 秒` 後に出ているため、attach timeout cleanup だけでは原因箇所の特定に不足がある
  - 2026-04-19 follow-up mitigation:
    retained probe port の `attach_open_port` では `timeout / write_timeout` の再設定も含めて serial port 再準備を完全にスキップするよう変更した
  - 2026-04-19 follow-up mitigation:
    session attach の lifecycle tap を GUI app event に接続し、`session_attach_open_port_close_*`、`session_prepare_serial_finished`、`session_reader_thread_started`、`session_writer_thread_started` の段階別ログを追加した
  - follow-up observation:
    後続ログでは `session_*` lifecycle event が同一 tick 内で完了し、停止箇所は再現していない
  - `20260419_151810_86eb.jsonl`:
    dongle 接続後、`COM8(location=1-1.2.3.1:x.2)` が最初に probe され、`hello.channel=gui` は `78 ms` で検出できた
  - `20260419_151810_86eb.jsonl`:
    `session_attach_open_port_*`、`session_prepare_serial_finished`、`session_reader_thread_started`、`session_writer_thread_started` が同一 tick 内で完了し、`receiver_attach_open_finished(elapsed_ms=0)` の後 `attached` へ遷移した
  - `20260419_151810_86eb.jsonl`:
    その後の `Receiver port disconnected: ClearCommError failed ...` は user 操作による dongle 取り外し後に発生しており、attach 失敗ではなく切断検出として扱う
  - latest observation:
    retained probe port の `serial re-prepare` 完全スキップ後、前回の `30 秒` attach hang は再現せず、GUI attach は成功した
  - `20260419_152258_78ec.jsonl`:
    初回 attach は `COM8` probe `62 ms`、`receiver_attach_open_finished(elapsed_ms=0)`、`attached` 遷移まで成功した
  - `20260419_152258_78ec.jsonl`:
    dongle 抜去後は `disconnected` になり、その後 discovery が再開して `receiver_not_found` を複数回挟んだ
  - `20260419_152258_78ec.jsonl`:
    再接続後の attach は `COM8` probe `47 ms`、`receiver_attach_open_finished(elapsed_ms=0)`、`attached` 遷移まで成功した
  - latest observation:
    `app 起動時` と `receiver 抜き差し後` の両方で `hello.channel=gui` port へ再接続できることを最新 Windows 実機ログで確認した

### 6. HID Bridge Regression Safety

- Status: `pass (user-reported Windows observation)`
- Target:
  - `connected` 到達後に実入力で明確なフリーズや入力欠落がない
- Evidence:
  - `receiver` 抜き差し後の再接続後も挙動に異常が見られなかったとの user observation を確認
- Notes:
  - 今回は `user-reported` な実機観測ベースでの pass とする
  - firmware 側 issue の切り分けが必要な追加症状が出た場合は別途記録する

### 7. Packaging

- Status: `pass (current Linux dev environment / Windows EXE launch smoke)`
- Target:
  - `uv run pyinstaller packaging/zmk-usb-bridge-gui.spec` 相当で build できる
- Evidence:
  - `packaging/zmk-usb-bridge-gui.spec` に `PySide6.QtCore` / `PySide6.QtWidgets` の hidden import を追加済み
  - `packaging/zmk-usb-bridge-gui.spec` の `project_root` 解決を修正し、PyInstaller spec 実行時の `__file__` 依存を除去済み
  - `src/zmk_usb_bridge_gui/__main__.py` を absolute import に修正し、frozen executable 起動時の import error を解消済み
  - `./.venv/bin/pyinstaller -y packaging/zmk-usb-bridge-gui.spec` 実行成功
  - `./dist/zmk-usb-bridge-gui/zmk-usb-bridge-gui --version` 実行成功
  - `./dist/zmk-usb-bridge-gui/zmk-usb-bridge-gui discover` 実行成功
  - `packaging/zmk-usb-bridge-gui.spec` を更新し、成果物を `dist/<platform>/` と `build/pyinstaller/<platform>/` に分離した
  - Windows で packaged `EXE` を起動し、GUI が表示されることを確認
  - Windows packaged `EXE` 上で `Connect` と `Bond Erase` が動作し、GUI state 遷移まで確認した
  - Windows packaged `EXE` 上で `receiver` 抜き差し後の再接続と、その後の安定動作も確認した
- Notes:
  - GUI 側は `importlib` で Qt module を読むため、配布 build では hidden import 明示が必要
  - `Windows EXE` の launch / `Connect` / `Bond Erase` / 再接続 observation は通過した
  - Linux build log には `xcb` 系 shared library warning が出るが、今回の smoke 範囲では build 自体と CLI 起動は成立している
  - Windows から `\\wsl.localhost\...` 配下で PyInstaller を実行した際、従来の共通 `dist/zmk-usb-bridge-gui/` を掃除しようとして Linux build 由来 symlink の削除で失敗した
  - 上記の再発防止として、以後は platform 別 output を使い Linux と Windows の build 成果物を混在させない

### 7.5. Local Firmware Build

- Status: `pass (local build environment)`
- Target:
  - workspace 既存の `zephyr/` と `toolchains/zephyr-sdk-*` を使って receiver firmware を再現可能に build できる
- Evidence:
  - `toolchains/zephyr-sdk-0.16.3` を `ZEPHYR_SDK_INSTALL_DIR` に指定して `west build -b seeeduino_xiao_ble . -d build/firmware-check` が成功
  - `build/firmware-check/zephyr/zephyr.elf` と `build/firmware-check/zephyr/zephyr.uf2` の生成を確認
  - repo 内に `scripts/build_receiver_firmware.sh` を追加し、SDK 自動検出つきの build 導線を固定した
  - helper script 実行後、`artifacts/builds/<timestamp>_receiver_seeeduino_xiao_ble/` と `artifacts/builds/latest/receiver_seeeduino_xiao_ble/` に `zephyr.uf2` と debug artifact が保存されることを確認
- Notes:
  - 現時点の次の blocker は build ではなく、`UF2` を board に流して実機観測へ進むこと

### 8. Reconnect Stability

- Status: `deferred (firmware stub)`
- Target:
  - 初回 pairing 成功後、keyboard 側電源の off/on もしくは一時切断から `15 秒以内` に bonded reconnect へ戻れる
- Evidence:
  - `receiver` の USB 抜き差し後に GUI 用 `COM port` へ再接続できることは確認済み
  - ただしこれは `BLE bonded reconnect` そのものの観測ではなく、`PoC Evaluation` の `Reconnect Stability` pass 判定とは別項目として扱う
- Notes:
  - current firmware は stub であり、実 BLE bond / bonded reconnect を持たない
  - したがってこの項目は `Phase 1` では close せず、real firmware 実装後の `Phase 3` validation へ移す
  - 次回は `LaLapadGen2` を初回 pairing 済みの状態にした上で、keyboard 側の一時切断または電源 off/on から `connected` 復帰までの時間を記録する
  - 判定時は少なくとも `1 回` の成功観測に加え、`3 回試して 1 回以上失敗する` の hold 条件にも該当しないことを確認する

## Open Questions

- 実機の `connect_candidate` failure code はどの集合になるか
- `status_snapshot` と `candidate_snapshot` の再送タイミングは current runtime の `Refresh` / watchdog 戦略で十分か
- `receiver not found`、`multiple receivers detected` など補助ケースの UI 観測はどう見えるか
- `bonded reconnect` の成功率と復帰時間は、real firmware 実装後に `PoC Evaluation` の `Reconnect Stability` 条件を満たすか
