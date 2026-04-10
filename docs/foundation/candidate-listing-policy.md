# Candidate Listing Policy

## Purpose

- `PoC Phase 1` の候補一覧に何を載せるかを固定する
- firmware の candidate cache と GUI の一覧表示前提をそろえる
- `既存 ZMK キーボード無改造` を守りつつ、誤候補の氾濫を抑える

## Display Eligibility

### Tier A: 通常表示

- `connectable advertisement` である
- advertisement または scan response に `HID service` が見える
- `keyboard appearance` がある

扱い:

- GUI の通常候補として表示する
- `PoC` では最優先の候補群として扱う

### Tier B: 警告付き表示

- `connectable advertisement` である
- advertisement または scan response に `HID service` が見える
- `keyboard appearance` は無い
- `local name` は取得できている

扱い:

- GUI には表示する
- `keyboard appearance 未確認` と分かる表示にする
- Tier A より後ろに並べる

### 非表示

- `connectable` ではない
- `HID service` が見えない
- `keyboard appearance` も `local name` も無い

扱い:

- candidate cache には保持してもよいが、GUI 一覧には出さない

## List Size And Ordering

- GUI に出す候補の上限は `12 件` とする
- 並び順は `Tier A -> Tier B -> RSSI 降順 -> last_seen 新しい順` とする
- 同順位では `display_name あり` を `display_name なし` より前に置く
- cache 上限を超える場合は、下位候補を表示対象から外し、上位 12 件だけを GUI に公開する

## Lifetime And Update Rules

- candidate cache は `scan_start` ごとに新しい `candidate_generation` を発行し、その generation 単位で管理する
- 1 つの generation 内では、同じ `BLE address` を同一候補として upsert する
- candidate は generation 内で中途削除せず、`次の scan_start` または `bond_erase` まで保持する
- GUI は `candidate_snapshot` を authoritative view とし、`candidate_upsert` で追従更新する
- `candidate_id` は generation 内でだけ安定していればよい

## Deduplication Rules

- 重複判定の主キーは `BLE address` とする
- 同一候補を再観測した場合は、`RSSI`、`last_seen_ms`、`display_name` を新しい情報で更新する
- `display_name` は `null` より非 `null` を優先して保持してよい
- 同名でも `BLE address` が異なる候補は別個体として扱う
- `last_seen_ms` は receiver ローカルな相対時刻として扱い、GUI では `新しい順` の並び替え補助にだけ使う

## Public Candidate Model For GUI

`protocol v1` で GUI に渡す最小 field は次のとおりとする。

- `candidate_id`
- `ble_address`
- `display_name`
- `connectable`
- `has_hid_service`
- `has_keyboard_appearance`
- `rssi`
- `last_seen_ms` は取得できる場合のみ付与してよい
- `last_seen_ms` の基準は host wall-clock ではなく receiver ローカル時刻でよい

GUI 側の表示原則:

- 表示優先度と警告表示は上記 `Tier A / Tier B` 定義に従う
- `display_name=null` の場合は `Unnamed HID device` 相当の代替表示を許容する

## Post-Connect Validation

- 候補一覧に出した時点では `keyboard らしい BLE HID` までしか保証しない
- 最終採用は `connect_candidate` 後の validation で決める
- 接続後に以下を満たさない場合は `connected` に入らず failure 扱いにして切断してよい
  - `HID service` の discovery が成立する
  - `keyboard input report` の discovery / subscription が成立する
  - receiver が bridge 可能な最小 report 構成を確認できる

## Rationale

- `keyboard appearance` は強い補助条件だが、無改造前提では欠ける個体もありうるため全面非表示にはしない
- 一方で `HID service` も `local name` も無い候補まで見せると GUI の価値が下がるため切り捨てる
- `12 件` 上限は、`Windows PoC` で一覧が飽和しにくく、手動選択の判断を保ちやすい数として置く
