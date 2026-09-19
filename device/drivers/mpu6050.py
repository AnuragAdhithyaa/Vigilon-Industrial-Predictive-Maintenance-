import smbus2

class MPU6050:
    def __init__(self, bus=1, address=0x68):
        self.bus = smbus2.SMBus(bus)
        self.address = address
        # Wake up the MPU6050
        self.bus.write_byte_data(self.address, 0x6B, 0)

    def _read_word(self, reg):
        high = self.bus.read_byte_data(self.address, reg)
        low = self.bus.read_byte_data(self.address, reg + 1)
        value = (high << 8) | low
        if value > 32768:
            value -= 65536
        return value

    def read_accel(self):
        """Returns Accelerometer X, Y, Z raw values"""
        return (
            self._read_word(0x3B),
            self._read_word(0x3D),
            self._read_word(0x3F)
        )

    def read_gyro(self):
        """Returns Gyroscope X, Y, Z raw values"""
        return (
            self._read_word(0x43),
            self._read_word(0x45),
            self._read_word(0x47)
        )