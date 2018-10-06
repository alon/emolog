/*
 * emolog_debug.h
 *
 *  Created on: 20 Jul 2017
 *      Author: Guy Ovadia
 */

#ifndef EMOLOG_DEBUG_H_
#define EMOLOG_DEBUG_H_

// TODO: write vararg function to prepend "EMOLOG: " instead of manually inserting it every debug call
#if defined(HOST_DEBUG) || (defined(EMOLOG_CLIENT_DEBUG) && defined(EMOLOG_PLATFORM_STM32) )
    #include <stdio.h>
    #define debug_printf printf
#elif defined(EMOLOG_CLIENT_DEBUG) && defined(EMOLOG_PLATFORM_TIVA_C)
    #include "utils/uartstdio.h"
    #include "../../Source/Hardware.h"
    #define debug_printf UARTprintf
#else
    #ifndef debug_printf
        #define debug_printf(...)
    #endif

    #ifndef set_blue_led
        #define set_blue_led(...)
    #endif

    #ifndef set_green_led
        #define set_green_led(...)
    #endif

    #ifndef set_yellow_led
        #define set_yellow_led(...)
    #endif

    #ifndef set_red_led
        #define set_red_led(...)
    #endif

    #ifndef set_aux_gpio_0
        #define set_aux_gpio_0(...)
    #endif

    #ifndef set_aux_gpio_1
        #define set_aux_gpio_1(...)
    #endif

    #ifndef set_aux_gpio_2
        #define set_aux_gpio_2(...)
    #endif

    #ifndef set_aux_gpio_3
        #define set_aux_gpio_3(...)
    #endif

    #ifndef set_aux_pins
        #define set_aux_pins(...)
    #endif
#endif


#endif /* EMOLOG_DEBUG_H_ */
