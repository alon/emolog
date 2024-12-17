/*
 * emolog_debug.h
 *
 *  Created on: 20 Jul 2017
 *      Author: Guy Ovadia
 */

#ifndef EMOLOG_DEBUG_H_
#define EMOLOG_DEBUG_H_

// #define EMO_DEBUG // uncomment to enable debug output to stdio

#if defined(EMO_DEBUG)
    #include <stdio.h>
    #define debug_printf printf
#else
    #ifndef debug_printf
        #define debug_printf(...)
    #endif
#endif

#endif /* EMOLOG_DEBUG_H_ */
