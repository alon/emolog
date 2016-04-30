/* vim: set tabstop=4 softtabstop=4 shiftwidth=4 expandtab : */

/*
 * cmwpp.h
 *
 * Main include for Comet-ME Water Pump Protocol.
 *
 *  Created on: Mar 17, 2016
 *      Author: alon
 *
 *
 */

#ifndef CMWPP_H_
#define CMWPP_H_


#include <stdint.h>


// Version of the library - major micro and minor
#define CMWPP_LIB_VERSION "0.0.1"


// protocol version - ever increasing
#define CMWPP_PROTOCOL_VERSION 1


typedef struct wpp_header {
    uint8_t  start[3];    // "CMP"
    uint8_t  type;        // message type, one of WPP_MESSAGE_TYPE
    uint16_t length;      // number of bytes in payload (not including header)
    uint16_t seq;         // used to tell ack/nacks targets
    uint8_t  payload_crc; // CRC8 of the payload only
    uint8_t  header_crc;  // CRC8 of the header not including the header_crc byte
} __attribute__((packed)) wpp_header;


#define WPP_HEADER_NO_CRC_SIZE (sizeof(wpp_header) - sizeof(((wpp_header*)0)->header_crc))


typedef enum {
    WPP_MESSAGE_TYPE_VERSION = 1,
} WPP_MESSAGE_TYPE;


typedef struct wpp_version_payload {
    uint16_t   protocol_version;
    uint16_t   reserved;
} __attribute__((packed)) wpp_version_payload;


typedef struct wpp_version {
    wpp_header h;
    wpp_version_payload p;
} __attribute__((packed)) wpp_version;


/*
 * All wpp_encode functions return the number of encoded bytes
 *
 * reply_to_seq: -1 if not replying, otherwise the sequence number
 * of the version message being replied.
 */
uint16_t wpp_encode_version(uint8_t *dest, int32_t reply_to_seq);


/**
 * parameters:
 *  src - buffer to decode message from
 *  size - number of valid bytes in src
 * return:
 *
 *   0 if src contains a valid message.
 *
 * > 0 : number of bytes to append to src before trying again. could be the
 *       number for a valid message or the number for a valid header after
 *       which a new number will be returned.
 *
 * < 0 : number of bytes to skip. used when there are errors in the buffer.
 *       for instance, bad start token, or wrong checksum.
 *       will always be smaller or equal to size.
 *
 *  if size == 0 will return sizeof(wpp_header)
 *
 *
 * Example usage:
 *
 * uint8_t buf[1024]; // read data from serial port into this
 * while ((missing = wpp_decode(buf, size)) != 0) {
 *   if (missing < 0) {
 *      memcpy(buf, buf + missing, size);
 *   } else {
 *      read_serial_data(buf + size, missing);
 *   }
 * }
 * wpp_header *header = (wpp_header *)buf;
 * switch (wpp_header->type) {
 * case WPP_MESSAGE_TYPE_VERSION:
 *   handle_version(wpp_header)
 *   break;
 *  ...
 * }
 */
int16_t wpp_decode(const uint8_t *src, uint16_t size);


#endif /* CMWPP_H_ */
