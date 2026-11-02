# ethernet_driver

Command-line build and flash setup for ST's **LwIP HTTP Server (Netconn, FreeRTOS)** example on the
NUCLEO-H743ZI / NUCLEO-H753ZI.

## Purpose

This folder brings up Ethernet on the Nucleo board as a first step toward using Ethernet for the
host link in the HIL system. It is a standalone demo and is **not** yet part of the HIL firmware in
the rest of this repo.

An STM32 has no separate Ethernet driver to install. The Ethernet MAC driver
(`stm32h7xx_hal_eth.c`), the LAN8742 PHY driver, the LwIP TCP/IP stack, and FreeRTOS are all
compiled into one firmware image together with the application. Flashing that image is what puts
the Ethernet driver on the board.

ST ships this example only as IDE projects (STM32CubeIDE, IAR, Keil). This folder adds a
hand-written `Makefile` so the example can be built and flashed from the terminal without an IDE.
It contains no source code of its own: every file it compiles comes from ST's `STM32CubeH7` repo.

| File          | What it is                                                              |
|---------------|-------------------------------------------------------------------------|
| `Makefile`    | Build, flash, and clean commands                                        |
| `sources.txt` | The 85 `.c` files compiled into the firmware, relative to `STM32CubeH7` |

The source list and compiler settings come from the example's `STM32CubeIDE/.project` and
`STM32CubeIDE/.cproject`.

## Requirements

1. **ARM GCC toolchain**, which provides `arm-none-eabi-gcc`:
   ```sh
   brew install --cask gcc-arm-embedded
   ```
2. **STM32CubeProgrammer CLI** (`STM32_Programmer_CLI`). The *STM32Cube for VS Code* extension
   installs it. The Makefile first looks for it on your `PATH`, then at
   `~/Library/Application Support/stm32cube/bundles/programmer/2.23.0/bin/STM32_Programmer_CLI`.
   If yours is somewhere else, pass `PROG=/path/to/STM32_Programmer_CLI` to `make flash`.
3. **ST's STM32CubeH7 repo**, cloned next to this repo (not inside it):
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
   If you keep it somewhere else, pass `R=/path/to/STM32CubeH7` to every `make` command.
   This setup was tested against STM32CubeH7 `v1.13.0-14-g8ec3113d4`.

## Build and flash

1. Connect the board to your computer by USB, using the **ST-LINK** USB port (the one at the
   opposite end of the board from the Ethernet jack).
2. From the repo root:
   ```sh
   cd ethernet_driver
   make          # build the firmware (app.elf, app.bin, app.map, obj/)
   make flash    # build if needed, then flash, verify, and reset the board
   make clean    # delete build output
   ```

`make flash` runs:

```sh
STM32_Programmer_CLI -c port=SWD mode=UR -w app.elf -v -rst
```

This connects over SWD through the on-board ST-LINK, writes `app.elf` to flash at `0x08000000`,
reads it back to verify it, and resets the board so the new firmware starts.

**Flashing overwrites whatever firmware was on the board**, including the HIL firmware. To go back
to HIL, run `make flash` (or `./flash.sh`) from the repo root.

### Alternative: drag and drop

When plugged in, the board appears as a USB drive (for example `NOD_H753ZI`). Copying `app.bin`
onto that drive also flashes it.

## Checking that Ethernet works

1. Plug an Ethernet cable from the board's RJ45 jack into a router or switch.
2. Watch the LEDs:
   - **LED2 (green)**: cable connected, link up
   - **LED3 (red)**: no cable / no link
3. Find the board's IP address:
   - DHCP is on (`LWIP_DHCP 1` in the example's `Inc/lwipopts.h`), so look for a new device in
     your router's DHCP client list.
   - With no DHCP server, the board falls back to the static address `192.168.0.10` (set in the
     example's `Inc/main.h`).
4. Open that IP in a web browser. You should see the STM32H7 home page, plus a second page
   showing live FreeRTOS task statistics.

## Notes

- **H743 vs H753:** the example targets the NUCLEO-H743ZI. The NUCLEO-H753ZI is the same board
  plus a crypto block, with the same pins and Ethernet PHY, so the firmware runs unchanged.
- **Optimization:** the Makefile builds with `-Os`, like CubeIDE's Release configuration. For
  easier step-through debugging, change `-Os` to `-O0` in `CFLAGS` and run `make clean && make`.
- **Changing code:** edit the files in the `STM32CubeH7` example (`Src/`, `Inc/`), then run
  `make flash` here. To add a new `.c` file, add its path (relative to `STM32CubeH7`) to
  `sources.txt`.
- **Build output is not committed.** `obj/`, `app.elf`, `app.bin` and `app.map` are excluded by
  the repo's `.gitignore`. Run `make` to recreate them.
