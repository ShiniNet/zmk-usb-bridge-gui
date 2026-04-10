# Phase 1 Validation Log

## Purpose

- `DesktopApp Phase 1` の確認結果を、`PoC Evaluation` に沿って簡潔に残す
- `stub bring-up`、`Windows 実機 validation`、`packaging` の進捗を 1 か所で追えるようにする
- 実装追加が必要か、観測待ちか、`hold` かを切り分けやすくする

## Current Snapshot

- 文書作成時点で `Priority 1: Stub Bring-up` はローカル GUI 手動確認ベースで概ね完了
- 自動 test: `uv run python -m unittest discover -s tests -v` 通過
- `PyInstaller` build は current Linux 開発環境で smoke 確認済み
- Windows packaged `EXE` の起動、`receiver attached`、`candidate list` 初期表示、`Connect`、`Bond Erase`、`receiver` 抜き差し後の再接続は実機で確認済み
- `DesktopApp Phase 1` の Windows 実機 validation では、USB 側 attach / candidate 表示 / connect / bond erase / receiver 抜き差し後の再接続まで確認済み

## Validation Entries

### 1. Stub Bring-up

- Status: `pass`
- Environment: `local desktop app + stub protocol`
- Confirmed:
  - `hello -> status_snapshot -> candidate_snapshot` の初期同期
  - `Scan`、`Refresh`、`Connect`、`Bond Erase` の基本操作導線
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

- Status: `pass (user-reported Windows observation)`
- Target:
  - `app 起動時` と `receiver 抜き差し後` の両方で `hello.channel=gui` port へ再接続できる
- Evidence:
  - Windows packaged `EXE` 起動時に `COM8` へ attach し、GUI の summary に反映された
  - `receiver` 抜き差し後に GUI 用 `COM port` へ正しく再接続し、その後も挙動に異常が見られなかったとの user observation を確認
- Notes:
  - `single receiver` 条件での再接続は確認済み
  - `receiver not found`、`multiple receivers detected` の各状態がどう見えたかは引き続き補助観測対象とする

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
