import os
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

# Load environment variables
load_dotenv()

DEVICE_MAC = os.getenv("SWITCHBOT_DEVICE_MAC", "").upper()
CO2_ALERT_THRESHOLD = int(os.getenv("CO2_ALERT_THRESHOLD", 1000))
SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL", 5))

# SwitchBot BLE identifiers
SWITCHBOT_COMPANY_ID = 0x0969  # SwitchBot manufacturer company ID

# File paths for OBS
CO2_FILE_PATH = "co2_level.txt"
ALERT_FILE_PATH = "alert.txt"


def parse_manufacturer_data(mac_address: str, data: bytes) -> dict | None:
    """
    Parses BLE manufacturer data from a SwitchBot MeterPro CO2 sensor.

    Manufacturer data layout (16 bytes):
    - Bytes 0-5:  Device MAC address
    - Byte  6:    Device info / flags
    - Byte  7:    Additional flags
    - Byte  8:    Temperature decimal part (lower 4 bits) * 0.1
    - Byte  9:    Temperature integer (lower 7 bits), sign (bit 7)
    - Byte 10:    Humidity (lower 7 bits)
    - Bytes 11-12: Unknown / reserved
    - Byte  13:   CO2 high byte
    - Byte  14:   CO2 low byte
    - Byte  15:   Unknown / flags
    """
    if len(data) < 15:
        return None

    # Verify MAC address matches (bytes 0-5)
    mac_from_data = ":".join(f"{b:02X}" for b in data[0:6])
    if mac_from_data != mac_address:
        return None

    temp_decimal = (data[8] & 0x0F) * 0.1
    temp_integer = data[9] & 0x7F
    temperature = temp_integer + temp_decimal

    humidity = data[10] & 0x7F

    co2 = (data[13] << 8) | data[14]

    return {
        "co2": co2,
        "temperature": round(temperature, 1),
        "humidity": humidity,
    }


def write_to_file(filepath: str, content: str):
    """Writes content to a file. Overwrites existing content."""
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
    except IOError as e:
        print(f"Error writing to file {filepath}: {e}")


def update_obs_files(co2: int):
    """Updates OBS text files based on CO2 level."""
    write_to_file(CO2_FILE_PATH, f"CO2: {co2} ppm")

    if co2 > CO2_ALERT_THRESHOLD:
        alert_msg = "【警告】換気が必要です！"
        write_to_file(ALERT_FILE_PATH, alert_msg)
    else:
        write_to_file(ALERT_FILE_PATH, "")


async def scan_for_co2():
    """Continuously scans for BLE advertisements from the CO2 sensor."""
    print("SwitchBot CO2 Monitor for OBS (BLE Mode)")
    print(f"Target Device MAC: {DEVICE_MAC}")
    print(f"Alert Threshold: {CO2_ALERT_THRESHOLD} ppm")
    print(f"Scan Interval: {SCAN_INTERVAL} seconds")
    print("-" * 40)

    last_co2 = None

    while True:
        try:
            found = False

            def detection_callback(device: BLEDevice, advertisement_data: AdvertisementData):
                nonlocal found, last_co2

                # Check manufacturer data for SwitchBot company ID
                if SWITCHBOT_COMPANY_ID not in advertisement_data.manufacturer_data:
                    return

                mfr_data = advertisement_data.manufacturer_data[SWITCHBOT_COMPANY_ID]
                result = parse_manufacturer_data(DEVICE_MAC, mfr_data)

                if result is None:
                    return

                found = True
                last_co2 = result["co2"]
                now = datetime.now().strftime("%H:%M:%S")
                print(
                    f"[{now}] CO2: {result['co2']} ppm | "
                    f"Temp: {result['temperature']}°C | "
                    f"Humidity: {result['humidity']}%"
                )
                update_obs_files(result["co2"])

            scanner = BleakScanner(detection_callback=detection_callback)
            await scanner.start()
            await asyncio.sleep(SCAN_INTERVAL)
            await scanner.stop()

            if not found and last_co2 is not None:
                now = datetime.now().strftime("%H:%M:%S")
                print(f"[{now}] (Waiting for data... last: {last_co2} ppm)")

        except KeyboardInterrupt:
            print("\nMonitoring stopped by user.")
            break
        except Exception as e:
            print(f"Scan error: {e}")
            await asyncio.sleep(SCAN_INTERVAL)


def main():
    if not DEVICE_MAC:
        print("ERROR: SWITCHBOT_DEVICE_MAC is not set in .env file.")
        return

    try:
        asyncio.run(scan_for_co2())
    except KeyboardInterrupt:
        print("\nMonitoring stopped by user.")


if __name__ == "__main__":
    main()
