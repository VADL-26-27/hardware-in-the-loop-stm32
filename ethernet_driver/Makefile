# App sources live in Src/ and Inc/. ST's libraries (Drivers/, Middlewares/) and the startup
# files (Startup/) are copied in from STM32CubeH7, so no separate clone is needed. Every .c file
# in those folders is compiled; only the files this firmware uses were copied.
SRCS := $(wildcard Src/*.c Startup/*.c) $(shell find Drivers Middlewares -name '*.c')
ASM := Startup/startup_stm32h743zitx.s
LD  := STM32H743ZITX_FLASH.ld
CPU := -mcpu=cortex-m7 -mfpu=fpv5-d16 -mfloat-abi=hard -mthumb
DEFS := -DSTM32H743xx -DUSE_HAL_DRIVER -DUSE_PWR_LDO_SUPPLY -DUSE_STM32H7XX_NUCLEO_144_MB1364
INCS := -IInc -ISrc \
  -IDrivers/CMSIS/Include -IDrivers/CMSIS/Device/ST/STM32H7xx/Include -IDrivers/CMSIS/RTOS2/Include \
  -IDrivers/STM32H7xx_HAL_Driver/Inc -IDrivers/BSP/STM32H7xx_Nucleo -IDrivers/BSP/Components/lan8742 \
  -IMiddlewares/Third_Party/LwIP/src/include -IMiddlewares/Third_Party/LwIP/system \
  -IMiddlewares/Third_Party/FreeRTOS/Source/include -IMiddlewares/Third_Party/FreeRTOS/Source/CMSIS_RTOS_V2 \
  -IMiddlewares/Third_Party/FreeRTOS/Source/portable/GCC/ARM_CM4F
CFLAGS := $(CPU) $(DEFS) $(INCS) -Os -g3 -std=gnu11 -ffunction-sections -fdata-sections -Wall
OBJS := $(addprefix obj/,$(notdir $(SRCS:.c=.o))) obj/startup.o
vpath %.c $(sort $(dir $(SRCS)))
all: app.elf app.bin
obj/%.o: %.c $(wildcard Inc/*.h) | obj ; arm-none-eabi-gcc $(CFLAGS) -c $< -o $@
obj/startup.o: $(ASM) | obj ; arm-none-eabi-gcc $(CPU) -x assembler-with-cpp -c $< -o $@
obj: ; mkdir -p obj
app.elf: $(OBJS) $(LD) ; arm-none-eabi-gcc $(CPU) -T$(LD) --specs=nano.specs -Wl,--gc-sections -Wl,-Map=app.map $(OBJS) -o $@ -lc -lm && arm-none-eabi-size $@
app.bin: app.elf ; arm-none-eabi-objcopy -O binary $< $@
# Uses STM32_Programmer_CLI from PATH if present, else the STM32Cube for VS Code install. Override with: make flash PROG=/path/to/STM32_Programmer_CLI
PROG ?= $(or $(shell command -v STM32_Programmer_CLI),$(HOME)/Library/Application Support/stm32cube/bundles/programmer/2.23.0/bin/STM32_Programmer_CLI)
flash: app.elf ; "$(PROG)" -c port=SWD mode=UR -w app.elf -v -rst
clean: ; rm -rf obj app.elf app.bin app.map
.PHONY: all flash clean
