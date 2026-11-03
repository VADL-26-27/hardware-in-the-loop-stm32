/**
  ******************************************************************************
  * @file    serial_log.c
  * @brief   Text output on USART3 (PD8 TX / PD9 RX), which the on-board
  *          ST-LINK bridges to a USB virtual COM port on the host.
  *          Also routes printf() to the same UART via __io_putchar().
  ******************************************************************************
  */

#include "serial_log.h"
#include "main.h"

/**
  * @brief  Configure USART3 as 8N1 at SERIAL_LOG_BAUDRATE.
  *         Call after HAL_Init() and SystemClock_Config().
  */
void serial_log_init(void)
{
  COM_InitTypeDef com_init = {
    .BaudRate   = SERIAL_LOG_BAUDRATE,
    .WordLength = COM_WORDLENGTH_8B,
    .StopBits   = COM_STOPBITS_1,
    .Parity     = COM_PARITY_NONE,
    .HwFlowCtl  = COM_HWCONTROL_NONE,
  };

  if (BSP_COM_Init(COM1, &com_init) != BSP_ERROR_NONE)
  {
    Error_Handler();
  }
}

/**
  * @brief  Blocking write of len bytes. Only one task should call this at a
  *         time, otherwise output from different tasks can interleave.
  */
void serial_log_write(const char *buf, uint16_t len)
{
  HAL_UART_Transmit(&hcom_uart[COM1], (uint8_t *)buf, len, SERIAL_LOG_TIMEOUT_MS);
}

/* Overrides the weak declaration in syscalls.c so printf() goes to USART3 */
int __io_putchar(int ch)
{
  uint8_t c = (uint8_t)ch;
  HAL_UART_Transmit(&hcom_uart[COM1], &c, 1, SERIAL_LOG_TIMEOUT_MS);
  return ch;
}
