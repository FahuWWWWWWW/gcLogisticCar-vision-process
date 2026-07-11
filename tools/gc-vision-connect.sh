#!/usr/bin/env bash
# ============================================================================
# gc-vision-connect.sh — 树莓派远程连接与验证一站式脚本
# ============================================================================
# 用法:
#   ./tools/gc-vision-connect.sh              # 快速连通性检查
#   ./tools/gc-vision-connect.sh --full       # 完整环境检查 + 验证
#   ./tools/gc-vision-connect.sh --sync       # 同步代码并验证
#   ./tools/gc-vision-connect.sh --setup      # 首次部署全流程
#   ./tools/gc-vision-connect.sh --help       # 查看帮助
#
# 依赖: ssh, scp (Windows 用户请用 Git Bash 或 WSL 运行)
# ============================================================================

set -euo pipefail

# ── 配置（按你的环境修改） ─────────────────────────────────
SSH_HOST="${GC_HOST:-rpi4b}"                # SSH 别名或 user@ip
PI_USER="${GC_USER:-g0904}"                 # Pi 用户名
PI_PROJECT_DIR="${GC_PROJECT_DIR:-~/Vision}" # Pi 上项目路径
PI_VENV="${GC_VENV:-~/gc_vision_venv}"      # Pi 上虚拟环境路径
LOCAL_PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"  # 本地项目根目录

# ── 颜色输出 ─────────────────────────────────────────────
# 使用 $'...' 语法确保 \033 被解释为真正的 ESC 字符
RED=$'\033[0;31m';    GREEN=$'\033[0;32m';    YELLOW=$'\033[1;33m'
BLUE=$'\033[0;34m';   CYAN=$'\033[0;36m';     BOLD=$'\033[1m'
NC=$'\033[0m'         # No Color

pass() { echo -e "  ${GREEN}✓${NC} $1"; }
fail() { echo -e "  ${RED}✗${NC} $1"; }
warn() { echo -e "  ${YELLOW}⚠${NC} $1"; }
info() { echo -e "  ${BLUE}➤${NC} $1"; }
h2()   { echo -e "\n${BOLD}${CYAN}━━━ $1 ━━━${NC}"; }

# ── 帮助 ─────────────────────────────────────────────────
show_help() {
    cat << EOF
${BOLD}gc-vision-connect.sh${NC} — 树莓派远程连接与验证工具

${BOLD}用法:${NC}
  ./tools/gc-vision-connect.sh [选项]

${BOLD}选项:${NC}
  (无参数)          快速检查：SSH 连通性 + 关键依赖
  --full, -f        完整检查：连通性 + 系统 + 环境 + 模块验证
  --sync, -s        同步代码到 Pi 并运行验证
  --setup           首次部署全流程（含 venv 创建和包安装）
  --verify, -v      仅运行 headless_verify.py 验证脚本
  --benchmark, -b   运行性能基准测试
  --logs            拉取 Pi 上最新的调试图像到本地 ./local_debug/
  --help, -h        显示此帮助

${BOLD}环境变量（可覆盖默认值）:${NC}
  GC_HOST            SSH 主机别名 (默认: rpi4b)
  GC_USER            Pi 用户名 (默认: g0904)
  GC_PROJECT_DIR     Pi 上项目路径 (默认: ~/Vision)
  GC_VENV            Pi 上虚拟环境路径 (默认: ~/gc_vision_venv)

${BOLD}示例:${NC}
  ./tools/gc-vision-connect.sh                  # 快速连通性检查
  ./tools/gc-vision-connect.sh --full           # 完整环境诊断
  ./tools/gc-vision-connect.sh --sync           # 改完代码后一键同步+验证
  GC_HOST=pi@192.168.1.100 ./tools/gc-vision-connect.sh --full

${BOLD}Windows 用户:${NC} 请在 Git Bash 或 WSL 中运行此脚本。
EOF
    exit 0
}

# ── SSH 执行封装 ─────────────────────────────────────────
ssh_exec() {
    ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no "$SSH_HOST" "$@" 2>&1
}

scp_upload() {
    scp -o ConnectTimeout=5 "$1" "$SSH_HOST:$2" 2>&1
}

# ── 1. SSH 连通性检查 ────────────────────────────────────
check_ssh() {
    h2 "SSH 连通性检查"
    local result
    result=$(ssh_exec "echo 'ALIVE' && hostname && whoami && uname -m" 2>&1) || true

    if echo "$result" | grep -q "ALIVE"; then
        local hostname=$(echo "$result" | grep -v "ALIVE" | head -1)
        local whoami=$(echo "$result" | grep -v "ALIVE" | head -2 | tail -1)
        local arch=$(echo "$result" | grep -v "ALIVE" | tail -1)
        pass "SSH 连接成功 → ${hostname} | 用户: ${whoami} | 架构: ${arch}"
        return 0
    else
        fail "SSH 连接失败"
        echo "  错误信息: $result"
        echo "  请检查: 1) Pi 是否开机 2) IP 是否正确 3) SSH 密钥是否配置"
        return 1
    fi
}

# ── 2. 系统健康检查 ──────────────────────────────────────
check_system() {
    h2 "Pi 系统状态"

    local disk info; disk=$(ssh_exec "df -h / | tail -1 | awk '{print \$3\"/\"\$2\" (\"\$5\")\"}'") || disk="N/A"
    info "磁盘使用: $disk"

    local mem; mem=$(ssh_exec "free -h | grep Mem | awk '{print \$3\"/\"\$2}'") || mem="N/A"
    info "内存使用: $mem"

    local temp; temp=$(ssh_exec "vcgencmd measure_temp 2>/dev/null" || echo "N/A")
    info "CPU 温度: ${temp#*=}"

    local uptime; uptime=$(ssh_exec "uptime -p" 2>/dev/null || echo "N/A")
    info "运行时间: $uptime"

    local disk_avail; disk_avail=$(ssh_exec "df -h / | tail -1 | awk '{print \$4}'") || disk_avail="N/A"
    if [[ "$disk_avail" != "N/A" ]]; then
        local num; num=$(echo "$disk_avail" | sed 's/G//')
        if (( $(echo "$num < 2" | bc -l 2>/dev/null || echo 0) )); then
            warn "磁盘剩余空间不足 2GB！建议清理"
        else
            pass "磁盘剩余空间充足 (${disk_avail})"
        fi
    fi
}

# ── 3. Python 环境检查 ───────────────────────────────────
check_python() {
    h2 "Python 环境"

    local py_ver; py_ver=$(ssh_exec "python3 --version 2>&1") || py_ver=""
    if [[ -n "$py_ver" ]]; then
        pass "$py_ver"
    else
        fail "Python3 未安装"
        return 1
    fi

    local cv_ver; cv_ver=$(ssh_exec "python3 -c 'import cv2; print(cv2.__version__)' 2>&1") || cv_ver=""
    if [[ -n "$cv_ver" ]]; then
        pass "OpenCV $cv_ver"
    else
        fail "OpenCV 未安装或不可导入"
    fi

    local np_ver; np_ver=$(ssh_exec "python3 -c 'import numpy; print(numpy.__version__)' 2>&1") || true
    [[ -n "$np_ver" ]] && pass "NumPy $np_ver" || fail "NumPy 不可用"

    # 虚拟环境检查
    local venv_py="$PI_VENV/bin/python"
    if ssh_exec "test -f $venv_py" 2>/dev/null; then
        pass "虚拟环境存在: $PI_VENV"

        # 检查 venv 中的关键包
        for pkg in "yaml" "serial" "pyzbar"; do
            local pkg_name
            case $pkg in
                yaml) pkg_name="PyYAML" ;;
                serial) pkg_name="PySerial" ;;
                pyzbar) pkg_name="pyzbar" ;;
            esac
            if ssh_exec "$venv_py -c 'import $pkg' 2>&1" 2>/dev/null; then
                pass "  $pkg_name ✓"
            else
                warn "  $pkg_name 未安装 — 执行 pip install"
            fi
        done

        # 检查 OCR 引擎
        if ssh_exec "$venv_py -c 'from ocr_recognition.ocr_engine import OCREngine; e=OCREngine(backend=\"auto\"); print(e.is_ready)' 2>&1" 2>/dev/null | grep -q "True"; then
            pass "  OCR 引擎可用"
        else
            warn "  OCR 引擎不可用（非致命，安装: pip install easyocr）"
        fi
    else
        warn "虚拟环境不存在: $PI_VENV"
        info "运行 --setup 自动创建"
    fi
}

# ── 4. 项目文件检查 ──────────────────────────────────────
check_project() {
    h2 "项目文件"

    if ssh_exec "test -f $PI_PROJECT_DIR/main.py" 2>/dev/null; then
        pass "main.py 存在"
    else
        fail "main.py 不存在！请先同步代码: --sync"
        return 1
    fi

    # 关键文件检查
    local files=(
        "config/serial_config.yaml"
        "config/color_config.yaml"
        "models/wechat_qrcode/detect.prototxt"
        "models/wechat_qrcode/detect.caffemodel"
        "models/wechat_qrcode/sr.prototxt"
        "models/wechat_qrcode/sr.caffemodel"
    )
    local missing=0
    for f in "${files[@]}"; do
        if ssh_exec "test -f $PI_PROJECT_DIR/$f" 2>/dev/null; then
            pass "  $f"
        else
            fail "  $f — 缺失！"
            ((missing++))
        fi
    done

    # 标定文件（可选）
    if ssh_exec "test -f $PI_PROJECT_DIR/config/camera_params.npz" 2>/dev/null; then
        pass "  config/camera_params.npz"
    else
        warn "  config/camera_params.npz 未标定（需现场标定）"
    fi

    if ssh_exec "test -f $PI_PROJECT_DIR/config/perspective_params.npz" 2>/dev/null; then
        pass "  config/perspective_params.npz"
    else
        warn "  config/perspective_params.npz 未标定（需现场标定）"
    fi

    return $missing
}

# ── 5. 外设检查 ──────────────────────────────────────────
check_peripherals() {
    h2 "外设检查"

    # 摄像头
    local video_devs; video_devs=$(ssh_exec "ls /dev/video* 2>/dev/null" || echo "")
    if [[ -n "$video_devs" ]]; then
        pass "摄像头已检测: $(echo "$video_devs" | tr '\n' ' ')"
    else
        warn "未检测到摄像头 (/dev/video*)"
    fi

    # 串口设备
    local tty_devs; tty_devs=$(ssh_exec "ls /dev/ttyACM* /dev/ttyUSB* 2>/dev/null" || echo "")
    if [[ -n "$tty_devs" ]]; then
        pass "串口设备: $(echo "$tty_devs" | tr '\n' ' ')"
        # 检查 dialout 权限
        if ssh_exec "groups | grep -q dialout" 2>/dev/null; then
            pass "  用户已在 dialout 组"
        else
            warn "  用户不在 dialout 组！串口可能 Permission denied"
            info "  修复: sudo usermod -a -G dialout \$USER && 重新登录"
        fi
    else
        warn "未检测到串口设备 (/dev/ttyACM*, /dev/ttyUSB*)"
    fi

    # 网络
    local ip_info; ip_info=$(ssh_exec "hostname -I 2>/dev/null" || echo "N/A")
    info "Pi IP 地址: $ip_info"
}

# ── 6. 运行验证测试 ──────────────────────────────────────
run_verify() {
    h2 "运行全模块验证 (headless_verify.py)"
    info "执行中（最长 120 秒）..."

    local result; result=$(ssh_exec "cd $PI_PROJECT_DIR && HEADLESS=1 $PI_VENV/bin/python tests/headless_verify.py 2>&1") || true

    # 提取通过/失败数
    local passed; passed=$(echo "$result" | grep -oP '通过:\s*\K\d+' || echo "?")
    local total; total=$(echo "$result" | grep -oP '/\s*\K\d+' || echo "?")

    if [[ "$passed" == "$total" ]]; then
        pass "全模块验证: $passed/$total 通过 ✅"
    else
        warn "全模块验证: $passed/$total 通过"
    fi

    # 显示失败项
    echo "$result" | grep '✗' || true

    # 报告路径
    info "详细报告: $PI_PROJECT_DIR/logs/verify_report.txt"
}

# ── 7. 运行性能基准 ──────────────────────────────────────
run_benchmark() {
    h2 "运行性能基准测试"
    info "执行中（最长 180 秒）..."

    ssh_exec "cd $PI_PROJECT_DIR && HEADLESS=1 $PI_VENV/bin/python tests/integration_benchmark.py 2>&1" || true
    info "报告: $PI_PROJECT_DIR/logs/benchmark_report.txt"
}

# ── 8. 代码同步 ──────────────────────────────────────────
sync_code() {
    h2 "同步代码到 Pi"

    info "打包本地项目..."
    local tmp_tar="/tmp/vision_sync_$$.tar.gz"
    cd "$LOCAL_PROJECT_DIR"
    tar -czf "$tmp_tar" \
        --exclude='__pycache__' --exclude='*.pyc' --exclude='.git' \
        --exclude='logs/' --exclude='calib_images*' --exclude='calib_images-backpack/' \
        . 2>/dev/null

    local size; size=$(du -h "$tmp_tar" | cut -f1)
    info "上传 ($size)..."
    scp_upload "$tmp_tar" "/tmp/vision_sync.tar.gz" >/dev/null 2>&1

    info "解压到 $PI_PROJECT_DIR ..."
    ssh_exec "mkdir -p $PI_PROJECT_DIR && tar -xzf /tmp/vision_sync.tar.gz -C $PI_PROJECT_DIR && rm /tmp/vision_sync.tar.gz" 2>&1

    rm -f "$tmp_tar"
    pass "代码同步完成"
}

# ── 9. 拉取调试图像 ─────────────────────────────────────
pull_debug_images() {
    h2 "拉取调试图像"
    local local_dir="$LOCAL_PROJECT_DIR/local_debug"
    mkdir -p "$local_dir"

    info "从 Pi 拉取 logs/debug_*.png 到 $local_dir ..."
    scp -o ConnectTimeout=5 "$SSH_HOST:$PI_PROJECT_DIR/logs/debug_*.png" "$local_dir/" 2>/dev/null || true

    local count; count=$(ls -1 "$local_dir"/debug_*.png 2>/dev/null | wc -l)
    if [[ "$count" -gt 0 ]]; then
        pass "已拉取 $count 张调试图像到 $local_dir/"
    else
        warn "未找到调试图像（先用 DEBUG_SAVE=1 运行主程序）"
    fi
}

# ── 10. 首次部署全流程 ──────────────────────────────────
run_setup() {
    h2 "首次部署全流程"

    # 检查 SSH
    check_ssh || return 1

    # 检查系统
    check_system

    # 创建 venv（如果不存在）
    if ! ssh_exec "test -f $PI_VENV/bin/python" 2>/dev/null; then
        info "创建虚拟环境..."
        ssh_exec "python3 -m venv $PI_VENV --system-site-packages" 2>&1
        pass "虚拟环境已创建"
    else
        pass "虚拟环境已存在，跳过创建"
    fi

    # 安装 Python 包
    info "安装 Python 依赖..."
    ssh_exec "$PI_VENV/bin/pip install --upgrade pip setuptools wheel -q" 2>&1
    ssh_exec "$PI_VENV/bin/pip install PyYAML pyzbar pyserial -q" 2>&1
    pass "Python 包安装完成"

    # 确保日志目录存在
    ssh_exec "mkdir -p $PI_PROJECT_DIR/logs" 2>/dev/null

    # 同步代码
    sync_code

    # 运行验证
    run_verify

    echo ""
    echo -e "${GREEN}${BOLD}╔══════════════════════════════════════╗${NC}"
    echo -e "${GREEN}${BOLD}║   🎉 部署完成！Pi 已就绪             ║${NC}"
    echo -e "${GREEN}${BOLD}╚══════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  运行程序: ${CYAN}ssh $SSH_HOST 'cd $PI_PROJECT_DIR && HEADLESS=1 $PI_VENV/bin/python main.py'${NC}"
    echo -e "  调试模式: ${CYAN}ssh $SSH_HOST 'cd $PI_PROJECT_DIR && DEBUG_SAVE=1 HEADLESS=1 $PI_VENV/bin/python main.py'${NC}"
}

# ── 主入口 ───────────────────────────────────────────────
main() {
    echo -e "${BOLD}${CYAN}"
    echo "  ╔══════════════════════════════════════════╗"
    echo "  ║   gc-vision-connect — Pi 远程工具       ║"
    echo "  ╚══════════════════════════════════════════╝"
    echo -e "${NC}"
    echo "  目标: $SSH_HOST | 项目: $PI_PROJECT_DIR"
    echo ""

    local mode="${1:-quick}"

    case "$mode" in
        --help|-h)
            show_help
            ;;
        --setup)
            run_setup
            ;;
        --full|-f)
            check_ssh || exit 1
            check_system
            check_python
            check_project
            check_peripherals
            run_verify
            echo ""
            echo -e "${GREEN}${BOLD}完整检查完成。${NC}"
            ;;
        --sync|-s)
            check_ssh || exit 1
            sync_code
            run_verify
            ;;
        --verify|-v)
            check_ssh || exit 1
            run_verify
            ;;
        --benchmark|-b)
            check_ssh || exit 1
            run_benchmark
            ;;
        --logs)
            check_ssh || exit 1
            pull_debug_images
            ;;
        *)
            # 默认快速检查
            check_ssh || exit 1
            check_system
            check_python
            check_project
            echo ""
            echo -e "  💡 运行 ${CYAN}--full${NC} 进行完整检查（含外设+验证）"
            echo -e "  💡 运行 ${CYAN}--sync${NC} 同步代码并验证"
            echo -e "  💡 运行 ${CYAN}--help${NC} 查看全部选项"
            ;;
    esac
}

main "$@"
