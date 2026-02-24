import time
from pymodbus.client import ModbusTcpClient
from pyregisterdict import read_registers

# Configurações
IP_ADDRESS = "192.168.31.235"
PORT = 502
UNIT_ID = 1

# Parâmetros do teste
N_ITERATIONS = 100
TEST_REGISTER = 'RGridFreq [Hz]'  # <- escolhe um registo simples

def main():
    client = ModbusTcpClient(IP_ADDRESS, port=PORT)
    if not client.connect():
        print("❌ Erro ao conectar ao servidor Modbus.")
        return
    print(f"✅ Conectado a {IP_ADDRESS}:{PORT}\n")

    address = read_registers[TEST_REGISTER]["address"]
    size = read_registers[TEST_REGISTER]["size"]

    durations = []

    print(f"⏱️ Iniciando teste de resolução temporal com {N_ITERATIONS} leituras de '{TEST_REGISTER}' (Addr {address})...\n")

    for i in range(N_ITERATIONS):
        start = time.perf_counter()
        result = client.read_holding_registers(address=address, count=size, slave=UNIT_ID)
        end = time.perf_counter()

        if result.isError():
            print(f"⚠️ Erro na leitura #{i+1}: {result}")
            continue

        elapsed = (end - start)
        durations.append(elapsed)

    client.close()

    if durations:
        avg = sum(durations) / len(durations)
        print("\n📊 Resultados:")
        print(f"Leituras válidas: {len(durations)}")
        print(f"Tempo médio por leitura: {avg*1000:.2f} ms")
        print(f"Tempo mínimo: {min(durations)*1000:.2f} ms")
        print(f"Tempo máximo: {max(durations)*1000:.2f} ms")

        diffs = [(x - avg) ** 2 for x in durations]
        std_dev = (sum(diffs) / len(durations)) ** 0.5
        print(f"Desvio padrão: {std_dev*1000:.2f} ms")
    else:
        print("❌ Nenhuma leitura válida foi obtida.")

if __name__ == "__main__":
    main()
