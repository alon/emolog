/*
 * sampler.h
 *
 *  Created on: 22 במאי 2016
 *      Author: Guy Ovadia
 */

#ifndef SAMPLER_H_
#define SAMPLER_H_

// Embedded to Host
void sampler_sample(void);

// Host to Embedded
void sampler_clear(void);
void sampler_start(void);
void sampler_stop(void);
void sampler_register_variable(uint32_t phase_ticks, uint32_t period_ticks, uint32_t address, uint16_t size, uint8_t seq);


#endif /* SAMPLER_H_ */
