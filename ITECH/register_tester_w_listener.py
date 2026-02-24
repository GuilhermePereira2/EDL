import threading
import time
import ctypes
from pymodbus.client import ModbusTcpClient
from py_rw_registers import readwrite_registers
from py_r_register import read_registers


# Configurações
IP_ADDRESS = "192.168.31.238"
PORT = 502
UNIT_ID = 1

# Função para escutar passivamente
def listen_passively(client):
    while True:
        time.sleep(2)
        try:
            # Tenta ler qualquer registo conhecido como "batimento cardíaco"
            reg = next(iter(readwrite_registers.values()))
            address = reg["address"]
            size = reg["size"]
            address = 0x0101
            size = 4
            result = client.read_holding_registers(address=address, count=size, slave=UNIT_ID)
            if not (result.isError()) : # and (result.address >0) and (result.registers >0)
                print("📡 Inversor respondeu (heartbeat OK)")
                print(result)
            elif (result.address ==0x0101):
                print(result)
        except:
            pass  # Ignora erros para manter a escuta viva

def print_active_errors(display_code: int, master1_code: int, master2_code: int):
    registers = {
        "display": display_code,
        "master_1": master1_code,
        "master_2": master2_code,
    }

    for group, reg_value in registers.items():
        print(f"\n[Grupo: {group.upper()}]")
        for bit in range(32):
            if (reg_value >> bit) & 1:
                error_msg = error_codes.get(group, {}).get(bit, "Erro desconhecido")
                print(f"  Bit {bit}: {error_msg}")

def main():
    client = ModbusTcpClient(IP_ADDRESS, port=PORT)
    if not client.connect():
        print("❌ Erro ao conectar ao servidor Modbus.")
        return

    print(f"✅ Conectado a {IP_ADDRESS}:{PORT}\n")

    # Inicia a escuta passiva num thread separado
    listener_thread = threading.Thread(target=listen_passively, args=(client,), daemon=True)
    listener_thread.start()

    # Mostra os registos disponíveis com índices distintos
    print("Registos de leitura disponíveis:")
    read_keys = list(read_registers.keys())
    for i, name in enumerate(read_keys):
        print(f"{i}: {name}")

    print("\nRegistos de escrita disponíveis:")
    readwrite_keys = list(readwrite_registers.keys())
    offset = len(read_keys)  # ponto de início para os índices de escrita
    for i, name in enumerate(readwrite_keys):
        print(f"{i + offset}: {name}")

    print("\nDigite 'r: número' para ler ou 'w: número' para escrever (ou 'exit' para sair).\n")

    while True:
        user_input = input("👉 Comando (r: ou w:) ou 'exit': ").strip().lower()

        if user_input == "exit":
            break

        if ":" not in user_input:
            print("⚠️ Formato inválido. Usa 'r: número' ou 'w: número'.")
            continue

        cmd_type, _, idx_str = user_input.partition(":")
        idx_str = idx_str.strip()

        if not idx_str.isdigit():
            print("⚠️ Índice inválido. Deve ser um número.")
            continue

        idx = int(idx_str)

        if cmd_type == "r":
            if idx >= len(read_keys)+len(readwrite_keys):
                print("⚠️ Índice fora dos limites para leitura.")
                continue
            elif idx < len(read_keys):
                key = read_keys[idx]
                reg_info = read_registers[key]
                address = reg_info["address"]
                size = reg_info["size"]
                scale = reg_info["scale"]
                data_type = reg_info.get("datatype", "UInt16")  # Valor por omissão

                # --- Ler ---
                try:
                    result = client.read_holding_registers(address=address, count=size, slave=UNIT_ID)
                    if not result.isError():
                        read_values = result.registers
                        combined_value = 0
                        for i in range(size):
                            combined_value = (combined_value << 16) + read_values[i]

                        # Interpretação consoante o tipo
                        if data_type == "Int16" and size == 1:
                            value = ctypes.c_int16(combined_value).value
                        elif data_type == "Int32" and size == 2:
                            value = ctypes.c_int32(combined_value).value
                        elif data_type == "HEX":
                            value = hex(combined_value)
                        else:  # Assume-se UInt16, UInt32 ou outro tipo sem sinal
                            value = combined_value

                        # Aplicar escala se não for HEX
                        if data_type != "HEX":
                            value *= scale

                        print(f"📖 Valor lido de '{key}' (Addr {address}): {value}")
                    else:
                        print(f"⚠️ Erro ao ler '{key}' (Addr {address}): {result}")
                except Exception as e:
                    print(f"⚠️ Exceção ao ler '{key}': {e}")

            else:
                key = readwrite_keys[idx-offset]
                reg_info = readwrite_registers[key]
                address = reg_info["address"]
                size = reg_info["size"]
                scale = reg_info["scale"]

                # --- Ler ---
                try:
                    result = client.read_holding_registers(address=address, count=size, slave=UNIT_ID)
                    if not result.isError():
                        read_values = result.registers
                        combined_value = 0
                        print(range(size))
                        for i in range(size):
                            help=(combined_value << 16)
                            combined_value = (combined_value << 16) + read_values[i]
                            print(f"Combined Values <<16: {help}")
                            print(f" read_values: {read_values[i]}")
                        scaled_value = combined_value * scale
                        print(f"📖 Valor lido de '{key}' (Addr {address}): {scaled_value}")
                    else:
                        print(f"⚠️ Erro ao ler '{key}' (Addr {address}): {result}")
                except Exception as e:
                    print(f"⚠️ Exceção ao ler '{key}': {e}")

        elif cmd_type == "w":
            if idx < offset or idx >= offset + len(readwrite_keys):
                print("⚠️ Índice fora dos limites para escrita.")
                continue
            key = readwrite_keys[idx - offset]
            reg_info = readwrite_registers[key]
            address = reg_info["address"]
            size = reg_info["size"]
            scale = reg_info["scale"]

            # --- Escrever ---
            try:
                user_val = float(input(f"✍️ Introduz valor para '{key}' (será escalado automaticamente): "))
                value = int(user_val / scale)
                result = client.write_register(address=address, value=value, slave=UNIT_ID)
                if not result.isError():
                    print(f"✅ Escreveu {user_val} (interno {value}) em '{key}' (Addr {address}) com sucesso.")
                else:
                    print(f"⚠️ Erro ao escrever em '{key}' (Addr {address}): {result}")
            except Exception as e:
                print(f"⚠️ Exceção ao escrever em '{key}': {e}")
                continue

            # --- Ler depois de escrever ---
            try:
                result = client.read_holding_registers(address=address, count=size, slave=UNIT_ID)
                if not result.isError():
                    read_values = result.registers
                    combined_value = 0
                    for i in range(size):
                        combined_value = (combined_value << 16) + read_values[i]
                    scaled_value = combined_value * scale
                    print(f"📖 Valor lido de '{key}' (Addr {address}): {scaled_value}")
                else:
                    print(f"⚠️ Erro ao ler '{key}' (Addr {address}): {result}")
            except Exception as e:
                print(f"⚠️ Exceção ao ler '{key}': {e}")

        else:
            print("⚠️ Comando desconhecido. Usa 'r: número' ou 'w: número'.")



    client.close()
    print("🚪 Ligação encerrada.")

if __name__ == "__main__":
    main()
