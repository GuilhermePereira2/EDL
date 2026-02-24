from pymodbus.client import ModbusTcpClient
from py_r_register import read_registers  # <--- aqui importas o dicionário
from py_rw_registers import readwrite_registers

# Configurações
IP_ADDRESS = "192.168.31.238"  # muda para o IP do teu inversor
PORT = 502
UNIT_ID = 1  # Modbus Unit ID (slave address)
test_read_registers =1



def main():
    client = ModbusTcpClient(IP_ADDRESS, port=PORT)
    if not client.connect():
        print("❌ Erro ao conectar ao servidor Modbus.")
        return

    print(f"✅ Conectado a {IP_ADDRESS}:{PORT}\n")

    if test_read_registers == 1:
        for name, reg in read_registers.items():
            address = reg["address"]
            size = reg["size"]
            scale = reg["scale"]

            try:
                result = client.read_holding_registers(address=address, count=size, slave=UNIT_ID)

                if not result.isError():
                    values = result.registers

                    # Combinar os registos num único valor
                    combined_value = 0
                    for i in range(size):
                        combined_value = (combined_value << 16) + values[i]
                    scaled_value = combined_value * scale
                    print(f"{name} (Addr {address}): {scaled_value}")
                else:
                    print(f"⚠️ Erro ao ler {name} (Addr {address}): {result}")
            except Exception as e:
                print(f"⚠️ Exceção ao ler {name}: {e}")


    # Obter a chave correspondente à 3ª entrada (índice 2, pois começa em 0)
    key = list(readwrite_registers.keys())[10]  # Isto dá: 'BatChgSocUpLimit [%]'

    # Obter o dicionário correspondente a essa chave
    reg_info = readwrite_registers[key]

    address = reg_info["address"]
    size = reg_info["size"]
    scale = reg_info["scale"]
    value = 1
    name = key

    # --- Escrever o valor ---
    try:
        result = client.write_register(address=address, value=value, slave=UNIT_ID)
        if not result.isError():
            print(f"✅ Escreveu {value} em '{name}' (Addr {address}) com sucesso.")
        else:
            print(f"⚠️ Erro ao escrever em '{name}' (Addr {address}): {result}")
    except Exception as e:
        print(f"⚠️ Exceção ao escrever em '{name}': {e}")

    # --- Ler o valor novamente ---
    try:
        result = client.read_holding_registers(address=address, count=size, slave=UNIT_ID)
        if not result.isError():
            read_value = result.registers

            # Combinar os registos num único valor
            combined_value = 0
            for i in range(size):
                combined_value = (combined_value << 16) + read_value[i]

            scaled_value = combined_value * scale
            print(f"📖 Valor lido de '{name}' (Addr {address}): {read_value}")
        else:
            print(f"⚠️ Erro ao ler '{name}' (Addr {address}): {result}")
    except Exception as e:
        print(f"⚠️ Exceção ao ler '{name}': {e}")

    client.close()

if __name__ == "__main__":
    main()
