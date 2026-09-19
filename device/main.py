import time
import sys
from drivers.mpu6050 import MPU6050
from drivers.ds18b20 import DS18B20
from data_logger import run_logging

def test_sensors():
    """Simple diagnostic loop to check if sensors are wired correctly"""
    print("\n--- Testing Sensors (Press Ctrl+C to stop) ---")
    
    try:
        mpu = MPU6050()
        ds = DS18B20()
    except Exception as e:
        print(f"Error initializing sensors: {e}")
        return

    try:
        while True:
            ax, ay, az = mpu.read_accel()
            gx, gy, gz = mpu.read_gyro()
            temp = ds.read_temp()

            print("\n------ SENSOR DATA ------")
            print(f"Accel: X={ax}, Y={ay}, Z={az}")
            print(f"Gyro : X={gx}, Y={gy}, Z={gz}")
            print(f"Temp : {temp:.2f} °C")
            
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nTest stopped.")

def main():
    while True:
        print("\n===============================")
        print(" SENSOR DATA LOGGER MENU ")
        print("===============================")
        print("1. Test Sensors (Live Output)")
        print("2. Run Data Logger (Generate CSV)")
        print("3. Exit")
        
        choice = input("Enter choice (1/2/3): ").strip()
        
        if choice == '1':
            test_sensors()
        elif choice == '2':
            fname = input("\nEnter output filename (default: dataset.csv): ").strip()
            if not fname:
                fname = "dataset.csv"
                
            samples_str = input("Enter number of samples to collect (default: 1000): ").strip()
            samples = int(samples_str) if samples_str.isdigit() else 1000
            
            run_logging(filename=fname, total_samples=samples)
        elif choice == '3':
            print("Exiting...")
            sys.exit(0)
        else:
            print("Invalid choice. Please try again.")

if __name__ == "__main__":
    main()