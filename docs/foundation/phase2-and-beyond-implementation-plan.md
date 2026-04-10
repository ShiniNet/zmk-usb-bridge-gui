# Phase 2 And Beyond Implementation Plan

## Purpose

- `Phase 1` 完了後の現状を整理し、実装完了までの残タスクを 1 つの document にまとめる
- `receiver firmware`、`desktop app`、`protocol`、`validation` の依存関係をそろえ、次の着手順を固定する
- `PoC 実装がどこまで終われば completion とみなすか` を明文化する

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

## Current Snapshot After Phase 1

### Done

- `desktop app Phase 1` の操作導線は実装済みで、`Windows packaged EXE` でも `attach / candidate list / connect / bond erase / receiver 再接続` まで観測済み
- `protocol v1`、`candidate listing policy`、`desktop app foundation`、`testing policy` は正本として成立している
- Python 側は `serial discovery`、`session`、`runtime`、`controller`、`ui/main_window` の責務分離と最小 test がある

### Not Done Yet

- `PoC Evaluation` の `Reconnect Stability` は未観測である
  - ただし現状 firmware は stub で、実 BLE bond / bonded reconnect を持たないため、stub のままではこの項目を close できない
  - したがって `Reconnect Stability` の pass / hold 判定は `Phase 2` と `Phase 3` の実 firmware 実装後に持ち越す
- `receiver firmware` は現状まだ stub である
  - `scan_start` は固定 candidate を返す擬似挙動
  - `connect_candidate` は実 BLE 処理ではなく擬似 `connecting -> connected`
  - `bond_erase` も local state reset 中心で、実 bond 管理の裏付けは未実装
- `battery / modifier / last key / mouse button` の telemetry は protocol と UI の両方で未着手
- `USB HID bridge` と `post-connect validation` を含む receiver の本実装は未完了

## Remaining Workstreams

### 1. Phase 1 Closeout

- `validation/phase1-validation-log.md` の未整理項目を整理する
- `Reconnect Stability` は stub firmware の範囲外であることを `validation/phase1-validation-log.md` に明記する
- `receiver not found`、`multiple receivers detected`、`connect_candidate` failure code の観測も補完する
- `Phase 1` で close する項目と、real firmware が入るまで保留する項目を固定する
- `Open Questions` のうち real firmware 前提のものは `Phase 2+` へ carry over する
- closeout 対象は stub firmware で観測できる範囲に限定し、real firmware 前提の `Open Questions` 全件解消までは要求しない

### 2. Receiver Firmware Stub Replacement

- 前提:
  - firmware 実装前提は [`project-concept.md`](project-concept.md) の `Initial Firmware Bring-up Assumptions` を正本とし、現行の独立 `Zephyr project` 構成で進める
- `CDC ACM(2 instance)` の現行 skeleton は維持しつつ、中身を実動作へ置き換える
- 実装対象:
  - BLE central scan の bounded window 実装
  - advertisement / scan response の解析
  - `BLE address` 主キーの candidate cache
  - `candidate_generation` と `candidate_id` の実運用
  - `candidate_snapshot + candidate_upsert + scan_complete` の実イベント化
- `candidate-listing-policy.md` の Tier 判定と上限 `12 件` を firmware / app 両方で同じ前提にそろえる
- 固定 `default_candidate` と擬似 state 遷移を排除し、実観測に基づく state 更新へ置き換える

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

- `battery / modifier / last key / mouse button` を `PoC scope` の completion 項目として追加実装する
- 先に protocol extension と versioning policy を決める
  - 既定方針は `protocol v1` の event / optional field 拡張で前方互換を保ち、`protocol_version` は据え置く
  - ただし既存 message の必須 field や解釈を壊す変更が必要になった場合は `protocol v2` を切る
  - 既存 `hello / status_snapshot / command / ack / error / event` の枠は維持する
- firmware 側で未取得値をどう表すかを固定する
  - `battery`: `null` 許容
  - `last key` / `mouse button`: transient event と state snapshot のどちらを正とするか整理する
- desktop app 側では `未取得 / 未対応 / 切断中` を区別して表示する

### 6. Desktop App Phase 2+

- 実 firmware 応答に合わせて `error surface` を見直す
- reconnect 中、telemetry 未取得、candidate 空一覧などの表示を `Phase 1` UI から拡張する
- summary 領域に telemetry を無理なく追加できる layout へ整理する
- 現行 `Refresh`、watchdog、再探索戦略が実 firmware でも過不足ないかを再評価する
- `hello.firmware_version` を実 version 表示へつなぎ、観測ログとの突合をしやすくする

### 7. Test And Validation Expansion

- `testing-policy.md` に従い、守るべき contract が増えた箇所だけ test を拡張する
- 追加候補:
  - telemetry event parse / state update
  - reconnect sequence と detach / rediscovery の競合
  - 実 error code に対応する controller の recovery
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
  - stub 状態で観測できる範囲を閉じ、stub 状態では観測できない項目を `Phase 2+` へ正しく送る
- Exit Criteria:
  - `validation/phase1-validation-log.md` に、`Reconnect Stability` を `Phase 3` へ移す理由と、補助観測項目の扱いが記録されている
  - `Phase 1` で close する項目と `Phase 2+` へ carry over する項目が分離され、real firmware 前提の `Open Questions` が pending と混在していない

### Phase 2: Real Receiver Core

- 目的:
  - stub firmware をやめて、実 BLE scan / candidate cache / manual connect の核を成立させる
- Main Deliverables:
  - 実 scan による `candidate_snapshot`
  - `connect_candidate` の実 connect / pairing
  - `bond_erase` の実 bond reset
- Exit Criteria:
  - 固定 candidate ではなく実機観測の候補が GUI に出る
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
  - `project concept` にある `battery / modifier / last key / mouse button` 表示を実装する
- Main Deliverables:
  - telemetry protocol extension
  - desktop app UI 拡張
  - 未取得値 / 非対応値の表示方針
- Exit Criteria:
  - 主要 telemetry が GUI に表示される
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

1. `Phase 1.5 / Workstream 1`: `Phase 1` の未解決項目を棚卸しし、stub firmware の範囲と carry-over 項目を固定する
2. `Phase 2 / Workstream 2`: firmware の `scan_start / candidate cache / connect_candidate / bond_erase` から stub を外す
3. `Phase 3 / Workstream 3-4`: `post-connect validation`、bond lifecycle、`USB HID bridge` を実装し、`PoC Evaluation` を本実装ベースで再評価する
4. `Phase 4 / Workstream 5-6`: telemetry protocol と GUI 表示を追加し、desktop app の実 firmware 追従を仕上げる
5. `Phase 5 / Workstream 7-8`: test / packaging / validation を `PoC scope` completion に合わせて締める

### Why This Order

- telemetry を先に足しても、receiver core が stub のままだと価値検証にならない
- bonded reconnect は本 project の価値仮説に直結するが、現状 stub では観測不能なので、まず real firmware を成立させる必要がある
- desktop app は Phase 1 で土台があるため、次の主戦場は firmware と protocol extension になる

## Out Of Scope Until Completion

- `macOS / Linux` の正式配布
- 複数 receiver の手動選択 UI
- 複数 keyboard profile 管理
- installer 作成
- auto update
- 高度な log viewer

## Related Documents

- project 全体前提: [`project-concept.md`](project-concept.md)
- protocol 正本: [`protocol-v1.md`](protocol-v1.md)
- candidate 公開条件: [`candidate-listing-policy.md`](candidate-listing-policy.md)
- desktop app 前提: [`desktop-app-foundation.md`](desktop-app-foundation.md)
- test 投資方針: [`testing-policy.md`](testing-policy.md)
- PoC 判定基準: [`poc-evaluation.md`](poc-evaluation.md)
- Phase 1 の観測結果: [`../validation/phase1-validation-log.md`](../validation/phase1-validation-log.md)
