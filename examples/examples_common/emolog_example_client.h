/*
 * emolog_example_client.h
 *
 *  Created on: 9 Aug 2017
 *      Author: Guy Ovadia
 */

#ifndef EMOLOG_EXAMPLE_CLIENT_H_
#define EMOLOG_EXAMPLE_CLIENT_H_

#include <stdint.h>

void emolog_example_main_loop(void);
void delay_ms(uint32_t ms);     // this needs to be implemented externally, as the example code uses it



#endif /* EMOLOG_EXAMPLE_CLIENT_H_ */
