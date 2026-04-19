# Phase 2 And Beyond Implementation Plan

## Purpose

- `Phase 1` 完了後の現状を整理し、実装完了までの残タスクを 1 つの document にまとめる
- `receiver firmware`、`desktop app`、`protocol`、`validation` の依存関係をそろえ、次の着手順を固定する
- `PoC 実装がどこまで終われば completion とみなすか` を明文化する
- この document は実装中だけ参照する一時 plan とし、完了後は確定した内容を各正本 document へ移して役目を終える

## This Document Defines

- 本文書では `Phase 1` 完了時点で合意している対象範囲を `PoC scope` と呼ぶ
- ここでいう `implementation complete` は、`PoC scope` の完了を指す
- 具体的には次を満たした状態を completion line とする
  - `receiver firmware` が stub ではなく、実 BLE scan / candidate cache / manual pairing / connect / bonded reconnect を持つ
  - receiver が `LaLapadGen2` などの `ZMK keyboard` から受けた `key input`、`consumer control`、`mouse event` を host PC へ正しく橋渡しできる
  - `desktop app` が `connection state / candidate list / battery / modifier / last key / mouse button` を表示できる
  - `bond erase`、receiver の抜き差し、bonded reconnect の recovery が Windows 実機で確認済みである
  - `Windows packaged EXE` の再現可能な build 手順が維持されている
  - 最低限の自動 test と `validation` document が対象 contract に追従している
- completion までの対象外項目は `Out Of Scope Until Completion` を参照する

## Current Snapshot After Phase 1.5

### Done

- `desktop app Phase 1` の操作導線は実装済みで、`Windows packaged EXE` でも `attach / candidate list / connect / bond erase / receiver 再接続` まで観測済み
- `protocol v1`、`candidate listing policy`、`desktop app foundation`、`debug log foundation`、`testing policy` は正本として成立している
- Python 側は `serial discovery`、`session`、`runtime`、`controller`、`ui/main_window` の責務分離と最小 test がある
- `protocol v1` と desktop app は `battery / modifier / last key / mouse button` の telemetry field と `telemetry_update` event を扱える
- desktop app の summary には telemetry 表示が入り、`Disconnected`、`Unsupported`、`Pending / Not reported yet` を区別できる
- desktop app には `GUI app event`、`receiver GUI protocol`、`receiver debug serial`、`keyboard debug serial` を同一 session log に集約する debug capture の土台がある
- `COM Port Detection Stability` は最新 Windows 実機再検証で pass に戻り、`GUI 起動 -> dongle 接続 -> attached -> dongle 抜去 -> 再接続 -> attached` まで確認済みである
- receiver firmware は固定 candidate だけの stub から進み、実 BLE active scan、advertisement 解析、`BLE address` 主キーの candidate cache、Tier A/B 相当の公開候補並び替え、`candidate_upsert`、`scan_complete` を持つ
- local firmware build helper は `UF2` と debug artifact を `artifacts/builds/` へ保存できる

### Not Done Yet

- `PoC Evaluation` の `Reconnect Stability` は未観測である
  - 現状 firmware は実 BLE bond / bonded reconnect を持たないため、この項目はまだ close できない
  - したがって `Reconnect Stability` の pass / hold 判定は `Phase 2` と `Phase 3` の実 firmware 実装後に持ち越す
- `receiver firmware` は scan / candidate cache までは実装が進んだが、connect 以降はまだ stub が残っている
  - `connect_candidate` は実 BLE 処理ではなく擬似 `connecting -> connected`
  - `bond_erase` も local state reset 中心で、実 bond 管理の裏付けは未実装
- `battery / modifier / last key / mouse button` は protocol と UI の土台はあるが、実 keyboard / HID report 由来の値にはまだ結び付いていない
- `USB HID bridge` と `post-connect validation` を含む receiver の本実装は未完了

## Remaining Workstreams

### 1. Phase 1.5 Closeout

- `validation/phase1-validation-log.md` には、`Reconnect Stability` が real firmware 前提であることと、Phase 2+ へ carry over する理由を記録済み
- `Phase 1 / 1.5` で close する項目と、real firmware が入るまで保留する項目は概ね分離済み
- `COM Port Detection Stability` は `20260419_152258_78ec.jsonl` で reconnect scenario まで pass と判断済み
- 追加で拾うと有用な補助観測は次のままとする
  - `receiver not found`
  - `multiple receivers detected`
  - 実 firmware の `connect_candidate` failure code
  - candidate noise と `12 件上限` 周りの実機観測
- これ以降の closeout は実装 blocker ではなく、Phase 2+ validation の補助作業として扱う

### 2. Receiver Firmware Core Completion

- 前提:
  - firmware 実装前提は [`../foundation/project-concept.md`](../foundation/project-concept.md) の `Initial Firmware Bring-up Assumptions` を正本とし、現行の独立 `Zephyr project` 構成で進める
- `CDC ACM(2 instance)` の現行 skeleton は維持しつつ、中身を実動作へ置き換える
- 実装済み:
  - BLE central scan の bounded window 実装
  - advertisement の解析
  - `BLE address` 主キーの candidate cache
  - `candidate_generation` と `candidate_id` の実運用
  - `candidate_snapshot + candidate_upsert + scan_complete` の実イベント化
  - 固定 `default_candidate` 依存の candidate listing からの脱却
- 残実装対象:
  - 実機 scan での `LaLapadGen2` 表示時間、candidate noise、Tier 判定、`12 件上限` の validation
  - scan 中断、connect 開始、bond erase、unexpected disconnect と candidate cache の整合確認
  - 実 firmware の error code 集合と GUI 表示文言の突合
- [`../foundation/candidate-listing-policy.md`](../foundation/candidate-listing-policy.md) の Tier 判定と上限 `12 件` を firmware / app 両方で同じ前提にそろえる
- 残る擬似 state 遷移は `connect_candidate` 以降に限定されるため、次 workstream で実 BLE lifecycle へ置き換える

### 3. Manual Pairing / Connect / Bond Lifecycle

- `connect_candidate` を実 BLE connect / pairing / service discovery に結び付ける
- 接続後 validation として最低限次を実装する
  - `HID service` discovery
  - keyboard input report の discovery / subscription
  - `key input`、`consumer control`、`mouse event` を bridge 可能な report 構成の確認
- failure 時は `protocol v1` の `error.code` または `connection_state(code,message)` へ正規化する
- `bond_erase` は実 bond storage と整合する実装へ置き換える
- 予期せぬ切断時に `connection_state(state=idle)` を自発通知し、必要なら bonded reconnect を firmware が自動再試行する

### 4. USB HID Bridge Completion

- 接続済み keyboard の `key input`、`consumer control`、`mouse event` を host PC 向け `USB HID` へ橋渡しする
- `CDC ACM` 追加後も入力欠落やフリーズが起きないことを確認する
- `USB Regression Safety` は実入力で再評価し、stub 段階の観測ではなく本実装ベースへ更新する
- report format や modifier 状態の取り出し方は telemetry 拡張と競合しない責務分割にしておく

### 5. Telemetry Extension

- `battery / modifier / last key / mouse button` を `PoC scope` の completion 項目として実値に結び付ける
- protocol extension と desktop app 表示の土台は先行実装済みで、既定方針は `protocol v1` の event / optional field 拡張のままとする
- 残実装対象:
  - firmware 側で `battery` を実 GATT / HID 情報から取得する
  - `modifier / last key / mouse button` を HID report parsing から更新する
  - `last key` / `mouse button` を transient event と state snapshot のどちらで扱うかを実入力ベースで確定する
  - 実値、未取得、未対応、切断中の表示が Windows 実機で破綻しないことを確認する

### 6. Desktop App Phase 2+

- 実 firmware 応答に合わせて `error surface` を見直す
- reconnect 中、telemetry 未取得、candidate 空一覧などの表示を実 firmware の挙動に合わせて調整する
- summary 領域の telemetry 表示は実装済みだが、実値が入った状態での layout と文言を再評価する
- 現行 `Refresh`、watchdog、再探索戦略が実 firmware でも過不足ないかを再評価する
- `hello.firmware_version` を実 version 表示へつなぎ、観測ログとの突合をしやすくする
- `debug-log-foundation.md` に沿った統合 capture の土台はあるため、実 firmware validation 時に必要な event / field を追加する

### 7. Test And Validation Expansion

- `testing-policy.md` に従い、守るべき contract が増えた箇所だけ test を拡張する
- 追加候補:
  - 実 connect / pairing / failure code に対応する controller recovery
  - reconnect sequence と detach / rediscovery の競合
  - HID report parsing から telemetry update までの contract
- `firmware-app` 跨ぎの全面自動化は後回しにしつつ、`stub` 依存が強すぎる箇所は少しずつ integration 化する
- `validation` は `Phase 1 closeout` と `Phase 2+` の実機観測を分けて記録する

### 8. Packaging And Release Readiness

- `Windows packaged EXE` の build 手順を repo 状態に追従させ続ける
- version 埋め込み、artifact 命名、platform 別出力先の扱いを固定する
- CI 常時実行は `protocol` と test 範囲が落ち着いた段階で導入判断する
- installer や auto update は `PoC scope` では deferred のままとする

## Recommended Phase Sequence

### Phase 1.5: Closeout And Risk Lock

- 目的:
  - stub / partial firmware 状態で観測できる範囲を閉じ、real BLE lifecycle 前提の項目を `Phase 2+` へ正しく送る
- Exit Criteria:
  - `validation/phase1-validation-log.md` に、`Reconnect Stability` を `Phase 3` へ移す理由と、補助観測項目の扱いが記録されている
  - `Phase 1` で close する項目と `Phase 2+` へ carry over する項目が分離され、real firmware 前提の `Open Questions` が pending と混在していない
- Status:
  - achieved
  - current code / validation document 上、GUI attach / receiver reconnect は Phase 2+ の blocker ではない

### Phase 2: Real Receiver Core

- 目的:
  - 実 BLE scan / candidate cache の土台を維持しながら、`connect_candidate` 以降の stub を実 BLE connect / pairing / bond lifecycle へ置き換える
- Main Deliverables:
  - 実 scan による `candidate_snapshot` / `candidate_upsert` の実機 validation
  - `connect_candidate` の実 connect / pairing
  - `bond_erase` の実 bond reset
- Exit Criteria:
  - 固定 candidate ではなく実機観測の候補が GUI に出ることを Windows 実機で確認できる
  - `LaLapadGen2` を GUI 選択で実接続できる

### Phase 3: Reconnect And Bridge Hardening

- 目的:
  - bonded reconnect と USB HID bridge を、本 project の価値仮説に必要な品質まで安定化する
- Main Deliverables:
  - 切断検知と reconnect sequence
  - `key input`、`consumer control`、`mouse event` の bridge
  - failure code の整理
- Exit Criteria:
  - `PoC Evaluation` の `Reconnect Stability` pass 条件として、少なくとも `1 回` の切断復帰試験で `15 秒以内` に `connected` へ戻る
  - `PoC Evaluation` の `Hold Criteria` にある `3 回試して 1 回以上失敗する` に該当しない
  - `key input`、`consumer control`、`mouse event` の実入力で回帰がない

### Phase 4: Telemetry And UX Expansion

- 目的:
  - `project concept` にある `battery / modifier / last key / mouse button` 表示を実 keyboard / HID report 由来の値へ結び付ける
- Main Deliverables:
  - firmware 側 telemetry source
  - desktop app UI の実値表示確認
  - 未取得値 / 非対応値の表示方針
- Exit Criteria:
  - 主要 telemetry が実入力 / 実 keyboard 状態に追従して GUI に表示される
  - 未取得時も UI が破綻しない

### Phase 5: Completion Hardening

- 目的:
  - `PoC scope` を継続開発可能な形で締める
- Main Deliverables:
  - test の最低限追加
  - packaging 手順の固定
  - completion 時点の validation 更新
- Exit Criteria:
  - `implementation complete` の各条件を満たし、次の拡張項目と切り分けられている

## Immediate Next Implementation Plan

### Priority Order

1. `Phase 2 / Workstream 2-3`: 実 BLE scan の実機 validation を取りながら、`connect_candidate / pairing / bond_erase` から stub を外す
2. `Phase 3 / Workstream 3-4`: `post-connect validation`、bond lifecycle、`USB HID bridge` を実装し、`PoC Evaluation` を本実装ベースで再評価する
3. `Phase 4 / Workstream 5-6`: telemetry を実 keyboard / HID report 由来の値へ接続し、desktop app の実 firmware 追従を仕上げる
4. `Phase 5 / Workstream 7-8`: test / packaging / validation を `PoC scope` completion に合わせて締める

### Why This Order

- GUI attach / receiver reconnect は最新 Windows 実機ログで pass したため、Phase 2+ では GUI を firmware validation の観測面として使える
- 実 BLE scan と telemetry UI の土台はすでにあるため、次の価値検証は `connect_candidate` 以降の実 BLE lifecycle に集中する
- bonded reconnect は本 project の価値仮説に直結するが、実 bond / reconnect が入るまでは観測不能なので、manual connect と bond lifecycle を先に成立させる
- desktop app は Phase 1.5 で土台があるため、次の主戦場は firmware の connect / HID bridge / reconnect になる

## Out Of Scope Until Completion

- `macOS / Linux` の正式配布
- 複数 receiver の手動選択 UI
- 複数 keyboard profile 管理
- installer 作成
- auto update
- 高度な log viewer

## Related Documents

- project 全体前提: [`../foundation/project-concept.md`](../foundation/project-concept.md)
- protocol 正本: [`../foundation/protocol-v1.md`](../foundation/protocol-v1.md)
- candidate 公開条件: [`../foundation/candidate-listing-policy.md`](../foundation/candidate-listing-policy.md)
- desktop app 前提: [`../foundation/desktop-app-foundation.md`](../foundation/desktop-app-foundation.md)
- debug log 収集方針: [`../foundation/debug-log-foundation.md`](../foundation/debug-log-foundation.md)
- test 投資方針: [`../foundation/testing-policy.md`](../foundation/testing-policy.md)
- PoC 判定基準: [`../foundation/poc-evaluation.md`](../foundation/poc-evaluation.md)
- Phase 1 の観測結果: [`../validation/phase1-validation-log.md`](../validation/phase1-validation-log.md)
