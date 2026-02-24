import pandas as pd

# Caminho para o teu ficheiro Excel
file_path = "saj-modbus-h2.xlsx"

# Lê a folha com os registos do inversor
df = pd.read_excel(file_path, sheet_name="Table 1")

# Mostrar os nomes das colunas reais
print("Colunas disponíveis:")
print(df.columns.tolist())

# Remove linhas vazias e garante que os nomes das colunas são tratados corretamente
df = df.dropna(subset=["Register Name", "Unit", "Size", " Address Dez","Ratio"])



# Cria o dicionário
registers = {}
for _, row in df.iterrows():
    name = f"{row['Register Name']} [{row['Unit']}]"
    address = int(row[" Address Dez"])
    size = int(row["Size"])
    ratio = int(row["Ratio"])
    registers[name] = {"address": address, "size": size, "scale": 10**ratio}

# Mostra o resultado
import pprint
pprint.pprint(registers)
