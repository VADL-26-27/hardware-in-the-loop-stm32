/**
  ******************************************************************************
  * @file    udp_receiver.h
  * @brief   Receives HILU packets over UDP and reports each one on the serial
  *          log. Packet layout must match scripts/protocol.py.
  ******************************************************************************
  */

#ifndef __UDP_RECEIVER_H
#define __UDP_RECEIVER_H

#ifdef __cplusplus
 extern "C" {
#endif

#include <stdint.h>

#define UDP_RX_PORT             5005U

/* HILU packet, all fields little-endian:
 *   offset  size  field
 *   0       4     magic         'H' 'I' 'L' 'U'
 *   4       1     version       HILU_VERSION
 *   5       1     msg_type      HILU_TYPE_DATA
 *   6       2     payload_len   N
 *   8       4     seq           starts at 0 for each sender run
 *   12      8     host_time_us  sender timestamp (not checked by the board)
 *   20      N     payload
 *   20+N    4     crc32         IEEE CRC-32 of bytes 0 .. 20+N-1
 */
#define HILU_MAGIC              0x554C4948U   /* "HILU" read as little-endian */
#define HILU_VERSION            1U
#define HILU_TYPE_DATA          1U
#define HILU_HEADER_SIZE        20U
#define HILU_CRC_SIZE           4U
/* 1500 MTU - 20 IP - 8 UDP: largest packet that is never IP-fragmented */
#define HILU_MAX_PACKET         1472U
#define HILU_MAX_PAYLOAD        (HILU_MAX_PACKET - HILU_HEADER_SIZE - HILU_CRC_SIZE)

void udp_receiver_init(void);

#ifdef __cplusplus
}
#endif

#endif /* __UDP_RECEIVER_H */
