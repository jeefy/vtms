# from .db import db_write
from .config import getDebug
import time

metric_commands = [
    'ENGINE_LOAD',
    'COOLANT_TEMP',
    'SHORT_FUEL_TRIM_1',
    'LONG_FUEL_TRIM_1',
    'SHORT_FUEL_TRIM_2',
    'LONG_FUEL_TRIM_2',
    'FUEL_PRESSURE',
    'INTAKE_PRESSURE',
    'RPM',
    'SPEED',
    'TIMING_ADVANCE',
    'INTAKE_TEMP',
    'MAF',
    'THROTTLE_POS',
    'O2_B1S1',
    'O2_B1S2',
    'O2_B1S3',
    'O2_B1S4',
    'O2_B2S1',
    'O2_B2S2',
    'O2_B2S3',
    'O2_B2S4',
    'RUN_TIME',
    'DISTANCE_W_MIL',
    'FUEL_RAIL_PRESSURE_VAC',
    'FUEL_RAIL_PRESSURE_DIRECT',
    'O2_S1_WR_VOLTAGE',
    'O2_S2_WR_VOLTAGE',
    'O2_S3_WR_VOLTAGE',
    'O2_S4_WR_VOLTAGE',
    'O2_S5_WR_VOLTAGE',
    'O2_S6_WR_VOLTAGE',
    'O2_S7_WR_VOLTAGE',
    'O2_S8_WR_VOLTAGE',
    'COMMANDED_EGR',
    'EGR_ERROR',
    'EVAPORATIVE_PURGE',
    'FUEL_LEVEL',
    'WARMUPS_SINCE_DTC_CLEAR',
    'DISTANCE_SINCE_DTC_CLEAR',
    'EVAP_VAPOR_PRESSURE',
    'BAROMETRIC_PRESSURE',
    'O2_S1_WR_CURRENT',
    'O2_S2_WR_CURRENT',
    'O2_S3_WR_CURRENT',
    'O2_S4_WR_CURRENT',
    'O2_S5_WR_CURRENT',
    'O2_S6_WR_CURRENT',
    'O2_S7_WR_CURRENT',
    'O2_S8_WR_CURRENT',
    'CATALYST_TEMP_B1S1',
    'CATALYST_TEMP_B2S1',
    'CATALYST_TEMP_B1S2',
    'CATALYST_TEMP_B2S2',
    'CONTROL_MODULE_VOLTAGE',
    'ABSOLUTE_LOAD',
    'COMMANDED_EQUIV_RATIO',
    'RELATIVE_THROTTLE_POS',
    'AMBIANT_AIR_TEMP',
    'THROTTLE_POS_B',
    'THROTTLE_POS_C',
    'ACCELERATOR_POS_D',
    'ACCELERATOR_POS_E',
    'ACCELERATOR_POS_F',
    'THROTTLE_ACTUATOR',
    'RUN_TIME_MIL',
    'TIME_SINCE_DTC_CLEARED',
    'MAX_MAF',
    'ETHANOL_PERCENT',
    'EVAP_VAPOR_PRESSURE_ABS',
    'EVAP_VAPOR_PRESSURE_ALT',
    'SHORT_O2_TRIM_B1',
    'LONG_O2_TRIM_B1',
    'SHORT_O2_TRIM_B2',
    'LONG_O2_TRIM_B2',
    'FUEL_RAIL_PRESSURE_ABS',
    'RELATIVE_ACCEL_POS',
    'HYBRID_BATTERY_REMAINING',
    'OIL_TEMP',
    'FUEL_INJECT_TIMING',
    'FUEL_RATE',
]

monitor_commands = [
    'MONITOR_CATALYST_B1',
#    'MONITOR_EGR_B1',
#    'MONITOR_EVAP_020',
#    'MONITOR_MISFIRE_CYLINDER_1',
#    'MONITOR_MISFIRE_CYLINDER_2',
#    'MONITOR_MISFIRE_CYLINDER_3',
#    'MONITOR_MISFIRE_CYLINDER_4',
#    'MONITOR_MISFIRE_GENERAL',
#    'MONITOR_O2_B1S1',
#    'MONITOR_O2_B1S2',
#    'MONITOR_O2_HEATER_B1S1',
#    'MONITOR_O2_HEATER_B1S2',
#    'MONITOR_PURGE_FLOW',
#    'MONITOR_VVT_B1',
#    'MONITOR_VVT_B2',
]

def new_dtc(r, mqttc):
    if not isinstance(r.value, list):
        r.value = [r.value]

    for dtc in r.value:
        if getDebug():
            print('OBD2 - New DTC: ', dtc)
        mqttc.publish("lemons/DTC/" +  dtc[0], dtc[1])


def new_monitor(r, mqttc):
    # Skip if null value
    if r.is_null():
        return 
    
    if getDebug():
        print('----')
        print('OBD2 - New Monitor: {}'.format(r.command.name))
        print(str(r.value))
        print('----')

    # db_write("INSERT INTO monitor VALUES(?, ?, ?)", (r.command.name, str(r.value), time.time()))

    mqttc.publish("lemons/{}".format(r.command.name), str(r.value))

def new_metric(r, mqttc):
    # Skip if null value
    if r.is_null():
        return 
    
    if getDebug():
        print('OBD2 - New Metric: {} - {}'.format(r.command.name,  r.value.magnitude))
    
    # db_write("INSERT INTO telemetry VALUES(?, ?, ?, ?)", (r.command.name, str(r.value.magnitude), str(r.messages), r.time))

    mqttc.publish("lemons/{}".format(r.command.name), str(r.value))