# Debug Log Foundation

## Purpose

- 実機デバッグ時に `GUI`、`receiver dongle`、`ZMK keyboard` の観測を `1 つの session log` に集約する方針を固定する
- `Codex` へ渡しやすい形で、時系列、因果関係、再現条件を残せる最低限の観測基盤を定義する
- `log viewer` の見た目より先に、`収集`、`時刻付け`、`保存` を安定させる

## Scope

- 対象は `desktop app` 側の debug capture subsystem とする
- この文書は `capture schema`、`lifecycle`、`保存運用` の正本であり、一般の `COM port discovery / attach` ルールの正本ではない
- `receiver` の検出、再接続、複数 receiver 判定など desktop app 全体の attach policy は [`desktop-app-foundation.md`](desktop-app-foundation.md) を正本とする
- 対象 source は次の 3 系統とする
  - `GUI app` 自身の内部 event / state change
  - `receiver` の `GUI protocol` と `debug log`
  - `ZMK keyboard` の `USB serial debug log`
- 保存対象は `PC 側で受信・観測できた内容` に限定する

## Non-Goals

- 最初から高度な `live log viewer` を作ること
- 機器内部 clock の厳密同期
- `GUI protocol` と `debug log` を同一 channel に混在させること
- すべての keyboard log port を自動判定すること

## Key Decisions

- 観測の共通基準は `PC` とし、正本時刻は `PC 側 timestamp` にそろえる
- 保存形式は `1 session = 1 file` の `NDJSON (.jsonl)` とする
- 各 record には `session_id`、`source`、`channel`、`ts_wall`、`ts_mono_ms` を付ける
- GUI 制御用 serial port は既存 session を流用し、log capture のために二重 open しない
- `receiver debug port` と `keyboard debug port` は別 reader thread で監視する
- `keyboard debug port` は初期段階では `manual selection` を正とする
- `log viewer` より先に、`収集`、`保存`、`後から解析できること` を優先する

## Why This Shape

- `GUI`、`receiver`、`keyboard` は直接つながっていないため、`PC` を共通観測点にするのが最も現実的である
- `PC 受信時刻` でそろえれば、完全同期ではなくても `scan 開始`、`connect`、`disconnect`、`telemetry 更新` の前後関係は十分追える
- `jsonl` は append に強く、途中で GUI が落ちても破損範囲を小さくしやすい
- `Codex` へ渡すときも、`1 session file` をそのまま解析対象にしやすい

## Architecture

### Main Components

- `LogCaptureCoordinator`
  - session 開始・終了を管理する
  - 各 source reader / emitter を start / stop する
  - record queue を `LogFileWriter` へ流す
- `LogFileWriter`
  - 単一 writer thread で `jsonl` に追記する
  - record ごとに `sequence` を振る
- `GuiAppEventEmitter`
  - GUI 内部 event を構造化 record として発行する
- `ReceiverProtocolTap`
  - 既存 `SerialSession` の `tx / rx` を log record 化する
- `SerialTextLogReader`
  - `receiver debug port` と `keyboard debug port` を監視する汎用 line reader

### Threading And Queue Model

- `GUI main thread`: UI と runtime の制御
- `receiver session reader thread`: 既存 `GUI protocol rx`
- `receiver debug reader thread`: receiver debug log 用
- `keyboard debug reader thread`: keyboard debug log 用
- `log writer thread`: `jsonl` 追記専用
- 各 source は `SimpleQueue[LogRecord]` 相当へ record を積み、file I/O は `single writer` のみが行う

## Record Model

### Source And Channel

- `source`
  - `gui`
  - `receiver`
  - `keyboard`
- `channel`
  - `app_event`
  - `gui_protocol_tx`
  - `gui_protocol_rx`
  - `debug_serial`
  - `capture_lifecycle`

### Required Fields

- `schema_version`: 初期値は `1`
- `session_id`: 1 回の収集 session を一意に識別する文字列
- `sequence`: writer が採番する単調増加整数
- `ts_wall`: `ISO 8601` の local time
- `ts_mono_ms`: `time.monotonic()` 基準の millisecond
- `source`: `gui | receiver | keyboard`
- `channel`: 上記 taxonomy に従う
- `kind`: `lifecycle | state | protocol | text | error`

### Optional Fields

- `port`: `COM8` のような OS port 名
- `device_path`
- `serial_number`
- `direction`: `tx | rx`
- `event`
- `raw`
- `parsed`
- `detail`
- `fields`

### Session Id Format

- `session_id` は `YYYYMMDD_HHMMSS_<suffix>` 形式を正本とする
- `<suffix>` は同秒内の衝突回避に使う短い一意文字列とする
- session file 名は `<session_id>.jsonl` とする
- `session_started.fields.log_path` は上記 file 名規則と整合していなければならない

### Serialization Rules

- 1 record = 1 line の `UTF-8 json`
- `raw` は可能な限り元の文字列を保持する
- `parsed` は `GUI protocol` のように構造化できるものだけ載せる
- parse に失敗した line も破棄せず保存する

### Canonical Lifecycle Events

- `capture_lifecycle` の `event` 名は次を正本とする
  - `session_started`
  - `session_stopped`
  - `session_aborted`
  - `receiver_debug_attach_started`
  - `receiver_debug_attached`
  - `receiver_debug_detached`
  - `receiver_debug_attach_skipped`
  - `keyboard_log_attach_started`
  - `keyboard_log_attached`
  - `keyboard_log_detached`
  - `keyboard_log_attach_skipped`
- `session_started`
  - `fields.log_path` を必須とする
- `session_stopped`
  - clean shutdown のときだけ使う
- `session_aborted`
  - process crash では書けない前提でよい
  - 書けた場合は `fields.reason` を持たせてよい
- `*_attach_skipped`
  - pre-attach 段階で attach を試みなかった、または正しく候補を 1 つに絞れなかったことを表す
  - `fields.reason` を必須とする
- `*_attached` と `*_detached`
  - 可能なら `port`、`device_path`、`serial_number` を持たせる
- port open 失敗や reader 起動失敗のような post-attach failure は `*_attach_skipped` ではなく `reader_failure` で記録する

### Canonical Error Events

- `kind=error` の `event` 名は次を正本とする
  - `protocol_parse_error`
  - `reader_failure`
  - `records_dropped`
- `protocol_parse_error`
  - `detail` を必須とする
  - 可能なら `raw` を持たせる
- `reader_failure`
  - `fields.reason` を必須とする
  - 可能なら `fields.exception_class` を持たせる
- `records_dropped`
  - `fields.dropped_count` を必須とする
  - 可能なら `fields.reason` を持たせる

### Canonical App Events

- `channel=app_event` の `event` 名は次を正本とする
  - `receiver_attach_state_changed`
  - `receiver_state_changed`
  - `scan_start_requested`
  - `refresh_requested`
  - `connect_candidate_requested`
  - `bond_erase_requested`
  - `retry_discovery_requested`
  - `last_error_changed`
- `receiver_attach_state_changed`
  - `kind=state` を使う
  - `fields.discovery_state` を必須とする
- `receiver_state_changed`
  - `kind=state` を使う
  - `fields.receiver_state` を必須とする
  - `fields.peer_name` は必要に応じて持たせてよい
- `*_requested`
  - `kind=state` ではなく `kind=lifecycle` を第一候補とする
  - `connect_candidate_requested` は `fields.candidate_id` を必須とする
- `last_error_changed`
  - `kind=error` を使ってよい
  - `detail` または `fields.message` のどちらかを必須とする

### Example

```json
{"schema_version":1,"session_id":"20260410_142311_ab12","sequence":1,"ts_wall":"2026-04-10T14:23:11.482+08:00","ts_mono_ms":123456789,"source":"gui","channel":"capture_lifecycle","kind":"lifecycle","event":"session_started","fields":{"log_path":"logs/sessions/20260410_142311_ab12.jsonl"}}
{"schema_version":1,"session_id":"20260410_142311_ab12","sequence":18,"ts_wall":"2026-04-10T14:23:14.102+08:00","ts_mono_ms":123459409,"source":"receiver","channel":"gui_protocol_tx","kind":"protocol","port":"COM8","direction":"tx","raw":"{\"type\":\"command\",\"request_id\":5,\"name\":\"scan_start\"}\n","parsed":{"type":"command","request_id":5,"name":"scan_start"}}
{"schema_version":1,"session_id":"20260410_142311_ab12","sequence":19,"ts_wall":"2026-04-10T14:23:14.170+08:00","ts_mono_ms":123459477,"source":"receiver","channel":"debug_serial","kind":"text","port":"COM9","raw":"[00:12:44.201] scan started"}
{"schema_version":1,"session_id":"20260410_142311_ab12","sequence":20,"ts_wall":"2026-04-10T14:23:14.291+08:00","ts_mono_ms":123459598,"source":"keyboard","channel":"debug_serial","kind":"text","port":"COM12","raw":"[00:03:51.993] HID report subscribed"}
```

## Source-Specific Policy

### GUI App Event

- GUI event は `raw text` ではなく構造化 record で残す
- 同じ state を短時間に重複送出しない
- 次の event は最低限 capture する
  - capture session 開始 / 終了
  - receiver discovery 開始 / 完了 / error
  - receiver attach / detach
  - user action
    - `scan_start`
    - `refresh`
    - `connect_candidate`
    - `bond_erase`
    - `retry_discovery`
  - state change
    - `receiver_state`
    - `peer_name`
    - `candidate_generation`
    - `last_error`
- canonical な event 名と最小 field は `Canonical App Events` を正本とする

### Receiver GUI Protocol

- GUI 制御 port は既存 `SerialSession` をそのまま使う
- `tx` は `send_message()` の直前で記録する
- `rx` は `_reader_loop()` で decode 成功後に記録する
- parse 失敗時も元 line を捨てず `kind=error` または `kind=text` で残す
- malformed `UTF-8`、改行欠落 fragment、途中切断で不完全になった frame も silent drop してはならない
- 上記の異常入力は `kind=error` を第一候補とし、`channel=gui_protocol_rx` のまま `raw` と `detail` を残す
- GUI 制御 port を log capture のために別 open してはならない

### Receiver Debug Port

- `receiver` の GUI port 検出と attach policy 自体は [`desktop-app-foundation.md`](desktop-app-foundation.md) を正本とする
- debug capture は、desktop app が `現在 attach 済みの receiver identity` を確定した後にだけ動く
- `receiver debug port` の紐付けは `VID/PID + serial_number` を最優先とする
- `serial_number` が取れない環境では `location / device path` を次点で使う
- `receiver debug reader` は `現在 attach 済みの receiver identity` に従属する
- GUI が `receiver attached` になった後にだけ debug port 探索を始める
- `receiver debug port` が見つからなくても GUI 機能は block しない
- current desktop app 実装では、Windows 実機で sibling CDC port の open が GUI session を不安定化させる観測があるため、`receiver debug auto-attach` は既定で無効としてよい
- 上記の間も `receiver debug` 自体は補助観測であり、GUI 制御 port の attach / session 維持を優先する
- receiver debug port 候補の選定では、すでに attach 済みの `GUI protocol port` を必ず除外する
- 同一 receiver identity に属する sibling port が、GUI port を除外した後にちょうど `1 件` だけ残る場合にその port を採用してよい
- sibling port が `0 件` または `2 件以上` 残る場合は attach を行わず、`receiver_debug_attach_skipped` を記録する
- 同一 `receiver identity` に対する retry は、attach が維持されている間だけ継続してよい
- `receiver_debug_attach_started` は 1 つの attach epoch につき 1 回を基本とし、retry ごとに重複送出しない
- `receiver_debug_attach_skipped` は、その epoch で attach 不可が確定した時点で 1 回だけ記録してよい
- GUI 側の receiver attach が失われた場合、または attach 先 identity が切り替わった場合は、旧 `receiver debug reader` の再試行と監視を止める
- その後に新しい attach 先が確定した場合だけ、新しい receiver identity に対して debug port 探索をやり直す
- debug port の attach / detach も `capture_lifecycle` として記録する

### Keyboard Debug Port

- `keyboard debug port` は初期段階では `manual selection` を正とする
- ここでいう `manual selection` は、session 開始時に自動 attach を試みず、利用者の明示操作を入口に attach を開始することを意味する
- 理由は次の通りとする
  - keyboard 側は receiver のような `hello.channel=...` が無い
  - board / firmware / USB descriptor 差分で自動判定が不安定になりやすい
  - 誤接続で別機器の serial log を吸う方がデバッグを汚す
- GUI は `Start keyboard log capture` のような UI 操作を入口に、候補 port 一覧を見せて利用者に選ばせてよい
- 選んだ port の `serial_number` または `device path` は次回 session の preferred candidate として記憶してよい
- saved `preferred candidate` は次回の候補一覧での preselect に使ってよいが、利用者の明示操作なしに自動 attach してはならない
- `keyboard_log_attach_skipped` は、利用者操作で attach を開始する前の候補選定段階で skip になった場合にだけ記録する
- port open 失敗や reader 起動失敗のような試行後 failure は `keyboard_log_attach_skipped` ではなく `reader_failure` で記録する
- keyboard log の late attach は、新しい session を切らず `現在の active session file` へ追記する
- keyboard log の attach / detach も `capture_lifecycle` として記録する

## Operational Policy

### Timestamp

- 正本の時系列は `PC 受信時刻` とする
- `ts_wall` は人間が読むための時刻として使う
- `ts_mono_ms` は前後差分比較の基準として使う
- 機器側 log に独自 timestamp が入っていても、それは `raw` の一部として保持し、正本時刻にはしない

### Session And File

- log は `desktop app` 起動ごとではなく `capture start` ごとに 1 session とする
- 初期方針は `app 起動時に自動で capture start` とする
- `capture stop` は app 正常終了時に行う
- session 開始時には必ず `session_started` を打つ
- clean shutdown で完了した session に限り、終了時に `session_stopped` を打つ
- file 末尾に `session_stopped` が無いこと自体は `abnormal termination` と解釈してよく、log file の破損を意味しない
- writer の open に失敗して `session_started` を書けない場合、desktop app 本体は継続してよいが、その app run では `active session not established` として capture を無効化する
- 上記の failure は GUI で利用者に見える error として通知し、silent failure にしてはならない
- 保存先は project root 直下ではなく、user data 配下の `logs/sessions/` を第一候補とする
- 開発中の既定値は app working directory 直下の `logs/sessions/` でもよい
- file 名は `<session_id>.jsonl` とする
- 1 session 1 file を基本とし、日次ローテーションは導入しない

### Flush And Durability

- 初期実装では `record ごと flush` を既定にする
- 強制終了時でも、それまで flush 済みの `jsonl` は残る前提にする
- 高負荷時に問題が出た場合のみ `100-250 ms` 単位の batched flush を検討する
- write / flush 途中で writer failure が起きた場合は、それ以降の capture を停止し、部分的に残った current file を保持したまま GUI に error を通知する
- clean shutdown の終了順は次を正本とする
  1. 新規 attach / retry を止める
  2. 各 reader / emitter を停止する
  3. queue を drain する
  4. 最後に `session_stopped` を 1 件だけ書く
  5. writer を flush / close する
- `session_stopped` より後に追加 record を書いてはならない

### Reader Behavior

- 各 `SerialTextLogReader` は `readline()` ベースで扱う
- `baudrate` は source ごとの設定値を持てるようにする
- decode は `UTF-8 errors=replace` を既定にする
- 空 line は捨ててよい
- 連続 disconnect 時は一定間隔で再試行してよい
- reader failure は GUI 全体を落とさず、record 化して継続する

### Backpressure And Volume

- queue が詰まっても `GUI protocol` 処理を止めないことを優先する
- 初期実装では `unbounded queue + single writer` を採用してよい
- log volume が高すぎる場合に備え、`debug_serial` のみ rate limit 対象にしてよい
- drop 発生時は件数をまとめた `kind=error` record を追加する
- `gui_protocol_tx / gui_protocol_rx` は原則 drop しない

### Privacy And Sharing

- log は `local file` 保存を基本とし、自動送信しない
- `Codex` へ共有するときは session file 単位で渡す
- `BLE address` や device 名が含まれることを前提に、公開共有前に review できるようにする

## Subsystem-Local Dependency Order

- これは project 全体の phase 順ではなく、debug log subsystem 内だけの依存順を表す
- project 全体の実装順と優先度は [`../plans/phase2-and-beyond-implementation-plan.md`](../plans/phase2-and-beyond-implementation-plan.md) を現行 plan として参照する

1. `LogRecord` schema と `jsonl writer` を追加する
2. `GUI protocol tx/rx tap` を `SerialSession` に差し込む
3. `GUI app event emitter` を `runtime / controller` に差し込む
4. `receiver debug port reader` を追加する
5. `keyboard debug port manual attach` を追加する
6. session file の export / 読み出し導線を整える

## Validation Needed

### Required Before Rollout

- `record flush` が Windows 実機でも十分軽いか
- receiver debug port の `serial_number / location` 紐付けが実機で安定するか
- keyboard debug port の manual selection と preferred candidate preselect が運用上十分か

### Ongoing Observation

- `receiver` と `keyboard` の log volume が高いときに GUI の操作感へ悪影響がないか
- lifecycle event と error event の量が実運用で過剰にならないか

### Evidence Location

- 上記 validation の結果は `validation/` 配下の current phase evidence document に残す
- debug log subsystem の rollout evidence は `Phase 1` closeout 文書へ混在させず、`Phase 2+` 用 validation log または専用 validation doc に残す
- [`../validation/phase1-validation-log.md`](../validation/phase1-validation-log.md) は `Phase 1` の履歴参照用であり、debug log rollout の正規記録先ではない

## Related Documents

- 全体前提: [`project-concept.md`](project-concept.md)
- desktop app 構成と COM port 方針: [`desktop-app-foundation.md`](desktop-app-foundation.md)
- GUI 制御 protocol: [`protocol-v1.md`](protocol-v1.md)
- 実装順: [`../plans/phase2-and-beyond-implementation-plan.md`](../plans/phase2-and-beyond-implementation-plan.md)
- 実機確認結果: [`../validation/phase1-validation-log.md`](../validation/phase1-validation-log.md)
