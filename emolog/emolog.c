#include <assert.h>
#include <string.h>

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

static uint16_t s_seq = 0;

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


uint16_t
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
 * seq: if -1 ignored, otherwise used instead of the static s_seq, which is also not incremented.
 */
void write_header(uint8_t *dest_u8, uint8_t type, uint16_t length, const uint8_t *payload, int32_t seq)
{
    emo_header *dest = (emo_header *)dest_u8;

    dest->start[0] = 'C';
    dest->start[1] = 'M';
    dest->start[2] = 'P';
    dest->seq = seq >= 0 ? seq : s_seq++;
    dest->type = type;
    dest->length = length;
    dest->payload_crc = crc8(payload, length);
    dest->header_crc = crc8((uint8_t *)dest, WPP_HEADER_NO_CRC_SIZE);
}


void write_message(uint8_t *dest, uint8_t type, uint16_t length, const uint8_t *payload, int32_t seq)
{
    write_header(dest, type, length, payload, seq);
    memcpy(dest + sizeof(emo_header), payload, length);
}


int header_check_start(const emo_header *header)
{
    return header->start[0] == 'C' && header->start[1] == 'M' &&
           header->start[2] == 'P';
}


uint16_t emo_encode_version(uint8_t *dest, int32_t reply_to_seq)
{
    emo_version_payload payload = {EMOLOG_PROTOCOL_VERSION, 0};

    write_message(dest, WPP_MESSAGE_TYPE_VERSION, sizeof(payload), (const uint8_t *)&payload, reply_to_seq);
    return sizeof(emo_version);
}


int16_t emo_decode(const uint8_t *src, uint16_t size)
{
    const emo_header *hdr;
    const uint8_t *payload;
    crc header_crc;
    crc payload_crc;
    int16_t ret;

    if (size < sizeof(emo_header)) {
        ret = sizeof(emo_header) - size;
        assert(ret > 0);
        return ret;
    }
    hdr = (const emo_header *)src;

    /* check header integrity, if fail skip a byte */
    header_crc = crc8(src, WPP_HEADER_NO_CRC_SIZE);
    if (header_crc != hdr->header_crc) {
        debug("EMOLOG: header crc failed %d expected, %d received.\n", header_crc, hdr->header_crc);
        return -1;
    }

    /* if we missed the header skip a byte, check again */
    if (!header_check_start(hdr)) {
        debug("EMOLOG: header check failed.\n");
        return -1;
    }

    /* check enough bytes for payload */
    if (hdr->length > size - sizeof(emo_header)) {
        ret = hdr->length + sizeof(emo_header) - size;
        assert(ret > 0);
        return ret;
    }
    debug("EMOLOG: about to check crc: expected len %lu >= got len %u (header len %lu)\n",
          hdr->length + sizeof(emo_header), size, sizeof(emo_header));


    /* check crc for payload */
    payload = src + sizeof(emo_header);
    payload_crc = crc8(payload, hdr->length);
    if (payload_crc != hdr->payload_crc) {
        /* we know the length is correct, since the header passed crc, so
         * skip the whole message (including payload) */
        debug("EMOLOG: payload crc failed %d expected, %d got\n", payload_crc, hdr->payload_crc);
        ret = -sizeof(emo_header) - hdr->length;
        assert(ret < 0);
        return ret;
    }

    /* home free, a valid message */
    return 0;
}

