/* vim: set tabstop=4 softtabstop=4 shiftwidth=4 expandtab : */

/*
 * emolog_protocol.h
 *
 * Main include for Emolog Protocol.
 *
 *  Created on: Mar 17, 2016
 *      Author: alon
 *
 *
 */

#ifndef EMOLOG_H_
#define EMOLOG_H_

#ifdef __cplusplus
extern "C" {
#endif

#include <stdint.h>


// Version of the library - major micro and minor
#define EMOLOG_LIB_VERSION "0.0.1"


// protocol version - ever increasing
#define EMOLOG_PROTOCOL_VERSION 1


#pragma pack(1) // mingw version-sheker doesn't honor __attribute__((packed))

typedef struct emo_header {
    uint8_t  start[2];    // "EM"
    uint8_t  type;        // message type, one of EMO_MESSAGE_TYPE
    uint16_t length;      // number of bytes in payload (not including header)
    uint8_t  seq;         // used to tell ack/nacks targets
    uint8_t  payload_crc; // CRC8 of the payload only
    uint8_t  header_crc;  // CRC8 of the header not including the header_crc byte
} __attribute__((packed)) emo_header;


#define EMO_HEADER_NO_CRC_SIZE (sizeof(emo_header) - sizeof(((emo_header*)0)->header_crc))


typedef enum {
#include "emo_message_t.h" // this is shared with python, must stay simple
} emo_message_t;


#define MAKE_STRUCT(payload_name)        \
typedef struct emo_ ## payload_name {    \
    emo_header h;                   \
    emo_ ## payload_name ## _payload p;             \
} __attribute__((packed)) emo_ ## payload_name;


/** version */


typedef struct emo_version_payload {
    uint16_t   protocol_version;
    uint8_t    reply_to_seq; // -1 if initiating, seq of replied to message if responding
    uint8_t    reserved;
} __attribute__((packed)) emo_version_payload;

MAKE_STRUCT(version)


/** ping */


typedef struct emo_ping_payload {
} __attribute__((packed)) emo_ping_payload;

MAKE_STRUCT(ping)


/*
 * ack used for both success and error result reporting. every host message
 * must get a response from the client:
 *
 * version / version
 * other   / ack
 */

typedef struct emo_ack_payload {
    uint16_t error;
    uint8_t  reply_to_seq;
} __attribute__((packed)) emo_ack_payload;

MAKE_STRUCT(ack);


/** sampler messages  */


/** register_variable_sampler */

typedef struct emo_sampler_register_variable_payload {
    uint32_t phase_ticks;
    uint32_t period_ticks;
    uint32_t address;
    uint16_t size;
    uint16_t reserved;
} __attribute__((packed)) emo_sampler_register_variable_payload;

MAKE_STRUCT(sampler_register_variable)


typedef struct emo_sampler_clear_payload {
} __attribute__((packed)) emo_sampler_clear_payload;

MAKE_STRUCT(sampler_clear)


typedef struct emo_sampler_start_payload {
} __attribute__((packed)) emo_sampler_start_payload;

MAKE_STRUCT(sampler_start)


typedef struct emo_sampler_stop_payload {
} __attribute__((packed)) emo_sampler_stop_payload;

MAKE_STRUCT(sampler_stop)


typedef struct emo_sampler_sample_payload {
    uint32_t ticks;
    // here come the variables themselves.
    // host sees the ticks, calculates which variables are contained (see XXX)
    // and then can parse the variables (length is known from header as well as additional redundant information)
} __attribute__((packed)) emo_sampler_sample_payload;

MAKE_STRUCT(sampler_sample)

#pragma pack()



/*
 * All emo_encode functions return the number of encoded bytes
 *
 * reply_to_seq: -1 if not replying, otherwise the sequence number
 * of the version message being replied to.
 */
uint16_t emo_encode_version(uint8_t *dest, uint8_t reply_to_seq);


/*
 * The simplest message that the sending of requires an ack.
 */
uint16_t emo_encode_ping(uint8_t *dest);


/*
 * ack.
 */
uint16_t emo_encode_ack(uint8_t *dest, uint8_t reply_to_seq, uint16_t error);


typedef enum {
    EMO_ERROR_NONE = 0,
    EMO_ERROR_GENERAL = 1,
    EMO_ERROR_UNEXPECTED_MESSAGE = 2,
    EMO_ERROR_BAD_HEADER_CRC = 3,
    EMO_ERROR_BAD_PAYLOAD_CRC = 4,
    EMO_ERROR_SAMPLER_REGISTER_VARIABLE__SIZE_EXCEEDED = 5,
    EMO_ERROR_SAMPLER_TABLE_EMPTY = 6,
} emo_error_t;


/**
 *
 */
uint16_t emo_encode_sampler_register_variable(uint8_t *dest, uint32_t phase_ticks,
        uint32_t period_ticks, uint32_t address, uint16_t size);

/*
 * All three (clear, start, stop) are sent by the Host, and the Embedded must ack
 */
uint16_t emo_encode_sampler_clear(uint8_t *dest);
uint16_t emo_encode_sampler_start(uint8_t *dest);
uint16_t emo_encode_sampler_stop(uint8_t *dest);

/*
 * encoding a sample uses three separate function calls:
 * start - initialize some state
 * add - add a variable to the message
 * end - compute crcs, ready for copying out
 *
 * Sent by the Embedded, Host does not reply
 */
void emo_encode_sampler_sample_start(uint8_t *dest);
void emo_encode_sampler_sample_add_var(uint8_t *dest, const uint8_t *p, uint16_t size);
uint16_t emo_encode_sampler_sample_end(uint8_t *dest, uint32_t ticks);


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
 *  if size == 0 will return sizeof(emo_header)
 *
 *
 * Example usage:
 *
 * uint8_t buf[1024]; // read data from serial port into this
 * while ((missing = emo_decode(buf, size)) != 0) {
 *   if (missing < 0) {
 *      memcpy(buf, buf + missing, size);
 *   } else {
 *      read_serial_data(buf + size, missing);
 *   }
 * }
 * emo_header *header = (emo_header *)buf;
 * switch (emo_header->type) {
 * case EMO_MESSAGE_TYPE_VERSION:
 *   handle_version(emo_header)
 *   break;
 *  ...
 * }
 */
int16_t emo_decode(const uint8_t *src, uint16_t size);

void crc_init(void);


#ifdef __cplusplus
}
#endif

#endif /* EMOLOG_H_ */
