/**
  ******************************************************************************
  * @file    serial_log.h
  * @brief   Text output on USART3, bridged to the ST-LINK virtual COM port.
  ******************************************************************************
  */

#ifndef __SERIAL_LOG_H
#define __SERIAL_LOG_H

#ifdef __cplusplus
 extern "C" {
#endif

#include <stdint.h>

/* Must match the baud rate used by scripts/serial_reader.py */
#define SERIAL_LOG_BAUDRATE     921600U
#define SERIAL_LOG_TIMEOUT_MS   100U

void serial_log_init(void);
void serial_log_write(const char *buf, uint16_t len);

#ifdef __cplusplus
}
#endif

#endif /* __SERIAL_LOG_H */
