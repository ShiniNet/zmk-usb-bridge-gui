# Phase 1 Validation Log

## Purpose

- `DesktopApp Phase 1` の確認結果を、`PoC Evaluation` に沿って簡潔に残す
- `stub bring-up`、`Windows 実機 validation`、`packaging` の進捗を 1 か所で追えるようにする
- 実装追加が必要か、観測待ちか、`hold` かを切り分けやすくする

## Current Snapshot

- 文書作成時点で `Priority 1: Stub Bring-up` はローカル GUI 手動確認ベースで概ね完了
- 自動 test: `./.venv/bin/python -m unittest discover -s tests -v` 通過
- `PyInstaller` build は current Linux 開発環境で smoke 確認済み
- 未確認の中心は `Windows 実機 validation` と `receiver firmware 実装との統合` である

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

- Status: `pending`
- Target:
  - `LaLapadGen2` が `10 秒以内` に候補一覧へ出る
- Evidence:
  - 未記入
- Notes:
  - `candidate_snapshot` 内容、一覧上位表示、`12 件上限` の実機観測を残す

### 3. Manual Pairing / Connect

- Status: `pending`
- Target:
  - `connect_candidate` 実行後に `connecting -> connected` へ到達し、接続先名が GUI に出る
- Evidence:
  - 未記入
- Notes:
  - 失敗時は `error.code` と GUI 表示文言の対応も記録する

### 4. Bond Erase Recovery

- Status: `pending`
- Target:
  - `bond_erase` 後に `idle` と空 snapshot へ戻り、再度 scan / connect に進める
- Evidence:
  - 未記入
- Notes:
  - `status_snapshot` と `candidate_snapshot` の再同期順も観測する

### 5. COM Port Detection Stability

- Status: `pending`
- Target:
  - `app 起動時` と `receiver 抜き差し後` の両方で `hello.channel=gui` port へ再接続できる
- Evidence:
  - 未記入
- Notes:
  - `single receiver`、`receiver not found`、`multiple receivers detected` の各状態がどう見えたか残す

### 6. HID Bridge Regression Safety

- Status: `pending`
- Target:
  - `connected` 到達後に実入力で明確なフリーズや入力欠落がない
- Evidence:
  - 未記入
- Notes:
  - firmware 側 issue の切り分けが必要なら別途記録する

### 7. Packaging

- Status: `pass (current Linux dev environment)` / `pending (Windows EXE validation)`
- Target:
  - `uv run pyinstaller packaging/zmk-usb-bridge-gui.spec` 相当で build できる
- Evidence:
  - `packaging/zmk-usb-bridge-gui.spec` に `PySide6.QtCore` / `PySide6.QtWidgets` の hidden import を追加済み
  - `packaging/zmk-usb-bridge-gui.spec` の `project_root` 解決を修正し、PyInstaller spec 実行時の `__file__` 依存を除去済み
  - `src/zmk_usb_bridge_gui/__main__.py` を absolute import に修正し、frozen executable 起動時の import error を解消済み
  - `./.venv/bin/pyinstaller -y packaging/zmk-usb-bridge-gui.spec` 実行成功
  - `./dist/zmk-usb-bridge-gui/zmk-usb-bridge-gui --version` 実行成功
  - `./dist/zmk-usb-bridge-gui/zmk-usb-bridge-gui discover` 実行成功
- Notes:
  - GUI 側は `importlib` で Qt module を読むため、配布 build では hidden import 明示が必要
  - 現在の成果物は Linux build であり、最終的な `Windows EXE` の確認は Windows 環境で別途必要
  - Linux build log には `xcb` 系 shared library warning が出るが、今回の smoke 範囲では build 自体と CLI 起動は成立している

## Open Questions

- 実機の `connect_candidate` failure code はどの集合になるか
- `status_snapshot` と `candidate_snapshot` の再送タイミングは current runtime の `Refresh` / watchdog 戦略で十分か
- Windows 実機での `COM port` 再列挙は `serial_number` 優先だけで安定するか
