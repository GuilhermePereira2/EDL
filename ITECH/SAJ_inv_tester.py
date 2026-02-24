import threading
import time
import ctypes
from datetime import datetime
from pymodbus.client import ModbusTcpClient
from py_rw_registers import readwrite_registers
from py_r_register import read_registers
from errors import error_codes

# Configuration
IP_ADDRESS = "192.168.31.238"
PORT = 502
UNIT_ID = 1

energy_thread = None
energy_stop_event = None


def start_passive_listener(client):
    """Reads inverter and battery status every 5 seconds, prints only on fault/status events."""

    monitored_registers = {
        'Time': {'address': 0x4000, 'scale': 0, 'size': 4, 'datatype': 'HEX'},
        'Battery_StatusDisp': {'address': 0x4027, 'scale': 1, 'size': 1, 'datatype': 'UInt16'},
        'Inverter_MPVMode': {'address': 0x4004, 'scale': 1, 'size': 1, 'datatype': 'UInt16'},
        'HFaultMSG (Board/Slave)': {'address': 0x4005, 'scale': 1, 'size': 1, 'datatype': 'UInt32'},
        'MFaultMSG (Master)': {'address': 0x4007, 'scale': 1, 'size': 1, 'datatype': 'UInt32'},
        'MFaultMSG2 (Master)': {'address': 0x4009, 'scale': 1, 'size': 1, 'datatype': 'UInt32'},
        'Error_Count (Inverter)': {'address': 0x400F, 'scale': 1, 'size': 1, 'datatype': 'UInt16'}
    }

    printed_time = False  # garante que o "Time" só é impresso uma vez

    while True:
        values = {}
        trigger_print = False  # só ativa quando condições críticas forem diferentes de 0

        # Lê todos os registos
        for key, reg in monitored_registers.items():
            try:
                result = client.read_holding_registers(
                    address=reg['address'], count=reg['size'])
                if not result.isError():
                    raw = result.registers
                    value = 0

                    if key != 'Time':
                        for word in raw:
                            value = (value << 16) + word
                        values[key] = value
                    else:
                        # Junta todos os words em bytes
                        bytes_list = []
                        for word in raw:
                            high = (word >> 8) & 0xFF
                            low = word & 0xFF
                            bytes_list.extend([high, low])

                        year = (bytes_list[0] << 8) + bytes_list[1]
                        month = bytes_list[2]
                        day = bytes_list[3]
                        hour = bytes_list[4]
                        minute = bytes_list[5]
                        second = bytes_list[6]

                        try:
                            timestamp = datetime(
                                year, month, day, hour, minute, second)
                            values[key] = timestamp
                        except ValueError:
                            values[key] = f"Invalid datetime -> {bytes_list}"

                else:
                    values[key] = f"⚠️ Error: {result}"

            except Exception as e:
                values[key] = f"❌ Exception: {e}"

        # Decide se imprime
        if (values.get("Battery_StatusDisp", 0) != 0 or
            values.get("HFaultMSG (Board/Slave)", 0) != 0 or
            values.get("MFaultMSG (Master)", 0) != 0 or
            values.get("MFaultMSG2 (Master)", 0) != 0 or
                values.get("Error_Count (Inverter)", 0) > 1):
            trigger_print = True

        # Impressão condicional
        if trigger_print:
            print("\n🔄 Reading inverter & battery status...\n")

            for key, val in values.items():
                if key == "Time":
                    if not printed_time:  # imprime só a primeira vez
                        print(f"📖 {key}: {val}")
                        printed_time = True
                else:
                    print(f"📖 {key}: {val}")

                    if key.startswith("Error_Count") and isinstance(val, int) and val != 0:
                        decode_fault_bits(val, error_codes["display"], key)
                    elif key == "MFaultMSG (Master)" and isinstance(val, int) and val != 0:
                        decode_fault_bits(val, error_codes["master_1"], key)
                    elif key == "MFaultMSG2 (Master)" and isinstance(val, int) and val != 0:
                        decode_fault_bits(val, error_codes["master_2"], key)

        time.sleep(120)


def decode_fault_bits(bitfield, error_dict, label):
    print(f"⚠️ Active faults in {label}:")
    for bit in range(32):
        if (bitfield >> bit) & 1:
            description = error_dict.get(bit, f"Unknown error at bit {bit}")
            print(f"  ⚠️ Bit {bit}: {description}")


def reading_powers(client, keys_to_read):
    """Reads inverter and battery status every 60 seconds."""

    i = 0
    monitored_registers = {
        'Meter_A_PowerWatt1 [W]': {'address': 41023, 'scale': 1, 'size': 1, 'datatype': 'Int16'},
        'BatPower [W]': {'address': 16493, 'scale': 1, 'size': 1, 'datatype': 'Int16'},
        'RGridPowerWatt [W]': {'address': 16437, 'scale': 1, 'size': 1, 'datatype': 'Int16'},
        'PV1Power [W]': {'address': 16499, 'scale': 1, 'size': 1, 'datatype': 'UInt16'},
        'PV2Power [W]': {'address': 16502, 'scale': 1, 'size': 1, 'datatype': 'UInt16'},
        'BatEnergyPercent [%]': {'address': 16495, 'scale': 0.01, 'size': 1, 'datatype': 'UInt16'},
        'BatVolt [V]': {'address': 16489, 'scale': 0.1, 'size': 1, 'datatype': 'UInt16'},
        'BatCurr [A]': {'address': 16490, 'scale': 0.01, 'size': 1, 'datatype': 'UInt16'},
        'BatTempC [℃]': {'address': 16494, 'scale': 0.1, 'size': 1, 'datatype': 'UInt16'},
        'SinkTemp [℃]': {'address': 16400, 'scale': 0.1, 'size': 1, 'datatype': 'UInt16'},
        'AmbTemp [ºC]': {'address': 16401, 'scale': 0.1, 'size': 1, 'datatype': 'UInt16'}
    }

    while i < 3:
        print("\n🔄 Reading monitored registers...")
        i = i+1
        for key in monitored_registers:
            if key in monitored_registers:
                reg_info = monitored_registers[key]
                read_register(client, key, reg_info)
            else:
                print(f"⚠️ Key '{key}' not found in monitored_registers.")


def display_register_options():
    """Print available register options for read and write."""
    print("Available read registers:")
    read_keys = list(read_registers.keys())
    for i, name in enumerate(read_keys):
        print(f"{i}: {name}")

    print("\nAvailable write registers:")
    readwrite_keys = list(readwrite_registers.keys())
    offset = len(read_keys)
    for i, name in enumerate(readwrite_keys):
        print(f"{i + offset}: {name}")
    return read_keys, readwrite_keys, offset


def read_register(client, key, reg_info):
    """Read and interpret register value from device."""
    address = reg_info["address"]
    size = reg_info["size"]
    scale = reg_info["scale"]
    data_type = reg_info.get("datatype", "UInt16")

    try:
        result = client.read_holding_registers(
            address=address, count=size)
        if not result.isError():
            read_values = result.registers
            combined_value = 0
            for i in range(size):
                combined_value = (combined_value << 16) + read_values[i]

            if data_type == "Int16" and size == 1:
                value = ctypes.c_int16(combined_value).value
            elif data_type == "Int32" and size == 2:
                value = ctypes.c_int32(combined_value).value
            elif data_type == "HEX":
                value = hex(combined_value)
            else:
                value = combined_value

            if data_type != "HEX":
                value *= scale

            print(f"📖 Read value from '{key}' (Addr {address}): {value}")
        else:
            print(f"⚠️ Error reading '{key}' (Addr {address}): {result}")
    except Exception as e:
        print(f"⚠️ Exception reading '{key}': {e}")


def progressive_charge(client):
    """
    Charge battery progressively from 500W to 5000W in 500W steps.
    Each step lasts 15 minutes, and reading_powers is called at minute 4, 8, and 12.
    """
    print("\n⚡ Starting progressive CHARGE test...")
    reg_info = readwrite_registers['BatChargePower [%]']

    for power in range(500, 4501, 500):  # 500W to 5000W, step 500W
        raw_value = int(power / (reg_info['scale']*5000))
        print(f"\n🔋 Setting charge power to {power} W (raw {raw_value})")

        # Write register
        result = client.write_register(
            address=reg_info['address'],
            value=raw_value
        )
        if result.isError():
            print(f"⚠️ Failed to write charge power {power}W: {result}")
            continue

        # 15-minute cycle for this power step
        for minute in range(1, 3):
            time.sleep(60)  # wait one minute
            if minute in [2]:
                print(
                    f"\n📊 Reading powers at minute {minute} (charge {power}W)...")
                reading_powers(client, read_registers)


def progressive_discharge(client):
    """
    Discharge battery progressively from 500W to 5000W in 500W steps.
    Each step lasts 15 minutes, and reading_powers is called at minute 4, 8, and 12.
    """
    print("\n🔋 Starting progressive DISCHARGE test...")
    # ⚠️ Replace with the correct register if it's different
    reg_info = readwrite_registers['BatDischargePower [%]']

    for power in range(2000, 4501, 500):  # 500W to 5000W, step 500W
        raw_value = int(power / (5000*reg_info['scale']))
        print(f"\n⚡ Setting discharge power to {power} W (raw {raw_value})")

        # Write register
        result = client.write_register(
            address=reg_info['address'],
            value=raw_value
        )
        if result.isError():
            print(f"⚠️ Failed to write discharge power {power}W: {result}")
            continue

        # 15-minute cycle for this power step
        for minute in range(1, 4):
            time.sleep(60)  # wait one minute
            if minute in [1, 3]:
                print(
                    f"\n📊 Reading powers at minute {minute} (discharge {power}W)...")
                reading_powers(client, read_registers)


def write_register(client, key, reg_info):
    """Write a value to a register on the device and confirm by reading."""
    address = reg_info["address"]
    size = reg_info["size"]
    scale = reg_info["scale"]

    try:
        user_val = float(
            input(f"✍️ Enter value for '{key}' (will be scaled): "))
        value = int(user_val / scale)
        # value = int(user_val)
        print(value)
        result = client.write_register(
            address=address, value=value)
        if not result.isError():
            print(
                f"✅ Wrote {user_val} (raw {value}) to '{key}' (Addr {address}) successfully.")
        else:
            print(f"⚠️ Error writing to '{key}' (Addr {address}): {result}")
    except Exception as e:
        print(f"⚠️ Exception writing to '{key}': {e}")
        return

    # Confirm by reading after writing
    try:
        result = client.read_holding_registers(
            address=address, count=size)
        if not result.isError():
            read_values = result.registers
            combined_value = 0
            for i in range(size):
                combined_value = (combined_value << 16) + read_values[i]
            scaled_value = combined_value * scale
            print(
                f"📖 Confirmed value from '{key}' (Addr {address}): {scaled_value}")
        else:
            print(
                f"⚠️ Error reading after write to '{key}' (Addr {address}): {result}")
    except Exception as e:
        print(f"⚠️ Exception reading after write: {e}")


def handle_user_command(client, user_input, read_keys, readwrite_keys, offset):
    """Handle a read or write command issued by the user."""
    cmd_type, _, idx_str = user_input.partition(":")
    idx_str = idx_str.strip()

    if not idx_str.isdigit():
        print("⚠️ Invalid index. Must be a number.")
        return

    idx = int(idx_str)

    if cmd_type == "r":
        if idx >= len(read_keys) + len(readwrite_keys):
            print("⚠️ Index out of range for reading.")
            return
        elif idx < len(read_keys):
            key = read_keys[idx]
            reg_info = read_registers[key]
        else:
            key = readwrite_keys[idx - offset]
            reg_info = readwrite_registers[key]

        read_register(client, key, reg_info)

    elif cmd_type == "w":
        if idx < offset or idx >= offset + len(readwrite_keys):
            print("⚠️ Index out of range for writing.")
            return
        key = readwrite_keys[idx - offset]
        reg_info = readwrite_registers[key]
        write_register(client, key, reg_info)

    else:
        print("⚠️ Unknown command. Use 'r: number' or 'w: number'.")


def start_passive_charge_discharge(client, mode="charge", coulomb_counting=False):
    """
    Start a charge or discharge process.

    Args:
        client: Modbus client
        mode: "charge" or "discharge"
        coulomb_counting: bool, whether to enable coulomb counting logic
    """
    try:
        # 1. Set AppMode = 3
        reg_appmode = readwrite_registers['AppMode']
        result = client.write_register(
            address=reg_appmode['address'],
            value=3
        )
        if result.isError():
            print("❌ Failed to set AppMode to 3")
            return
        else:
            print("✅ AppMode set to 3")

        # 2. Enable passive charge/discharge
        reg_passive = readwrite_registers['Passive_charg_enable']
        if mode.lower() == "charge":
            value = 2
        elif mode.lower() == "discharge":
            value = 1
        else:
            print("⚠️ Invalid mode. Use 'charge' or 'discharge'.")
            return

        result = client.write_register(
            address=reg_passive['address'],
            value=value
        )
        if result.isError():
            print(f"❌ Failed to enable {mode}")
            return
        else:
            print(f"✅ {mode.capitalize()} process started")

        # 3. Coulomb counting flag
        if coulomb_counting:
            print("🔋 Coulomb counting ENABLED (tracking battery Ah).")
            # 👉 Here you can call your coulomb counting routine,
            # e.g. start a thread that integrates current over time.
            start_energy_counting(client, polling_interval=1.0)
        else:
            print("ℹ️ Coulomb counting DISABLED.")

    except Exception as e:
        print(f"⚠️ Exception in start_charge_discharge: {e}")


def energy_counting_worker(client, stop_event, polling_interval=1.0):
    """
    Worker thread for energy counting.
    Reads BatPower, integrates until power <100 W, then exits.
    """
    reg_info = {
        'address': 16493,
        'scale': 1,
        'size': 1,
        'datatype': 'Int16'
    }

    total_energy_Wh = 0.0
    last_time = time.time()
    help_time1 = time.time()
    help_time2 = time.time()

    print("\n🔋 Energy counting thread started...")

    while not stop_event.is_set():
        try:
            # Read BatPower
            result = client.read_holding_registers(
                address=reg_info['address'],
                count=reg_info['size']
            )
            if result.isError():
                print(f"⚠️ Error reading BatPower: {result}")
                time.sleep(polling_interval)
                continue

            raw_value = result.registers[0]
            bat_power = ctypes.c_int16(
                raw_value).value * reg_info['scale']  # [W]

            now = time.time()
            dt_hours = (now - last_time) / 3600.0
            last_time = now
            help_time1 = now

            # Integrate
            total_energy_Wh += abs(bat_power) * dt_hours

            if (help_time1-help_time2) > 60*8:
                print(
                    f"📖 BatPower: {bat_power} W | Accumulated: {total_energy_Wh:.2f} Wh")
                reading_powers(client, read_registers)
                help_time2 = now

            # Stop condition
            if abs(bat_power) < 200:
                print(
                    f"\n✅ Energy counting finished. Final Energy: {total_energy_Wh:.2f} Wh")
                break

        except Exception as e:
            print(f"⚠️ Exception in energy_counting_worker: {e}")

        time.sleep(polling_interval)

    print(
        f"\n✅ Energy counting finished. Final Energy: {total_energy_Wh:.2f} Wh")


def start_energy_counting(client, polling_interval=1.0):
    """
    Start energy counting in a new thread.
    """
    global energy_thread
    global energy_stop_event
    if energy_thread is not None and energy_thread.is_alive():
        print("⚠️ Energy counting is already running!")
        return

    energy_stop_event = threading.Event()  # reset every time
    energy_thread = threading.Thread(
        target=energy_counting_worker,
        args=(client, energy_stop_event, polling_interval),
        daemon=False
    )
    energy_thread.start()
    print("▶️ Energy counting thread launched.")


def read_registers_average_pv_eff(client, keys, register_dict):
    """
    Read three registers five times and calculate the average for each one.

    Args:
        client: Modbus client.
        keys: List of 3 register names (strings).
        register_dict: Dictionary of available registers (e.g. read_registers or readwrite_registers).

    Returns:
        Dictionary with average values per register.
    """

    results = {key: [] for key in keys}

    for i in range(5):
        print(f"\n🔁 Reading cycle {i + 1}/5...")
        for key in keys:
            reg_info = register_dict[key]
            address = reg_info["address"]
            size = reg_info["size"]
            scale = reg_info["scale"]
            data_type = reg_info.get("datatype", "UInt16")

            try:
                result = client.read_holding_registers(
                    address=address, count=size)
                if not result.isError():
                    read_values = result.registers
                    combined_value = 0
                    for j in range(size):
                        combined_value = (combined_value <<
                                          16) + read_values[j]

                    if data_type == "Int16" and size == 1:
                        value = ctypes.c_int16(combined_value).value
                    elif data_type == "Int32" and size == 2:
                        value = ctypes.c_int32(combined_value).value
                    elif data_type == "HEX":
                        value = int(combined_value)
                    else:
                        value = combined_value

                    if data_type != "HEX":
                        value *= scale

                    print(f"📖 {key}: {value}")
                    results[key].append(value)
                else:
                    print(f"⚠️ Error reading '{key}': {result}")
            except Exception as e:
                print(f"⚠️ Exception reading '{key}': {e}")

        # time.sleep(1)  # Optional pause between cycles

    # Compute average
    averages = {key: sum(values) / len(values)
                if values else None for key, values in results.items()}

    print("\n📊 Averages:")
    for key, avg in averages.items():
        print(f"🔸 {key}: {avg}")

    return averages


def scheduled_charge(client, write_dict, read_dict):
    print("\n⚡ Scheduling CHARGE")

    try:
        # Pedir inputs ao utilizador
        start_hour = int(input("🕒 Start Hour (0-23): "))
        start_minute = int(input("🕒 Start Minute (0-59): "))
        end_hour = int(input("🕔 End Hour (0-23): "))
        end_minute = int(input("🕔 End Minute (0-59): "))
        weekday = int(
            input("📅 Weekday bitmask (Ex: 0b010000 for Wednesday = 16): "), 2)
        power_percent = int(input("🔋 Power (% of rated power, e.g. 50): "))

        # Compor valores
        start_time = (start_hour << 8) + start_minute
        end_time = (end_hour << 8) + end_minute
        power_time = (weekday << 8) + power_percent

        # start_time = hex(start_hour) + hex(start_minute)
        # end_time = hex(end_hour) + hex(end_minute)
        # power_time = hex(weekday) + hex(power_percent)

        print(f"{hex(start_time)},{hex(end_time)},{hex(power_time)}")

        # Ativar bit 0 (primeiro horário de carga) do registo de controlo
        result = client.write_register(
            address=write_dict['Charge_time_enable_control']['address'],
            value=0b00000001
        )
        if result.isError():
            print("❌ Failed to enable charge time control.")
            return

        # Escrever restantes registos
        writes = {
            'First_charge_start_time': start_time,
            'First_charge_end_time': end_time,
            'First_charge_power_time': power_time
        }

        for key, value in writes.items():
            addr = write_dict[key]['address']
            result = client.write_register(
                address=addr, value=value)
            if not result.isError():
                print(f"✅ {key} set to {hex(value)} at address {hex(addr)}")
            else:
                print(f"⚠️ Failed to write {key}: {result}")
    except Exception as e:
        print(f"❌ Exception during charge scheduling: {e}")


def scheduled_discharge(client, read_dict, write_dict):
    print("\n🔋 Scheduling DISCHARGE")

    try:
        # Pedir inputs ao utilizador
        start_hour = int(input("🕒 Start Hour (0-23): "))
        start_minute = int(input("🕒 Start Minute (0-59): "))
        end_hour = int(input("🕔 End Hour (0-23): "))
        end_minute = int(input("🕔 End Minute (0-59): "))
        weekday = int(
            input("📅 Weekday bitmask (Ex: 0b010000 for Wednesday = 16): "), 2)
        power_percent = int(input("⚡ Power (% of rated power, e.g. 80): "))

        # Compor valores
        start_time = (start_hour << 8) + start_minute
        end_time = (end_hour << 8) + end_minute
        power_time = (weekday << 8) + power_percent

        # start_time = hex(start_hour) + hex(start_minute)
        # end_time = hex(end_hour) + hex(end_minute)
        # power_time = hex(weekday) + hex(power_percent)

        # Ativar bit 0 (primeiro horário de descarga) do registo de controlo
        result = client.write_register(
            address=write_dict['Discharge_time_enable_control']['address'],
            value=0b00000001
        )
        if result.isError():
            print("❌ Failed to enable discharge time control.")
            return

        # Escrever restantes registos
        writes = {
            'First_discharge_start_time': start_time,
            'First_discharge_end_time': end_time,
            'First_discharge_power_time': power_time
        }

        for key, value in writes.items():
            addr = write_dict[key]['address']
            result = client.write_register(
                address=addr, value=value)
            if not result.isError():
                print(f"✅ {key} set to {hex(value)} at address {hex(addr)}")
            else:
                print(f"⚠️ Failed to write {key}: {result}")
    except Exception as e:
        print(f"❌ Exception during discharge scheduling: {e}")


def main():

    last_power_reading_time = 0
    extra_listening = 0
    client = ModbusTcpClient(IP_ADDRESS, port=PORT)
    if not client.connect():
        print("❌ Failed to connect to Modbus server.")
        return

    print(f"✅ Connected to {IP_ADDRESS}:{PORT}\n")

    # Start passive listener thread
    listener_thread = threading.Thread(
        target=start_passive_listener, args=(client,), daemon=True)
    listener_thread.start()

    # Show available registers
    read_keys, readwrite_keys, offset = display_register_options()

    print("\nEnter 'r: number' to read or 'w: number' to write (or 'exit' to quit).\n")

    while True:
        if extra_listening == 1 and (time.time() - last_power_reading_time) > 5:
            reading_powers(client, read_registers)
            last_power_reading_time = time.time()

        user_input = input("👉 Command (r: or w:) or 'exit': ").strip().lower()
        if user_input == "exit":
            # if energy_stop_event.is_set():
            #    energy_stop_event.set()
            break

        if user_input == "read_eff_pv":
            keys_to_read = ["Meter_A_PowerWatt1 [W]", "RGridPowerWatt [W]",
                            "ROnGridOutPowerWatt [W]", "PV1Power [W]"]  # Replace with actual register names
            averages = read_registers_average_pv_eff(
                client, keys_to_read, read_registers)
            continue
        elif user_input == "start listening" or user_input == "sl":
            extra_listening = 1
        elif user_input == "start listening" or user_input == "stl":
            extra_listening = 0
        elif user_input == "scheduled_charge":
            scheduled_charge(client, readwrite_registers, read_registers)
            continue
        elif user_input == "scheduled_discharge":
            scheduled_discharge(client, read_registers, readwrite_registers,)
            continue
        elif user_input == "progressive_charge":
            start_passive_charge_discharge(client, mode="charge")
            progressive_charge(client)
            continue
        elif user_input == "progressive_discharge":
            start_passive_charge_discharge(client, mode="discharge")
            progressive_discharge(client)
            continue
        elif user_input == "energy_counting":
            start_energy_counting(client, polling_interval=1.0)
            continue
        elif user_input == "stop_energy_counting":
            if energy_stop_event.is_set():
                energy_stop_event.set()
            continue
        elif user_input in ["start_charge", "start_discharge"]:
            # Ask for coulomb counting
            cc_choice = input(
                "🔋 Do you want to enable Coulomb Counting? (y/n): ").strip().lower()
            coulomb_counting = (cc_choice == "y")

            if user_input == "start_charge":
                start_passive_charge_discharge(
                    client, mode="charge", coulomb_counting=coulomb_counting)
            else:
                start_passive_charge_discharge(
                    client, mode="discharge", coulomb_counting=coulomb_counting)
            continue
        elif ":" not in user_input:
            print("⚠️ Invalid format. Use 'r: number' or 'w: number'.")
            continue
        else:
            handle_user_command(client, user_input,
                                read_keys, readwrite_keys, offset)

    client.close()
    print("🚪 Connection closed.")


if __name__ == "__main__":
    main()
