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
- `20260419_161200_5720` / `20260419_162645_723c` の実機 scan 試験では USB attach は成功したが、`scan_start` 後に receiver protocol response が途絶したため、scan command handler から Bluetooth init / BLE scan start を外し、`ack` 経路を保護した
- `20260419_163909_ac1e` では `ack(scan_start)` / `scan_started` / generation `1` の `candidate_snapshot` まで改善したが、その後の Bluetooth init / BLE scan path で protocol response が止まったため、Bluetooth init を dedicated worker thread へ移した
- `20260419_164737_e7ca` でも scan acceptance は安定したが、その後の BLE scan start path で protocol response が止まったため、`bt_le_scan_start()` も dedicated worker thread へ移した
- `20260419_165557_8d22` でも scan acceptance は安定したが、scan window 終了後の response が止まったため、`bt_le_scan_stop()` も dedicated worker thread へ移した
- `20260419_170124_59d9` でも scan acceptance は安定したが、scan window 終了後の response が止まったため、advertisement observation processing を 1 poll あたり bounded にした
- `20260419_170751_f68c` でも scan window 終了後の response が止まったため、BLE scan callback から advertisement parse / BLE address formatting / queue-full logging を外す案を試したが、`20260419_171117` 以降で receiver application COM enumeration regression が出たため、この raw observation enqueue 化はいったん revert した
- `20260419_171445_fa4c` / `20260419_171816_f28c` / `20260419_172414_237d` では receiver application VID/PID `0x2FE3/0x0012` が見えず、A/B flash の結果 `20260419_170324_receiver_seeeduino_xiao_ble` と `20260419_175947_receiver_seeeduino_xiao_ble` では COM7 / COM8 が復帰し、`20260419_171117` / `20260419_173114` では復帰しなかった
- `20260419_180648_receiver_seeeduino_xiao_ble` は raw observation enqueue を避けたため COM7 / COM8 と GUI attach は復帰したが、`scan_start` 後に receiver protocol response が止まった
- `20260419_181448_receiver_seeeduino_xiao_ble` でも `scan_start` 後に receiver protocol response が止まり、明示的 timeout/error が返らなかった
- `20260419_181920_receiver_seeeduino_xiao_ble` は main protocol loop priority を Bluetooth TX/RX より高くして、`scan_start` の `ack` / `scan_started` までは復帰したが、scan window completion / watchdog response はまだ途絶した
- `20260419_182504_receiver_seeeduino_xiao_ble` は main loop とは別に scan deadline を見る高優先度 supervisor thread を追加したが、`scan_complete` はまだ GUI に届かなかった
- `20260419_183030_receiver_seeeduino_xiao_ble` は GUI protocol CDC writer を supervisor / main loop より高優先度にしたが、`scan_complete` はまだ GUI に届かなかった
- `20260419_183530_receiver_seeeduino_xiao_ble` は continuous active scan から低デューティ passive scan に切り替えたが、`scan_complete` はまだ GUI に届かなかった
- `20260419_183950_receiver_seeeduino_xiao_ble` は advertisement callback を一時無効化したが、`20260419_184158_7e13` でも `scan_complete` は GUI に届かなかった
- `20260419_184502_receiver_seeeduino_xiao_ble` は BLE scan を開始直後に停止する start/stop smoke path だったが、`20260419_185525_3087` でも `scan_complete` は GUI に届かなかった
- `20260419_185712_receiver_seeeduino_xiao_ble` は BLE scan を開始せず、`bt_enable(NULL)` が戻った時点で `scan_complete(result=ok)` を返す enable-only smoke path だったが、`20260419_190515_e742` でも `scan_complete` は GUI に届かなかった
- `20260419_190633_receiver_seeeduino_xiao_ble` は Bluetooth に一切触れず、protocol-only smoke path で `scan_complete(result=ok)` を返す build だったが、`20260419_190851_c8b9` でも `scan_complete` は GUI に届かなかった
- `20260419_191148_receiver_seeeduino_xiao_ble` は `scan_start` command handler 内で即時 `scan_complete(result=ok)` を返す build で、`20260419_191411_5952` により 4 本目の `scan_complete` も GUI へ届くことを確認した
- `20260419_191652_receiver_seeeduino_xiao_ble` は `scan_start` response 後に BLE scan module を明示的に kick し、`20260419_191848_05eb` により protocol-only smoke completion が GUI へ届くことを確認した
- `20260419_192118_receiver_seeeduino_xiao_ble` は after-response kick を維持したまま Bluetooth enable-only smoke に戻したが、`20260419_192301_fb3f` では `bt_enable(NULL)` 開始後に `scan_complete` / watchdog response が戻らなかった
- `20260419_192619_receiver_seeeduino_xiao_ble` は app 側 thread priority を high-priority cooperative から preemptive へ戻し、`20260419_192816_6453` により Bluetooth enable-only smoke が `scan_complete(result=ok)` まで届くことを確認した
- `20260419_192939_receiver_seeeduino_xiao_ble` は preemptive-priority baseline を維持したまま BLE scan start/stop smoke に進め、`20260419_195750_5a7b` により `bt_le_scan_start()` / immediate `bt_le_scan_stop()` が `scan_complete(result=ok)` まで届くことを確認した
- `20260419_195906_receiver_seeeduino_xiao_ble` は passive / low-duty scan で advertisement callback と candidate cache を復帰し、`20260419_200130_e27c` により `candidate_upsert` までは GUI へ届くことを確認した
- `20260419_200130_e27c` では keyboard advertising 後に `candidate_upsert` が出た一方、long scan window 終了の `scan_complete` と watchdog refresh response は戻らなかったため、次は first-candidate completion で scan を即時 close する
- `20260419_200313_receiver_seeeduino_xiao_ble` は `candidate_upsert` 後に即 `scan_complete(result=ok)` を返す first-candidate completion build で、`20260419_200654_bd5f` により protocol stall 回避と `LaLapadGen2` 表示を確認した
- `20260419_200654_bd5f` では非公開 Tier の匿名候補で先に `scan_complete(candidate_count=0)` が出たため、`20260419_200942_receiver_seeeduino_xiao_ble` では public Tier A/B candidate のみを upsert / first-candidate completion 対象にした
- `20260419_201239_d9ca` により public-candidate completion が `LaLapadGen2 candidate_upsert -> scan_complete(result=ok, candidate_count=1)` まで安定したため、scan / candidate listing / completion は pass とする
- `20260419_201654_8166` では `connect_candidate` 送信後に `ack` / `connection_state(connecting)` が戻らず、command handler 内の同期 BLE connect start が protocol response を塞ぐ疑いが出たため、`20260419_202105_receiver_seeeduino_xiao_ble` では connect start を dedicated worker へ分離した
- desktop app は bootloader らしき VID/PID `0x2886/0x0045` を検出した場合に flash hint を出せるようにした
- `connect_candidate` は擬似 timer stub から、実 `bt_conn_le_create`、`BT_SECURITY_L2` request、HID service primary discovery を行う BLE connect path へ置き換え済み
- `bond_erase` は active BLE connection cancel と `bt_unpair(BT_ID_DEFAULT, BT_ADDR_LE_ANY)` へ接続済み
- local firmware build helper は `UF2` と debug artifact を `artifacts/builds/` へ保存できる

### Not Done Yet

- `PoC Evaluation` の `Reconnect Stability` は未観測である
  - 現状 firmware は実 BLE bond / bonded reconnect を持たないため、この項目はまだ close できない
  - したがって `Reconnect Stability` の pass / hold 判定は `Phase 2` と `Phase 3` の実 firmware 実装後に持ち越す
- `receiver firmware` は scan / candidate cache / BLE connect 開始までは実装が進んだが、connect 後の HID report bridge はまだ未実装である
  - `connected` 到達は `HID service` 存在確認までで、keyboard input report discovery / subscription は未実装
  - bonded reconnect の自動再試行は未実装
  - `bond_erase` は `bt_unpair` を呼ぶが、永続 bond storage を含む実機挙動は未検証である
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
  - scan command handler から Bluetooth init / BLE scan start / BLE scan stop を分離した non-blocking response path
  - advertisement observation processing の bounded poll 化
  - `connect_candidate` の実 BLE connection establishment
  - connect 後の `BT_SECURITY_L2` request
  - connect 後の `HID service` primary discovery
  - `bond_erase` から active connection cancel と `bt_unpair` への接続
- 残実装対象:
  - `20260419_202105_receiver_seeeduino_xiao_ble` で `LaLapadGen2` の公開候補を GUI で選択し、`connect_candidate` が即時 `ack` / `connection_state(connecting)` を返したうえで、`connected` または明示的 failure code へ進むかを validation する
  - passive scan で候補が出ない場合、protocol path が健康であることを維持したまま active scan に切り替えて scan response / local name の取得を確認する
  - scan 中断、connect 開始、bond erase、unexpected disconnect と candidate cache の実機 validation
  - 実 firmware の error code 集合と GUI 表示文言の突合
- [`../foundation/candidate-listing-policy.md`](../foundation/candidate-listing-policy.md) の Tier 判定と上限 `12 件` を firmware / app 両方で同じ前提にそろえる

### 3. Manual Pairing / Connect / Bond Lifecycle

- `connect_candidate` は実 BLE connect / pairing request / HID service discovery に結び付け済み
- 接続後 validation として最低限次を実装する
  - keyboard input report の discovery / subscription
  - `key input`、`consumer control`、`mouse event` を bridge 可能な report 構成の確認
- failure 時は `protocol v1` の `error.code` または `connection_state(code,message)` へ正規化する
- `bond_erase` は `bt_unpair` へ接続済みだが、永続 bond storage を含む Windows / 実 keyboard validation を取る
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
  - `scan_start` 後に `ack` / `scan_started` / explicit failure code が返ることの実機 validation
  - scan window 終了後に `scan_complete(result=ok)` または明示的な failure code が返ることの実機 validation
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

1. `Phase 2 / Workstream 2-3`: `20260419_202105_receiver_seeeduino_xiao_ble` を実機へ flash し、scan で得た `LaLapadGen2` 候補に対する async `connect_candidate` / pairing / HID service discovery の実機 validation を行う
2. `Phase 3 / Workstream 3-4`: keyboard input report discovery / subscription、bond lifecycle、`USB HID bridge` を実装し、`PoC Evaluation` を本実装ベースで再評価する
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
- Phase 2+ の観測結果: [`../validation/phase2-validation-log.md`](../validation/phase2-validation-log.md)
