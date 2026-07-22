import subprocess
import os

MAC_ADDRESS = "d8-3a-dd-aa-af-76" # 树莓派的 MAC 地址

def find_pi_ip():
    print("正在扫描局域网寻找树莓派 IP (MAC: d8-3a-dd-aa-af-76) ...")
    try:
        output = subprocess.check_output("arp -a", shell=True, text=True)
        for line in output.split('\n'):
            if MAC_ADDRESS.lower() in line.lower() or MAC_ADDRESS.replace('-', ':').lower() in line.lower():
                parts = line.split()
                if len(parts) >= 2:
                    ip = parts[0]
                    print(f"✅ 找到树莓派! IP 地址为: {ip}")
                    return ip
    except Exception as e:
        print(f"执行 arp -a 失败: {e}")
    return None

def main():
    ip = find_pi_ip()
    if not ip:
        print("❌ 未能在局域网中找到树莓派，请检查是否连接到了同一个 WiFi 热点。")
        return
        
    username = input(f"请输入树莓派用户名 [直接回车默认 g0904]: ").strip()
    if not username:
        username = "g0904"
        
    action = input(f"请选择操作:\n  1: 仅 SSH 登录树莓派\n  2: 部署新的 main.py 到树莓派并 SSH 登录\n[直接回车默认 2]: ").strip()
    if not action:
        action = "2"
        
    if action == "2":
        local_main = r"E:\Learning\Competition\GC_Competition\2027_GC_C\Vision\main.py"
        target_dir = input("请输入树莓派上的 Vision 文件夹路径 [直接回车默认 ~/Vision/]: ").strip()
        if not target_dir:
            target_dir = "~/Vision/"
            
        if not target_dir.endswith('/'):
            target_dir += '/'
            
        remote_path = f"{username}@{ip}:{target_dir}main.py"
        
        print(f"\n🚀 开始传输 PC 上最新的 main.py 到树莓派...")
        print("💡 提示：此时需要输入树莓派的密码 (已知为: 1025)")
        # 使用 scp 上传文件 (关闭严格的主机密钥检查，防止动态 IP 变更导致报错)
        os.system(f"scp -o StrictHostKeyChecking=no \"{local_main}\" {remote_path}")
        print("✅ 文件传输命令已执行结束！")
        
    print(f"\n🔌 正在构建 SSH 连接 ({username}@{ip})...")
    print("💡 提示：此时需要再次输入树莓派的密码 (已知为: 1025)")
    os.system(f"ssh -o StrictHostKeyChecking=no {username}@{ip}")

if __name__ == "__main__":
    main()
