/*
 * emolog_debug.h
 *
 *  Created on: 20 Jul 2017
 *      Author: Guy Ovadia
 */

#ifndef EMOLOG_DEBUG_H_
#define EMOLOG_DEBUG_H_

// TODO: write vararg function to prepend "EMOLOG: " instead of manually inserting it every debug call
#if defined(HOST_DEBUG) || (defined(CLIENT_DEBUG) && defined(EMOLOG_PLATFORM_STM32) )
    #include <stdio.h>
    #define debug_printf printf
#elif defined(CLIENT_DEBUG) && defined(EMOLOG_PLATFORM_TIVA_C)
    #include "utils/uartstdio.h"
    #define debug_printf UARTprintf
#else
#define debug_printf(...)
#endif


#endif /* EMOLOG_DEBUG_H_ */
