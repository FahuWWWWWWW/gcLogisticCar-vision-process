import paramiko
import sys

ip = '192.168.65.190'
user = 'g0904'
passwords = ['g0904', 'raspberry', '123456', '12345678', 'root', 'admin']

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

success = False
for pwd in passwords:
    try:
        ssh.connect(ip, username=user, password=pwd, timeout=5)
        print(f"SUCCESS with password: {pwd}")
        success = True
        break
    except paramiko.AuthenticationException:
        pass
    except Exception as e:
        print(f"Error: {e}")
        break

if success:
    stdin, stdout, stderr = ssh.exec_command('ls -la /home/g0904/Nori_Xvision_Development_Kit_Ver10.00.09_Linux')
    print("STDOUT:")
    print(stdout.read().decode())
    print("STDERR:")
    print(stderr.read().decode())
    
    # Check Python samples
    stdin, stdout, stderr = ssh.exec_command('ls -la /home/g0904/Nori_Xvision_Development_Kit_Ver10.00.09_Linux/Samples/Python/Nori_Import')
    print("Python Samples:")
    print(stdout.read().decode())
    ssh.close()
else:
    print("Failed to connect with common passwords.")
