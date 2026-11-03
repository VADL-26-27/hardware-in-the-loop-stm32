# ethernet_driver

Ethernet bring-up firmware for the NUCLEO-H753ZI (or NUCLEO-H743ZI), with matching scripts to
send data to the board over UDP and check that it arrives intact.

## Purpose

This folder is a first step toward using Ethernet, not USART, for the host link in the HIL
system. It is a standalone test and is **not** yet part of the HIL firmware in the rest of this
repo.

The firmware is ST's **LwIP HTTP Server (Netconn, FreeRTOS)** example, plus a UDP receiver:

```
[Windows PC] --Ethernet, UDP--> [STM32] --USB, ST-LINK serial--> [Mac]
 udp_sender.py                  checks every packet       serial_reader.py
 writes sent.csv                and reports it            writes received.log
                                        compare_logs.py sent.csv received.log
```

- The **Windows PC** sends numbered packets, each with a CRC-32, and logs what it sent.
- The **board** receives each packet, checks its header and CRC, and prints one line per packet
  over USART3. The on-board ST-LINK forwards USART3 to the Mac as a USB serial port.
- The **Mac** records those lines. `compare_logs.py` then matches them against the PC's log, to
  show that every packet arrived, in order, with identical contents.

There is no separate Ethernet driver to install on an STM32. The Ethernet MAC driver, the
LAN8742 PHY driver, the LwIP TCP/IP stack and FreeRTOS are all compiled into one firmware image
together with the application. Flashing that image is what puts the Ethernet driver on the board.

## Folder layout

| Path          | What it is                                                                    |
|---------------|-------------------------------------------------------------------------------|
| `Makefile`    | Build, flash and clean commands                                               |
| `Src/`, `Inc/`| Application code: ST's example files plus the UDP receiver (see below)        |
| `sources.txt` | ST library files compiled from `STM32CubeH7` (HAL, BSP, LwIP, FreeRTOS)       |
| `scripts/`    | Python scripts for the PC and the Mac                                         |

Files added to ST's example:

| File                                        | What it does                                      |
|---------------------------------------------|---------------------------------------------------|
| `Src/udp_receiver.c`, `Inc/udp_receiver.h`  | Receives and checks packets on UDP port 5005; defines the packet format |
| `Src/serial_log.c`, `Inc/serial_log.h`      | USART3 output at 921600 baud; also routes `printf` there |

Files changed from ST's example:

| File                   | Change                                                                 |
|------------------------|------------------------------------------------------------------------|
| `Src/main.c`           | Starts the serial log and the UDP receiver                             |
| `Inc/lwipopts.h`       | `LWIP_DHCP` set to `0`, so the board uses its static IP immediately    |
| `Inc/FreeRTOSConfig.h` | FreeRTOS heap raised from 25 KB to 48 KB for the two new tasks         |

## Requirements

On the Mac (to build and flash):

1. **ARM GCC toolchain**, which provides `arm-none-eabi-gcc`:
   ```sh
   brew install --cask gcc-arm-embedded
   ```
2. **STM32CubeProgrammer CLI** (`STM32_Programmer_CLI`). The *STM32Cube for VS Code* extension
   installs it. The Makefile first looks for it on your `PATH`, then at
   `~/Library/Application Support/stm32cube/bundles/programmer/2.23.0/bin/STM32_Programmer_CLI`.
   If yours is somewhere else, pass `PROG=/path/to/STM32_Programmer_CLI` to `make flash`.
3. **ST's STM32CubeH7 repo**, cloned next to this repo (not inside it), for the HAL, BSP, LwIP
   and FreeRTOS sources:
   ```sh
   cd ..   # the folder that contains hardware-in-the-loop-stm32
   git clone --recursive https://github.com/STMicroelectronics/STM32CubeH7.git
   ```
   The expected layout is:
   ```
   parent/
   ├── STM32CubeH7/
   └── hardware-in-the-loop-stm32/
       └── ethernet_driver/
   ```
   If you keep it somewhere else, pass `R=/path/to/STM32CubeH7` to every `make` command. This
   setup was tested against STM32CubeH7 `v1.13.0-14-g8ec3113d4`.
4. **Python 3** with pyserial, for `serial_reader.py`:
   ```sh
   python3 -m pip install pyserial
   ```

On the Windows PC: **Python 3** only. The sender and the connection check use only the standard
library. Copy the whole `scripts/` folder over, since every script imports `protocol.py`.

## Build and flash

1. Connect the board to the Mac by USB, using the **ST-LINK** USB port (the one at the opposite
   end of the board from the Ethernet jack).
2. From the repo root:
   ```sh
   cd ethernet_driver
   make          # build the firmware (app.elf, app.bin, app.map, obj/)
   make flash    # build if needed, then flash, verify, and reset the board
   make clean    # delete build output
   ```

`make flash` runs `STM32_Programmer_CLI -c port=SWD mode=UR -w app.elf -v -rst`. That connects
through the on-board ST-LINK, writes `app.elf` to flash at `0x08000000`, reads it back to verify
it, and resets the board so the new firmware starts.

**Flashing overwrites whatever firmware was on the board**, including the HIL firmware. To go back
to HIL, run `make flash` (or `./flash.sh`) from the repo root.

Alternatively, copy `app.bin` onto the USB drive the board shows up as (for example
`NOD_H753ZI`).

## Network setup

The board uses a static IP: **192.168.0.10**, mask 255.255.255.0, set in `Inc/main.h`.

1. Connect the board's RJ45 jack directly to the Windows PC's Ethernet port.
2. Give the Windows Ethernet adapter a static IP of **192.168.0.11**, mask **255.255.255.0**, with
   no gateway and no DNS (Settings → Network → Ethernet → IP assignment → Manual).
3. Check the board's LEDs: **LED2 (green)** on means the link is up; **LED3 (red)** means no link.

If the PC's Wi-Fi is also on a `192.168.0.x` network, Windows may send traffic out the wrong
adapter. Turn Wi-Fi off, or pass `--bind 192.168.0.11` to `udp_sender.py`.

Windows Defender Firewall needs no changes. Data only flows from the PC to the board, and Windows
allows outbound UDP and ping replies by default.

## Step 1: check the connection

On the Windows PC:

```sh
python check_connection.py
```

This pings the board and checks that the replies have **TTL=255**. lwIP always uses 255, so a TTL
of 64 or 128 means a different device answered. It then fetches ST's demo web page from port 80.
You can also open `http://192.168.0.10/` in a browser.

## Step 2: send data and check it

1. **On the Mac**, start the reader first, so it catches the start of the run:
   ```sh
   cd ethernet_driver/scripts
   python3 serial_reader.py
   ```
   It prints a `STAT` line every second, plus any rejected packets. Add `--verbose` to see every
   packet. If it can't find the port, pass `--port /dev/tty.usbmodemXXXX`
   (`ls /dev/tty.usbmodem*` lists them).

2. **On the Windows PC**, send packets:
   ```sh
   python udp_sender.py --rate 200 --size 64 --duration 10
   ```

   | Option       | Default        | Meaning                                                |
   |--------------|----------------|--------------------------------------------------------|
   | `--ip`       | `192.168.0.10` | Board IP                                               |
   | `--port`     | `5005`         | Board UDP port                                         |
   | `--rate`     | `200`          | Packets per second                                     |
   | `--size`     | `64`           | Payload bytes, 0 to 1448                               |
   | `--payload`  | `counter`      | `counter`, `random` or `zeros`                         |
   | `--count`    | `0`            | Stop after this many packets (0 = no limit)            |
   | `--duration` | `0`            | Stop after this many seconds (0 = no limit)            |
   | `--bind`     | none           | Local IP to send from, e.g. `192.168.0.11`             |
   | `--log`      | `sent.csv`     | Log of every packet sent                               |

3. When the sender finishes, wait for one more `STAT` line on the Mac, then press Ctrl-C.

4. Copy `sent.csv` from the PC to the Mac (or `received.log` the other way) and compare:
   ```sh
   python3 compare_logs.py sent.csv received.log
   ```
   It lists missing, corrupted, duplicated and out-of-order packets, and ends with `PASS` or
   `FAIL`. The exit code is 0 only on `PASS`.

Each sender run starts again at sequence number 0, and the board resets its counters when it
sees seq 0. If `received.log` covers several runs, `compare_logs.py` uses the last one.

## Packet format

UDP to port 5005, all fields little-endian. The format is defined in `Inc/udp_receiver.h` and
`scripts/protocol.py`, and the two must match.

| Offset | Size | Field          | Value                                             |
|--------|------|----------------|---------------------------------------------------|
| 0      | 4    | `magic`        | `HILU` (ASCII)                                    |
| 4      | 1    | `version`      | 1                                                 |
| 5      | 1    | `msg_type`     | 1 (data)                                          |
| 6      | 2    | `payload_len`  | N, at most 1448                                   |
| 8      | 4    | `seq`          | Starts at 0 for each run, +1 per packet           |
| 12     | 8    | `host_time_us` | Sender's clock, in µs (the board doesn't check it) |
| 20     | N    | `payload`      | Your data                                         |
| 20+N   | 4    | `crc32`        | CRC-32 (same as Python's `zlib.crc32`) of bytes 0 to 20+N−1 |

The 1448-byte limit keeps every packet within one 1500-byte Ethernet frame. The payload is
currently test data. To send real HIL data, put it in `payload` and parse it in
`handle_packet()` in `Src/udp_receiver.c`.

## Serial output

USART3 at 921600 baud, 8N1, one line per event:

```
BOOT,hilu-udp-rx v1,port=5005,baud=921600
SESSION,48211
RX,0,64,9C1B3F0A,OK,48211
RX,1,64,0E5D21C4,OK,48216
STAT,49000,ip=192.168.0.10,rx=158,ok=158,bad_crc=0,bad_hdr=0,bad_len=0,lost=0,late=0,log_drop=0
```

- **`RX` fields:** `seq`, `payload_len`, the CRC the board computed, the status, and the board's
  uptime in ms.
- **Status values:**
  - `OK`: the packet passed every check
  - `CRC`: the contents changed in transit
  - `HDR`: wrong magic, version or type
  - `LEN`: the size doesn't match `payload_len`
- **`STAT` counters:**
  - `lost`: gaps in the sequence numbers
  - `late`: a packet arrived older than one already seen (reordered or duplicated)
  - `log_drop`: packets the board received but didn't have time to print

## Limits

- **The serial link is the bottleneck, not Ethernet.** At 921600 baud the board can print about
  2,500 `RX` lines per second. Up to that rate, every packet is logged. Above it, or in long
  bursts, `log_drop` goes up and those packets show as missing in `compare_logs.py`, even though
  the board received them. The board queues up to 256 lines to absorb short bursts.
- To raise the limit, increase `SERIAL_LOG_BAUDRATE` in `Inc/serial_log.h` and pass the same
  value to `serial_reader.py --baud`.
- **Receive buffers:** the board has 12 receive buffers of 1000 bytes each, and a packet over
  about 1000 bytes uses two. Bursts of large packets with no gap can run out of buffers, which
  appear as `lost`.

## Notes

- **H743 vs H753:** ST's example targets the NUCLEO-H743ZI. The NUCLEO-H753ZI is the same board
  plus a crypto block, with the same pins and Ethernet PHY, so the firmware runs unchanged.
- **Debugging:** the Makefile builds with `-Os`. For easier step-through debugging, change `-Os`
  to `-O0` in `CFLAGS` and run `make clean && make`.
- **Adding files:** new `.c` files in `Src/` are picked up automatically. To compile another
  STM32CubeH7 library file, add its path (relative to `STM32CubeH7`) to `sources.txt`.
- **Not committed:** build output (`obj/`, `app.elf`, `app.bin`, `app.map`) and script logs
  (`*.csv`, `*.log`) are excluded by `.gitignore`.
- **License:** the files in `Src/` and `Inc/` that came from ST's example keep their ST copyright
  headers. They are under ST's SLA0044 license, which allows use only with ST microcontrollers.
  They are not covered by this repo's MIT `LICENSE`. The UDP receiver and serial log files are
  part of this repo.
