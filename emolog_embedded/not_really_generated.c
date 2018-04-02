/*
 * not_really_generated.c
 *
 *  Created on: 2 Apr 2018
 *      Author: Guy Ovadia
 */

#include <stdint.h>


volatile uint64_t __attribute__((used)) build_timestamp = 12345678;
#ifdef __TI_ARM__
#pragma RETAIN(build_timestamp)
#endif


void dummy_use_timestamp()
{
    volatile uint64_t __attribute__((unused)) dummy = build_timestamp;
}
