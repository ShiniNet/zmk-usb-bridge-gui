# Implementation Start Checklist

## Purpose

- `DesktopApp Phase 1` を完成させるための実装タスクを、レビュー可能な粒度で固定する
- `PoC 完了条件` から逆算して、`先に作るべき土台` と `後回しでよい項目` を分ける
- `desktop app 単独で先行実装できる範囲` と `receiver firmware 依存の確認待ち` を切り分ける

## Current State Summary

- serial port 列挙と `hello` probe の骨組みはある
- protocol の parse / serialize module はある
- PySide6 の main window は `port discovery skeleton` に留まる
- receiver との常時接続 session、受信 loop、command 送信、候補一覧 UI、再接続制御、テストは未実装
- receiver firmware 側には desktop app bring-up 用の `stub protocol` があり、app 側は stub 相手に先行実装できる

## Current Implementation Assessment

- 以下は repository 上の `desktop app` 実装と test をもとにした現時点の棚卸しであり、`Current State Summary` の初版記述より進んだ状態を反映する
- `serial_discovery.py`、`session.py`、`controller.py`、`runtime.py`、`ui/main_window.py`、`tests/` が存在し、`Phase 1` の土台実装は概ね入っている
- `./.venv/bin/python -m unittest discover -s tests -v` は通過しており、protocol / state / controller / runtime / session の主要 contract は自動 test で一通り守られている

### 既にコード化されているもの

- `VID/PID prefilter + hello 応答確認` による GUI 用 `COM port` 候補の絞り込み
- `SerialSession` による open / close、reader loop、line-delimited JSON 受信、command 送信、切断検知
- `hello`、`status_snapshot`、`candidate_snapshot`、`ack`、`error`、`event` の parse / state 反映
- `2 秒周期` の再探索、単一 receiver 自動 attach、複数 receiver 検知、切断後 rediscovery
- `Connection`、`Receiver Port`、`Protocol Version`、`Peer Name`、`Receiver State`、候補一覧、`Scan`、`Refresh`、`Connect`、`Bond Erase`、`Retry` を持つ `Phase 1` GUI
- candidate の公開条件、`Tier A -> Tier B -> RSSI -> last_seen` の sort、`12 件上限`
- `scan_complete(result=stopped)`、`stale generation`、scan watchdog timeout、disconnect recovery の主要 state 遷移 test

### 残タスクの扱い

- 現時点の主な残りは `desktop app の基盤実装` よりも、`stub / 実機での操作確認`、`Windows 実機 validation`、`firmware 側との摺り合わせ` に寄っている
- したがって以降の優先順位は、`コード未実装の洗い出し` ではなく `Phase 1 Exit Criteria` を閉じるための確認と不足補完を中心に置く

## Remaining Task Backlog

### Priority 1: Stub Bring-up 完了

- `stub protocol` 相手に `hello -> status_snapshot -> candidate_snapshot` の初期同期を GUI 上で確認する
- `Scan`、`Refresh`、`Connect`、`Bond Erase` の各ボタン操作が stub 応答と整合しているかを手動確認する
- `scan_complete(result=stopped)` 後に `connecting` 表示へ遷移する導線を GUI で確認する
- `last error` の表示文言が実運用で追跡しやすいかを確認し、必要なら調整する

### Priority 2: Receiver Firmware との統合確認

- 実機の `candidate_snapshot` が app 想定の field と更新頻度で流れるか確認する
- 実機の `connect_candidate` 成功系 / 失敗系 code を確認し、GUI の表示文言へ反映する
- `hello`、`status_snapshot`、`candidate_snapshot` の再送タイミングが current runtime の再同期戦略で十分か確認する
- `candidate_not_found`、`stale_candidate_generation`、`scan_busy`、`connect_busy` などの実機 error surface を整理する

### Priority 3: Windows 実機 Validation

- `app 起動時` に GUI 用 `COM port` を誤接続せず attach できることを確認する
- receiver 抜き差し後に `receiver discovery -> reattach` へ戻れることを確認する
- `LaLapadGen2` を候補一覧に出し、`connect_candidate` から `connected` 到達まで確認する
- `bond_erase` 後に `idle` と空 candidate 一覧へ戻り、再度 scan / connect に進めることを確認する
- 接続成立後に HID bridge 側の実入力が破綻していないことを確認する

### Priority 4: Packaging And Review Evidence

- `uv run pyinstaller packaging/zmk-usb-bridge-gui.spec` の build 成功を確認する
- `poc-evaluation.md` の `Pass / Hold / Fail` 観点に沿って、実機確認結果を記録する
- `Candidate Discovery`、`Manual Pairing / Connect`、`Bond Erase Recovery`、`COM Port Detection Stability` の結果を review 用に残す

## Suggested Next Slice

- 次の着手単位は `stub bring-up の手動確認 -> Windows 実機 validation -> packaging 確認` の順を推奨する
- もし追加実装が必要になった場合も、まずは `実機で観測された不足` に限定して補完し、`Deferred After Phase 1` の項目は混ぜない

## Scope

- 対象は `Windows 優先 PoC` の `desktop app` 側とする
- 完了線は [`project-concept.md`](project-concept.md) の `Phase 1 Completion Line` と `Minimum Functional Set For PoC Complete` に従う
- `Phase 1` の対象外項目は `Deferred After Phase 1` にまとめる

## Phase 1 Exit Criteria

- `VID/PID prefilter + hello 応答確認` で receiver を誤接続せず検出できる
- app が `hello -> status_snapshot -> candidate_snapshot` を取り込み、初期状態を表示できる
- GUI から `scan_start`、`connect_candidate`、`bond_erase` を実行できる
- `idle / scanning / connecting / connected` と接続先 keyboard 名を GUI に反映できる
- receiver 抜き差し時に切断検知し、`GUI port の再探索と再接続` へ戻れる
- `PoC Evaluation` の `Candidate Discovery`、`Manual Pairing / Connect`、`Bond Erase Recovery`、`COM Port Detection Stability` を確認できる

## Terminology Guardrails

- この checklist でいう `再接続` は、特記がない限り `receiver の GUI 用 COM port への再接続` を指す
- `keyboard の bonded reconnect` は [`poc-evaluation.md`](poc-evaluation.md) の system-level validation として別扱いにする
- UI 操作の `Refresh` は `接続済み receiver への再同期`、`Retry` は `receiver 未接続時の discovery / attach 再試行` を指す

## Implementation Principles

- まず `通信基盤` を作り、その上に `状態管理`、最後に `UI 操作` を載せる
- `UI から serial/protocol の詳細を直接扱わない` 責務分離を守る
- `Phase 1 必須機能` を先に閉じ、deferred 項目は混ぜない
- receiver firmware の本実装待ちでも、`stub protocol` で操作導線と状態反映を先に完成させる

## Task Breakdown

### 1. Serial Session Layer

- `GUI 用 COM port` を open / close する session object を追加する
- 専用 reader loop で `line-delimited JSON` を継続受信する
- 送信 API を持ち、`command` を protocol line として書き出せるようにする
- `request_id` 採番を app 側で一元管理する
- `read timeout`、port close、例外時の切断検知を UI へ通知できるようにする
- `hello.product`、`hello.channel=gui`、`protocol_version` が期待値に合う port のみを接続対象として採用する

### 2. Protocol Application Layer

- `hello`、`status_snapshot`、`candidate_snapshot`、`ack`、`error`、`event` を app 状態へ反映する controller を追加する
- `event(scan_started)`、`event(candidate_upsert)`、`event(scan_complete)`、`event(connection_state)`、`event(bonds_cleared)` の適用規則を実装する
- `scan_complete(result=stopped)` は `connect_candidate` 受理による scan 中断として扱い、`scanning` 表示を解除して connect シーケンスへ移行できるようにする
- `scan_complete` が bounded scan 想定時間を超えても来ない場合に備え、UI 側 watchdog timeout で `scanning` 固着を解消し、再同期または再試行へ戻せるようにする
- `stale candidate_generation` や `candidate_not_found` を利用者に分かる形で扱う
- `get_status` と `get_candidates` を初期同期と再同期に使えるようにする

### 3. Discovery And Attach Flow

- `2 秒周期` の軽い再探索 timer を入れる
- receiver 未接続時は `receiver not found` を明示する
- `hello.channel=gui` を返す receiver が `1 台だけ` の場合のみ自動接続する
- `2 台以上` 見つかった場合は接続せず、`multiple receivers detected` を表示する
- 抜き差しや再列挙時に再探索へ戻る
- 可能なら `serial_number` または安定した device path を session 内メモリで記憶し、同一 app 起動中の再接続時に優先候補にする
- disk への永続化は `Phase 1` の対象外とする

### 4. GUI State Model

- 画面表示用の単一 state model を追加する
- 最低限 `discovery state`、`receiver_state`、`scan_in_progress`、`peer_name`、`peer_address`、`candidate_generation`、`candidate list`、`selected candidate`、`last error` を持つ
- `status_snapshot` の整合判定では `receiver_state` を authoritative とし、`scan_in_progress` は UI 制御と診断補助に使う
- `busy` 状態を持ち、`scanning` や `connecting` 中のボタン制御を一元化する
- protocol 由来 state と UI 補助 state を分けて保持する
- `last error` は次の user action 開始時または `status_snapshot` による正常再同期完了時にクリアできるようにする

### 5. Main Window Phase 1 UI

- summary 表示を `port discovery dump` から `receiver 操作 UI` へ拡張する
- `Connection`、`Receiver Port`、`Protocol Version`、`Peer Name` を見える位置に表示する
- 候補一覧 view を追加し、`display_name`、`address`、`RSSI`、`Tier` を出す
- `Scan`、`Refresh`、`Connect`、`Bond Erase`、`Retry` の操作ボタンを配置する
- `Refresh` は `get_status` を主とした再同期操作として扱い、現在状態と candidate cache を取り直せるようにする
- `Tier B` は `keyboard appearance 未確認` が分かる表示にする
- `display_name=null` は `Unnamed HID device` 相当の代替表示にする

### 6. Candidate Presentation Rules

- [`candidate-listing-policy.md`](candidate-listing-policy.md) に従い `Tier A -> Tier B -> RSSI 降順 -> last_seen 新しい順` で表示する
- GUI 公開上限は `12 件` にする
- `candidate_snapshot` を authoritative view とし、`candidate_upsert` で追従更新する
- generation が切り替わったら一覧を新しい scan window として置き換える

### 7. User Action Wiring

- `Scan` は `scan_start` を送信し、受理後は `scan_started` と `candidate_snapshot` を待つ
- `Refresh` は接続済み receiver に対して `get_status` を送り、必要なら `candidate_snapshot` の再同期まで待つ
- `Connect` は選択中候補の `candidate_generation` と `candidate_id` を付けて `connect_candidate` を送信する
- `Bond Erase` は確認後に `bond_erase` を送信し、`idle` への復帰と空 snapshot を反映する
- `Retry` は未接続時の discovery / attach flow を即時再実行し、接続済み状態では `Refresh` と役割を混ぜない

### 8. Error Handling And Recovery

- `serial open failure`、`protocol parse error`、`error` message を区別して表示する
- 一時的エラー後に app 全体を再起動しなくても再探索へ戻れるようにする
- `connection_state(state=idle)` を受けた場合は `connected` 表示を解除し、`receiver_state=idle` として扱う
- `COM port` 自体の切断を検知した場合にだけ `receiver discovery` の再探索へ戻す
- `connecting` 中に `COM port` が切断した場合は、`connecting` 表示を即時解除し、port 切断を優先して `receiver discovery` の再探索へ戻す
- `unsupported_command` や `invalid_request` は開発時に原因が追える文言へ寄せる

### 9. Tests

- test の投資判断と優先順位は [`testing-policy.md`](testing-policy.md) を正本とする
- 本節は `Phase 1` で検討すべき test 候補一覧であり、現フェーズでは `少数の高価値 test を維持する` 方針を優先する
- protocol parse / serialize の unit test を追加する
- controller の state 遷移 test を追加する
- `scan_start -> candidate_snapshot -> candidate_upsert -> scan_complete` の sequence test を追加する
- `scan_complete(result=stopped)` を受けたときに `scanning` 表示を解除し connect シーケンスへ移る test を追加する
- `Refresh(get_status)` による再同期フロー test を追加する
- `bond_erase -> bonds_cleared -> status_snapshot -> candidate_snapshot` の sequence test を追加する
- `connect_candidate` 成功 / 失敗、`bond_erase`、`stale generation`、切断復帰の test を追加する
- `scan_busy` と `connect_busy` を受けたときの UI 挙動 test を追加する
- `multiple receivers detected` では自動接続しない test を追加する
- `hello.product` 不一致、`protocol_version` 不一致、`hello.channel=log` など期待外の port を接続対象から外す test を追加する
- `scan_complete` が来ない場合の timeout / recovery test を追加する
- candidate sorting と `12 件上限` の test を追加する

### 10. Windows Validation And Packaging

- `app 起動時` と `receiver 再接続時` の両方で GUI port へ再接続できることを確認する
- `LaLapadGen2` の候補表示、connect、bond erase を実機確認する
- `uv run pyinstaller packaging/zmk-usb-bridge-gui.spec` で build できることを確認する
- PoC レビュー時は [`poc-evaluation.md`](poc-evaluation.md) の pass / hold 項目に沿って結果を記録する

## Recommended Execution Order

- 実装順は `Task Breakdown` の `1 -> 10` を基本とし、まず `通信基盤` と `attach flow` を固め、その上に `UI` と `validation` を重ねる

## Milestones

- `Phase 1 Exit Criteria` が最終到達点であり、この節はそこへ至る途中チェックポイントを段階的に切ったものである

### Milestone A: Bring-up

- `hello.channel=gui` verified port へ接続できる
- `status_snapshot` と `candidate_snapshot` を画面へ反映できる
- stub firmware 相手に `Scan` と `Bond Erase` が動く

### Milestone B: Interaction Complete

- 候補一覧から 1 件選択し `Connect` を実行できる
- `connecting -> connected` と接続先名が表示される
- `multiple receivers detected` と `receiver not found` を扱える

### Milestone C: Recovery Complete

- receiver 抜き差しで自動再探索に戻れる
- `bond_erase` 後の初期化を確認できる
- receiver firmware 依存の system validation として `keyboard の bonded reconnect` を観測できる
- `PoC Evaluation` の desktop app 側 pass 条件を埋められる

## Dependencies And Split Of Responsibility

- `Task Breakdown` のうち desktop app の基盤実装、UI、state 管理、test は `stub protocol` を使って firmware 本実装待ちなしに先行できる

### Receiver Firmware 側の確認待ちが必要なもの

- 実機の `candidate_snapshot` 内容と更新頻度
- 実機の `connect_candidate` 成功条件と failure code
- `keyboard の bonded reconnect` timing
- `hello` と `status_snapshot` の再送タイミング
- Windows 実機での COM port 再列挙安定性

## Review Checklist

- この節は `implementation task` ではなく、文書レビュー時に使う確認観点である

- `Phase 1` の完了線に直接つながらない項目が混ざっていないか
- `DesktopApp 単独で先に閉じられるタスク` が明確か
- UI 仕様が `状態表示 + 候補一覧 + 操作ボタン` の最小構成に収まっているか
- receiver firmware 待ちの項目が blocker として混線していないか
- `PoC Evaluation` の観点で不足する確認項目がないか

## Deferred After Phase 1

- battery 表示と未取得時 UI
- modifier / last key / mouse button の live telemetry
- 複数 receiver の手動選択 UI
- 高度なログ viewer
- installer と自動更新
- `macOS / Linux` の正式配布
