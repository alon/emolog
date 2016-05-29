#include <assert.h>
#include <string.h>
#ifdef FOUND_HTONS_IN_CCS
#include <arpa/inet.h>
#endif

#ifdef DEBUG
#include <stdio.h>
#endif

#include "emolog.h"


// TODO: write vararg function to prepend "EMOLOG: " instead of manually inserting it every debug call
#ifdef DEBUG
#define debug printf
#else
#define debug(...)
#endif

static uint8_t s_seq = 0;

#ifndef FOUND_HTONS_IN_CCS
#define htons(x) x
#define ntohs(x) x
#endif

/**
 * TODO: store the crc table in flash instead of ram by putting it in a global?
 */

#define POLYNOMIAL 0xD8  /* 11011 followed by 0's */

typedef uint8_t crc;
static crc  crcTable[256];
#define WIDTH  (8 * sizeof(crc))
#define TOPBIT (1 << (WIDTH - 1))


uint8_t*
getCrcTable(void)
{
    return crcTable;
}


uint8_t
get_seq(void)
{
    return s_seq;
}


void
crc_init(void)
{
    crc  remainder;
    uint8_t bit;
    static uint8_t crc_inited = 0;
    int dividend;

    if (crc_inited != 0) {
        return;
    }

    /*
     * Compute the remainder of each possible dividend.
     */
    for (dividend = 0; dividend < 256; ++dividend)
    {
        /*
         * Start with the dividend followed by zeros.
         */
        remainder = dividend << (WIDTH - 8);

        /*
         * Perform modulo-2 division, a bit at a time.
         */
        for (bit = 8; bit > 0; --bit)
        {
            /*
             * Try to divide the current data bit.
             */
            if (remainder & TOPBIT)
            {
                remainder = (remainder << 1) ^ POLYNOMIAL;
            }
            else
            {
                remainder = (remainder << 1);
            }
        }

        /*
         * Store the result into the table.
         */
        crcTable[dividend] = remainder;
    }

    crc_inited = 1;

}   /* crc_init() */


crc
crc8(uint8_t const message[], int nBytes)
{
    uint8_t data;
    crc remainder = 0;
    int byte;

    crc_init();

    /*
     * Divide the message by the polynomial, a byte at a time.
     */
    for (byte = 0; byte < nBytes; ++byte)
    {
        data = message[byte] ^ (remainder >> (WIDTH - 8));
        remainder = crcTable[data] ^ (remainder << 8);
    }

    /*
     * The final remainder is the CRC.
     */
    return (remainder);

}   /* crc8() */


/**
 */
void write_header(uint8_t *dest_u8, uint8_t type, uint16_t length, const uint8_t *payload)
{
    emo_header *dest = (emo_header *)dest_u8;

    dest->start[0] = 'E';
    dest->start[1] = 'M';
    dest->seq = s_seq++;
    dest->type = type;
    dest->length = htons(length);
    dest->payload_crc = crc8(payload, length);
    dest->header_crc = crc8((uint8_t *)dest, EMO_HEADER_NO_CRC_SIZE);
}


void write_message(uint8_t *dest, uint8_t type, uint16_t length, const uint8_t *payload)
{
    write_header(dest, type, length, payload);
    memcpy(dest + sizeof(emo_header), payload, length);
}


int header_check_start(const emo_header *header)
{
    return header->start[0] == 'E' && header->start[1] == 'M';
}


uint16_t emo_encode_version(uint8_t *dest, uint8_t reply_to_seq)
{
    emo_version_payload payload = {EMOLOG_PROTOCOL_VERSION, reply_to_seq, 0};

    write_message(dest, EMO_MESSAGE_TYPE_VERSION, sizeof(payload), (const uint8_t *)&payload);
    return sizeof(emo_version);
}


uint16_t emo_encode_sampler_register_variable(uint8_t *dest, uint32_t phase_ticks,
        uint32_t period_ticks, uint32_t address, uint16_t size)
{
    emo_sampler_register_variable_payload payload = {
            .phase_ticks=phase_ticks,
            .period_ticks=period_ticks,
            .address=address,
            .size=size};

    write_message(dest, EMO_MESSAGE_TYPE_SAMPLER_REGISTER_VARIABLE, sizeof(payload), (const uint8_t *)&payload);
    return sizeof(emo_sampler_register_variable);
}

#define EMPTY_MESSAGE_ENCODER(suffix, msg_type)             \
uint16_t emo_encode_ ## suffix(uint8_t *dest)                \
{                                                                    \
    write_message(dest, msg_type, 0, NULL);                            \
    return sizeof(emo_ ## suffix);                                    \
}


EMPTY_MESSAGE_ENCODER(sampler_stop, EMO_MESSAGE_TYPE_SAMPLER_STOP)
EMPTY_MESSAGE_ENCODER(sampler_clear, EMO_MESSAGE_TYPE_SAMPLER_CLEAR)
EMPTY_MESSAGE_ENCODER(sampler_start, EMO_MESSAGE_TYPE_SAMPLER_START)

EMPTY_MESSAGE_ENCODER(ping, EMO_MESSAGE_TYPE_PING)


uint16_t emo_encode_ack(uint8_t *dest, uint8_t reply_to_seq)
{
    emo_ack_payload payload = { reply_to_seq };

    write_message(dest, EMO_MESSAGE_TYPE_ACK, sizeof(payload), (const uint8_t *)&payload);
    return sizeof(emo_ack);
}


uint16_t emo_encode_nack(uint8_t *dest, uint8_t reply_to_seq, uint16_t error)
{
    emo_nack_payload payload = { reply_to_seq, error };

    write_message(dest, EMO_MESSAGE_TYPE_NACK, sizeof(payload), (const uint8_t *)&payload);
    return sizeof(emo_nack);
}


/* sampler_sample encoding start */


static uint16_t sample_payload_length = 0;


void emo_encode_sampler_sample_start(uint8_t *dest)
{
    sample_payload_length = 0;
}


void emo_encode_sampler_sample_add_var(uint8_t *dest, const uint8_t *p, uint16_t size)
{
    memcpy(dest + sizeof(emo_sampler_sample) + sample_payload_length, p, size);
    sample_payload_length += size;
}


uint16_t emo_encode_sampler_sample_end(uint8_t *dest, uint32_t ticks)
{
    uint16_t ret;
    emo_sampler_sample_payload *payload = (emo_sampler_sample_payload *)(dest + sizeof(emo_header));

    payload->ticks = ticks;
    write_header(dest,
                 EMO_MESSAGE_TYPE_SAMPLER_SAMPLE,
                 sizeof(emo_sampler_sample_payload) + sample_payload_length,
                 dest + sizeof(emo_header));
    ret = sizeof(emo_sampler_sample) + sample_payload_length;
    sample_payload_length = 0;
    return ret;
}


/* sampler_sample encoding end */


int16_t emo_decode(const uint8_t *src, uint16_t size)
{
    const emo_header *hdr;
    const uint8_t *payload;
    crc header_crc;
    crc payload_crc;
    int16_t ret;
    uint16_t length;

    if (size < sizeof(emo_header)) {
        ret = sizeof(emo_header) - size;
        assert(ret > 0);
        return ret;
    }
    hdr = (const emo_header *)src;

    /* check header integrity, if fail skip a byte */
    header_crc = crc8(src, EMO_HEADER_NO_CRC_SIZE);
    if (header_crc != hdr->header_crc) {
        debug("EMOLOG: header crc failed %d expected, %d received.\n", header_crc, hdr->header_crc);
        return -1;
    }

    /* if we missed the header skip a byte, check again */
    if (!header_check_start(hdr)) {
        debug("EMOLOG: header check failed.\n");
        return -1;
    }

    /* convert length to local format */
    length = ntohs(hdr->length);

    /* check enough bytes for payload */
    if (length > size - sizeof(emo_header)) {
        ret = length + sizeof(emo_header) - size;
        assert(ret > 0);
        return ret;
    }
    debug("EMOLOG: about to check crc: expected len %lu >= got len %u (header len %lu)\n",
          length + sizeof(emo_header), size, sizeof(emo_header));


    /* check crc for payload */
    payload = src + sizeof(emo_header);
    payload_crc = crc8(payload, length);
    if (payload_crc != hdr->payload_crc) {
        /* we know the length is correct, since the header passed crc, so
         * skip the whole message (including payload) */
        debug("EMOLOG: payload crc failed %d expected, %d got\n", payload_crc, hdr->payload_crc);
        ret = -sizeof(emo_header) - length;
        assert(ret < 0);
        return ret;
    }

    /* home free, a valid message */
    return 0;
}

