/*
 * emolog_embedded.c
 *
 *  Created on: 12 бреб„ 2016
 *      Author: Guy Ovadia
 */
#include <stdint.h>
#include <stdbool.h>
#include <assert.h>

#include "emolog_embedded.h"
#include "emolog_comm.h"
#include "emolog_sampler.h"
#include "emolog_protocol.h"
#include "emolog_debug.h"


void emolog_handle_message(emo_header* header, uint32_t ticks);
void queue_ack(uint8_t reply_to_seq, emo_error_t error);


// TODO replace this with a file generated in a pre-build step:
volatile uint64_t __attribute__((used)) build_timestamp = 12345678;
#ifdef __TI_ARM__
#pragma RETAIN(build_timestamp)
#endif

void emolog_init(void)
{
    debug_printf("emolog_init\n");
    volatile uint64_t __attribute__((unused)) dummy = build_timestamp;

    crc_init();
	comm_setup();
}


void emolog_run_step(uint32_t ticks)
{
	emo_header *header;

	sampler_sample(ticks);
	if ((header = comm_peek_message()) != NULL) {
		emolog_handle_message(header, ticks);
		comm_consume_message();
	}
}


void emolog_handle_message(emo_header* header, uint32_t ticks)
{
	uint8_t buf_out[32];
	uint16_t encoded_len;
	emo_error_t error = EMO_ERROR_NONE;

	switch (header->type) {
	case EMO_MESSAGE_TYPE_VERSION: {
		debug_printf("got Version message.\n");
		encoded_len = emo_encode_version(buf_out, header->seq);
		comm_queue_message(buf_out, encoded_len);
		debug_printf("sending Version message.\n");
		break;
	}
	case EMO_MESSAGE_TYPE_PING: {
		debug_printf("got Ping message.\n");
		// TODO
		break;
	}
	case EMO_MESSAGE_TYPE_SAMPLER_REGISTER_VARIABLE: {
		debug_printf("got Register Variable message.\n");
		emo_sampler_register_variable *m = (emo_sampler_register_variable *)header;
		emo_sampler_register_variable_payload *p = &m->p;
		error = sampler_register_variable(p->phase_ticks, p->period_ticks, p->address, p->size, header->seq);
		break;
	}
	case EMO_MESSAGE_TYPE_SAMPLER_CLEAR: {
		debug_printf("got Sampler Clear message.\n");
		sampler_clear();
		break;
	}
	case EMO_MESSAGE_TYPE_SAMPLER_START: {
		debug_printf("got Sampler Start message.\n");
		sampler_start(ticks);
		break;
	}
	case EMO_MESSAGE_TYPE_SAMPLER_STOP: {
		debug_printf("got Sampler Stop message.\n");
		sampler_stop();
		break;
	}
	default: {
		error = handle_app_specific_message(header);
	}
	}

	// every message needs an ACK except VERSION message, which gets a VERSION message in return instead of a regular ACK
	if (header->type != EMO_MESSAGE_TYPE_VERSION) {
		queue_ack(header->seq, error);
	}
}


void queue_ack(uint8_t reply_to_seq, emo_error_t error)
{
    uint8_t buf_out[32];
    uint16_t encoded_len;

	debug_printf("sending ACK message.\n");
    encoded_len = emo_encode_ack(buf_out, reply_to_seq, error);
    assert(encoded_len <= sizeof(buf_out));
    comm_queue_message(buf_out, encoded_len);
}


