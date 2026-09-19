import glob
import time
import os

class DS18B20:
    def __init__(self):
        base_dir = '/sys/bus/w1/devices/'
        try:
            self.device_folder = glob.glob(base_dir + '28*')[0]
            self.device_file = self.device_folder + '/w1_slave'
            self.sensor_found = True
        except IndexError:
            self.device_file = None
            self.sensor_found = False
            print("Warning: DS18B20 sensor not found. Check wiring/1-wire setup.")

    def read_temp(self):
        """Reads temperature in Celsius"""
        if not self.sensor_found:
            return 0.0 # Return 0 if not connected to avoid crashing
            
        with open(self.device_file, 'r') as f:
            lines = f.readlines()

        # Wait until sensor is ready
        while lines[0].strip()[-3:] != 'YES':
            time.sleep(0.1)
            with open(self.device_file, 'r') as f:
                lines = f.readlines()

        temp_line = lines[1]
        temp = float(temp_line.split('t=')[-1]) / 1000.0
        return temp