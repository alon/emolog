/*
 * emolog_sampler.h
 *
 *  Created on: 22 ���� 2016
 *      Author: Guy Ovadia
 */

#ifndef EMOLOG_SAMPLER_H_
#define EMOLOG_SAMPLER_H_

#include "emolog_protocol.h"

// Embedded to Host
void sampler_sample(uint32_t ticks);

// Host to Embedded
void sampler_clear(void);
emo_error_t sampler_start(uint32_t ticks);
void sampler_stop(void);
emo_error_t sampler_register_variable(uint32_t phase_ticks, uint32_t period_ticks, uint32_t address, uint16_t size, uint8_t seq);


#endif /* EMOLOG_SAMPLER_H_ */
