#include <assert.h>
#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <math.h>

#include "inc/hw_ints.h"
#include "inc/hw_memmap.h"
#include "inc/hw_types.h"
#include "driverlib/debug.h"
#include "driverlib/gpio.h"
#include "driverlib/interrupt.h"
#include "driverlib/pin_map.h"
#include "driverlib/rom.h"
#include "driverlib/rom_map.h"
#include "driverlib/sysctl.h"
#include "driverlib/uart.h"

#include <emolog.h>

#include "comm.h"
#include "sampler.h"

#ifndef M_PI
#define M_PI 3.14159265358979323846 // pedantic
#endif

/* Water Pump Protocol */


uint32_t sys_clk_hz;

uint32_t sawtooth = 0;
float sine = 0;

// The error routine that is called if the driver library encounters an error.
#ifdef DEBUG
void
__error__(char *pcFilename, uint32_t ui32Line)
{
}
#endif


/* Main */


void delay_ms(uint32_t ms)
{
	SysCtlDelay(sys_clk_hz / 1000 / 3 * ms);
}


void setup_clock(void)
{
    sys_clk_hz = MAP_SysCtlClockFreqSet((SYSCTL_XTAL_25MHZ |
                                             SYSCTL_OSC_MAIN |
                                             SYSCTL_USE_PLL |
                                             SYSCTL_CFG_VCO_480), 120000000);
}

void setup_led(void)
{
    ROM_SysCtlPeripheralEnable(SYSCTL_PERIPH_GPION);
    SysCtlDelay(3);
    ROM_GPIOPinTypeGPIOOutput(GPIO_PORTN_BASE, GPIO_PIN_0); // led
}


void setup(void)
{
    setup_clock();
    comm_setup();
    setup_led();
    ROM_IntMasterEnable();
}


// helpers

void queue_ack(uint8_t reply_to_seq, emo_error_t error)
{
    uint8_t buf_out[32];
    uint16_t encoded_len;

    encoded_len = emo_encode_ack(buf_out, reply_to_seq, error);
    assert(encoded_len <= sizeof(buf_out));
    comm_queue_message(buf_out, encoded_len);
}


void handle_message(emo_header *header)
{
    uint8_t buf_out[32];
    uint16_t encoded_len;
    emo_error_t error = EMO_ERROR_NONE;

    switch (header->type) {
    case EMO_MESSAGE_TYPE_VERSION: {
        encoded_len = emo_encode_version(buf_out, header->seq);
        comm_queue_message(buf_out, encoded_len);
        break;
    }
    case EMO_MESSAGE_TYPE_PING: {
        // TODO
        break;
    }
    case EMO_MESSAGE_TYPE_SAMPLER_REGISTER_VARIABLE: {
        emo_sampler_register_variable *m = (emo_sampler_register_variable *)header;
        emo_sampler_register_variable_payload *p = &m->p;
        error = sampler_register_variable(p->phase_ticks, p->period_ticks, p->address, p->size, header->seq);
        break;
    }
    case EMO_MESSAGE_TYPE_SAMPLER_CLEAR: {
        sampler_clear();
        break;
    }
    case EMO_MESSAGE_TYPE_SAMPLER_START: {
        sampler_start();
        break;
    }
    case EMO_MESSAGE_TYPE_SAMPLER_STOP: {
        sampler_stop();
        break;
    }
    default: {
        error = EMO_ERROR_UNEXPECTED_MESSAGE;
    }
    }

    if (header->type != EMO_MESSAGE_TYPE_VERSION) {
        queue_ack(header->seq, error);
    }
}


void main(void)
{
    setup();
    uint32_t ticks = 0;

    while (1) {
        sawtooth = (sawtooth + 1) % 100;
        sine = 50.0 * sin(2 * M_PI * ((float)ticks / 100.0));

        emo_header *header;
        if ((header = comm_peek_message()) != NULL) {
            handle_message(header);
            comm_consume_message();
        }
        sampler_sample();
        ticks++;
        delay_ms(50);

    }
}

