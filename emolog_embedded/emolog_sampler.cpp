/*
 * emolog_sampler.c
 *
 *  Created on: 22 במאי 2016
 *      Author: Guy Ovadia
 */


#include "emolog_sampler.h"

#include <stdbool.h>
#include <stdint.h>

#include "emolog_protocol.h"

#include "emolog_comm.h"
#include "emolog_debug.h"


bool sampler_running = false;


#define MAX_VARS 128


typedef struct row_t {
	uint32_t phase_ticks;
	uint32_t period_ticks;
	uint32_t address;
	uint16_t size;
} row_t;


static row_t sampler_table[MAX_VARS];
static unsigned sampler_table_size = 0;

static uint32_t start_ticks = 0;

void sampler_sample(uint32_t ticks)
{
	unsigned num_encoded_vars = 0;
	uint16_t encoded_len;
	uint8_t buf[512];
	unsigned index;
	uint32_t relative_ticks = ticks - start_ticks;

	if (!sampler_running) {
		return;
	}

    set_aux_pins(8);
    emo_encode_sampler_sample_start(buf);
    set_aux_pins(9);
	for (index = 0 ; index < sampler_table_size ; ++index) {
		row_t *row = &sampler_table[index];
		if ((row->period_ticks == 1) || (relative_ticks % row->period_ticks == row->phase_ticks)) {
			num_encoded_vars++;
			emo_encode_sampler_sample_add_var(buf, (const uint8_t*)row->address, row->size);
		}
	}
    set_aux_pins(10);
	if (num_encoded_vars > 0) {
		encoded_len = emo_encode_sampler_sample_end(buf, relative_ticks);
		set_aux_pins(11);
		comm_queue_message(buf, encoded_len);
	}
}


/**
 * output: This message can generate a nack if the variable table overflows.
 */

emo_error_t sampler_register_variable(uint32_t phase_ticks, uint32_t period_ticks, uint32_t address, uint16_t size, uint8_t seq)
{
	row_t *row;

	if (sampler_table_size >= MAX_VARS) {
		return EMO_ERROR_SAMPLER_REGISTER_VARIABLE__SIZE_EXCEEDED;
	}
	row = &sampler_table[sampler_table_size];
	row->address = address;
	row->size = size;
	row->phase_ticks = phase_ticks;
	row->period_ticks = period_ticks;
	sampler_table_size++;
	return EMO_ERROR_NONE;
}


void sampler_clear(void)
{
	sampler_stop();
	sampler_table_size = 0;
}


void sampler_stop(void)
{
	sampler_running = false;
}


emo_error_t sampler_start(uint32_t ticks)
{
	if (sampler_table_size == 0) {
		return EMO_ERROR_SAMPLER_TABLE_EMPTY;
	}
	sampler_running = true;
	start_ticks = ticks;

	return EMO_ERROR_NONE;
}
