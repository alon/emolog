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
#include "emolog.h"


void emolog_handle_message(emo_header* header);
void queue_ack(uint8_t reply_to_seq, emo_error_t error);


void emolog_init(void)
{
	comm_setup();
}


void emolog_run_step(void)
{
	emo_header *header;

	if ((header = comm_peek_message()) != NULL) {
		emolog_handle_message(header);
		comm_consume_message();
	}

	sampler_sample();
}


void emolog_handle_message(emo_header* header)
{
	uint8_t buf_out[32];
	uint16_t encoded_len;
	emo_error_t error = EMO_ERROR_NONE;

	switch (header->type) {
	case EMO_MESSAGE_TYPE_VERSION: {
		encoded_len = emo_encode_version(buf_out, header->seq);
		comm_queue_message(buf_out, encoded_len);
		break;
	}
	case EMO_MESSAGE_TYPE_PING: {
		// TODO
		break;
	}
	case EMO_MESSAGE_TYPE_SAMPLER_REGISTER_VARIABLE: {
		emo_sampler_register_variable *m = (emo_sampler_register_variable *)header;
		emo_sampler_register_variable_payload *p = &m->p;
		error = sampler_register_variable(p->phase_ticks, p->period_ticks, p->address, p->size, header->seq);
		break;
	}
	case EMO_MESSAGE_TYPE_SAMPLER_CLEAR: {
		sampler_clear();
		break;
	}
	case EMO_MESSAGE_TYPE_SAMPLER_START: {
		sampler_start();
		break;
	}
	case EMO_MESSAGE_TYPE_SAMPLER_STOP: {
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

    encoded_len = emo_encode_ack(buf_out, reply_to_seq, error);
    assert(encoded_len <= sizeof(buf_out));
    comm_queue_message(buf_out, encoded_len);
}


