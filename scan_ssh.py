import socket
import concurrent.futures

def check_ssh(ip):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.3)
        if sock.connect_ex((ip, 22)) == 0:
            return ip
    except Exception:
        pass
    finally:
        sock.close()
    return None

def scan():
    base = "10.233.31."
    ips = [f"{base}{i}" for i in range(1, 255)]
    found = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        results = executor.map(check_ssh, ips)
        for r in results:
            if r:
                print("Found SSH open at:", r)
                found.append(r)
    return found

if __name__ == "__main__":
    scan()
