/*
 * emolog_example_client.c
 *
 *  Created on: 8 Aug 2017
 *      Author: Guy Ovadia
 */

#include <stdint.h>
#include <math.h>

#include "emolog_example_hw.h"
#include "emolog_protocol.h"
#include "emolog_embedded.h"

#ifndef M_PI
#define M_PI 3.14159265358979323846 // pedantic
#endif


// these are the variables we're going to sample with Emolog.
// they are changed periodically by the code below.
uint32_t sawtooth = 0;
float sine = 0;


int main(void)
{
    uint32_t ticks = 0;

    hw_init();  // platform specific HW initialization.
    emolog_init(); // this must be called before using Emolog;

    while (1)
    {
        sawtooth = (sawtooth + 1) % 100;
        sine = 50.0 * sin(2 * M_PI * ((float)ticks / 100.0));

        emolog_run_step(ticks); // this is where the magic happens.
        ticks++;

        // not best practice, as tick time will equal 50ms + run time of loop, but it will do for this simple example
        delay_ms(50);
    }
}


emo_error_t handle_app_specific_message(emo_header* message)
{
    return EMO_ERROR_UNEXPECTED_MESSAGE;
}


