/**
  ******************************************************************************
  * @file    udp_receiver.c
  * @brief   Receives HILU packets on UDP_RX_PORT, validates them, and reports
  *          the result of each packet on the serial log.
  *
  *          Two tasks keep the slow UART out of the receive path:
  *          - UdpRx (above normal priority) receives, checks the CRC and
  *            sequence number, and posts a small record to a queue.
  *          - UdpLog (low priority) drains the queue and prints one line per
  *            record, plus a STAT line every second.
  *          If the queue is full, the record is dropped and counted as
  *          log_drop; the packet itself was still received and counted.
  *
  *          Serial output (one line each):
  *            BOOT,<fw>,port=<port>,baud=<baud>
  *            SESSION,<board_ms>                       seq 0 seen: counters reset
  *            RX,<seq>,<payload_len>,<crc32>,<status>,<board_ms>
  *            STAT,<board_ms>,ip=..,rx=..,ok=..,bad_crc=..,bad_hdr=..,bad_len=..,
  *                 lost=..,late=..,log_drop=..
  *          <status> is OK, CRC (checksum mismatch), HDR (bad magic, version
  *          or type) or LEN (size does not match payload_len). <crc32> is the
  *          CRC the board computed over what it received.
  ******************************************************************************
  */

#include "udp_receiver.h"
#include "serial_log.h"
#include "main.h"
#include "cmsis_os2.h"
#include "lwip/api.h"
#include "lwip/netif.h"
#include <stdio.h>

#define LOG_QUEUE_LEN           256U
#define STAT_PERIOD_MS          1000U

typedef enum
{
  RX_OK = 0,
  RX_BAD_CRC,
  RX_BAD_HDR,
  RX_BAD_LEN,
} RxStatus;

typedef enum
{
  REC_PACKET = 0,
  REC_SESSION,
} RecordKind;

typedef struct
{
  uint32_t seq;
  uint32_t crc;
  uint32_t board_ms;
  uint16_t payload_len;
  uint8_t  kind;
  uint8_t  status;
} RxRecord;

typedef struct
{
  uint32_t rx;
  uint32_t ok;
  uint32_t bad_crc;
  uint32_t bad_hdr;
  uint32_t bad_len;
  uint32_t lost;
  uint32_t late;
  uint32_t log_drop;
} RxStats;

static const char *const status_names[] = { "OK", "CRC", "HDR", "LEN" };

extern struct netif gnetif;

/* Written only by UdpRx. UdpLog reads it after an RTOS call, which the
   compiler treats as a barrier, and 32-bit reads are atomic on Cortex-M7. */
static RxStats stats;
static uint32_t expected_seq;
static uint8_t have_seq;

static uint8_t rx_buf[HILU_MAX_PACKET];
static uint32_t crc_table[256];
static osMessageQueueId_t log_queue;

static const osThreadAttr_t UdpRx_attributes = {
  .name = "UdpRx",
  .stack_size = 512 * 4,
  .priority = (osPriority_t) osPriorityAboveNormal,
};

static const osThreadAttr_t UdpLog_attributes = {
  .name = "UdpLog",
  .stack_size = 512 * 4,
  .priority = (osPriority_t) osPriorityLow,
};

static void udp_rx_thread(void *argument);
static void udp_log_thread(void *argument);

static void crc32_init(void)
{
  for (uint32_t i = 0; i < 256U; i++)
  {
    uint32_t c = i;
    for (uint32_t k = 0; k < 8U; k++)
    {
      c = (c & 1U) ? (0xEDB88320U ^ (c >> 1)) : (c >> 1);
    }
    crc_table[i] = c;
  }
}

/* Same as Python's zlib.crc32 */
static uint32_t crc32(const uint8_t *p, uint32_t n)
{
  uint32_t c = 0xFFFFFFFFU;
  while (n--)
  {
    c = crc_table[(c ^ *p++) & 0xFFU] ^ (c >> 8);
  }
  return c ^ 0xFFFFFFFFU;
}

static uint16_t rd16(const uint8_t *p)
{
  return (uint16_t)(p[0] | (p[1] << 8));
}

static uint32_t rd32(const uint8_t *p)
{
  return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static void post_record(const RxRecord *rec)
{
  if (osMessageQueuePut(log_queue, rec, 0U, 0U) != osOK)
  {
    stats.log_drop++;
  }
}

static void track_seq(uint32_t seq)
{
  if (!have_seq || seq == expected_seq)
  {
    expected_seq = seq + 1U;
    have_seq = 1U;
  }
  else if (seq > expected_seq)
  {
    stats.lost += seq - expected_seq;
    expected_seq = seq + 1U;
  }
  else
  {
    /* Older than expected: reordered or duplicated */
    stats.late++;
  }
}

/**
  * @brief  Validate one received datagram and post its record.
  * @param  len    bytes copied into buf
  * @param  total  full datagram size (larger than len if it did not fit)
  */
static void handle_packet(const uint8_t *buf, uint16_t len, uint16_t total)
{
  RxRecord rec = { .kind = REC_PACKET, .board_ms = osKernelGetTickCount() };

  if (total > HILU_MAX_PACKET || len < HILU_HEADER_SIZE + HILU_CRC_SIZE)
  {
    rec.status = RX_BAD_LEN;
  }
  else if (rd32(&buf[0]) != HILU_MAGIC || buf[4] != HILU_VERSION || buf[5] != HILU_TYPE_DATA)
  {
    rec.status = RX_BAD_HDR;
  }
  else
  {
    rec.payload_len = rd16(&buf[6]);
    rec.seq = rd32(&buf[8]);

    if ((uint32_t)HILU_HEADER_SIZE + rec.payload_len + HILU_CRC_SIZE != len)
    {
      rec.status = RX_BAD_LEN;
    }
    else
    {
      rec.crc = crc32(buf, len - HILU_CRC_SIZE);
      rec.status = (rec.crc == rd32(&buf[len - HILU_CRC_SIZE])) ? RX_OK : RX_BAD_CRC;
    }
  }

  /* A valid seq 0 means the sender restarted: start a new session */
  if (rec.status == RX_OK && rec.seq == 0U)
  {
    RxStats cleared = { 0 };
    stats = cleared;
    have_seq = 0U;
    RxRecord session = { .kind = REC_SESSION, .board_ms = rec.board_ms };
    post_record(&session);
  }

  stats.rx++;
  switch (rec.status)
  {
    case RX_OK:      stats.ok++; track_seq(rec.seq); break;
    case RX_BAD_CRC: stats.bad_crc++; break;
    case RX_BAD_HDR: stats.bad_hdr++; break;
    default:         stats.bad_len++; break;
  }

  post_record(&rec);
}

static void udp_rx_thread(void *argument)
{
  struct netconn *conn;
  struct netbuf *buf;

  conn = netconn_new(NETCONN_UDP);
  if (conn == NULL || netconn_bind(conn, IP_ADDR_ANY, UDP_RX_PORT) != ERR_OK)
  {
    static const char msg[] = "ERR,udp bind failed\r\n";
    serial_log_write(msg, sizeof(msg) - 1U);
    osThreadExit();
  }

  for (;;)
  {
    if (netconn_recv(conn, &buf) == ERR_OK)
    {
      /* Received frames can span several pbufs; copy into one flat buffer */
      uint16_t total = netbuf_len(buf);
      uint16_t len = netbuf_copy(buf, rx_buf, sizeof(rx_buf));
      netbuf_delete(buf);
      handle_packet(rx_buf, len, total);
    }
  }
}

static void print_record(const RxRecord *rec)
{
  char line[96];
  int n;

  if (rec->kind == REC_SESSION)
  {
    n = snprintf(line, sizeof(line), "SESSION,%lu\r\n", (unsigned long)rec->board_ms);
  }
  else
  {
    n = snprintf(line, sizeof(line), "RX,%lu,%u,%08lX,%s,%lu\r\n",
                 (unsigned long)rec->seq, (unsigned)rec->payload_len,
                 (unsigned long)rec->crc, status_names[rec->status],
                 (unsigned long)rec->board_ms);
  }
  serial_log_write(line, (uint16_t)n);
}

static void print_stats(uint32_t now)
{
  char line[192];
  const ip4_addr_t *ip = netif_ip4_addr(&gnetif);
  int n = snprintf(line, sizeof(line),
                   "STAT,%lu,ip=%u.%u.%u.%u,rx=%lu,ok=%lu,bad_crc=%lu,bad_hdr=%lu,"
                   "bad_len=%lu,lost=%lu,late=%lu,log_drop=%lu\r\n",
                   (unsigned long)now,
                   ip4_addr1(ip), ip4_addr2(ip), ip4_addr3(ip), ip4_addr4(ip),
                   (unsigned long)stats.rx, (unsigned long)stats.ok,
                   (unsigned long)stats.bad_crc, (unsigned long)stats.bad_hdr,
                   (unsigned long)stats.bad_len, (unsigned long)stats.lost,
                   (unsigned long)stats.late, (unsigned long)stats.log_drop);
  serial_log_write(line, (uint16_t)n);
}

static void udp_log_thread(void *argument)
{
  uint32_t next_stat = osKernelGetTickCount() + STAT_PERIOD_MS;
  RxRecord rec;

  for (;;)
  {
    /* Tick rate is 1 kHz, so ticks are milliseconds */
    int32_t wait = (int32_t)(next_stat - osKernelGetTickCount());
    if (osMessageQueueGet(log_queue, &rec, NULL, (wait > 0) ? (uint32_t)wait : 0U) == osOK)
    {
      print_record(&rec);
    }

    uint32_t now = osKernelGetTickCount();
    if ((int32_t)(now - next_stat) >= 0)
    {
      print_stats(now);
      next_stat += STAT_PERIOD_MS;
    }
  }
}

/**
  * @brief  Start the UDP receiver. Call after tcpip_init() and Netif_Config().
  */
void udp_receiver_init(void)
{
  char line[64];
  int n = snprintf(line, sizeof(line), "BOOT,hilu-udp-rx v%u,port=%u,baud=%lu\r\n",
                   HILU_VERSION, UDP_RX_PORT, (unsigned long)SERIAL_LOG_BAUDRATE);
  serial_log_write(line, (uint16_t)n);

  crc32_init();

  log_queue = osMessageQueueNew(LOG_QUEUE_LEN, sizeof(RxRecord), NULL);
  if (log_queue == NULL)
  {
    Error_Handler();
  }

  osThreadNew(udp_log_thread, NULL, &UdpLog_attributes);
  osThreadNew(udp_rx_thread, NULL, &UdpRx_attributes);
}
