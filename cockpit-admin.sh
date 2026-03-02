#!/bin/bash
#
# API Cockpit - Multi-Node Admin Script
# Manages health checks, service restarts, and alerting across 3 nodes
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="${SCRIPT_DIR}/config"
LOG_DIR="${SCRIPT_DIR}/logs"

# Load environment variables
if [ -f "${CONFIG_DIR}/.env" ]; then
    source "${CONFIG_DIR}/.env"
else
    echo "Error: ${CONFIG_DIR}/.env not found. Copy .env.example and configure it."
    exit 1
fi

# Ensure log directory exists
mkdir -p "${LOG_DIR}"

# Node definitions
declare -A NODES
NODES=(
    ["central"]="43.163.225.27"
    ["silicon"]="170.106.73.160"
    ["tokyo"]="43.167.192.145"
)

# Timestamp for logging
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
LOG_FILE="${LOG_DIR}/admin_$(date '+%Y%m%d').log"

# Function to log messages
log() {
    echo "[${TIMESTAMP}] $*" | tee -a "${LOG_FILE}"
}

# Function to send Telegram alert
send_telegram_alert() {
    local message="$1"
    
    if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
        curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
            -d "chat_id=${TELEGRAM_CHAT_ID}" \
            -d "text=${message}" \
            -d "parse_mode=Markdown" > /dev/null 2>&1
    fi
}

# Check if node is reachable
check_node_reachable() {
    local node_name="$1"
    local node_ip="${NODES[$node_name]}"
    
    log "Checking ${node_name} (${node_ip})..."
    
    if ping -c 2 -W 2 "${node_ip}" > /dev/null 2>&1; then
        log "${node_name} is reachable"
        return 0
    else
        log "${node_name} is NOT reachable"
        send_telegram_alert "❌ *NODE DOWN*: ${node_name} (${node_ip}) is unreachable"
        return 1
    fi
}

# Check OpenClaw gateway status
check_gateway_status() {
    local node_name="$1"
    local node_ip="${NODES[$node_name]}"
    
    log "Checking OpenClaw gateway on ${node_name}..."
    
    local status
    status=$(ssh -o ConnectTimeout=5 -o BatchMode=yes "root@${node_ip}" "openclaw status 2>&1" || echo "failed")
    
    if [[ "$status" == *"failed"* ]]; then
        log "${node_name} gateway check failed"
        send_telegram_alert "⚠️ *GATEWAY ISSUE*: ${node_name} gateway check failed"
        return 1
    elif [[ "$status" == *"running"* ]]; then
        log "${node_name} gateway is running"
        return 0
    else
        log "${node_name} gateway is stopped"
        send_telegram_alert "⚠️ *GATEWAY STOPPED*: ${node_name} gateway is not running"
        return 2
    fi
}

# Check CPU and memory usage
check_system_resources() {
    local node_name="$1"
    local node_ip="${NODES[$node_name]}"
    
    log "Checking system resources on ${node_name}..."
    
    local cpu_usage
    local mem_usage
    local cpu_load
    
    cpu_usage=$(ssh -o ConnectTimeout=5 -o BatchMode=yes "root@${node_ip}" "top -bn1 | grep 'Cpu(s)' | sed 's/.*, *\([0-9.]*\)%* id.*/\1/' | awk '{print 100 - \$1}'") || cpu_usage="unknown"
    mem_usage=$(ssh -o ConnectTimeout=5 -o BatchMode=yes "root@${node_ip}" "free | grep Mem | awk '{printf \"%.2f\", \$3/\$2 * 100.0}'") || mem_usage="unknown"
    cpu_load=$(ssh -o ConnectTimeout=5 -o BatchMode=yes "root@${node_ip}" "uptime | awk -F'load average:' '{print \$2}' | awk -F, '{print \$1}' | xargs") || cpu_load="unknown"
    
    if [ "$cpu_usage" != "unknown" ] && (( $(echo "$cpu_usage > 90" | bc -l) )); then
        send_telegram_alert "🔥 *HIGH CPU*: ${node_name} CPU at ${cpu_usage}%"
    fi
    
    if [ "$mem_usage" != "unknown" ] && (( $(echo "$mem_usage > 90" | bc -l) )); then
        send_telegram_alert "🔥 *HIGH MEMORY*: ${node_name} memory at ${mem_usage}%"
    fi
    
    echo "CPU: ${cpu_usage}%, Memory: ${mem_usage}%, Load: ${cpu_load}"
}

# Restart OpenClaw gateway
restart_gateway() {
    local node_name="$1"
    local node_ip="${NODES[$node_name]}"
    
    log "Restarting OpenClaw gateway on ${node_name}..."
    send_telegram_alert "🔄 *RESTARTING*: ${node_name} gateway"
    
    ssh -o ConnectTimeout=10 -o BatchMode=yes "root@${node_ip}" "openclaw gateway restart" || return 1
    
    sleep 5
    
    if check_gateway_status "${node_name}"; then
        log "${node_name} gateway restarted successfully"
        send_telegram_alert "✅ *RESTARTED*: ${node_name} gateway is running"
        return 0
    else
        log "${node_name} gateway restart failed"
        send_telegram_alert "❌ *RESTART FAILED*: ${node_name} gateway did not come up"
        return 1
    fi
}

# Check all nodes
check_all_nodes() {
    log "=== Starting full health check ==="
    
    for node_name in "${!NODES[@]}"; do
        echo ""
        echo "--- ${node_name} ---"
        
        if check_node_reachable "${node_name}"; then
            check_gateway_status "${node_name}" || true
            check_system_resources "${node_name}"
        fi
    done
    
    log "=== Health check complete ==="
}

# Sync skills to all nodes
sync_skills() {
    log "=== Starting skills sync ==="
    
    for node_name in "${!NODES[@]}"; do
        if [ "$node_name" != "silicon" ]; then  # Skip self
            local node_ip="${NODES[$node_name]}"
            log "Syncing skills to ${node_name}..."
            
            rsync -avz --delete ~/.openclaw/workspace/skills/ "root@${node_ip}:~/.openclaw/workspace/skills/" || {
                log "Failed to sync to ${node_name}"
                send_telegram_alert "❌ *SYNC FAILED*: Could not sync skills to ${node_name}"
                continue
            }
            
            log "Successfully synced to ${node_name}"
        fi
    done
    
    send_telegram_alert "✅ *SYNC COMPLETE*: Skills synced to all nodes"
    log "=== Skills sync complete ==="
}

# Show help
show_help() {
    cat <<EOF
API Cockpit - Multi-Node Admin Script

Usage: $0 [COMMAND]

Commands:
  health        - Run full health check on all nodes
  status <node> - Check specific node status (central|silicon|tokyo)
  restart <node>- Restart gateway on specific node
  sync          - Sync skills to all nodes
  help          - Show this help

Nodes:
  central   - 43.163.225.27
  silicon   - 170.106.73.160 (localhost)
  tokyo     - 43.167.192.145

Examples:
  $0 health
  $0 status central
  $0 restart tokyo
  $0 sync
EOF
}

# Main execution
main() {
    local command="${1:-}"
    
    case "$command" in
        health)
            check_all_nodes
            ;;
        status)
            local node_name="${2:-}"
            if [ -z "$node_name" ] || [ -z "${NODES[$node_name]:-}" ]; then
                echo "Error: Valid node required (central|silicon|tokyo)"
                exit 1
            fi
            check_node_reachable "$node_name" && check_gateway_status "$node_name" && check_system_resources "$node_name"
            ;;
        restart)
            local node_name="${2:-}"
            if [ -z "$node_name" ] || [ -z "${NODES[$node_name]:-}" ]; then
                echo "Error: Valid node required (central|silicon|tokyo)"
                exit 1
            fi
            restart_gateway "$node_name"
            ;;
        sync)
            sync_skills
            ;;
        help|--help|-h)
            show_help
            ;;
        "")
            show_help
            ;;
        *)
            echo "Error: Unknown command '$command'"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

main "$@"
