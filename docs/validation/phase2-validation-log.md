# Phase 2 Validation Log

## Purpose

- `Phase 2+` の receiver firmware 実装を、実機観測と local verification に分けて記録する
- `scan -> connect_candidate -> pairing / validation -> bond_erase` の real BLE lifecycle を追跡する
- `DesktopApp Phase 1` の validation は [`phase1-validation-log.md`](phase1-validation-log.md) を正本とし、この文書では firmware 実装以降の観測を扱う

## Current Snapshot

- GUI と USB dongle の attach / reconnect は `Phase 1` で pass 済み
- receiver firmware は実 BLE scan / candidate cache に加え、`connect_candidate` を実 BLE connection establishment へ接続済み
- desktop app は receiver application VID/PID `0x2FE3/0x0012` だけでなく、receiver bootloader らしき VID/PID `0x2886/0x0045` を見た場合に flash hint を出せる
- `scan_start` は GUI protocol の `ack` / `scan_started` を返した後、firmware poll loop で Bluetooth init / BLE scan を開始する非同期 path に更新済み
- Bluetooth init は dedicated worker thread へ移し、main loop / GUI protocol response が `bt_enable()` に巻き込まれないようにしている
- BLE scan start も dedicated worker thread へ移し、main loop / GUI protocol response が `bt_le_scan_start()` に巻き込まれないようにしている
- BLE scan stop も dedicated worker thread へ移し、scan window 終了時に `scan_complete` を先に返せるようにしている
- BLE advertisement observation processing は main loop 側で 1 poll あたりの処理件数に上限を設けている
- `20260419_171117` 以降の raw observation enqueue 化は receiver application COM enumeration regression と時系列が一致し、`20260419_175947` で `20260419_170324` 相当の callback parsing path に戻すと COM7 / COM8 が復帰した
- BLE scan callback は raw observation enqueue 化へ戻さず、parsed observation path のまま、公開候補になり得ない観測の drop、queue-full 時の silent drop、同一 address の重複 throttle で callback pressure を下げている
- `20260419_180648` では COM7 / COM8 と GUI attach は復帰したが、`scan_start` 後に receiver protocol response が再び止まったため、Bluetooth enable を callback / system workqueue path ではなく dedicated worker 内の synchronous `bt_enable(NULL)` path へ変更した
- `20260419_181448` でも `scan_start` 後に receiver protocol response が止まり、明示的 timeout/error まで戻れなかったため、main protocol loop priority を Bluetooth TX/RX より高くして timeout / recovery path を保護している
- `20260419_184158` で advertisement callback を無効化しても `scan_complete` / watchdog response は戻らなかったため、callback parsing ではなく、明示 BLE scan を走らせた状態そのものが USB/protocol path を止めている可能性が高い
- `20260419_185525` で BLE scan start/stop smoke path でも `scan_complete` が戻らなかったため、次は BLE scan 以前の `bt_enable(NULL)` が戻るかを単独で確認する
- `20260419_190515` で Bluetooth enable-only smoke path でも `scan_complete` が戻らなかったため、Bluetooth に一切触れない protocol-only smoke path で GUI protocol / USB writer 側の健全性を確認する
- `20260419_190851` で protocol-only smoke path でも `scan_complete` が戻らなかったため、次は `scan_start` command handler 内で即時 `scan_complete` を enqueue できるかを確認する
- `20260419_191411` で immediate command-handler smoke path は成功し、4 本目の `scan_complete` も GUI へ届いたため、async GUI writer / ring buffer / host read path は健全である
- `20260419_191848` で after-response kick path の protocol-only smoke も成功したため、`scan_start` response 後に handler から明示 kick する経路を維持し、次は Bluetooth enable-only smoke へ戻して `bt_enable(NULL)` の影響を単独で確認する
- `20260419_192301` で after-response kick + Bluetooth enable-only smoke は `ack` / `scan_started` / `candidate_snapshot` までは返ったが、`bt_enable(NULL)` 開始後に `scan_complete` と watchdog refresh response が戻らなかった
- 次 build では main / GUI writer / scan supervisor を high-priority cooperative thread から preemptive priority へ戻し、USB / Bluetooth internal workqueue and HCI threads を app thread より優先できるようにする
- `20260419_192816` で preemptive-priority build の Bluetooth enable-only smoke は成功し、`bt_enable(NULL)` 後の `scan_complete(result=ok)` が GUI へ戻った
- 次 build では同じ priority 設定を維持し、BLE scan start/stop smoke で `bt_le_scan_start()` / `bt_le_scan_stop()` の最小経路を確認する
- `20260419_195750` で BLE scan start/stop smoke は成功し、`bt_le_scan_start()` / immediate `bt_le_scan_stop()` 後の `scan_complete(result=ok)` が GUI へ戻った
- 次 build では同じ priority 設定と passive / low-duty scan を維持し、advertisement callback と candidate cache を復帰して実候補検出を確認する
- `20260419_200130` で candidate-capable passive scan は `candidate_upsert` まで成功したが、long scan window の終了 `scan_complete` と watchdog refresh response が戻らなかった
- `20260419_200654` で first-candidate completion は `scan_complete(result=ok)` まで成功し、`LaLapadGen2` も GUI 候補一覧に出た
- ただし `20260419_200654` では先に観測した非公開 Tier の匿名候補で scan を close し、`candidate_count=0` の `scan_complete` 後に `LaLapadGen2` upsert が続いたため、次 build では公開候補だけを upsert / first-candidate completion 対象にする
- `20260419_201239` で public-candidate completion は成功し、`LaLapadGen2` の `candidate_upsert` 直後に `scan_complete(result=ok, candidate_count=1)` が戻った
- scan / candidate listing / completion はこの checkpoint では pass とし、次は表示された `LaLapadGen2` に対する `connect_candidate` 実機 validation に進む
- `20260419_201654` では `connect_candidate` command 送信後に `ack` / `connection_state(connecting)` が戻らず GUI が hang したため、connect start を command handler から切り離し、ack 後に dedicated worker で BLE connect を開始する
- `connect_candidate` は `bt_conn_le_create`、`BT_SECURITY_L2` request、`HID service` primary discovery を通してから `connection_state(connected)` を返す
- `bond_erase` は active connection cancel と `bt_unpair(BT_ID_DEFAULT, BT_ADDR_LE_ANY)` へ接続済み
- keyboard input report discovery / subscription、USB HID bridge、bonded reconnect は未実装

## Local Verification

### 2026-04-19

- Firmware build:
  - command: `./scripts/build_receiver_firmware.sh`
  - result: `pass`
  - artifact: `/home/dev/00_Dev_BLE_Reciever/artifacts/builds/20260419_202105_receiver_seeeduino_xiao_ble/zephyr.uf2`
- Desktop app tests:
  - command: `env PYTHONPATH=src python3 -m unittest discover -s tests -v`
  - result: `pass`
  - count: `72 tests`

## Hardware Observations

### 2026-04-19: `logs/sessions/20260419_161200_5720.jsonl`

- Scenario:
  - GUI start
  - USB dongle attach
  - `Scan` clicked
  - keyboard pairing mode started
  - USB dongle unplugged after waiting
  - GUI closed
- Observed:
  - Receiver discovery moved to `attached` on `COM8` at `2026-04-19T16:13:11.355+08:00`
  - GUI sent `scan_start` request `1` at `2026-04-19T16:13:16.385+08:00`
  - No receiver `ack`, `scan_started`, `candidate_upsert`, or `scan_complete` was received after `scan_start`
  - GUI watchdog sent `get_status` / `get_candidates` at `2026-04-19T16:13:28.529+08:00`, but no receiver reply was observed
  - Keyboard debug log shows profile 1 opening / advertising while GUI was waiting
  - Dongle unplug later surfaced as `Receiver port write failed: Write timeout`
- Interpretation:
  - USB attach path remained healthy.
  - Failure point is after `scan_start` reaches receiver firmware.
  - Because even `ack(scan_start)` was not emitted, candidate filtering is not the likely cause; the firmware command handler was likely blocked before the protocol response completed.
- Follow-up implemented:
  - `zmk_usb_bridge_gui_ble_scan_start()` no longer calls `bt_le_scan_start()` synchronously from the command handler.
  - The command handler now can emit `ack`, `scan_started`, and `candidate_snapshot` before the firmware poll loop attempts the actual BLE scan start.
  - If BLE scan start fails in poll, receiver should emit `scan_complete(result=error, code=scan_start_failed)` instead of leaving GUI waiting silently.

### 2026-04-19: `logs/sessions/20260419_162645_723c.jsonl`

- Scenario:
  - GUI start
  - USB dongle attach attempt failed
  - USB dongle reconnected
  - `Scan` clicked
  - keyboard pairing mode started
  - USB dongle unplugged after waiting
  - GUI closed
- Observed:
  - Initial receiver probe saw `COM8` / `COM7`, but failed with `probe worker timed out` and then repeated `PermissionError(13, 'アクセスが拒否されました。')`.
  - Later receiver probe on `COM8` succeeded in `30 ms` via `hello`.
  - GUI reached `attached` at `2026-04-19T16:27:36.528+08:00`.
  - GUI sent `scan_start` request `1` at `2026-04-19T16:27:46.334+08:00`.
  - No receiver `ack`, `scan_started`, `candidate_upsert`, or `scan_complete` was received after `scan_start`.
  - Keyboard debug log shows profile 1 selected, advertising changed from `0` to `2`, and `Profile 1 open, blinking yellow`.
  - GUI watchdog sent `get_status` / `get_candidates`, but no receiver reply was observed.
- Interpretation:
  - Attach can recover after the OS releases the receiver CDC ports, but the first reconnect window may expose transient `PermissionError`.
  - The previous `bt_le_scan_start()` deferral was not sufficient.
  - Because no boot snapshot / protocol response was observed after attach, eager Bluetooth init on GUI-ready or `scan_start` command handling is still a likely block point.
- Follow-up implemented:
  - Removed eager `zmk_usb_bridge_gui_ble_init()` from GUI-ready handling in startup.
  - `zmk_usb_bridge_gui_ble_scan_start()` now only prepares scan state and returns to the protocol handler.
  - Bluetooth init is deferred to the firmware poll loop after the `scan_start` response has had a short window to leave the USB protocol channel.

### 2026-04-19: `logs/sessions/20260419_163909_ac1e.jsonl`

- Scenario:
  - GUI start
  - USB dongle attached
  - `Scan` clicked
  - keyboard pairing mode started
- Observed:
  - Receiver probe on `COM8` succeeded in `62 ms` via `hello`.
  - GUI reached `attached` at `2026-04-19T16:39:25.384+08:00`.
  - Receiver emitted repeated boot snapshots while waiting for a host command.
  - GUI sent `scan_start` request `1` at `2026-04-19T16:39:33.693+08:00`.
  - Receiver replied with `ack(scan_start)` and `scan_started(candidate_generation=1)` at `2026-04-19T16:39:33.708+08:00`.
  - Receiver also emitted `candidate_snapshot(candidate_generation=1, candidates=[])` immediately after `scan_started`.
  - Keyboard debug log shows profile 1 selected, advertising changed from `0` to `2`, and `Profile 1 open, blinking yellow`.
  - No `candidate_upsert` or `scan_complete` was observed before the GUI watchdog requested `get_status` / `get_candidates`.
  - Receiver did not respond to the watchdog refresh after the scan had been accepted.
- Interpretation:
  - The previous fix succeeded for the `scan_start` acceptance path.
  - The remaining failure point moved after `ack` / `scan_started`, likely when Bluetooth init or BLE scan start runs from the firmware poll loop.
  - GUI protocol must remain responsive even if Bluetooth init blocks or takes longer than expected.
- Follow-up implemented:
  - Bluetooth init now runs in a dedicated firmware thread instead of the main protocol loop.
  - If Bluetooth init does not reach ready within the pending scan window, receiver should emit `scan_complete(result=error, code=bluetooth_init_timeout)`.
  - This keeps the GUI protocol loop available for `get_status` / `get_candidates` recovery while BLE init is pending or blocked.

### 2026-04-19: `logs/sessions/20260419_164737_e7ca.jsonl`

- Scenario:
  - GUI start
  - USB dongle attached
  - `Scan` clicked
  - keyboard pairing mode started
  - USB dongle unplugged after waiting
  - GUI closed
- Observed:
  - Receiver probe on `COM8` succeeded in `62 ms` via `hello`.
  - GUI reached `attached` at `2026-04-19T16:47:54.017+08:00`.
  - Receiver emitted repeated boot snapshots while waiting for a host command.
  - GUI sent `scan_start` request `1` at `2026-04-19T16:47:59.631+08:00`.
  - Receiver replied with `ack(scan_start)` and `scan_started(candidate_generation=1)` at `2026-04-19T16:47:59.642+08:00` / `16:47:59.643+08:00`.
  - Receiver also emitted `candidate_snapshot(candidate_generation=1, candidates=[])` immediately after `scan_started`.
  - Keyboard debug log shows profile 1 selected, advertising changed from `0` to `2`, and `Profile 1 open, blinking yellow`.
  - No `candidate_upsert`, `scan_complete`, or response to watchdog `get_status` / `get_candidates` was observed after scan acceptance.
- Interpretation:
  - `scan_start` acceptance remains stable.
  - Moving Bluetooth init to a dedicated worker was not sufficient, so the likely block point moved to `bt_le_scan_start()` itself.
  - The main loop must avoid direct BLE stack start/stop calls while still reporting timeout / failure codes to the GUI.
- Follow-up implemented:
  - BLE scan start now runs in the same dedicated worker path as Bluetooth init.
  - The main protocol loop only queues the scan start request and remains available for GUI recovery commands.
  - If BLE scan start does not complete while scan is pending, receiver should emit `scan_complete(result=error, code=scan_start_timeout)`.

### 2026-04-19: `logs/sessions/20260419_165557_8d22.jsonl`

- Scenario:
  - GUI start
  - USB dongle attached
  - `Scan` clicked
  - keyboard pairing mode started
  - USB dongle unplugged after waiting
  - GUI closed
- Observed:
  - Receiver probe on `COM8` succeeded in `31 ms` via `hello`.
  - GUI reached `attached` at `2026-04-19T16:56:08.895+08:00`.
  - Receiver emitted repeated boot snapshots while waiting for a host command.
  - GUI sent `scan_start` request `1` at `2026-04-19T16:56:12.882+08:00`.
  - Receiver replied with `ack(scan_start)`, `scan_started(candidate_generation=1)`, and `candidate_snapshot(candidate_generation=1, candidates=[])` by `2026-04-19T16:56:12.891+08:00`.
  - Keyboard debug log shows profile 1 selected, advertising changed from `0` to `2`, and `Profile 1 open, blinking yellow`.
  - No `candidate_upsert`, `scan_complete`, or response to watchdog `get_status` / `get_candidates` was observed after scan acceptance.
- Interpretation:
  - `scan_start` acceptance remains stable after moving BLE scan start to the worker.
  - Because the GUI watchdog fires after the 8 second scan window should have completed, the likely remaining block point is `bt_le_scan_stop()` during scan completion.
  - The main loop must avoid direct BLE scan stop calls and emit `scan_complete` before asking the BLE worker to stop scanning.
- Follow-up implemented:
  - BLE scan stop now runs in the dedicated worker thread.
  - `complete_scan()` emits `scan_complete` after updating receiver state and queues BLE scan stop asynchronously.
  - This should keep GUI recovery commands responsive even if `bt_le_scan_stop()` blocks or takes longer than expected.

### 2026-04-19: `logs/sessions/20260419_170124_59d9.jsonl`

- Scenario:
  - GUI start
  - USB dongle attached
  - `Scan` clicked
  - keyboard pairing mode started
  - USB dongle unplugged after waiting
  - GUI closed
- Observed:
  - Receiver probe on `COM8` succeeded in `31 ms` via `hello`.
  - GUI reached `attached` at `2026-04-19T17:01:36.638+08:00`.
  - Receiver emitted repeated boot snapshots while waiting for a host command.
  - GUI sent `scan_start` request `1` at `2026-04-19T17:01:38.987+08:00`.
  - Receiver replied with `ack(scan_start)`, `scan_started(candidate_generation=1)`, and `candidate_snapshot(candidate_generation=1, candidates=[])` by `2026-04-19T17:01:38.995+08:00`.
  - Keyboard debug log shows profile 1 selected, advertising changed from `0` to `2`, and `Profile 1 open, blinking yellow`.
  - No `candidate_upsert`, `scan_complete`, or response to watchdog `get_status` / `get_candidates` was observed after scan acceptance.
- Interpretation:
  - `scan_start` acceptance remains stable after moving BLE scan start / stop to the worker.
  - Because `scan_complete` still was not emitted after the 8 second scan window, the remaining failure is likely in main-loop work after scan has started rather than in start / stop calls.
  - The strongest current hypothesis is unbounded advertisement observation draining: if BLE advertisements keep filling the queue, the poll loop can keep processing observations and delay timeout / protocol command handling indefinitely.
- Follow-up implemented:
  - `zmk_usb_bridge_gui_ble_poll()` now checks the active scan deadline before draining observations.
  - Advertisement observation processing is capped per poll cycle.
  - This should allow `scan_complete(result=ok)` and watchdog refresh responses to happen even under a noisy BLE advertisement stream.

### 2026-04-19: `logs/sessions/20260419_170751_f68c.jsonl`

- Scenario:
  - GUI start
  - USB dongle attached
  - `Scan` clicked
  - keyboard pairing mode started
  - USB dongle unplugged after waiting
  - GUI closed
- Observed:
  - Receiver probe on `COM8` succeeded in `62 ms` via `hello`.
  - GUI reached `attached` at `2026-04-19T17:08:02.759+08:00`.
  - Receiver emitted repeated boot snapshots while waiting for a host command.
  - GUI sent `scan_start` request `1` at `2026-04-19T17:08:05.111+08:00`.
  - Receiver replied with `ack(scan_start)`, `scan_started(candidate_generation=1)`, and `candidate_snapshot(candidate_generation=1, candidates=[])` by `2026-04-19T17:08:05.125+08:00`.
  - Keyboard debug log shows profile 1 selected, advertising changed from `0` to `2`, and `Profile 1 open, blinking yellow`.
  - GUI watchdog fired at `2026-04-19T17:08:17.263+08:00` and sent `get_status` / `get_candidates`.
  - No `candidate_upsert`, `scan_complete`, or response to watchdog `get_status` / `get_candidates` was observed.
- Interpretation:
  - `scan_start` acceptance is still stable.
  - Moving scan deadline checks before observation processing and limiting poll-side observation count was not sufficient.
  - The likely remaining pressure point is the BLE scan callback itself: it was still parsing advertisement data, formatting BLE addresses, and logging queue-full cases from the Bluetooth callback context.
  - If advertisement callbacks arrive continuously, that callback work can still starve the main protocol loop before `scan_complete` or watchdog recovery can run.
- Follow-up implemented:
  - BLE scan callback now only copies `bt_addr_le_t`, advertisement type, RSSI, timestamp, and raw AD bytes into the observation queue.
  - Advertisement parsing and BLE address string formatting moved to bounded main-loop processing.
  - Queue-full drops no longer emit a log line from the BLE callback.
  - This should reduce Bluetooth callback pressure enough for `scan_complete(result=ok)` and refresh responses to be emitted.

### 2026-04-19: `logs/sessions/20260419_171445_fa4c.jsonl`

- Scenario:
  - GUI start
  - USB dongle connected
  - receiver attach did not complete
  - USB dongle unplugged after waiting
  - GUI closed
- Observed:
  - GUI discovery ran from `2026-04-19T17:14:45.573+08:00` to `2026-04-19T17:14:59.150+08:00`.
  - Discovery repeatedly saw `COM10`, `COM4`, and `COM9`.
  - `COM4` was the keyboard debug serial port with VID/PID `0x1D50/0x615E`.
  - No receiver VID/PID `0x2FE3/0x0012` port was observed.
  - No receiver probe, `hello`, `status_snapshot`, or `candidate_snapshot` was observed.
- Interpretation:
  - This run failed before GUI protocol attach.
  - Unlike the scan-blocking runs, there is no evidence that the GUI reached the receiver firmware at all.
  - The most likely state is that the receiver did not enumerate as the application CDC device during this session, or Windows had not exposed the receiver COM ports before the dongle was removed.
  - The latest BLE scan callback change should not execute before `scan_start`, so this observation is not enough by itself to identify a firmware scan regression.
- Follow-up:
  - Re-run a short attach-only test after unplugging / replugging the receiver, and confirm whether `COM8` / `COM7` or another port with VID/PID `0x2FE3/0x0012` appears.
  - If the receiver still does not enumerate, verify whether the dongle is in bootloader mode or whether the latest `zephyr.uf2` was successfully flashed.
  - If enumeration returns, continue with the existing `scan_start -> scan_complete` validation.

### 2026-04-19: `logs/sessions/20260419_171816_f28c.jsonl`

- Scenario:
  - GUI start
  - USB dongle connected
  - receiver attach did not complete
  - USB dongle unplugged after waiting
  - GUI closed
- Observed:
  - GUI discovery ran from `2026-04-19T17:18:16.575+08:00` to `2026-04-19T17:18:57.919+08:00`.
  - Discovery repeatedly saw `COM10`, `COM4`, `COM6`, and `COM9`.
  - `COM4` was the keyboard debug serial port with VID/PID `0x1D50/0x615E`.
  - `COM6` had the receiver serial number `08CC99D9331ADDD5`, but VID/PID `0x2886/0x0045`, not the receiver application VID/PID.
  - No receiver application VID/PID `0x2FE3/0x0012` port was observed.
  - No receiver probe, `hello`, `status_snapshot`, or `candidate_snapshot` was observed.
- Interpretation:
  - This is a second consecutive attach-only failure before GUI protocol attach.
  - The receiver hardware identity appears partially visible via `COM6`, but the expected application CDC ports are absent.
  - Current blocker is likely receiver application enumeration / flash / boot mode, not the BLE scan path.
  - Since no `scan_start` happened, this log does not validate or invalidate the latest BLE scan callback lightening change.
- Follow-up:
  - Verify whether the receiver dongle is in bootloader mode or otherwise not running the application firmware.
  - Reflash `/home/dev/00_Dev_BLE_Reciever/artifacts/builds/latest/receiver_seeeduino_xiao_ble/zephyr.uf2`.
  - After flashing, confirm that discovery sees VID/PID `0x2FE3/0x0012` again before continuing scan validation.

### 2026-04-19: `logs/sessions/20260419_172414_237d.jsonl`

- Scenario:
  - GUI start
  - USB dongle connected
  - receiver attach did not complete
  - GUI closed
- Observed:
  - GUI discovery ran from `2026-04-19T17:24:14.730+08:00` to `2026-04-19T17:24:34.823+08:00`.
  - Discovery repeatedly saw `COM10`, `COM4`, and `COM9`.
  - `COM4` was the keyboard debug serial port with VID/PID `0x1D50/0x615E`.
  - No receiver application VID/PID `0x2FE3/0x0012` port was observed.
  - No receiver bootloader-like VID/PID `0x2886/0x0045` port was observed in this run.
  - No receiver probe, `hello`, `status_snapshot`, or `candidate_snapshot` was observed.
- Interpretation:
  - This is a third consecutive failure before GUI protocol attach.
  - Unlike `20260419_171816_f28c`, the receiver serial number / bootloader-like `COM6` was not visible either.
  - Current blocker remains receiver USB enumeration / boot mode / flash state, not BLE scan or GUI protocol handling.
  - This log does not validate the latest BLE scan callback lightening change because the receiver application never appeared.
- Follow-up implemented:
  - Desktop app discovery now surfaces a clearer flash hint if VID/PID `0x2886/0x0045` is observed without a matching receiver application port.
  - A targeted runtime test covers this bootloader hint path.
  - Firmware-side raw observation enqueue change was reverted after A/B testing showed `20260419_170324_receiver_seeeduino_xiao_ble` enumerates `COM7` / `COM8`, while `20260419_171117_receiver_seeeduino_xiao_ble` and `20260419_173114_receiver_seeeduino_xiao_ble` do not.
  - Verification firmware `20260419_175947_receiver_seeeduino_xiao_ble` was built with the reverted callback path; flashing it restored `COM7` / `COM8`.
  - New scan-pressure mitigation firmware `20260419_180648_receiver_seeeduino_xiao_ble` keeps the COM-working callback parsing path and adds callback-side observation filtering / duplicate throttling without raw AD enqueue.
- Follow-up required:
  - Superseded by the `20260419_181030_592e` observation and `20260419_181448_receiver_seeeduino_xiao_ble` follow-up firmware below.

### 2026-04-19: `logs/sessions/20260419_181030_592e.jsonl`

- Scenario:
  - UF2 `20260419_180648_receiver_seeeduino_xiao_ble` flashed
  - GUI start
  - USB dongle attached
  - `Scan` clicked
  - keyboard advertising started
  - GUI watchdog timed out
  - USB dongle unplugged and GUI closed
- Observed:
  - At session start, discovery briefly saw bootloader-like `COM6` with VID/PID `0x2886/0x0045`.
  - Receiver application ports then appeared as `COM8` / `COM7` with VID/PID `0x2FE3/0x0012`.
  - Receiver probe on `COM8` succeeded in `77 ms` via `hello`.
  - GUI reached `attached` at `2026-04-19T18:10:37.416+08:00`.
  - Before `scan_start`, receiver emitted repeated `hello` / `status_snapshot` / `candidate_snapshot` boot snapshots.
  - GUI sent `scan_start` request `1` at `2026-04-19T18:10:46.300+08:00`.
  - Receiver replied with `ack(scan_start)`, `scan_started(candidate_generation=1)`, and `candidate_snapshot(candidate_generation=1, candidates=[])` by `2026-04-19T18:10:46.307+08:00`.
  - Keyboard debug log shows profile 1 advertising open at `2026-04-19T18:10:48.043+08:00`.
  - No `candidate_upsert`, `scan_complete`, or response to watchdog `get_status` / `get_candidates` was observed.
  - GUI watchdog fired at `2026-04-19T18:10:58.495+08:00`.
  - USB unplug later surfaced as `Receiver port write failed: Write timeout`.
- Interpretation:
  - The raw observation enqueue regression remains avoided: receiver application COM7 / COM8 enumeration and GUI attach both worked.
  - The scan-blocking failure remains after `ack` / `scan_started`.
  - Since no `scan_complete(result=error, code=bluetooth_init_timeout|scan_start_timeout)` was emitted, the main protocol loop likely stopped reaching `zmk_usb_bridge_gui_ble_poll()` after Bluetooth enable / scan start began.
  - The strongest current hypothesis is that asynchronous `bt_enable(callback)` moved initialization into a higher-priority system workqueue path that can prevent the main loop timeout path from running.
- Follow-up implemented:
  - Bluetooth enable now runs synchronously as `bt_enable(NULL)` inside the dedicated lower-priority BLE worker thread.
  - The main protocol loop should remain able to emit `bluetooth_init_timeout` / `scan_start_timeout` if Bluetooth init or scan start blocks.
  - New verification firmware `20260419_181448_receiver_seeeduino_xiao_ble` was built for this path.

### 2026-04-19: `logs/sessions/20260419_181648_532e.jsonl`

- Scenario:
  - UF2 `20260419_181448_receiver_seeeduino_xiao_ble` flashed
  - GUI start
  - USB dongle attached
  - `Scan` clicked
  - keyboard advertising started
  - GUI watchdog timed out
  - USB dongle unplugged and GUI closed
- Observed:
  - Receiver application ports appeared as `COM8` / `COM7` with VID/PID `0x2FE3/0x0012`.
  - Receiver probe on `COM8` succeeded in `30 ms` via `hello`.
  - GUI reached `attached` at `2026-04-19T18:16:55.775+08:00`.
  - Before `scan_start`, receiver emitted repeated `hello` / `status_snapshot` / `candidate_snapshot` boot snapshots.
  - GUI sent `scan_start` request `1` at `2026-04-19T18:16:59.281+08:00`.
  - Receiver emitted one more `hello` at `2026-04-19T18:16:59.295+08:00`, but no `ack(scan_start)`, `scan_started`, `candidate_snapshot(candidate_generation=1)`, `scan_complete`, or response to watchdog `get_status` / `get_candidates` was observed.
  - GUI watchdog fired at `2026-04-19T18:17:11.368+08:00`.
  - USB unplug later surfaced as `Receiver port write failed: Write timeout`.
- Interpretation:
  - COM enumeration and attach remain healthy.
  - Synchronous `bt_enable(NULL)` inside the dedicated worker did not restore the firmware timeout path.
  - Because even `ack(scan_start)` was absent in this run, the main protocol loop appears unable to reliably finish command handling once Bluetooth work starts or competes for CPU.
  - Zephyr config shows main thread priority `0`, while Bluetooth TX/RX are cooperative priorities equivalent to `-9` / `-8`; they can preempt the main protocol loop.
- Follow-up implemented:
  - `CONFIG_MAIN_THREAD_PRIORITY=-10` added so the main protocol loop can outrank Bluetooth TX/RX and still yield via its existing `k_msleep(10)` idle path.
  - New verification firmware `20260419_181920_receiver_seeeduino_xiao_ble` was built for this priority path.

### 2026-04-19: `logs/sessions/20260419_182131_7a8f.jsonl`

- Scenario:
  - UF2 `20260419_181920_receiver_seeeduino_xiao_ble` flashed
  - GUI start
  - USB dongle attached
  - `Scan` clicked
  - keyboard advertising started
  - GUI watchdog timed out
  - USB dongle unplugged and GUI closed
- Observed:
  - At session start, discovery briefly saw bootloader-like `COM6` with VID/PID `0x2886/0x0045`.
  - Receiver application ports then appeared as `COM8` / `COM7` with VID/PID `0x2FE3/0x0012`.
  - Receiver probe on `COM8` succeeded in `31 ms` via `hello`.
  - GUI reached `attached` at `2026-04-19T18:21:36.056+08:00`.
  - GUI sent `scan_start` request `1` at `2026-04-19T18:21:39.534+08:00`.
  - Receiver replied with `ack(scan_start)`, `scan_started(candidate_generation=1)`, and `candidate_snapshot(candidate_generation=1, candidates=[])` by `2026-04-19T18:21:39.549+08:00`.
  - No `candidate_upsert`, `scan_complete`, or response to watchdog `get_status` / `get_candidates` was observed.
  - GUI watchdog fired at `2026-04-19T18:21:51.791+08:00`.
  - USB unplug later surfaced as `Receiver port write failed: Write timeout`.
- Interpretation:
  - COM enumeration, GUI attach, and immediate scan command response are healthy again.
  - Main protocol loop priority protected `ack(scan_start)` and `scan_started`, but scan completion still depends on a path that does not run once BLE scan activity begins.
  - The current blocker is now narrower: receiver must emit `scan_complete` or a specific scan start/init timeout even if the normal main poll loop is delayed by Bluetooth scan work.
- Follow-up implemented:
  - Added a dedicated scan supervisor thread at priority `-11`, above the main protocol loop priority `-10`.
  - The supervisor checks the Bluetooth init / scan-start deadline and active scan window every `50 ms`, and calls the same `complete_scan()` path to emit `scan_start_timeout`, `bluetooth_init_timeout`, or `scan_complete(result=ok)`.
  - New verification firmware `20260419_182504_receiver_seeeduino_xiao_ble` was built for this supervisor path.

### 2026-04-19: `logs/sessions/20260419_182841_a6fb.jsonl`

- Scenario:
  - UF2 `20260419_182504_receiver_seeeduino_xiao_ble` flashed
  - GUI start
  - USB dongle attached
  - `Scan` clicked
  - keyboard advertising started
  - GUI watchdog timed out
  - USB dongle unplugged and GUI closed
- Observed:
  - At session start, discovery briefly saw bootloader-like `COM6` with VID/PID `0x2886/0x0045`.
  - Receiver application ports then appeared as `COM8` / `COM7` with VID/PID `0x2FE3/0x0012`.
  - Receiver probe on `COM8` succeeded in `62 ms` via `hello`.
  - GUI reached `attached` at `2026-04-19T18:28:46.729+08:00`.
  - GUI sent `scan_start` request `1` at `2026-04-19T18:28:48.378+08:00`.
  - Receiver replied with `ack(scan_start)`, `scan_started(candidate_generation=1)`, and `candidate_snapshot(candidate_generation=1, candidates=[])` by `2026-04-19T18:28:48.388+08:00`.
  - No `candidate_upsert`, `scan_complete`, or response to watchdog `get_status` / `get_candidates` was observed.
  - GUI watchdog fired at `2026-04-19T18:29:00.572+08:00`.
  - USB unplug later surfaced as `Receiver port write failed: Write timeout`.
- Interpretation:
  - COM enumeration, GUI attach, and immediate scan command response remain healthy.
  - The scan supervisor alone did not make `scan_complete` visible to the GUI.
  - Because `complete_scan()` emits through the asynchronous GUI CDC writer, the remaining likely choke point is that the GUI writer thread still runs at low priority `5` and cannot flush queued protocol lines once BLE scan work is active.
- Follow-up implemented:
  - GUI protocol CDC writer priority was raised to `-12`, above scan supervisor `-11` and main protocol loop `-10`.
  - Log CDC writer remains priority `5` to avoid making debug output compete with the control protocol path.
  - New verification firmware `20260419_183030_receiver_seeeduino_xiao_ble` was built for this USB writer priority path.

### 2026-04-19: `logs/sessions/20260419_183338_3167.jsonl`

- Scenario:
  - UF2 `20260419_183030_receiver_seeeduino_xiao_ble` flashed
  - GUI start
  - USB dongle attached
  - `Scan` clicked
  - keyboard advertising started
  - GUI watchdog timed out
  - USB dongle unplugged and GUI closed
- Observed:
  - At session start, discovery briefly saw bootloader-like `COM6` with VID/PID `0x2886/0x0045`.
  - Receiver application ports then appeared as `COM8` / `COM7` with VID/PID `0x2FE3/0x0012`.
  - Receiver probe on `COM8` succeeded in `47 ms` via `hello`.
  - GUI reached `attached` at `2026-04-19T18:33:43.244+08:00`.
  - GUI sent `scan_start` request `1` at `2026-04-19T18:33:45.842+08:00`.
  - Receiver replied with `ack(scan_start)`, `scan_started(candidate_generation=1)`, and `candidate_snapshot(candidate_generation=1, candidates=[])` by `2026-04-19T18:33:45.856+08:00`.
  - No `candidate_upsert`, `scan_complete`, or response to watchdog `get_status` / `get_candidates` was observed.
  - GUI watchdog fired at `2026-04-19T18:33:58.043+08:00`.
  - USB unplug later surfaced as `Receiver port write failed: Write timeout`.
- Interpretation:
  - COM enumeration, GUI attach, and immediate scan command response remain healthy.
  - Raising the GUI CDC writer priority did not restore scan completion or watchdog responses.
  - The active BLE scan itself is now the likely source of starvation or a lower-level USB/Bluetooth scheduling conflict after `bt_le_scan_start()`.
- Follow-up implemented:
  - Scan mode was changed from continuous active scan to lower-duty passive scan.
  - Scan parameters are now interval `0x01E0` and window `0x0030`, roughly `300 ms` interval and `30 ms` window.
  - Firmware scan window was increased from `8000 ms` to `10000 ms`, still ahead of the desktop watchdog window.
  - New verification firmware `20260419_183530_receiver_seeeduino_xiao_ble` was built for this lower-duty passive scan path.

### 2026-04-19: `logs/sessions/20260419_183721_a093.jsonl`

- Scenario:
  - UF2 `20260419_183530_receiver_seeeduino_xiao_ble` flashed
  - GUI start
  - USB dongle attached
  - `Scan` clicked
  - keyboard advertising started
  - GUI watchdog timed out
  - USB dongle unplugged and GUI closed
- Observed:
  - Discovery initially saw repeated bootloader-like `COM6` with VID/PID `0x2886/0x0045`.
  - Receiver application ports then appeared as `COM8` / `COM7` with VID/PID `0x2FE3/0x0012`.
  - Receiver probe on `COM8` succeeded in `47 ms` via `hello`.
  - GUI reached `attached` at `2026-04-19T18:37:39.369+08:00`.
  - GUI sent `scan_start` request `1` at `2026-04-19T18:37:42.162+08:00`.
  - Receiver replied with `ack(scan_start)`, `scan_started(candidate_generation=1)`, and `candidate_snapshot(candidate_generation=1, candidates=[])` by `2026-04-19T18:37:42.170+08:00`.
  - No `candidate_upsert`, `scan_complete`, or response to watchdog `get_status` / `get_candidates` was observed.
  - GUI watchdog fired at `2026-04-19T18:37:54.279+08:00`.
  - USB unplug later surfaced as `Receiver port write failed: Write timeout`.
- Interpretation:
  - Low-duty passive scan still did not restore scan completion or watchdog responses.
  - The remaining uncertainty is whether the advertisement callback work is causing the stall, or whether merely enabling an explicit BLE scan is enough to starve the protocol/USB path.
- Follow-up implemented:
  - Temporarily disabled the advertisement callback by starting BLE scan with `bt_le_scan_start(&scan_param, NULL)`.
  - This validation build is expected to produce no candidates; it only tests whether scan start/stop and `scan_complete(result=ok)` can reach the GUI when advertisement callbacks are absent.
  - New verification firmware `20260419_183950_receiver_seeeduino_xiao_ble` was built for this no-callback scan path.

### 2026-04-19: `logs/sessions/20260419_184158_7e13.jsonl`

- Scenario:
  - UF2 `20260419_183950_receiver_seeeduino_xiao_ble` flashed
  - GUI start
  - USB dongle attached
  - `Scan` clicked
  - keyboard advertising started
  - GUI watchdog timed out
  - USB dongle unplugged and GUI closed
- Observed:
  - Discovery initially saw repeated bootloader-like `COM6` with VID/PID `0x2886/0x0045`.
  - Receiver application ports then appeared as `COM8` / `COM7` with VID/PID `0x2FE3/0x0012`.
  - Receiver probe on `COM8` succeeded in `78 ms` via `hello`.
  - GUI reached `attached` at `2026-04-19T18:42:05.917+08:00`.
  - GUI sent `scan_start` request `1` at `2026-04-19T18:42:07.488+08:00`.
  - Receiver replied with `ack(scan_start)`, `scan_started(candidate_generation=1)`, and `candidate_snapshot(candidate_generation=1, candidates=[])` by `2026-04-19T18:42:07.500+08:00`.
  - No `candidate_upsert`, `scan_complete`, or response to watchdog `get_status` / `get_candidates` was observed.
  - GUI watchdog fired at `2026-04-19T18:42:19.730+08:00`.
  - USB unplug later surfaced as `Receiver port write failed: Write timeout`.
- Interpretation:
  - COM enumeration, GUI attach, and immediate scan command response remain healthy.
  - Advertisement callback disabled build still did not restore scan completion or watchdog responses.
  - This rules out callback parsing / callback-side candidate enqueue as the primary cause for the current stall.
  - The current blocker is likely below that layer: either `bt_le_scan_start()` enters a state where application/protocol threads cannot make forward progress, or a long-running explicit scan prevents the USB/protocol writer from running.
- Follow-up implemented:
  - New verification firmware starts BLE scan and immediately calls `bt_le_scan_stop()` in the BLE worker.
  - It then emits `scan_complete(result=ok)` only if the immediate start/stop smoke path returns.
  - This build is expected to produce no candidates; it isolates whether `bt_le_scan_start()` plus immediate `bt_le_scan_stop()` can complete without leaving the GUI waiting.
  - New verification firmware `20260419_184502_receiver_seeeduino_xiao_ble` was built for this start/stop smoke path.

### 2026-04-19: `logs/sessions/20260419_185525_3087.jsonl`

- Scenario:
  - UF2 `20260419_184502_receiver_seeeduino_xiao_ble` flashed
  - GUI start
  - USB dongle attached
  - `Scan` clicked
  - keyboard advertising started
  - GUI watchdog timed out
  - USB dongle unplugged and GUI closed
- Observed:
  - Discovery initially saw bootloader-like `COM6` with VID/PID `0x2886/0x0045`.
  - Receiver application ports then appeared as `COM8` / `COM7` with VID/PID `0x2FE3/0x0012`.
  - Receiver probe on `COM8` succeeded in `47 ms` via `hello`.
  - GUI reached `attached` at `2026-04-19T18:55:30.369+08:00`.
  - GUI sent `scan_start` request `1` at `2026-04-19T18:55:31.658+08:00`.
  - Receiver replied with `ack(scan_start)`, `scan_started(candidate_generation=1)`, and `candidate_snapshot(candidate_generation=1, candidates=[])` by `2026-04-19T18:55:31.667+08:00`.
  - No `scan_complete` was observed, even though this build should stop BLE scan immediately after starting it.
  - GUI watchdog fired at `2026-04-19T18:55:43.791+08:00` and sent `get_status` / `get_candidates`.
  - No receiver response to watchdog refresh was observed.
  - USB unplug later surfaced as `Receiver port write failed: Write timeout`.
- Interpretation:
  - COM enumeration, GUI attach, and immediate scan command response remain healthy.
  - Immediate BLE scan start/stop smoke path still did not return `scan_complete`.
  - The blocker is now narrowed to either `bt_enable(NULL)` not returning / starving the app after scan request, or `bt_le_scan_start()` not returning even before the immediate stop can run.
- Follow-up implemented:
  - New verification firmware skips `bt_le_scan_start()` entirely.
  - It calls `bt_enable(NULL)` through the existing BLE worker and emits `scan_complete(result=ok)` as soon as Bluetooth enable returns.
  - This build is expected to produce no candidates; it isolates whether Bluetooth enable alone is enough to block the GUI protocol path.
  - New verification firmware `20260419_185712_receiver_seeeduino_xiao_ble` was built for this Bluetooth-enable-only smoke path.

### 2026-04-19: `logs/sessions/20260419_190515_e742.jsonl`

- Scenario:
  - UF2 `20260419_185712_receiver_seeeduino_xiao_ble` flashed
  - GUI start
  - USB dongle attached
  - `Scan` clicked
  - GUI watchdog timed out
  - USB dongle unplugged and GUI closed
- Observed:
  - Discovery initially saw bootloader-like `COM6` with VID/PID `0x2886/0x0045`.
  - Receiver application ports then appeared as `COM8` / `COM7` with VID/PID `0x2FE3/0x0012`.
  - Receiver probe on `COM8` succeeded in `62 ms` via `hello`.
  - GUI reached `attached` at `2026-04-19T19:05:20.837+08:00`.
  - GUI sent `scan_start` request `1` at `2026-04-19T19:05:21.773+08:00`.
  - Receiver replied with `ack(scan_start)`, `scan_started(candidate_generation=1)`, and `candidate_snapshot(candidate_generation=1, candidates=[])` by `2026-04-19T19:05:21.787+08:00`.
  - No `scan_complete` was observed, even though this build should skip BLE scan and emit completion as soon as `bt_enable(NULL)` returns.
  - GUI watchdog fired at `2026-04-19T19:05:33.792+08:00` and sent `get_status` / `get_candidates`.
  - No receiver response to watchdog refresh was observed.
  - USB unplug later surfaced as `Receiver port write failed: Write timeout`.
- Interpretation:
  - COM enumeration, GUI attach, and immediate scan command response remain healthy.
  - Bluetooth enable-only smoke path still did not return `scan_complete`.
  - The blocker is now likely at or after `bt_enable(NULL)`, but before treating that as final, the protocol completion path needs a no-Bluetooth control case.
- Follow-up implemented:
  - New verification firmware does not call `bt_enable(NULL)` and does not start BLE scan.
  - It completes the scan from the normal firmware poll path after the deferred response window.
  - This build is expected to produce no candidates; it isolates whether `scan_complete` and watchdog response can still reach the GUI when Bluetooth is not touched.
  - New verification firmware `20260419_190633_receiver_seeeduino_xiao_ble` was built for this protocol-only smoke path.

### 2026-04-19: `logs/sessions/20260419_190851_c8b9.jsonl`

- Scenario:
  - UF2 `20260419_190633_receiver_seeeduino_xiao_ble` flashed
  - GUI start
  - USB dongle eventually attached after an extended bootloader-only discovery period
  - `Scan` clicked
  - GUI watchdog timed out
  - USB dongle unplugged and GUI closed
- Observed:
  - For roughly the first minute, discovery repeatedly saw only bootloader-like `COM6` with VID/PID `0x2886/0x0045`, not receiver application VID/PID `0x2FE3/0x0012`.
  - Receiver application ports later appeared as `COM8` / `COM7` with VID/PID `0x2FE3/0x0012`.
  - GUI reached `attached` at `2026-04-19T19:10:10.870+08:00`.
  - GUI sent `scan_start` request `1` at `2026-04-19T19:10:12.441+08:00`.
  - Receiver replied with `ack(scan_start)`, `scan_started(candidate_generation=1)`, and `candidate_snapshot(candidate_generation=1, candidates=[])` by `2026-04-19T19:10:12.455+08:00`.
  - No `scan_complete` was observed, even though this build should not initialize Bluetooth and should complete from the normal firmware poll path after the deferred response window.
  - GUI watchdog fired at `2026-04-19T19:10:24.731+08:00` and sent `get_status` / `get_candidates`.
  - No receiver response to watchdog refresh was observed.
  - USB unplug later surfaced as `Receiver port write failed: Write timeout`.
- Interpretation:
  - `ack` / `scan_started` / `candidate_snapshot` can still be emitted from the command handler.
  - The firmware does not appear to resume the expected normal poll path after accepting `scan_start`, even when Bluetooth is not touched.
  - The current blocker is therefore not BLE-specific yet; it is either command-handler return / poll-loop scheduling after scan state changes, or an interaction with the scan supervisor / async writer after `scan_start`.
- Follow-up implemented:
  - New verification firmware emits `scan_complete(result=ok)` immediately from the `scan_start` command handler after `ack`, `scan_started`, and `candidate_snapshot`.
  - This build is expected to produce no candidates and does not prove BLE readiness; it only tests whether the same handler context can enqueue and flush `scan_complete`.
  - New verification firmware `20260419_191148_receiver_seeeduino_xiao_ble` was built for this immediate-complete smoke path.

### 2026-04-19: `logs/sessions/20260419_191411_5952.jsonl`

- Scenario:
  - UF2 `20260419_191148_receiver_seeeduino_xiao_ble` flashed
  - GUI start
  - USB dongle attached
  - `Scan` clicked
  - receiver responded immediately
  - GUI closed
- Observed:
  - Receiver application ports appeared as `COM8` / `COM7` with VID/PID `0x2FE3/0x0012`.
  - Receiver probe on `COM8` succeeded in `47 ms` via `hello`.
  - GUI reached `attached` at `2026-04-19T19:14:18.997+08:00`.
  - GUI sent `scan_start` request `1` at `2026-04-19T19:14:22.343+08:00`.
  - Receiver replied with `ack(scan_start)`, `scan_started(candidate_generation=1)`, `candidate_snapshot(candidate_generation=1, candidates=[])`, and `scan_complete(result=ok, candidate_count=0)` by `2026-04-19T19:14:22.359+08:00`.
  - GUI state transitioned `scanning -> idle` and the Scan button became available again.
  - No watchdog timeout was observed.
- Interpretation:
  - The fourth GUI protocol line can be enqueued, flushed, read, and applied by the desktop app.
  - The blocker is not async GUI writer capacity, ring buffer truncation, or host read handling.
  - The failed protocol-only poll build indicates that the post-handler `protocol_poll()` / `ble_poll()` path was not a reliable place to start or complete scan work after `scan_start`.
- Follow-up implemented:
  - `scan_start` handling now calls `zmk_usb_bridge_gui_ble_scan_kick_after_response()` immediately after emitting `ack`, `scan_started`, and `candidate_snapshot`.
  - The current verification build still uses protocol-only smoke behavior, but the completion is now routed through the BLE scan module's after-response kick path rather than a direct handler-local `scan_cancel`.
  - New verification firmware `20260419_191652_receiver_seeeduino_xiao_ble` was built for this after-response kick path.

### 2026-04-19: `logs/sessions/20260419_191848_05eb.jsonl`

- Scenario:
  - UF2 `20260419_191652_receiver_seeeduino_xiao_ble` flashed
  - GUI start
  - USB dongle attached
  - `Scan` clicked
  - receiver responded immediately
  - USB dongle unplugged
  - GUI closed
- Observed:
  - Receiver application ports appeared as `COM8` / `COM7` with VID/PID `0x2FE3/0x0012`.
  - Receiver probe on `COM8` succeeded in `46 ms` via `hello`.
  - GUI reached `attached` at `2026-04-19T19:18:55.933+08:00`.
  - GUI sent `scan_start` request `1` at `2026-04-19T19:18:57.700+08:00`.
  - Receiver replied with `ack(scan_start)`, `scan_started(candidate_generation=1)`, `candidate_snapshot(candidate_generation=1, candidates=[])`, and `scan_complete(result=ok, candidate_count=0)` by `2026-04-19T19:18:57.716+08:00`.
  - GUI state transitioned `scanning -> idle`; no watchdog timeout was observed.
  - USB unplug surfaced as the expected disconnected state / `ClearCommError` after the scan had already completed.
- Interpretation:
  - The after-response kick path works when Bluetooth is not initialized.
  - The earlier protocol-only failure was caused by relying on post-handler poll progress, not by GUI writer capacity or host read handling.
  - This establishes the safe pattern for the next BLE-related experiments: emit the scan response frame set first, then kick the BLE scan module directly from the command handler tail.
- Follow-up implemented:
  - Protocol-only smoke was disabled.
  - Bluetooth enable-only smoke was enabled while keeping `zmk_usb_bridge_gui_ble_scan_kick_after_response()`.
  - New verification firmware `20260419_192118_receiver_seeeduino_xiao_ble` was built for this Bluetooth enable-only path.

### 2026-04-19: `logs/sessions/20260419_192301_fb3f.jsonl`

- Scenario:
  - UF2 `20260419_192118_receiver_seeeduino_xiao_ble` flashed
  - GUI start
  - USB dongle attached
  - `Scan` clicked
  - GUI timed out while waiting for receiver response
  - USB dongle unplugged
  - GUI closed
- Observed:
  - Receiver application ports appeared as `COM8` / `COM7` with VID/PID `0x2FE3/0x0012`.
  - Receiver probe on `COM8` succeeded in `282 ms` via `hello`.
  - GUI reached `attached` at `2026-04-19T19:23:06.276+08:00`.
  - GUI sent `scan_start` request `1` at `2026-04-19T19:23:08.315+08:00`.
  - Receiver replied with `ack(scan_start)`, `scan_started(candidate_generation=1)`, and `candidate_snapshot(candidate_generation=1, candidates=[])` by `2026-04-19T19:23:08.324+08:00`.
  - No `scan_complete` was observed.
  - GUI watchdog fired at `2026-04-19T19:23:20.589+08:00` and sent `get_status` / `get_candidates`.
  - No receiver response to watchdog refresh was observed.
  - USB unplug later surfaced as `Receiver port write failed: Write timeout`.
- Interpretation:
  - After-response kick itself remains healthy because the initial three response frames returned immediately.
  - The failure starts only after Bluetooth enable-only smoke kicks `bt_enable(NULL)`.
  - Because the firmware-side timeout/supervisor did not produce `scan_complete(error=bluetooth_init_timeout)`, the issue is likely thread scheduling / priority interaction or a hard stall inside Bluetooth enable, not just a slow enable.
- Follow-up implemented:
  - `CONFIG_MAIN_THREAD_PRIORITY` was changed from high-priority cooperative `-10` to preemptive `8`.
  - GUI CDC writer priority was changed from high-priority cooperative `-12` to preemptive `8`.
  - scan supervisor priority was changed from high-priority cooperative `-11` to preemptive `8`.
  - BLE init worker priority was lowered to preemptive `10`, and its stack was increased from `2048` to `4096`.
  - Main stack was increased from `2048` to `4096`; GUI writer stack was increased from `1024` to `2048`.
  - New verification firmware `20260419_192619_receiver_seeeduino_xiao_ble` was built for this preemptive-priority Bluetooth enable-only path.

### 2026-04-19: `logs/sessions/20260419_192816_6453.jsonl`

- Scenario:
  - UF2 `20260419_192619_receiver_seeeduino_xiao_ble` flashed
  - GUI start
  - USB dongle attached
  - `Scan` clicked
  - receiver responded quickly
  - USB dongle unplugged
  - GUI closed
- Observed:
  - Receiver application ports appeared as `COM8` / `COM7` with VID/PID `0x2FE3/0x0012`.
  - Receiver probe on `COM8` succeeded in `280 ms` via `hello`.
  - GUI reached `attached` at `2026-04-19T19:28:23.620+08:00`.
  - GUI sent `scan_start` request `1` at `2026-04-19T19:28:25.747+08:00`.
  - Receiver replied with `ack(scan_start)`, `scan_started(candidate_generation=1)`, and `candidate_snapshot(candidate_generation=1, candidates=[])` by `2026-04-19T19:28:25.756+08:00`.
  - Receiver emitted `scan_complete(result=ok, candidate_count=0)` at `2026-04-19T19:28:26.039+08:00`, roughly `292 ms` after the command was sent.
  - GUI state transitioned `scanning -> idle`; no watchdog timeout was observed.
- Interpretation:
  - `bt_enable(NULL)` can complete and the GUI protocol path can recover when app-owned threads do not outrank Zephyr USB / Bluetooth internal threads.
  - The prior `192301` timeout was therefore most likely caused by priority starvation / scheduling interaction, not by a fundamental board-level Bluetooth bring-up failure.
  - The current safe baseline is preemptive app threads plus after-response kick.
- Follow-up implemented:
  - Bluetooth enable-only smoke was disabled.
  - BLE scan start/stop smoke was enabled while keeping the preemptive-priority baseline and after-response kick.
  - New verification firmware `20260419_192939_receiver_seeeduino_xiao_ble` was built for this BLE scan start/stop smoke path.

### 2026-04-19: `logs/sessions/20260419_195750_5a7b.jsonl`

- Scenario:
  - UF2 `20260419_192939_receiver_seeeduino_xiao_ble` flashed
  - GUI start
  - USB dongle attached
  - `Scan` clicked
  - receiver responded quickly
  - USB dongle unplugged
  - GUI closed
- Observed:
  - Receiver application ports appeared as `COM8` / `COM7` with VID/PID `0x2FE3/0x0012`.
  - Receiver probe on `COM8` succeeded in `62 ms` via `hello`.
  - GUI reached `attached` at `2026-04-19T19:57:55.494+08:00`.
  - GUI sent `scan_start` request `1` at `2026-04-19T19:57:57.477+08:00`.
  - Receiver replied with `ack(scan_start)`, `scan_started(candidate_generation=1)`, and `candidate_snapshot(candidate_generation=1, candidates=[])` by `2026-04-19T19:57:57.486+08:00`.
  - Receiver emitted `scan_complete(result=ok, candidate_count=0)` at `2026-04-19T19:57:57.753+08:00`, roughly `276 ms` after the command was sent.
  - GUI state transitioned `scanning -> idle`; no watchdog timeout was observed.
  - USB unplug surfaced as the expected disconnected state / `ClearCommError` after the scan had already completed.
- Interpretation:
  - `bt_le_scan_start()` and immediate `bt_le_scan_stop()` can complete without blocking the GUI protocol path under the preemptive-priority baseline.
  - The active blocker has moved beyond Bluetooth enable and scan start/stop smoke; the next validation should restore advertisement callback and candidate cache processing.
- Follow-up implemented:
  - BLE scan start/stop smoke was disabled.
  - `device_found` advertisement callback was restored.
  - Scan remains passive / low-duty for the first candidate-capable validation to keep callback pressure low.
  - New verification firmware `20260419_195906_receiver_seeeduino_xiao_ble` was built for candidate-capable passive scan.

### 2026-04-19: `logs/sessions/20260419_200130_e27c.jsonl`

- Scenario:
  - UF2 `20260419_195906_receiver_seeeduino_xiao_ble` flashed
  - GUI start
  - USB dongle attached
  - `Scan` clicked
  - keyboard advertising started
  - GUI timed out while waiting for scan completion
  - USB dongle unplugged
  - GUI closed
- Observed:
  - Receiver application ports appeared as `COM8` / `COM7` with VID/PID `0x2FE3/0x0012`.
  - Receiver probe on `COM8` succeeded in `32 ms` via `hello`.
  - GUI reached `attached` at `2026-04-19T20:01:41.965+08:00`.
  - GUI sent `scan_start` request `1` at `2026-04-19T20:01:43.655+08:00`.
  - Receiver replied with `ack(scan_start)`, `scan_started(candidate_generation=1)`, and `candidate_snapshot(candidate_generation=1, candidates=[])` by `2026-04-19T20:01:43.670+08:00`.
  - Keyboard log shows profile 1 selected and advertising changed from `0` to `2` at `2026-04-19T20:01:44.342+08:00`, followed by `Profile 1 open, blinking yellow`.
  - Receiver emitted one `candidate_upsert` at `2026-04-19T20:01:44.569+08:00` for address `51:1D:01:06:6E:C1 (random)`, `connectable=true`, RSSI `-86`.
  - No `scan_complete` was observed after the candidate.
  - GUI watchdog fired at `2026-04-19T20:01:55.795+08:00` and sent `get_status` / `get_candidates`.
  - No receiver response to watchdog refresh was observed.
  - USB unplug later surfaced as `Receiver port write failed: Write timeout`.
- Interpretation:
  - Candidate detection, candidate cache insertion, and GUI `candidate_upsert` delivery work.
  - The remaining stall is caused by keeping the BLE scan window open after candidate discovery; once long scanning continues with callbacks active, protocol completion / refresh responses can still starve.
  - The next target should close the scan immediately after the first accepted candidate and emit `scan_complete` while the protocol path is still known to be alive.
- Follow-up implemented:
  - Added `ZMK_USB_BRIDGE_GUI_COMPLETE_ON_FIRST_CANDIDATE`.
  - After emitting a candidate upsert from the poll path, firmware now emits `scan_complete(result=ok)` immediately for this validation build.
  - New verification firmware `20260419_200313_receiver_seeeduino_xiao_ble` was built for first-candidate completion.

### 2026-04-19: `logs/sessions/20260419_200654_bd5f.jsonl`

- Scenario:
  - UF2 `20260419_200313_receiver_seeeduino_xiao_ble` flashed
  - GUI start
  - USB dongle attached
  - `Scan` clicked
  - keyboard advertising started
  - `LaLapadGen2` appeared in the candidate list
  - USB dongle unplugged
  - GUI closed
- Observed:
  - GUI initially surfaced the bootloader flash hint, then cleared it after the application receiver port was found.
  - Receiver probe on `COM8` succeeded in `78 ms` via `hello`.
  - GUI reached `attached` at `2026-04-19T20:06:59.072+08:00`.
  - GUI sent `scan_start` request `1` at `2026-04-19T20:07:02.967+08:00`.
  - Receiver replied with `ack(scan_start)`, `scan_started(candidate_generation=1)`, and `candidate_snapshot(candidate_generation=1, candidates=[])` by `2026-04-19T20:07:02.981+08:00`.
  - Receiver emitted an anonymous connectable-only `candidate_upsert` at `2026-04-19T20:07:05.073+08:00`.
  - Receiver emitted `scan_complete(result=ok, candidate_count=0)` immediately after that anonymous candidate.
  - Receiver then emitted `candidate_upsert` for `LalapadGen2` at `2026-04-19T20:07:05.084+08:00`, address `EE:6E:0E:2F:29:A0 (random)`, `connectable=true`, `has_hid_service=true`, `has_keyboard_appearance=true`, RSSI `-50`.
  - GUI returned to `idle` at `2026-04-19T20:07:05.213+08:00`.
  - USB unplug was reported as `disconnected`; the close-time serial error is expected for physical removal.
- Interpretation:
  - First-candidate completion successfully prevents the long-scan protocol stall.
  - `LaLapadGen2` is now discoverable with local name, HID service, keyboard appearance, and strong RSSI.
  - The completion trigger was too broad because it treated an internal cache-only anonymous candidate as a public candidate.
- Follow-up implemented:
  - Added shared `zmk_usb_bridge_gui_candidate_is_public()` eligibility helper matching the candidate listing policy.
  - Firmware now emits `candidate_upsert` and triggers first-candidate completion only for public Tier A/B candidates.
  - New verification firmware `20260419_200942_receiver_seeeduino_xiao_ble` was built for public-candidate completion.

### 2026-04-19: `logs/sessions/20260419_201239_d9ca.jsonl`

- Scenario:
  - UF2 `20260419_200942_receiver_seeeduino_xiao_ble` flashed
  - GUI start
  - USB dongle attached
  - `Scan` clicked
  - keyboard advertising started
  - `LaLapadGen2` appeared in the candidate list
  - USB dongle unplugged
  - GUI closed
- Observed:
  - GUI detected bootloader mode on `COM6` before the application receiver port appeared, then cleared the flash hint once the application receiver was attached.
  - Receiver probe on `COM8` succeeded in `280 ms` via `hello`.
  - GUI reached `attached` at `2026-04-19T20:12:44.510+08:00`.
  - GUI sent `scan_start` request `1` at `2026-04-19T20:12:47.705+08:00`.
  - Receiver replied with `ack(scan_start)`, `scan_started(candidate_generation=1)`, and `candidate_snapshot(candidate_generation=1, candidates=[])` by `2026-04-19T20:12:47.721+08:00`.
  - Receiver emitted `candidate_upsert` for `LalapadGen2` at `2026-04-19T20:12:48.600+08:00`, address `EE:6E:0E:2F:29:A0 (random)`, `connectable=true`, `has_hid_service=true`, `has_keyboard_appearance=true`, RSSI `-57`.
  - Receiver emitted `scan_complete(result=ok, candidate_count=1)` at `2026-04-19T20:12:48.601+08:00`.
  - GUI returned to `idle` at `2026-04-19T20:12:48.605+08:00`.
  - USB unplug was reported as `disconnected`; subsequent bootloader detection is expected because the receiver was physically removed / reset.
- Interpretation:
  - Anonymous internal candidates no longer close the scan early.
  - Public-candidate completion works: visible `LaLapadGen2` is delivered before `scan_complete`, and the GUI returns to idle without watchdog timeout.
  - Scan / candidate listing / completion is stable enough to proceed to manual connect validation.

### 2026-04-19: `logs/sessions/20260419_201654_8166.jsonl`

- Scenario:
  - UF2 `20260419_200942_receiver_seeeduino_xiao_ble` flashed
  - GUI start
  - USB dongle attached
  - `Scan` clicked
  - keyboard advertising started
  - `LaLapadGen2` appeared in the candidate list
  - `Connect` clicked
  - GUI hung, then USB dongle was unplugged
  - GUI closed
- Observed:
  - Scan path remained healthy: `candidate_upsert(LalapadGen2)` and `scan_complete(result=ok, candidate_count=1)` arrived at `2026-04-19T20:17:03.489+08:00` / `20:17:03.490+08:00`.
  - GUI sent `connect_candidate` request `2` for `candidate_generation=1`, `candidate_id=1` at `2026-04-19T20:17:18.605+08:00`.
  - No `ack(connect_candidate)` was observed.
  - No `connection_state(connecting)` or explicit failure code was observed.
  - USB unplug later surfaced as receiver `disconnected`; subsequent bootloader detection is expected after physical removal / reset.
- Interpretation:
  - The hang occurs before the protocol acceptance response for `connect_candidate`.
  - The likely cause is that the command handler starts BLE connection work synchronously when Bluetooth is already ready, entering `bt_conn_le_create()` before GUI protocol `ack` / `connection_state(connecting)` can be emitted.
- Follow-up implemented:
  - `zmk_usb_bridge_gui_ble_connect_start()` now only parses and queues the connect target, starts Bluetooth init if needed, and returns promptly.
  - BLE connection creation is deferred by `50 ms` and performed by a dedicated preemptive connect worker thread.
  - New verification firmware `20260419_202105_receiver_seeeduino_xiao_ble` was built for async connect start.

## Next Hardware Validation

1. Flash `/home/dev/00_Dev_BLE_Reciever/artifacts/builds/20260419_202105_receiver_seeeduino_xiao_ble/zephyr.uf2` to the receiver dongle.
2. Start the GUI and confirm USB attach reaches `attached`.
3. Run `Scan`.
4. Start keyboard advertising / pairing mode while scan is running.
5. Confirm `LaLapadGen2` appears and scan completes with `scan_complete(result=ok, candidate_count=1)`.
6. Select `LaLapadGen2` and run `Connect`.
7. Confirm the receiver emits `ack(connect_candidate)` and `connection_state(connecting)` immediately after `Connect`.
8. Record whether the receiver later emits:
   - `connection_state(connected)`
   - or `connection_state(idle, code=...)`
9. If `connected`, run `Bond Erase` and confirm `bonds_cleared` plus idle state.
10. Save the GUI session log and record the observed code / message here.

## Known Pending Work

- `connected` currently means BLE connection, security request, and HID service presence validation succeeded.
- Input report discovery / subscription is not implemented yet, so real key / consumer / mouse forwarding is not expected to work in this checkpoint.
- Bond persistence and bonded reconnect still require real keyboard validation.
