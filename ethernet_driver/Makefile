# Path to the STM32CubeH7 repo. Override with: make R=/path/to/STM32CubeH7
R ?= ../../STM32CubeH7
ifeq ($(wildcard $(R)/Drivers),)
$(error STM32CubeH7 not found at '$(R)'. Clone it there or run: make R=/path/to/STM32CubeH7)
endif
P := $(R)/Projects/NUCLEO-H743ZI/Applications/LwIP/LwIP_HTTP_Server_Netconn_RTOS
SRCS := $(addprefix $(R)/,$(shell cat sources.txt))
ASM := $(P)/STM32CubeIDE/Application/Startup/startup_stm32h743zitx.s
LD  := $(P)/STM32CubeIDE/STM32H743ZITX_FLASH.ld
CPU := -mcpu=cortex-m7 -mfpu=fpv5-d16 -mfloat-abi=hard -mthumb
DEFS := -DSTM32H743xx -DUSE_HAL_DRIVER -DUSE_PWR_LDO_SUPPLY -DUSE_STM32H7XX_NUCLEO_144_MB1364
INCS := -I$(P)/Inc -I$(P)/Src \
  -I$(R)/Drivers/CMSIS/Include -I$(R)/Drivers/CMSIS/Device/ST/STM32H7xx/Include \
  -I$(R)/Drivers/STM32H7xx_HAL_Driver/Inc -I$(R)/Drivers/BSP/STM32H7xx_Nucleo \
  -I$(R)/Drivers/BSP/Components/Common -I$(R)/Drivers/BSP/Components -I$(R)/Drivers/BSP/Components/lan8742 \
  -I$(R)/Middlewares/Third_Party/LwIP/src/include -I$(R)/Middlewares/Third_Party/LwIP/system \
  -I$(R)/Middlewares/Third_Party/FreeRTOS/Source/portable/GCC/ARM_CM4F -I$(R)/Middlewares/Third_Party/FreeRTOS/Source \
  -I$(R)/Middlewares/Third_Party/FreeRTOS/Source/CMSIS_RTOS_V2 -I$(R)/Middlewares/Third_Party/FreeRTOS/Source/include \
  -I$(R)/Drivers/CMSIS/RTOS2/Include -I$(R)/Utilities
CFLAGS := $(CPU) $(DEFS) $(INCS) -Os -g3 -std=gnu11 -ffunction-sections -fdata-sections -Wall
OBJS := $(addprefix obj/,$(notdir $(SRCS:.c=.o))) obj/startup.o
vpath %.c $(sort $(dir $(SRCS)))
all: app.elf app.bin
obj/%.o: %.c | obj ; arm-none-eabi-gcc $(CFLAGS) -c $< -o $@
obj/startup.o: $(ASM) | obj ; arm-none-eabi-gcc $(CPU) -x assembler-with-cpp -c $< -o $@
obj: ; mkdir -p obj
app.elf: $(OBJS) ; arm-none-eabi-gcc $(CPU) -T$(LD) --specs=nano.specs -Wl,--gc-sections -Wl,-Map=app.map $^ -o $@ -lc -lm && arm-none-eabi-size $@
app.bin: app.elf ; arm-none-eabi-objcopy -O binary $< $@
# Uses STM32_Programmer_CLI from PATH if present, else the STM32Cube for VS Code install. Override with: make flash PROG=/path/to/STM32_Programmer_CLI
PROG ?= $(or $(shell command -v STM32_Programmer_CLI),$(HOME)/Library/Application Support/stm32cube/bundles/programmer/2.23.0/bin/STM32_Programmer_CLI)
flash: app.elf ; "$(PROG)" -c port=SWD mode=UR -w app.elf -v -rst
clean: ; rm -rf obj app.elf app.bin app.map
.PHONY: all flash clean
