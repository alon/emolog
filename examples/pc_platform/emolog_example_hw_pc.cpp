/* Emolog client example - Hardware abstraction for TI Tiva C series MCUs.
 *
 * This file can be used as-is on a TI Connected Launchpad (EK-TM4C1294XL)
 * but can be adapted to other Tiva platforms with minimal changes.
 * If using the Connected Launchpad, wire it as follows:
 * MCU pin PC4 (UART7 RX) to USB-UART adapter's TX
 * MCU pin PC5 (UART7 TX) to USB-UART adapter's RX
 * and of course Launchpad's ground to USB-UART adapter's ground.
 */


// General includes
#include <unistd.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>

#include "../examples_common/emolog_example_client.h" // include for example code that is common to all platforms
#include "emolog_embedded.h"       // for calling emolog_init()
#include "emolog_comm.h"
#include "emolog_sampler.h"
#include "emolog_protocol.h"


// These delay functions are not very accurate as they rely on a busy loop that can be subject to wait states and stuff
extern "C"
void delay_us(uint32_t us)
{
    usleep(us);
}


extern "C"
void delay_ms(uint32_t ms)
{
    usleep(ms * 1000);
}

/** Communication */

/** TODO - move this somewhere else. maybe make this the emolog test instead of the pc example */

const float comm_advance_table_down[][2] = {
    {0.5, 0.8},
    {0.9, 1.4},
};

const float soft_start_table[][2] = {{1.0, 1.0}, {2.0, 2.0}, {3.0, 3.0}};

const float comm_advance_table_up[][2] = {
    {0.9, 1.4},
    {0.5, 0.8},
};

typedef struct {
    int duty_cycle;
} duty_cycle_t;

typedef struct {
    float top_coasting_start;
    float state_during_dir_change;
    float stall_timeout;
    float top_travel_limit;
    float ref_sensor_pos;
    float bottom_coasting_start;
    float comm_advance_mode;
    float comm_advance_during_accel;
    float acceleration_steps_down;
    float comm_advance_const_delay_down;
    float comm_advance_const_delay_up;
    float dir_change_behavior;
    float acceleration_steps_up;
    float use_soft_start;
    float bottom_travel_limit;
    float dir_change_duration;
    float turn_on_v_threshold;
    float turn_off_v_threshold;
} params_t;

enum Direction
{
	DOWN = -1,
	DIR_NONE = 0,
	UP = 1
};

enum Controller_Mode
{
   MODE_ACCEL,
   MODE_CRUISING,
   MODE_DIR_CHANGE,
   MODE_STALLED,
   MODE_MANUAL_OFF,
   MODE_SELF_OFF,
   MODE_UNDERVOLTAGE_SHUTDOWN,
   MODE_INIT,
   MODE_OPEN_LOOP
};

typedef struct AnalogSensors {
    float temp_a;
    float temp_b;
    float temp_c;
    float temp_ext;
    float total_i;
    float dc_bus_v;
} AnalogSensors;

typedef struct state_t {
    AnalogSensors analog_sensors;
    Direction actual_dir;
    int position;
    float last_flow_rate_lpm;
    uint8_t commutation_sensors;
    int step_time_prediction;
    Controller_Mode mode;
    int motor_state;
    duty_cycle_t duty_cycle;
    Direction required_dir;
    float ref_sensor;
} state_t;


struct {
    params_t params;
    state_t state;
} controller;


int main(void)
{
    controller.state.actual_dir = DOWN,
    controller.state.required_dir = DOWN,
    controller.state.mode = MODE_CRUISING;
    emolog_example_main_loop(); // this never returns
}

