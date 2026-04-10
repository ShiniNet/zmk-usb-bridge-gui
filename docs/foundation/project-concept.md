# Project Concept

## Document Purpose

- `zmk-usb-bridge-gui` を `zmk-usb-bridge` とは別 project として立ち上げる前提を整理する
- `Windows 優先の desktop GUI` から、receiver の状態表示と pairing 操作を行う `PoC` の成立条件を明文化する
- `既存 ZMK BLE keyboard 無改造` を維持したまま、`一覧表示 + 手動選択 pairing` が現実的かを見極める
- 詳細仕様は `foundation/` 配下の正本 document に分けて管理する

## Canonical Documents

- protocol の正本は [`protocol-v1.md`](protocol-v1.md)
- candidate 評価と GUI 公開モデルの正本は [`candidate-listing-policy.md`](candidate-listing-policy.md)
- desktop app 技術スタックと `COM port` 検出方式の正本は [`desktop-app-foundation.md`](desktop-app-foundation.md)
- `PoC` の `pass / hold / fail` 条件の正本は [`poc-evaluation.md`](poc-evaluation.md)

## Project Boundary

- `zmk-usb-bridge-gui` は `ZMK keyboard firmware` の拡張 project ではない
- 本 project は `receiver 側 firmware` と `desktop GUI app` を対象にする **独立した Zephyr project** である
- 接続対象の `ZMK BLE keyboard` は既存機をそのまま使う前提で、keyboard 側 firmware 改造は要求しない
- `CDC ACM`、debug log、候補一覧公開、GUI 制御 protocol は **receiver 側 USB device / firmware** の仕様である
- したがって `GUI 用 endpoint` と `log 用 endpoint` を持つのは receiver 側であり、keyboard 側に複数 endpoint を要求するものではない

## Positioning

- 本 project は `NoGUI 1:1 bridge` の後継ではなく、`GUI 前提の別系統 receiver` として扱う
- 現行 `zmk-usb-bridge` は `allowlist + 自動接続` を重視する reference として扱う
- `zmk-usb-bridge-gui` は `候補一覧表示 + 利用者選択` を重視する
- GUI は receiver 本体に載せる組み込み画面ではなく、`Windows desktop app` を第一候補とする
- 初期 PoC は `Windows` を優先し、`macOS` と `Linux` は成立阻害がないかを後続評価とする
- 両 project は firmware / build / deliverable を分けて扱う
- 実装単位としては `receiver firmware` と `desktop app` を別 deliverable として扱い、`ZMK keyboard firmware` はスコープ外とする

## Current Assumptions

- project 名は `zmk-usb-bridge-gui` とする
- 初期評価対象は `LaLapadGen2` の 1 台に絞る
- `既存 ZMK キーボード無改造` を必須とする
- receiver は `ZMK keyboard` とは別に build / flash される独立 firmware とする
- GUI 側では receiver を `COM port 自動検出` する

## Problem / Value Hypothesis

- `Windows` の標準 BLE 接続経路より、専用 receiver の方が reconnect 安定性で優位を出せる可能性がある
- 一般的な BLE UI より、専用 GUI の方が `接続状態 / keyboard 名 / battery / 入力状態` を利用者に分かりやすく見せられる
- `allowlist 編集` を要求せず、候補一覧から手動で pairing できる導線は、GUI 付き project の価値になりうる
- `既存 ZMK キーボード無改造` を守れれば、利用開始コストを上げずに receiver 側だけで UX を改善できる

## Initial PoC Scope

### Phase 1 Completion Line

- 第一段階のゴールは、`Windows desktop app から receiver を自動検出し、候補一覧に出た LaLapadGen2 を利用者選択で pairing / connect 開始でき、接続状態と接続先名を安定して確認できること` とする
- ここでいう `PoC 完了` は **初期スコープの機能境界** を指し、品質評価や kill 判定の閾値は [`poc-evaluation.md`](poc-evaluation.md) を正本とする

### Minimum Functional Set For PoC Complete

- receiver と GUI の間で `hello`、`status snapshot`、`command ack / error` の最小往復が成立する
- GUI から `scan_start` を実行し、候補一覧を手動更新できる
- GUI が候補一覧から 1 件を選び、`pairing / connect` を開始できる
- `idle / scanning / connecting / connected` の状態遷移と、接続先 keyboard 名を GUI で表示できる
- GUI から `bond erase` を実行できる
- 参照対象 `LaLapadGen2` 1 台で end-to-end 動作を確認できる

### Deferred Until After Phase 1

- `battery` 表示の有無や、未取得時の UI 表現
- `modifier`、`last key`、`mouse button` の live 表示
- 候補一覧の磨き込みを超える高度な candidate 評価や複数 keyboard の本格管理
- `macOS / Linux` の利用性確認
- UI の見た目の磨き込みや高度なログ表示

### Bring-up Reference Environment

- 初期 bring-up の参照 board は `Seeed XIAO nRF52840` とする
- desktop app の参照環境は `Windows` とする
- USB 構成の第一候補は `USB HID + CDC ACM(2 instance)` の composite device とする
- これらは **実装開始用の参照前提** であり、この時点では正式固定仕様ではない
- firmware 観点の補足と理由は `Initial Firmware Bring-up Assumptions` を参照する
- board や USB 構成を変更する場合も、まずは `LaLapadGen2 1 台で第一段階を成立させる` というゴールを優先する

### Full Scope Reference

- 以下は `Initial PoC` 全体で見据える表示・操作の全体像であり、`Phase 1` 完了条件そのものは `Minimum Functional Set For PoC Complete` を正とする

- 現在の接続状態を表示できる
- 接続中キーボード名を表示できる
- battery 情報を表示できる
- modifier key 状態を表示できる
- 直近キー入力の簡易表示を行える
- mouse button 状態を表示できる
- 候補デバイス一覧を表示できる

### User Actions

- GUI から scan 開始を指示できる
- GUI から候補一覧を再取得できる
- GUI で選択した候補へ pairing / connect を開始できる
- GUI から `bond erase` を実行できる

## Candidate Listing Policy

- 理想は `ZMK keyboard だけ` を一覧表示対象にすることだが、`無改造必須` のため完全判定は前提にしない
- PoC では、候補一覧表示時点で `できるだけ keyboard らしい BLE HID` に絞る
- 最低条件の第一候補は `connectable advertisement` と `HID service`
- `keyboard appearance` は強い補助条件として使う
- `local name` は表示用と補助判断に使ってよい
- 現行 `NoGUI` 版のような `allowlist` は GUI 版 PoC では使わない
- 候補一覧は `receiver が自動接続するための内部候補` ではなく、`GUI で利用者に見せる候補` として扱う
- 最終採用は `利用者選択` と `接続後 validation` の両方を通した相手だけに限定する
- 詳細仕様は [`candidate-listing-policy.md`](candidate-listing-policy.md) を正本とする

## Communication Model

### Why `CDC ACM`

- `Windows 優先の最速 PoC` として実装しやすい
- receiver と desktop app の双方向通信を単純に構成しやすい
- bring-up 時にログ確認もしやすい

### CDC ACM Endpoint 構成

- ここでいう endpoint は **receiver 側 USB device** が host PC に見せる endpoint を指す
- `GUI 用 channel` と `debug log` は **別々の CDC ACM endpoint** として分離する
- GUI 用 endpoint: machine-readable なメッセージ交換専用
- log 用 endpoint: human-readable なデバッグ出力専用

### Constraints

- GUI との通信は `machine-readable` なメッセージ形式にする
- message format は `line-delimited JSON` で固定する
- GUI 起動時には `hello` か `status snapshot` を返し、自動検出と初期同期をしやすくする
- GUI から送る command には `request_id` を持たせ、`ack` と `error` は同じ `request_id` を返す
- `protocol v1` の詳細仕様は [`protocol-v1.md`](protocol-v1.md) を正本とする

### Initial Message Examples

- 以下の例は `protocol v1` の代表例であり、詳細は [`protocol-v1.md`](protocol-v1.md) を参照する

```json
{"type":"hello","product":"zmk-usb-bridge-gui","protocol_version":1,"channel":"gui"}
{"type":"status_snapshot","receiver_state":"idle","peer_name":null,"peer_address":null,"scan_in_progress":false,"candidate_generation":7,"candidate_count":0}
{"type":"candidate_snapshot","candidate_generation":7,"candidates":[]}
{"type":"command","request_id":16,"name":"scan_start"}
{"type":"ack","request_id":16,"name":"scan_start","accepted":true}
{"type":"event","name":"scan_started","candidate_generation":8}
{"type":"event","name":"candidate_upsert","candidate_generation":8,"candidate":{"candidate_id":3,"ble_address":"E4:B6:69:12:34:56","display_name":"LaLapadGen2","connectable":true,"has_hid_service":true,"has_keyboard_appearance":true,"rssi":-49}}
{"type":"event","name":"scan_complete","candidate_generation":8,"result":"ok","candidate_count":1}
{"type":"command","request_id":17,"name":"connect_candidate","candidate_generation":8,"candidate_id":3}
{"type":"ack","request_id":17,"name":"connect_candidate","accepted":true}
{"type":"event","name":"connection_state","state":"connecting","peer_name":null,"peer_address":null}
{"type":"event","name":"connection_state","state":"connected","peer_name":"LaLapadGen2","peer_address":"E4:B6:69:12:34:56"}
{"type":"error","request_id":17,"name":"connect_candidate","code":"candidate_not_found","message":"candidate_id not found"}
{"type":"command","request_id":18,"name":"bond_erase"}
{"type":"ack","request_id":18,"name":"bond_erase","accepted":true}
{"type":"event","name":"bonds_cleared","cleared_count":1}
```

## Desktop App Direction

- GUI は最初から豪華にせず、`状態表示 + 候補一覧 + 操作ボタン` の最小構成を優先する
- 実装言語は PoC 速度を優先し、`Python + PySide6` を第一実装とする
- ただし利用者体験を考え、PoC 段階から最終的に `EXE` 化しやすい構成を優先する
- 技術スタックと `COM port` 検出方式の正本は [`desktop-app-foundation.md`](desktop-app-foundation.md) とする

## Firmware Direction

- receiver firmware は `zmk-usb-bridge` をリファレンスとして読みつつも、`候補一覧 + 手動選択` 前提の独立した設計を取る（fork ではなく新規実装）
- receiver firmware は `ZMK keyboard firmware` とは別 firmware として build / flash / 配布する
- pairing scan 中に `最初の候補へ即 connect` する挙動は採らない
- candidate cache は GUI 向けに公開できるモデルとして持つ
- GUI からの `connect_candidate` を受けて初めて connect を開始する
- 接続後 validation は `HID service`、`keyboard input report`、必要な report discovery の成立を通過条件にする
- bond 済みデバイスへの reconnect は firmware が自動処理する。GUI からの明示的な reconnect 指示は持たない
- `LaLapadGen2` を参照対象にしつつも、設計上は将来の ZMK keyboard 一般化を阻害しない責務分割を保つ

## Initial Firmware Bring-up Assumptions

- この節は `PoC 着手時点の初期前提` であり、最終固定仕様ではない
- 初期 bring-up board の第一候補は `Seeed XIAO nRF52840` とする
- 理由は `nRF52840` で BLE central と USB device を同一 SoC に載せやすく、既存 `zmk-usb-bridge` 側の知見を参照しやすいため
- USB 構成の第一候補は `USB HID + CDC ACM(2 instance)` の composite device とする
- Zephyr 側では `GUI 用 CDC ACM` と `log 用 CDC ACM` を別 instance として持ち、DTS / overlay で役割を分ける前提で考える
- BLE scan の第一候補は Zephyr Bluetooth host の central 側 scan API を使う
- 具体的な実装入口は `bt_le_scan_start(...)` 相当の API を基準にし、scan callback で advertisement を候補評価へ流す
- candidate cache は `固定長 array` かそれに準じる単純構造を第一候補にする
- cache の最小 field は `candidate_id`、`BLE address`、`local name`、`connectable`、`has_hid_service`、`has_keyboard_appearance`、`last_seen`、`RSSI` を想定する
- cache は `GUI 表示用の snapshot source` と `connect_candidate` 実行時の `lookup source` を兼ねる
- ここでの前提は実装着手の足場であり、正式仕様は各正本 document に従う
- `protocol と command / event` は [`protocol-v1.md`](protocol-v1.md) を正本とする
- `candidate cache の GUI 公開モデル` は [`candidate-listing-policy.md`](candidate-listing-policy.md) を正本とする
- `GUI/log CDC instance` と `COM port` 識別は [`desktop-app-foundation.md`](desktop-app-foundation.md) を正本とする

## Non-Goals For Initial PoC

- 組み込み display を使う GUI receiver 本体
- `macOS` と `Linux` の同時成立
- 複数 keyboard の本格的な profile 管理
- 汎用 BLE HID 機器への広範な正式対応
- 詳細 debug log を GUI に常時表示すること
- 派手な desktop UI や高度な設定画面

## Difficulty Assessment

- 全体難易度は `やや高`
- 主因は `候補一覧の外部公開`、`手動選択 pairing`、`GUI 向け双方向 protocol` の追加にある
- `Windows 優先`、`CDC ACM`、`LaLapadGen2 1 台固定`、`簡素な desktop app` に絞ることで、PoC としての現実性は高い

### Relative Cost

- desktop app 単体: `中`
- CDC ACM 通信と COM port 自動検出: `中`
- 接続状態 / 入力状態の GUI 向け正規化: `中`
- 候補一覧取得と表示: `やや高`
- 選択候補への pairing / connect: `やや高`
- battery 表示の安定化: `中〜やや高`

## Recommended PoC Sequence

- 実装時は次の順を第一候補とする
- `Phase 1 必須機能の成立 -> PoC 評価 -> deferred 項目の拡張` の順で進める

1. `CDC ACM` の GUI 用双方向 channel を用意する
2. `hello / status snapshot / command ack` の最小 protocol を定義する
3. 接続状態と接続先 keyboard 名を GUI 表示できるようにする
4. candidate cache を GUI 向けに公開し、一覧表示を成立させる
5. GUI から選択した候補への pairing / connect を成立させる
6. `bond erase` と再初期化の一連の操作を成立させ、`PoC Phase 1` を評価する
7. `battery` 表示や未取得時 UI を追加する
8. `modifier`、直近キー、mouse button などの live telemetry を拡張する

## Open Questions

- battery の取得失敗や未取得を GUI 上でどう表現するか

### Resolved References

- 解決済みの論点は [`candidate-listing-policy.md`](candidate-listing-policy.md) と [`desktop-app-foundation.md`](desktop-app-foundation.md) を正本とする

## Validation Needed

- この節は `PoC で答えを出すべき問い` の一覧であり、正式な `pass / fail` 基準そのものではない
- `PoC` 評価基準の現時点の正本は [`poc-evaluation.md`](poc-evaluation.md) とする

- `LaLapadGen2` を無改造で候補一覧表示し、手動選択 pairing まで到達できるか
- `HID service + keyboard appearance` の候補絞り込みで誤候補がどの程度残るか
- `CDC ACM` 追加が receiver の HID 動作や reconnect 安定性を悪化させないか
- COM port 自動検出が Windows 実機で十分安定するか
- 接続状態、入力状態、battery 表示が実利用で分かりやすいか
- `allowlist なし` でも GUI 版の pairing 導線が十分扱いやすいか

## Kill Criteria

- 正式な `fail / hold` 判定は [`poc-evaluation.md`](poc-evaluation.md) を正本とする
