# ethernet_driver

Ethernet firmware for the NUCLEO-H753ZI (or NUCLEO-H743ZI) that receives the rocket simulation's
telemetry over UDP and forwards it to a listening PC over USB serial, plus Python scripts to read,
test and verify the link.

This is a standalone step toward using Ethernet, not USART, as the host link for the HIL system.
It is **not** yet part of the HIL firmware in the rest of this repo.

## Overview

Two computers are used:

- The **simulation PC** (Windows) runs the sim and is connected to the board by Ethernet.
- The **listening PC** (currently a Mac) is connected to the board by USB. It flashes the board
  and reads what the board receives.

```
[Simulation PC]                   [STM32 board]                     [Listening PC]
 Unreal sim (RocketUdpBridge) ─┐   udp_receiver.c                    serial_reader.py
   JSON telemetry               ├─► receives on UDP 5005  ──USB──►   parses JSON, shows it,
 udp_sender.py (test packets) ─┘   prints each packet     serial     writes telemetry.csv
        Ethernet, 192.168.0.11      192.168.0.10                     and received.log
```

- The **sim** on the simulation PC sends one JSON line per UDP packet to the board.
- The **board** receives each packet and prints it over its USB serial port, which the on-board
  ST-LINK provides. It does not decode the JSON yet; it forwards the bytes as hex.
- The **listening PC** reads the serial port, turns the hex back into text, parses the JSON into typed
  values, and saves each packet as a row of a CSV.

For testing the link without the sim, `udp_sender.py` sends numbered test packets with a CRC-32,
which the board checks itself, and `compare_logs.py` confirms that every one arrived intact.

There is no separate Ethernet driver to install on an STM32. The Ethernet driver, LwIP (the network
stack) and FreeRTOS are compiled into one firmware image with the application, and flashing that
image puts them all on the board.

## Firmware outline

The firmware started as ST's **LwIP HTTP Server (Netconn, FreeRTOS)** example for the
NUCLEO-H743ZI. We kept its board and network setup and ST's libraries, removed the web server and
TCP, and added a UDP receiver and a serial log.

```
ethernet_driver/
├── Src/, Inc/              the application: edit these
├── Startup/                code that runs before main()
├── STM32H743ZITX_FLASH.ld  memory layout
├── Drivers/                ST's chip and board drivers: don't edit
├── Middlewares/            LwIP and FreeRTOS: don't edit
├── scripts/                Python scripts for both PCs
└── Makefile                build, flash and clean
```

| Folder | What it holds |
|---|---|
| `Src/`, `Inc/` | The application: board and network setup, the UDP receiver and the serial log. `Inc/` also holds the libraries' settings: `main.h` (IP address), `lwipopts.h` (LwIP), `FreeRTOSConfig.h` and `stm32h7xx_hal_conf.h` (which HAL drivers are on). |
| `Startup/` | `startup_stm32h743zitx.s` runs first at power-on: it sets up the stack and RAM, then calls `main()`. `syscalls.c` and `sysmem.c` make `printf` and `malloc` work on the board. |
| `STM32H743ZITX_FLASH.ld` | The linker script: where code goes in flash and data goes in RAM. |
| `Drivers/CMSIS/` | Arm's standard Cortex-M definitions and ST's register definitions for the STM32H7. |
| `Drivers/STM32H7xx_HAL_Driver/` | ST's HAL: drivers for the chip's Ethernet, UART, GPIO, clocks and timers. |
| `Drivers/BSP/` | Board support: the Nucleo's LEDs and serial port, and the LAN8742 Ethernet chip driver. |
| `Middlewares/Third_Party/LwIP/` | The network stack, used here for IP, ARP, ping and UDP. |
| `Middlewares/Third_Party/FreeRTOS/` | The real-time OS that runs the tasks. |

`Drivers/`, `Middlewares/`, `Startup/` and the linker script are copied unchanged from
[STM32CubeH7](https://github.com/STMicroelectronics/STM32CubeH7) `v1.13.0-14-g8ec3113d4`, keeping
its folder layout. Only the files this firmware compiles or includes were copied, so no separate
STM32CubeH7 clone is needed.

### Files Added

| File | What it does |
|---|---|
| `Src/udp_receiver.c`, `Inc/udp_receiver.h` | Receives packets on UDP port 5005 and reports each one over serial. See [How the UDP receiver works](#how-the-udp-receiver-works). |
| `Src/serial_log.c`, `Inc/serial_log.h` | Sets up USART3 at 921600 baud and sends text to the listening PC. Also sends `printf` output there. |

### Files changed from ST's example

| File | Change |
|---|---|
| `Src/main.c` | Starts the serial log and the UDP receiver; no longer starts the web server |
| `Inc/lwipopts.h` | `LWIP_DHCP` set to `0`, so the board uses its static IP immediately; `LWIP_TCP` set to `0`, since only UDP is used |
| `Inc/FreeRTOSConfig.h` | FreeRTOS heap raised from 25 KB to 48 KB for the receiver's tasks and queues |

Removed from the example: the demo web server (`httpserver_netconn.c/.h`, `fsdata_custom.c`) and
the unused `stmpe811_conf.h`.

### ST's files kept as is

| File | What it does |
|---|---|
| `Src/ethernetif.c` | Connects LwIP to the Ethernet hardware and the LAN8742 chip, and checks the cable link |
| `Src/app_ethernet.c` | Turns the green LED on when the link is up, and the red LED when it is down |
| `Src/stm32h7xx_it.c` | Interrupt handlers, including the Ethernet interrupt that fires when a frame arrives |
| `Src/stm32h7xx_hal_timebase_tim.c` | A 1 ms timer for ST's drivers, separate from FreeRTOS's tick |
| `Src/system_stm32h7xx.c` | Low-level chip setup that runs before `main()` |

### Startup sequence

1. `main()` sets up the memory protection unit for the Ethernet hardware, turns on the CPU caches,
   sets the clock to 400 MHz, and sets up the LEDs and the serial log.
2. It starts FreeRTOS with one startup task.
3. The startup task starts LwIP, brings up the network with the static IP from `Inc/main.h`, then
   calls `udp_receiver_init()`.

## How the UDP receiver works

`Src/udp_receiver.c` runs as two FreeRTOS tasks connected by queues:

```
UDP packet ─► [UdpRx task] ─► queue ─► [UdpLog task] ─► serial_log_write() ─► listening PC
              receives and             prints one line
              classifies               per packet
```

The serial link is about 100 times slower than Ethernet, so the two jobs are split: the receive
task never waits on printing, and printing can't cause missed packets. If a queue fills up, that
packet's line is dropped and counted in `log_drop`, but the packet itself was still received.

**`udp_receiver_init()`** is called once the network is up. It prints the `BOOT` line, builds the
CRC lookup table, creates the queues and starts both tasks.

**The receive task (`udp_rx_thread`)**, at above-normal priority:

1. Opens a UDP connection with LwIP's netconn API and binds it to port 5005.
2. Waits for each packet and copies it into one buffer, since LwIP can split a packet across
   several pieces.
3. Passes it to `handle_packet()`, which sorts it by its first 4 bytes:

| Packet | What happens |
|---|---|
| Doesn't start with `HILU`, like the sim's JSON | `handle_raw()` copies up to 1024 bytes onto the raw queue, unchecked, and counts it in `raw` |
| Starts with `HILU`, a test packet from `udp_sender.py` | It checks the version and type, the length, then the CRC-32. It updates the counters and tracks the sequence number to detect lost or out-of-order packets. Seq 0 starts a new session and resets the counters. |

**The logging task (`udp_log_thread`)**, at low priority, takes each record off the queue and
prints it as a line: `RAW` for raw packets, `RX` for test packets, and `SESSION` when a new test
run starts. Once a second it also prints a `STAT` line with all the counters. See
[Serial output](#serial-output) for the formats.

The board doesn't decode the sim's JSON; the listening PC does. To use the values on the board, such as in
flight code, parse them in `handle_raw()` or a function it calls.

## Scripts

All scripts are in `scripts/`. The simulation PC only needs Python 3; copy the whole folder over,
since the scripts share `protocol.py`.

| Script | Runs on | What it does |
|---|---|---|
| `serial_reader.py` | Listening PC | Reads the board's serial output, shows it, and saves it to `received.log`. Parses JSON packets and saves them to `telemetry.csv`. |
| `check_connection.py` | Simulation PC | Pings the board and checks the replies have TTL=255, which only LwIP uses, to confirm the board is the device answering |
| `udp_sender.py` | Simulation PC | Sends numbered test packets with a CRC-32 at a set rate, and logs each one to `sent.csv` |
| `compare_logs.py` | Listening PC | Compares `sent.csv` with `received.log` and reports missing, corrupted, duplicated or out-of-order test packets. Ends with `PASS` or `FAIL`. |
| `protocol.py` | Both | The test packet format, shared by the other scripts |

### serial_reader.py

```sh
python3 serial_reader.py          # STAT lines once a second, plus parsed JSON and any errors
python3 serial_reader.py --text   # only each packet's text (the sim's JSON), nothing else
```

| Option | Default | Meaning |
|---|---|---|
| `--port` | auto-detect | Serial port, for example `/dev/tty.usbmodem1103` (`ls /dev/tty.usbmodem*` lists them) |
| `--baud` | `921600` | Must match `SERIAL_LOG_BAUDRATE` in `Inc/serial_log.h` |
| `--log` | `received.log` | Every line the board prints |
| `--telemetry` | `telemetry.csv` | Parsed JSON: one row per packet, one column per field, plus the board's uptime in ms |
| `--text` | off | Show only each packet's text |
| `--verbose` | off | Also show every `RX` line and the hex of JSON packets |

For JSON packets, it turns the hex back into text, parses it with `json.loads`, and shows each
field as `name=value` with its real type: numbers as floats, `phase` as a string, the flags as
booleans. A packet that can't be parsed, for example because it was cut off, is reported and
counted when you stop.

- **The log and CSV only cover while the reader runs.** The board stores nothing, so start the
  reader before the sim or sender.
- **Both files are overwritten** each time the reader starts.
- **The CSV's columns come from the first packet.** A field the sim adds partway through a run
  isn't saved.

### udp_sender.py

```sh
python udp_sender.py --rate 200 --size 64 --duration 10
```

| Option | Default | Meaning |
|---|---|---|
| `--ip` | `192.168.0.10` | Board IP |
| `--port` | `5005` | Board UDP port |
| `--rate` | `200` | Packets per second |
| `--size` | `64` | Payload bytes, 0 to 1448 |
| `--payload` | `counter` | `counter`, `random` or `zeros` |
| `--count` | `0` | Stop after this many packets (0 = no limit) |
| `--duration` | `0` | Stop after this many seconds (0 = no limit) |
| `--bind` | none | Local IP to send from, for example `192.168.0.11` |
| `--log` | `sent.csv` | Log of every packet sent |

## Configuration for the simulation

Everything below must match for the sim's data to reach the listening PC. Additionally, ensure that RocketUDP is auto started.

### Wiring

| Connection | From | To |
|---|---|---|
| Ethernet | Simulation PC's Ethernet port | Board's RJ45 jack, directly |
| USB | Listening PC | Board's **ST-LINK** USB port, at the opposite end from the Ethernet jack |

The USB connection powers the board, flashes it, and carries the serial output.

### Network

| Device | IP | Mask | Gateway | Set in |
|---|---|---|---|---|
| Board | `192.168.0.10` | `255.255.255.0` | none needed | `Inc/main.h` |
| Simulation PC's Ethernet adapter | `192.168.0.11` | `255.255.255.0` | none | Windows: Settings → Network → Ethernet → IP assignment → Manual |

- On the board, **LED2 (green)** on means the Ethernet link is up, and **LED3 (red)** means no link.
- If the simulation PC's Wi-Fi is also on a `192.168.0.x` network, Windows may send packets out
  the wrong adapter. Turn Wi-Fi off.
- Windows Defender Firewall on the simulation PC needs no changes, because outbound UDP and ping
  replies are allowed by default.

### Simulation

Set these in the sim's UDP bridge (`RocketUdpBridge`) settings:

| Setting | Value | Notes |
|---|---|---|
| Telemetry IP | `192.168.0.10` | The board |
| Telemetry port | `5005` | `UDP_RX_PORT` in `Inc/udp_receiver.h` |
| Listen port | Unchanged (5761) | The board doesn't send anything back |
| Send rate | Your choice | Set in the sim. The firmware and scripts don't control it. |

Restart the sim after changing them. When the bridge starts, the sim's log
(`Saved/Logs/UnrealSpaceProgram.log`) shows its settings:

```
RocketUdpBridge: listening on UDP 5761, telemetry -> 192.168.0.10:5005 @ 30 Hz.
```

Requirements on what the sim sends:

- **One JSON object per UDP packet.** A trailing newline is fine.
- **At most 1024 bytes per packet.** The board prints only the first 1024 bytes of each packet,
  so a longer one arrives cut off and can't be parsed. Telemetry packets are currently about 335
  bytes.
- **ASCII only.** The reader only turns fully printable ASCII back into text. A packet with other
  characters is shown as hex and not parsed.
- **Not starting with `HILU`.** Those bytes mark a test packet. A JSON object always starts with
  `{`.

A telemetry packet currently looks like this:

```json
{"met":21.005,"phase":"COAST","ignited":true,"liftoff":true,"apogee":false,"separated":false,
 "drogue":false,"main":false,"landed":false,"agl_ft":3500.75,"asl_ft":3934.60,"vs_fps":166.99,
 "thrust_lbf":0.00,"max_agl_ft":3500.75,"apogee_agl_ft":0.00,"lat":36.1757166,"lon":-86.8900506,
 "yaw_deg":270.25,"pitch_deg":78.12,"roll_deg":131.69}
```

The sim sends it as one line. If the sim's fields change, nothing in the firmware or scripts needs
to change.

### Listening PC

`serial_reader.py` needs pyserial and finds the board's serial port automatically. See
[Requirements](#requirements).

## Requirements

On the listening PC, to build, flash and read the board. These steps are for macOS, which the
listening PC currently runs:

1. **ARM GCC toolchain**, which provides `arm-none-eabi-gcc`:
   ```sh
   brew install --cask gcc-arm-embedded
   ```
2. **STM32CubeProgrammer CLI** (`STM32_Programmer_CLI`). The *STM32Cube for VS Code* extension
   installs it. The Makefile first looks for it on your `PATH`, then at
   `~/Library/Application Support/stm32cube/bundles/programmer/2.23.0/bin/STM32_Programmer_CLI`.
   If yours is somewhere else, pass `PROG=/path/to/STM32_Programmer_CLI` to `make flash`.
3. **Python 3 with pyserial**:
   ```sh
   python3 -m pip install pyserial
   ```
   If pip refuses with `externally-managed-environment`, as Homebrew's Python does, use a virtual
   environment:
   ```sh
   cd ethernet_driver/scripts
   python3 -m venv .venv
   source .venv/bin/activate      # run this in each new terminal before the scripts
   python3 -m pip install pyserial
   ```

On the simulation PC: **Python 3** only.

## Build and flash

With the board's ST-LINK USB port connected to the listening PC:

```sh
cd ethernet_driver
make          # build the firmware (app.elf, app.bin, app.map, obj/)
make flash    # build if needed, then flash, verify, and reset the board
make clean    # delete build output
```

`make flash` runs `STM32_Programmer_CLI -c port=SWD mode=UR -w app.elf -v -rst`. That writes
`app.elf` to flash through the on-board ST-LINK, reads it back to verify it, and resets the board
so the new firmware starts. You can also copy `app.bin` onto the USB drive the board shows up as,
for example `NOD_H753ZI`.

**Flashing overwrites whatever firmware was on the board**, including the HIL firmware. To go back
to HIL, run `make flash` (or `./flash.sh`) from the repo root.

## Running with the simulation

1. **Listening PC:** flash the board, then start the reader and leave it running:
   ```sh
   cd ethernet_driver
   make flash
   cd scripts
   python3 serial_reader.py --text
   ```
2. **Simulation PC:** check the connection from the `scripts` folder. The pings should show `TTL=255`.
   ```sh
   python check_connection.py
   ```
3. **Simulation PC:** start the sim, configured as in
   [Configuration for the simulation](#configuration-for-the-simulation).
4. **Listening PC:** each packet's JSON appears as one line. Without `--text`, the `raw=` count on the
   `STAT` lines should climb at the sim's send rate.
5. **Listening PC:** press Ctrl-C to stop. The parsed telemetry is in `scripts/telemetry.csv`, and
   everything the board printed is in `scripts/received.log`.

If nothing appears and `raw=` stays at 0, the packets aren't reaching the board:

- Check the sim's log for the `RocketUdpBridge` line. No line means the bridge didn't start; the
  wrong IP or port means the settings didn't apply.
- Run the link test below. If it passes, the problem is on the sim's side.
- If the ping fails, check the cable, the LEDs and the simulation PC's Ethernet adapter IP.

## Testing the link without the simulation

`udp_sender.py` sends test packets that the board checks for corruption and loss itself.

1. **Listening PC:** start the reader:
   ```sh
   python3 serial_reader.py
   ```
2. **Simulation PC:** send packets:
   ```sh
   python udp_sender.py --rate 200 --size 64 --duration 10
   ```
3. **Listening PC:** after the sender finishes, wait for one more `STAT` line, then press Ctrl-C.
4. **Listening PC:** copy `sent.csv` from the simulation PC, then compare it with the board's log:
   ```sh
   python3 compare_logs.py sent.csv received.log
   ```
   It must be the `sent.csv` from the same run as `received.log`, because each packet's CRC
   includes the sender's timestamp. The exit code is 0 only on `PASS`.

Each sender run starts at sequence number 0, and the board resets its counters when it sees seq 0.
If `received.log` covers several runs, `compare_logs.py` uses the last one.

## Reference

### Test packet format

UDP to port 5005, all fields little-endian. Defined in `Inc/udp_receiver.h` and
`scripts/protocol.py`, and the two must match.

| Offset | Size | Field | Value |
|---|---|---|---|
| 0 | 4 | `magic` | `HILU` (ASCII) |
| 4 | 1 | `version` | 1 |
| 5 | 1 | `msg_type` | 1 (data) |
| 6 | 2 | `payload_len` | N, at most 1448 |
| 8 | 4 | `seq` | Starts at 0 for each run, +1 per packet |
| 12 | 8 | `host_time_us` | Sender's clock in µs (not checked by the board) |
| 20 | N | `payload` | Test data |
| 20+N | 4 | `crc32` | CRC-32 (same as Python's `zlib.crc32`) of bytes 0 to 20+N−1 |

The 1448-byte limit keeps every packet within one 1500-byte Ethernet frame.

### Serial output

USART3 at 921600 baud, 8N1, one line per event:

```
BOOT,hilu-udp-rx v1,port=5005,baud=921600
RAW,335,32880,7B226D6574223A32312E3030352C...
SESSION,48211
RX,0,64,9C1B3F0A,OK,48211
STAT,49000,ip=192.168.0.10,rx=158,ok=158,bad_crc=0,bad_hdr=0,bad_len=0,lost=0,late=0,log_drop=0,raw=0
```

| Line | Fields |
|---|---|
| `BOOT` | Firmware version, UDP port and baud rate. Printed once at startup. |
| `RAW` | Packet size in bytes, board uptime in ms, then the packet's bytes in hex (up to 1024) |
| `SESSION` | Board uptime in ms when a test run started (seq 0 seen) |
| `RX` | Sequence number, payload size, the CRC the board computed, status, board uptime in ms |
| `STAT` | Board uptime in ms, the board's IP, then the counters below. Printed once a second. |

`RX` status values:

- `OK`: the packet passed every check
- `CRC`: the contents changed in transit
- `HDR`: wrong version or type
- `LEN`: the size doesn't match `payload_len`

`STAT` counters:

- `rx`, `ok`, `bad_crc`, `bad_hdr`, `bad_len`: test packets received, and by result
- `lost`: test packets missing, from gaps in the sequence numbers
- `late`: test packets older than one already seen (reordered or duplicated)
- `log_drop`: packets received but not printed in time
- `raw`: non-test packets received, such as the sim's JSON

### Limits

- **The serial link is the bottleneck, not Ethernet.** 921600 baud carries about 92 KB/s.
  - Each `RAW` line is about twice the packet's size, because of the hex. A 335-byte telemetry
    packet becomes about 700 bytes, so the limit is about 130 telemetry packets per second.
  - Each test packet's `RX` line is about 35 bytes, so the limit is about 2,500 test packets per
    second.
  - Above these rates, `log_drop` goes up. The board can queue 4 raw packets and 256 test-packet
    lines to absorb short bursts.
  - To raise the limits, increase `SERIAL_LOG_BAUDRATE` in `Inc/serial_log.h` and pass the same
    value to `serial_reader.py --baud`.
- **Raw packets are not checked.** The board can't detect corruption or loss in the sim's packets,
  and `compare_logs.py` ignores them.
- **Raw packets over 1024 bytes are cut off** when printed. To change the limit, edit
  `RAW_PRINT_BYTES` in `Src/udp_receiver.c`.
- **Receive buffers:** the board has 12 Ethernet receive buffers of 1000 bytes each, and a packet
  over about 1000 bytes uses two. Bursts of large packets with no gap can run out of buffers.

### Notes

- **H743 vs H753:** ST's example targets the NUCLEO-H743ZI. The NUCLEO-H753ZI is the same board
  plus a crypto block, with the same pins and Ethernet chip, so the firmware runs unchanged.
- **Debugging:** the Makefile builds with `-Os`. For easier step-through debugging, change `-Os`
  to `-O0` in `CFLAGS` and run `make clean && make`.
- **Adding files:** every `.c` file in `Src/`, `Startup/`, `Drivers/` and `Middlewares/` is
  compiled automatically. To use another ST driver or library file, for example a HAL driver for
  SPI, copy it and any headers it needs from STM32CubeH7 into the same path here. A HAL driver must
  also be turned on in `Inc/stm32h7xx_hal_conf.h`.
- **Not committed:** build output (`obj/`, `app.elf`, `app.bin`, `app.map`) and script logs
  (`*.csv`, `*.log`) are excluded by `.gitignore`.
- **License:** the files in `Src/`, `Inc/` and `Startup/` that came from ST's example keep their ST
  copyright headers and are under ST's SLA0044 license, which allows use only with ST
  microcontrollers. They are not covered by this repo's MIT `LICENSE`. The UDP receiver and serial
  log files are part of this repo. The files in `Drivers/` and `Middlewares/` keep their own
  licenses, copied alongside them: BSD-3-Clause for ST's HAL and BSP, Apache-2.0 for CMSIS, BSD
  for LwIP and MIT for FreeRTOS.
