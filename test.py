import obd
from obd import OBDStatus
import pprint

ports = obd.scan_serial()
print('Possible ports: ')
print(ports)
print('----')

for port in ports:
    #port = '/dev/ttyUSB0'
    connection = obd.Async(port, delay_cmds=0, fast=True)

    if connection.status() is not OBDStatus.CAR_CONNECTED:
        print('OBD2 - No connection to OBDII port from {}'.format(port))
        continue
    else:
        print('OBD2 - Connected to OBDII port on {}'.format(port))
        break
            
if connection.status() is not OBDStatus.CAR_CONNECTED:
    print('OBD2 - No connection to OBDII port')
    exit(1)

print(connection.protocol_id())
print(connection.protocol_name())
print('----')