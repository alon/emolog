/*
 * emolog_example_client.c
 *
 *  Created on: 8 Aug 2017
 *      Author: Guy Ovadia
 */

#include "emolog_example_client.h"

#include <stdint.h>
#include <math.h>

#include "emolog_protocol.h"
#include "emolog_embedded.h"
#include "emolog_debug.h"


#ifndef M_PI
#define M_PI 3.14159265358979323846 // pedantic
#endif

typedef struct
{
    int a;
    float b;
}MyStruct;

// these are the variables we're going to sample with Emolog.
// they are changed periodically by the code below.
uint32_t sawtooth = 0;
float sine = 0;
MyStruct my_struct;


#define TICK_PERIOD_MS     5


void emolog_example_main_loop(void)
{
    uint32_t ticks = 0;
    my_struct.a = 42;
    my_struct.b = M_PI;

    debug_printf("\n--- Emolog Example Start ---\n\n");
    emolog_init();

    while (1)
    {
        sawtooth = (sawtooth + 1) % 100;
        sine = 50.0 * sin(2 * M_PI * ((float)ticks / 100.0));
        my_struct.a++;
        my_struct.b += 1.0F;

        emolog_run_step(ticks); // this is where the magic happens.
        ticks++;

        // not best practice, as tick time will equal TICK_PERIOD_MS + run time of loop, but it will do for this simple example
        delay_ms(TICK_PERIOD_MS);
    }
}


emo_error_t handle_app_specific_message(emo_header* message)
{
    return EMO_ERROR_UNEXPECTED_MESSAGE;
}


