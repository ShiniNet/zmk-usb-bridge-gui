# Project Concept

## Document Purpose

- `zmk-usb-bridge-gui` を `zmk-usb-bridge` とは別 project として立ち上げる前提を整理する
- `Windows 優先の desktop GUI` から、receiver の状態表示と pairing 操作を行う `PoC` の成立条件を明文化する
- `既存 ZMK BLE keyboard 無改造` を維持したまま、`一覧表示 + 手動選択 pairing` が現実的かを見極める

## Positioning

- 本 project は `NoGUI 1:1 bridge` の後継ではなく、`GUI 前提の別系統 receiver` として扱う
- 現行 `zmk-usb-bridge` は `allowlist + 自動接続` を重視する reference として扱う
- `zmk-usb-bridge-gui` は `候補一覧表示 + 利用者選択` を重視する
- GUI は receiver 本体に載せる組み込み画面ではなく、`Windows desktop app` を第一候補とする
- 初期 PoC は `Windows` を優先し、`macOS` と `Linux` は成立阻害がないかを後続評価とする
- 両 project は firmware / build / deliverable を分けて扱う

## Current Assumptions

- project 名は `zmk-usb-bridge-gui` とする
- 初期評価対象は `LaLapadGen2` の 1 台に絞る
- `既存 ZMK キーボード無改造` を必須とする
- GUI 側では receiver を `COM port 自動検出` する

## Problem / Value Hypothesis

- `Windows` の標準 BLE 接続経路より、専用 receiver の方が reconnect 安定性で優位を出せる可能性がある
- 一般的な BLE UI より、専用 GUI の方が `接続状態 / keyboard 名 / battery / 入力状態` を利用者に分かりやすく見せられる
- `allowlist 編集` を要求せず、候補一覧から手動で pairing できる導線は、GUI 付き project の価値になりうる
- `既存 ZMK キーボード無改造` を守れれば、利用開始コストを上げずに receiver 側だけで UX を改善できる

## Initial PoC Scope

### Display

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

## Communication Model

### Why `CDC ACM`

- `Windows 優先の最速 PoC` として実装しやすい
- receiver と desktop app の双方向通信を単純に構成しやすい
- bring-up 時にログ確認もしやすい

### CDC ACM Endpoint 構成

- `GUI 用 channel` と `debug log` は **別々の CDC ACM endpoint** として分離する
- GUI 用 endpoint: machine-readable なメッセージ交換専用
- log 用 endpoint: human-readable なデバッグ出力専用

### Constraints

- GUI との通信は `machine-readable` なメッセージ形式にする
- 第一候補は `line-delimited JSON`
- GUI 起動時には `hello` か `status snapshot` を返し、自動検出と初期同期をしやすくする

### Initial Message Examples

```json
{"type":"hello","product":"zmk-usb-bridge-gui","protocol_version":1}
{"type":"state","value":"connected"}
{"type":"peer","name":"LaLapadGen2"}
{"type":"battery","percent":87}
{"type":"modifiers","left_shift":true,"left_ctrl":false}
{"type":"last_key","usage_name":"K","pressed":true}
{"type":"mouse_buttons","left":false,"right":true,"middle":false}
{"type":"scan_candidate","id":3,"name":"LaLapadGen2","has_hid":true,"keyboard_appearance":true}
{"type":"command","name":"connect_candidate","candidate_id":3}
```

## Desktop App Direction

- GUI は最初から豪華にせず、`状態表示 + 候補一覧 + 操作ボタン` の最小構成を優先する
- 実装言語は PoC 速度を優先し、`Python + GUI toolkit` のような構成を許容する
- ただし利用者体験を考え、PoC 段階から最終的に `EXE` 化しやすい構成を優先する

## Firmware Direction

- receiver firmware は `zmk-usb-bridge` をリファレンスとして読みつつも、`候補一覧 + 手動選択` 前提の独立した設計を取る（fork ではなく新規実装）
- pairing scan 中に `最初の候補へ即 connect` する挙動は採らない
- candidate cache は GUI 向けに公開できるモデルとして持つ
- GUI からの `connect_selected_candidate` を受けて初めて connect を開始する
- 接続後 validation は `HIDS service`、`keyboard input report`、必要な report discovery の成立を通過条件にする
- bond 済みデバイスへの reconnect は firmware が自動処理する。GUI からの明示的な reconnect 指示は持たない
- `LaLapadGen2` を参照対象にしつつも、設計上は将来の ZMK keyboard 一般化を阻害しない責務分割を保つ

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

1. `CDC ACM` の GUI 用双方向 channel を用意する
2. `hello / status snapshot / command ack` の最小 protocol を定義する
3. 接続状態、keyboard 名、modifier、直近キー、mouse button を GUI 表示できるようにする
4. candidate cache を GUI 向けに公開し、一覧表示を成立させる
5. GUI から選択した候補への pairing / connect を成立させる
6. battery 表示を追加し、未取得時の UI 表現を詰める

## Open Questions

- candidate 一覧の上限件数をいくつに置くか
- `keyboard appearance` が無い機器を GUI 上でどう見せるか
- COM port 自動検出を `VID/PID` 主体にするか、`hello` 応答主体にするか
- battery の取得失敗や未取得を GUI 上でどう表現するか
- desktop app の実装言語と EXE 化手順を何で固定するか

## Validation Needed

- `LaLapadGen2` を無改造で候補一覧表示し、手動選択 pairing まで到達できるか
- `HID service + keyboard appearance` の候補絞り込みで誤候補がどの程度残るか
- `CDC ACM` 追加が receiver の HID 動作や reconnect 安定性を悪化させないか
- COM port 自動検出が Windows 実機で十分安定するか
- 接続状態、入力状態、battery 表示が実利用で分かりやすいか
- `allowlist なし` でも GUI 版の pairing 導線が十分扱いやすいか

## Kill Criteria

- `既存 ZMK keyboard 無改造` では候補絞り込みや pairing 成立が実用にならない
- `CDC ACM` 導入で HID bridge の安定性や reconnect が悪化する
- 候補一覧が広すぎて、GUI 操作の価値より誤操作リスクが上回る
- `LaLapadGen2` 1 台固定でも、PoC の pairing / reconnect / 状態表示が安定しない
