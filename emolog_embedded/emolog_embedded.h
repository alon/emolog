/*
 * emolog_embedded.h
 *
 *  Created on: 12 бреб„ 2016
 *      Author: Guy Ovadia
 */

#ifndef EMOLOG_EMBEDDED_H_
#define EMOLOG_EMBEDDED_H_

#ifdef __cplusplus
extern "C" {
#endif

#include "emolog_protocol.h"

void emolog_init(void);
void emolog_run_step(uint32_t ticks);

extern emo_error_t handle_app_specific_message(emo_header* message); // to be implemented by application code

#ifdef __cplusplus
}
#endif

#endif /* EMOLOG_EMBEDDED_H_ */
