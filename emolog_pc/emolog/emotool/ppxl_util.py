HALF_CYCLE_TITLE_TO_CELL_NAME = {
    'Flow Rate [LPM]': 'flow_rate_cell',
    'Pump Head [m]': 'pump_head_cell',
    'Power Out [W]': 'power_out_cell',
    'Average Power In [W]': 'power_in_cell',
    'Cruising Flow Rate [LPM]': 'cruising_flow_rate_cell',
    'Cruising Power In [W]': 'cruising_power_in_cell',
    'Cruising Power Out [W]': 'cruising_power_out_cell',
    'Cruising Efficiency [%]': 'cruising_efficiency_cell',
    'Efficiency [%]': 'efficiency_cell'
}

HALF_CYCLE_CELL_TO_TITLE_NAME = {v: k for k, v in HALF_CYCLE_TITLE_TO_CELL_NAME.items()}

def ppxl_formula_power_out(flow_rate_cell, pump_head_cell, **unused):
    """
    NOTE: the unused is a hack to allow calling like:
    ppxl_formula_flow_rate_lpm(**locals())

    :param flow_rate_cell:
    :param pump_head_cell:
    :param unused:
    :return:
    """
    return '={flow_rate_cell} / 60 * 9.80665 * {pump_head_cell}'.format(**locals())


def ppxl_formula_cruising_power_out(cruising_flow_rate_cell, pump_head_cell, **unused):
    return '=' + cruising_flow_rate_cell + ' / 60 * 9.80665 * ' + pump_head_cell


def ppxl_formula_efficiency(power_out_cell, power_in_cell, **unused):
    return '={power_out_cell} / {power_in_cell}'.format(**locals())


def ppxl_formula_cruising_efficiency(cruising_power_out_cell, cruising_power_in_cell, **unused):
    return '=' + cruising_power_out_cell + ' / ' + cruising_power_in_cell


HALF_CYCLE_CELL_TO_FORMULA = dict(
    # cell_name to formula
    power_out_cell=ppxl_formula_power_out,
    efficiency_cell=ppxl_formula_efficiency,
    cruising_power_out_cell=ppxl_formula_cruising_power_out,
    cruising_efficiency_cell=ppxl_formula_cruising_efficiency,
)

HALF_CYCLE_FORMULA_TITLES = [HALF_CYCLE_CELL_TO_TITLE_NAME[k] for k in HALF_CYCLE_CELL_TO_FORMULA.keys()]

# These will always be entered
HALF_CYCLE_PREDEFINED_CELL_NAMES = ['pump_head_cell']
HALF_CYCLE_PREDEFINED_TITLES = [HALF_CYCLE_CELL_TO_TITLE_NAME[k] for k in HALF_CYCLE_PREDEFINED_CELL_NAMES]
