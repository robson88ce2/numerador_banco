import socket
import os
import json
import subprocess

# Caminho do arquivo de configuração
CONFIG_FILE = "ip_config.json"

def get_local_ip():
    """Obtém o IP local da máquina"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0)
    try:
        s.connect(('8.8.8.8', 1))  # Conecta-se a um DNS externo para pegar o IP correto
        ip = s.getsockname()[0]
    except Exception:
        ip = 'localhost'  # Se não conseguir, usa localhost
    finally:
        s.close()
    return ip

def read_stored_ip():
    """Lê o IP armazenado no arquivo"""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
            return config.get("ip", None)
    return None

def save_ip(ip):
    """Salva o IP no arquivo de configuração"""
    config = {"ip": ip}
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f)

def is_ip_reachable(ip):
    """Testa se o IP salvo ainda está acessível na rede"""
    try:
        result = subprocess.run(["ping", "-n", "1", ip], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return result.returncode == 0
    except Exception:
        return False

def main():
    stored_ip = read_stored_ip()
    
    # Se houver IP armazenado, testa se ele ainda está disponível
    if stored_ip and is_ip_reachable(stored_ip):
        print(f"Conectado ao IP armazenado: {stored_ip}")
    else:
        print("IP salvo não está acessível ou não foi encontrado. Obtendo um novo IP...")
        new_ip = get_local_ip()
        print(f"Novo IP obtido: {new_ip}")
        save_ip(new_ip)
        print(f"IP '{new_ip}' foi salvo e será usado nas próximas execuções.")

if __name__ == "__main__":
    main()