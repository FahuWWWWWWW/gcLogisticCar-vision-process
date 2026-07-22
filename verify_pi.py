import paramiko

def verify():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect('10.150.144.190', username='g0904', password='1025', timeout=5)
        stdin, stdout, stderr = ssh.exec_command('cat ~/Vision/main.py | grep -A 5 "task_queue.empty"')
        print(stdout.read().decode('utf-8'))
    except Exception as e:
        print(f"Failed: {e}")
    finally:
        ssh.close()

if __name__ == '__main__':
    verify()
