# data_logger.py
import time
import csv
import math
import threading
from drivers.mpu6050 import MPU6050
from drivers.ds18b20 import DS18B20

# Global variable to hold the latest temperature safely
current_temp = 0.0
is_logging = False

def update_temperature(ds_sensor):
    """Background thread function to read temp so it doesn't block the 100Hz MPU loop"""
    global current_temp, is_logging
    while is_logging:
        try:
            current_temp = ds_sensor.read_temp()
        except Exception:
            pass
        time.sleep(0.5)

def run_logging(filename="dataset.csv", total_samples=1000):
    global current_temp, is_logging
    
    # ==============================
    # SETTINGS
    # ==============================
    SAMPLE_RATE = 100          # 100 Hz
    DT = 1.0 / SAMPLE_RATE
    BASELINE_SAMPLES = 100     # first 1 sec for normal baseline
    CONSECUTIVE_HITS = 2       # avoid noise

    # ==============================
    # INIT SENSORS
    # ==============================
    print("Initializing sensors...")
    mpu = MPU6050()
    ds = DS18B20()
    
    # Start temperature polling in the background
    is_logging = True
    temp_thread = threading.Thread(target=update_temperature, args=(ds,))
    temp_thread.daemon = True
    temp_thread.start()

    print("\nKeep sensor still... collecting baseline")
    time.sleep(2)

    rows = []
    baseline_vib = []
    hit_count = 0

    # ==============================
    # READ FUNCTION
    # ==============================
    def read_mpu():
        ax, ay, az = mpu.read_accel()
        gx, gy, gz = mpu.read_gyro()

        # Convert to real units
        ax /= 16384.0
        ay /= 16384.0
        az /= 16384.0

        gx /= 131.0
        gy /= 131.0
        gz /= 131.0

        return ax, ay, az, gx, gy, gz

    # ==============================
    # MAIN LOOP
    # ==============================
    start_time = time.time()
    base_mean, base_std, threshold = 0, 0, 0

    for i in range(total_samples):
        loop_start = time.time()

        # Time column
        t = round(i * DT, 6)

        ax, ay, az, gx, gy, gz = read_mpu()

        # Vibration magnitude
        vib = math.sqrt(ax**2 + ay**2 + az**2)

        # --------------------------
        # BASELINE PHASE
        # --------------------------
        if i < BASELINE_SAMPLES:
            label = 0
            baseline_vib.append(vib)

            if i == BASELINE_SAMPLES - 1:
                base_mean = sum(baseline_vib) / len(baseline_vib)
                base_std = (sum((x - base_mean) ** 2 for x in baseline_vib) / len(baseline_vib)) ** 0.5
                threshold = base_mean + (4 * base_std) + 0.15

                print("\nBaseline complete.")
                print("Now tap or hit the sensor to create faults.")
                print(f"Threshold = {threshold:.4f}\n")

        # --------------------------
        # FAULT DETECTION
        # --------------------------
        else:
            gyro_mag = math.sqrt(gx**2 + gy**2 + gz**2)

            # Combined score
            score = abs(vib - base_mean) + 0.25 * gyro_mag

            if score > threshold:
                hit_count += 1
            else:
                hit_count = 0

            # Label 1 for fault, 0 for normal
            label = 1 if hit_count >= CONSECUTIVE_HITS else 0

        # Store row including temperature!
        rows.append([t, ax, ay, az, gx, gy, gz, vib, round(current_temp, 2), label])

        # --------------------------
        # TIMING CONTROL
        # --------------------------
        elapsed = time.time() - loop_start
        if elapsed < DT:
            time.sleep(DT - elapsed)

    # Stop background thread
    is_logging = False 

    # ==============================
    # SAVE CSV
    # ==============================
    with open(filename, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["time", "ax", "ay", "az", "gx", "gy", "gz", "vib", "temp_c", "label"])
        writer.writerows(rows)

    print(f"\nDataset saved to: {filename}")
    print(f"Total samples: {total_samples}")
    print(f"Duration ≈ {total_samples / SAMPLE_RATE:.2f} seconds")


if __name__ == "__main__":
    fname = input("Enter output filename (default: dataset.csv): ").strip()
    if not fname:
        fname = "dataset.csv"
    run_logging(fname)