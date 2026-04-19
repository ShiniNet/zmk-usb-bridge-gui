# GUI Receiver Protocol v1

## Purpose

- `zmk-usb-bridge-gui` の `GUI 用 CDC ACM channel` で使う最小 protocol を定義する
- receiver firmware と desktop app を並行実装できるようにする
- `PoC scope` のうち、`scan / candidate list / connect / bond erase` と telemetry 表示に必要な message を対象にする

## Scope

- transport は `receiver 側 GUI 用 CDC ACM instance` に限定する
- message format は `UTF-8 line-delimited JSON` で固定する
- `Windows 優先 PoC` の仕様として、初回同期、候補一覧同期、command 応答、非同期 event、telemetry 同期を定義する

## Out Of Scope For v1

- binary framing、圧縮、認証
- log 用 CDC channel の message format

## Transport Rules

- 1 行に 1 message の JSON object を載せ、改行は `\n` を使う
- 文字コードは `UTF-8` とする
- すべての message は top-level に `type` を持つ
- GUI は未知の field を無視してよい
- receiver は未知の command `name` を `error` で返す
- GUI は `request_id` を GUI session 内で一意にする
- `ack` は `command を受理した` ことを表し、処理完了そのものは後続の `event` で知らせる

## Design Rationale

- `candidate_generation` は `scan_start` ごとの candidate 集合を識別し、古い一覧を見た GUI からの `connect_candidate` を弾きやすくする
- `candidate_snapshot + candidate_upsert` は、GUI 再起動直後の全量同期と scan 中の増分更新を同じ枠で扱いやすくする
- `ack` を completion ではなく receipt に寄せることで、長めの BLE 処理を `event` へ切り出し、command 応答を単純に保つ

## Message Types

### `hello`

receiver が GUI port open 後に自発送信する。COM port 自動検出と protocol version 判定の起点に使う。

必須 field:

- `type`: `hello`
- `product`: `zmk-usb-bridge-gui`
- `protocol_version`: `integer`（現行値は `1`）
- `channel`: `gui`

任意 field:

- `board`
- `firmware_version`

例:

```json
{"type":"hello","product":"zmk-usb-bridge-gui","protocol_version":1,"channel":"gui","board":"xiao_nrf52840"}
```

### `status_snapshot`

receiver の現在状態を GUI に同期するための full snapshot。`hello` の直後と `get_status` / `bond_erase` の後に送る。

必須 field:

- `type`: `status_snapshot`
- `receiver_state`: `idle` | `scanning` | `connecting` | `connected`
- `peer_name`: `string | null`
- `peer_address`: `string | null`
- `scan_in_progress`: `boolean`
- `candidate_generation`: `integer`
- `candidate_count`: `integer`

整合ルール:

- `scan_in_progress` は `receiver_state` の補助 field とし、`receiver_state=scanning` のときだけ `true` を取る
- `receiver_state=idle | connecting | connected` のときは `scan_in_progress=false` とする
- 両者が矛盾する message は `protocol error` 相当として扱い、GUI は `receiver_state` を優先して解釈してよい

例:

```json
{"type":"status_snapshot","receiver_state":"idle","peer_name":null,"peer_address":null,"scan_in_progress":false,"candidate_generation":4,"candidate_count":0}
```

任意 telemetry field:

- `battery_supported`: `boolean | null`
- `battery_percent`: `integer | null`
- `modifiers_supported`: `boolean | null`
- `modifiers`: `array[string] | null`
- `last_key_supported`: `boolean | null`
- `last_key`: `string | null`
- `mouse_buttons_supported`: `boolean | null`
- `mouse_buttons`: `array[string] | null`

運用ルール:

- `status_snapshot` は full snapshot として扱い、telemetry を実装した receiver は現在値と support 状態をここにも載せてよい
- `battery_percent=null` は `battery は対応しているが現時点で未取得` を表してよい
- `modifiers=[]` と `mouse_buttons=[]` は `対応しており、現在は押下なし` を表してよい
- `last_key=null` は `対応しているが、この session ではまだ key event 未観測` を表してよい
- `*_supported=false` は、その telemetry を current firmware が提供しないことを表す

### `candidate_snapshot`

現在の candidate cache 全体を GUI に渡す authoritative snapshot。GUI はこの message を受けたら一覧を丸ごと置き換える。

必須 field:

- `type`: `candidate_snapshot`
- `candidate_generation`: `integer`
- `candidates`: `array`

`candidate` object の必須 field:

- `candidate_id`: `integer`
- `ble_address`: `string`
- `display_name`: `string | null`
- `connectable`: `boolean`
- `has_hid_service`: `boolean`
- `has_keyboard_appearance`: `boolean`
- `rssi`: `integer | null`

任意 field:

- `last_seen_ms`

`last_seen_ms` の意味:

- receiver ローカルな相対時刻の `ms` とし、絶対時刻や host 時刻との対応は持たない
- GUI は `同じ receiver session` 内での並び順補助にだけ使い、絶対時刻表示や session をまたぐ比較には使わない

例:

```json
{"type":"candidate_snapshot","candidate_generation":7,"candidates":[{"candidate_id":3,"ble_address":"E4:B6:69:12:34:56","display_name":"LaLapadGen2","connectable":true,"has_hid_service":true,"has_keyboard_appearance":true,"rssi":-51}]}
```

### `command`

GUI から receiver へ送る操作要求。

共通必須 field:

- `type`: `command`
- `request_id`: `integer`
- `name`: `string`

### `ack`

receiver が command を受理したことを返す。

`accepted` は `command を拒否しなかった` ことを明示する印であり、`v1` では常に `true` とする。
受理拒否や前提不一致は `accepted=false` ではなく `error` へ寄せ、応答分岐を単純に保つ。

必須 field:

- `type`: `ack`
- `request_id`: `integer`
- `name`: `string`
- `accepted`: `true`

例:

```json
{"type":"ack","request_id":16,"name":"scan_start","accepted":true}
```

### `error`

receiver が command を受理できなかったときに返す。

必須 field:

- `type`: `error`
- `request_id`: `integer`
- `name`: `string`
- `code`: `string`
- `message`: `string`

代表的な `code`:

- `unsupported_command`
- `invalid_request`
- `scan_busy`
- `connect_busy`
- `candidate_not_found`
- `stale_candidate_generation`
- `invalid_state`
- `internal_error`

例:

```json
{"type":"error","request_id":17,"name":"connect_candidate","code":"candidate_not_found","message":"candidate_id not found"}
```

### `event`

非同期状態変化や、`ack` 後に完了する処理結果を表す。

共通必須 field:

- `type`: `event`
- `name`: `string`

## Event Set

### `scan_started`

必須 field:

- `type`: `event`
- `name`: `scan_started`
- `candidate_generation`: `integer`

意味:

- 新しい scan window を開始したことを表す
- GUI は `scan_started` を受けた時点で新しい generation へ切り替えて一覧を初期化してよい
- 追加で `candidate_snapshot` を受けたら、その generation の authoritative view として一覧を置き換える

例:

```json
{"type":"event","name":"scan_started","candidate_generation":8}
```

### `candidate_upsert`

必須 field:

- `type`: `event`
- `name`: `candidate_upsert`
- `candidate_generation`: `integer`
- `candidate`: `candidate object`

意味:

- 同じ `candidate_id` が既に一覧にあれば置き換え、無ければ追加する
- `candidate_snapshot + candidate_upsert` を `v1` の candidate 同期方式とする

例:

```json
{"type":"event","name":"candidate_upsert","candidate_generation":8,"candidate":{"candidate_id":3,"ble_address":"E4:B6:69:12:34:56","display_name":"LaLapadGen2","connectable":true,"has_hid_service":true,"has_keyboard_appearance":true,"rssi":-49}}
```

### `scan_complete`

必須 field:

- `type`: `event`
- `name`: `scan_complete`
- `candidate_generation`: `integer`
- `result`: `ok` | `stopped` | `error`
- `candidate_count`: `integer`

任意 field:

- `code`

意味:

- `ok` は receiver が scan window を通常完了したことを表す
- `stopped` は scan が自然完了前に中断されたことを表す
- `stopped` の代表例は、GUI からの `connect_candidate` を受理して connect へ遷移するとき
- `error` は scan 実行中に内部エラーで継続不能になったことを表す
- `PoC Phase 1` の scan window は receiver 実装側の bounded scan とし、目安は `5-10 秒` とする

例:

```json
{"type":"event","name":"scan_complete","candidate_generation":8,"result":"ok","candidate_count":3}
```

### `connection_state`

必須 field:

- `type`: `event`
- `name`: `connection_state`
- `state`: `connecting` | `connected` | `idle`
- `peer_name`: `string | null`
- `peer_address`: `string | null`

任意 field:

- `code`
- `message`

意味:

- `connect_candidate` 受理後はまず `connecting` を返す
- 成功時は `connected`
- 失敗時や切断後は `idle` に戻し、必要なら `code` と `message` を添える
- BLE が予期せず切断された場合も receiver は自発的に `connection_state(state=idle)` を送る
- `peer_name` と `peer_address` は `idle` 遷移時に `null` へ戻してよい
- 現行 receiver firmware は `connected` を返す前に、BLE connection、`BT_SECURITY_L2` request、HID service primary discovery の最低限の validation を通す

例:

```json
{"type":"event","name":"connection_state","state":"connected","peer_name":"LaLapadGen2","peer_address":"E4:B6:69:12:34:56"}
```

### `telemetry_update`

用途:

- 接続後に変化する telemetry を非同期で更新する

必須 field:

- `type`: `event`
- `name`: `telemetry_update`

任意 field:

- `battery_supported`
- `battery_percent`
- `modifiers_supported`
- `modifiers`
- `last_key_supported`
- `last_key`
- `mouse_buttons_supported`
- `mouse_buttons`

意味:

- 変化した field だけを送ってよい
- `status_snapshot` が full snapshot、`telemetry_update` が増分更新という役割分担を基本とする
- support 情報だけ先に送り、その後に値を送ってもよい
- `protocol_version` は据え置き、unknown field 無視の前方互換ルールで拡張する

例:

```json
{"type":"event","name":"telemetry_update","battery_supported":true,"battery_percent":82,"modifiers_supported":true,"modifiers":["LCTRL"],"last_key_supported":true,"last_key":"A","mouse_buttons_supported":true,"mouse_buttons":[]}
```

### `bonds_cleared`

必須 field:

- `type`: `event`
- `name`: `bonds_cleared`

任意 field:

- `cleared_count`

例:

```json
{"type":"event","name":"bonds_cleared","cleared_count":1}
```

## Command Set

### `get_status`

用途:

- GUI 再接続時に receiver の現在状態を再同期する

request:

```json
{"type":"command","request_id":1,"name":"get_status"}
```

成功時の後続 message:

- `ack`
- `status_snapshot`
- `candidate_snapshot`

### `scan_start`

用途:

- 新しい scan window を開始する

request:

```json
{"type":"command","request_id":2,"name":"scan_start"}
```

成功時の後続 message:

- `ack`
- `event(scan_started)`
- `candidate_snapshot`
- `event(candidate_upsert)` x 0..N
- `event(scan_complete)`

備考:

- `scan_start` は新しい `candidate_generation` を発行する
- receiver は `ack` / `scan_started` を先に返し、Bluetooth init / BLE stack の scan start は後続処理で開始してよい
- 後続処理で BLE scan start に失敗した場合は `scan_complete(result=error, code=scan_start_failed)` を返す
- 後続処理で BLE scan start が完了しない場合は `scan_complete(result=error, code=scan_start_timeout)` を返す
- Bluetooth init が pending scan window 内で ready にならない場合は `scan_complete(result=error, code=bluetooth_init_timeout)` を返す
- scan 中に再度 `scan_start` を受けた場合は `scan_busy` を返してよい
- `scan_complete(result=ok)` は bounded scan window の通常終了時に返す

### `get_candidates`

用途:

- 現在の candidate cache を再送させる

request:

```json
{"type":"command","request_id":3,"name":"get_candidates"}
```

成功時の後続 message:

- `ack`
- `candidate_snapshot`

### `connect_candidate`

用途:

- GUI が選択した候補に対して pairing / connect を開始する

追加必須 field:

- `candidate_generation`: `integer`
- `candidate_id`: `integer`

request:

```json
{"type":"command","request_id":4,"name":"connect_candidate","candidate_generation":8,"candidate_id":3}
```

成功時の後続 message:

- `ack`
- scan 中に受理した場合は必要に応じて `event(scan_complete: stopped)`
- `event(connection_state: connecting)`
- `event(connection_state: connected | idle)`

失敗条件:

- `candidate_generation` が古い場合は `stale_candidate_generation`
- `candidate_id` が存在しない場合は `candidate_not_found`
- すでに別の connect attempt が進行中の場合は `connect_busy`
- `connected` 状態など、receiver が新しい connect 開始を受けられない状態では `invalid_state`
- BLE connect 開始前に失敗した場合は command `error(code=connect_failed)` を返してよい
- BLE connect 開始後の失敗は `connection_state(state=idle, code=...)` で返す

代表的な `connection_state(state=idle)` code:

- `connect_failed`: BLE connection establishment が失敗した
- `bluetooth_init_failed`: Bluetooth init が失敗した
- `security_failed`: BLE security / pairing request が失敗した
- `hid_discovery_failed`: HID service discovery を開始できなかった
- `hid_service_not_found`: 接続先が HID service を公開していなかった
- `validation_timeout`: connect 後 validation が timeout した
- `peer_disconnected`: 接続済み peer が予期せず切断した

状態ルール:

- `receiver_state=idle` でも、同じ generation の `candidate_id` がまだ有効なら `connect_candidate` を受理してよい
- `receiver_state=scanning` の間に、同じ generation の `candidate_id` への `connect_candidate` を送ってよい
- receiver はその場合 scan を停止して connect へ進み、必要なら `scan_complete(result=stopped)` を送る
- `receiver_state=connected` など新しい connect 開始を受けられない状態では `invalid_state` を返す

### `bond_erase`

用途:

- 既存 bond を消去し、receiver を初期状態へ戻す

request:

```json
{"type":"command","request_id":5,"name":"bond_erase"}
```

成功時の後続 message:

- `ack`
- 必要なら `event(connection_state: idle)`
- `event(bonds_cleared)`
- `status_snapshot`
- `candidate_snapshot`

generation ルール:

- `candidate_generation` を新しく発行する契機は `scan_start` のみとする
- `bond_erase` 後の `candidate_snapshot` は、直前 generation を維持したまま `candidates=[]` を返してよい
- GUI は `bond_erase` の文脈では `bonds_cleared` を受けたうえで空 snapshot を初期化結果として扱う

## Initial Connection Sequence

1. GUI が `COM port` を開く
2. receiver が `hello` を送る
3. receiver が `status_snapshot` を送る
4. receiver が `candidate_snapshot` を送る
5. GUI は必要に応じて `get_status` を送って再同期してよい

## Scan Sequence

1. GUI が `scan_start` を送る
2. receiver が `ack` を返す
3. receiver が `scan_started` を送る
4. receiver が同 generation の `candidate_snapshot` を送る
5. receiver が候補発見ごとに `candidate_upsert` を送る
6. receiver が `scan_complete` を送る

## Connect Sequence

1. GUI が `connect_candidate` を送る
2. receiver が `ack` を返す
3. scan 中に受理した場合、receiver は `scan_complete(result=stopped)` を送ってよい
4. receiver が `connection_state(connecting)` を送る
5. 成功時は `connection_state(connected)`、失敗時または切断時は `connection_state(idle)` を送る

## Notes For Later Items

- candidate の寿命、一覧上限、並び順、非表示条件は [`candidate-listing-policy.md`](candidate-listing-policy.md) を正本とする
- COM port 自動検出アルゴリズムの正本は [`desktop-app-foundation.md`](desktop-app-foundation.md) とし、`hello.channel=gui` は識別材料として使ってよい
- telemetry を追加・拡張する場合も、`hello / status_snapshot / command / ack / error / event` の基本枠は維持する
