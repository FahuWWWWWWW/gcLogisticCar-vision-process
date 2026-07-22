import os
import paramiko
import subprocess

# Generate SSH key if not exists
ssh_dir = os.path.expanduser('~/.ssh')
key_file = os.path.join(ssh_dir, 'id_rsa')
pub_key_file = key_file + '.pub'

if not os.path.exists(key_file):
    os.makedirs(ssh_dir, exist_ok=True)
    subprocess.run(['ssh-keygen', '-t', 'rsa', '-b', '2048', '-N', '', '-f', key_file], check=True)

with open(pub_key_file, 'r') as f:
    pub_key = f.read().strip()

ip = '192.168.65.190'
user = 'g0904'
pwd = '1025'

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

try:
    ssh.connect(ip, username=user, password=pwd, timeout=5)
    print("Connected successfully!")
    
    # Create .ssh dir and add authorized_keys
    ssh.exec_command('mkdir -p ~/.ssh && chmod 700 ~/.ssh')
    stdin, stdout, stderr = ssh.exec_command(f'echo "{pub_key}" >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys')
    print("SSH key uploaded.")
    
    # Check SDK directory structure
    sdk_path = "/home/g0904/Nori_Xvision_Development_Kit_Ver10.00.09_Linux"
    stdin, stdout, stderr = ssh.exec_command(f'tree -L 3 {sdk_path} || ls -R {sdk_path}')
    print("--- SDK STRUCTURE ---")
    print(stdout.read().decode())
    
    # Look for Python interface
    stdin, stdout, stderr = ssh.exec_command(f'cat {sdk_path}/Samples/Python/Nori_Import/Nor_public.py')
    with open('nor_public_dump.txt', 'w', encoding='utf-8') as f:
        f.write(stdout.read().decode())
        
    ssh.close()
except Exception as e:
    print(f"Error: {e}")
