#!/usr/bin/env bash
set -euo pipefail

# ── MetaEduBase 一键开发启动脚本 ──────────────────────────────
# 用法:
#   ./dev.sh          # 启动全部服务 (幂等: 已运行的服务跳过)
#   ./dev.sh infra    # 仅启动基础设施 (PostgreSQL / Redis / MinIO)
#   ./dev.sh backend  # 仅重启后端 (强制重启)
#   ./dev.sh frontend  # 仅重启前端 (强制重启)
#   ./dev.sh celery   # 仅启动 Celery Worker
#   ./dev.sh init-db  # 显式初始化开发数据库 (迁移 + 默认开发账号)
#   ./dev.sh init-test-db # 显式初始化测试数据库 (建库 + 扩展 + 迁移)
#   ./dev.sh stop     # 停止全部服务
#   ./dev.sh status   # 查看运行状态
#   ./dev.sh logs     # 查看后端日志 (logs frontend/celery 查看)
#
# 日常开发:
#   首次: ./dev.sh                    → 全部启动
#   改代码: FastAPI 自动 (--reload) / Celery 自动 (--autoreload) / 前端 HMR 自动
#   重启后端: ./dev.sh backend         → 仅重启后端
#   下班: ./dev.sh stop               → 停止全部
#
# 环境变量 (可选):
#   METAEDU_INFRA   - infra 启动模式: docker | local (默认: auto-detect)
#   METAEDU_PG_DIR  - 本地 PostgreSQL 数据目录 (默认: /opt/homebrew/var/postgresql@16)
#   METAEDU_PG_BIN  - 本地 PostgreSQL bin 目录 (默认: /opt/homebrew/opt/postgresql@16/bin)

CYAN='\033[0;36m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; DIM='\033[2m'; NC='\033[0m'

log()  { echo -e "${CYAN}[MetaEdu]${NC} $*"; }
ok()   { echo -e "${GREEN}[OK]${NC} $*"; }
skip() { echo -e "${DIM}[SKIP]${NC} $1 — $2"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
die()  { echo -e "${RED}[FAIL]${NC} $*"; exit 1; }

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
SERVER_DIR="$PROJECT_ROOT/packages/server-python"
WEB_DIR="$PROJECT_ROOT/packages/web"
DEPLOY_DIR="$PROJECT_ROOT/deploy"
LOG_DIR="$PROJECT_ROOT/.dev-logs"
PG_BIN="${METAEDU_PG_BIN:-/opt/homebrew/opt/postgresql@16/bin}"
PG_DIR="${METAEDU_PG_DIR:-/opt/homebrew/var/postgresql@16}"
INFRA_MODE="${METAEDU_INFRA:-}"

mkdir -p "$LOG_DIR"

wait_for_url() {
  local url=$1 name=$2 timeout=${3:-30}
  local elapsed=0
  while ! curl -sf "$url" >/dev/null 2>&1; do
    sleep 1
    elapsed=$((elapsed + 1))
    if [[ $elapsed -ge $timeout ]]; then
      warn "$name 在 ${timeout}s 内未就绪（进程可能仍在启动中）"
      return 1
    fi
  done
  return 0
}

colima_is_running() {
  command -v colima &>/dev/null && colima status &>/dev/null 2>&1
}

docker_is_available() {
  command -v docker &>/dev/null && docker info &>/dev/null 2>&1
}

compose_cmd() {
  if command -v docker-compose &>/dev/null; then
    docker-compose "$@"
  else
    docker compose "$@"
  fi
}

backend_is_running() {
  curl -sf http://localhost:8000/api/v1/health >/dev/null 2>&1
}

celery_is_running() {
  pgrep -f "celery.*worker" >/dev/null 2>&1
}

frontend_is_running() {
  curl -sf http://localhost:3000 >/dev/null 2>&1 || curl -sf http://localhost:3001 >/dev/null 2>&1
}

detect_infra_mode() {
  if [[ -n "$INFRA_MODE" ]]; then
    echo "$INFRA_MODE"
    return
  fi
  if docker_is_available; then
    echo "docker"
  elif command -v colima &>/dev/null; then
    echo "docker"
  else
    echo "local"
  fi
}

ensure_colima() {
  if colima_is_running; then
    ok "Colima VM 已运行"
    return
  fi
  if ! command -v colima &>/dev/null; then
    die "Colima 未安装，请执行: brew install colima docker docker-compose"
  fi
  log "启动 Colima VM..."
  colima start --cpu 2 --memory 4 --disk 60
  ok "Colima VM 已启动"
}

pg_is_running() {
  "$PG_BIN/pg_isready" -q 2>/dev/null
}

ensure_pg_local() {
  if pg_is_running; then
    ok "PostgreSQL 已运行"
    return
  fi
  if [[ ! -d "$PG_DIR" ]]; then
    die "PostgreSQL 数据目录不存在: $PG_DIR"
  fi
  log "启动本地 PostgreSQL..."
  "$PG_BIN/pg_ctl" -D "$PG_DIR" -l "$PG_DIR/postmaster.log" start -w
  ok "PostgreSQL 已启动"
}

ensure_db_and_user() {
  local db_exists user_exists
  db_exists=$("$PG_BIN/psql" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='metaedu'" 2>/dev/null || echo "")
  if [[ "$db_exists" != "1" ]]; then
    log "创建数据库 metaedu..."
    "$PG_BIN/psql" -d postgres -c "CREATE DATABASE metaedu;" 2>/dev/null || true
  fi
  user_exists=$("$PG_BIN/psql" -d postgres -tAc "SELECT 1 FROM pg_roles WHERE rolname='metaedu'" 2>/dev/null || echo "")
  if [[ "$user_exists" != "1" ]]; then
    log "创建用户 metaedu..."
    "$PG_BIN/psql" -d postgres -c "CREATE USER metaedu WITH PASSWORD 'dev_only_123' SUPERUSER;" 2>/dev/null || true
    "$PG_BIN/psql" -d postgres -c "ALTER DATABASE metaedu OWNER TO metaedu;" 2>/dev/null || true
  fi
  local ext_check
  ext_check=$("$PG_BIN/psql" -U metaedu -d metaedu -tAc "SELECT 1 FROM pg_extension WHERE extname='vector'" 2>/dev/null || echo "")
  if [[ "$ext_check" != "1" ]]; then
    log "安装 pgvector 扩展..."
    "$PG_BIN/psql" -U metaedu -d metaedu -c "CREATE EXTENSION IF NOT EXISTS vector;" 2>/dev/null || warn "pgvector 扩展安装失败，需要手动安装"
  fi
  ext_check=$("$PG_BIN/psql" -U metaedu -d metaedu -tAc "SELECT 1 FROM pg_extension WHERE extname='ltree'" 2>/dev/null || echo "")
  if [[ "$ext_check" != "1" ]]; then
    log "安装 ltree 扩展..."
    "$PG_BIN/psql" -U metaedu -d metaedu -c "CREATE EXTENSION IF NOT EXISTS ltree;" 2>/dev/null || warn "ltree 扩展安装失败"
  fi
  ok "数据库 metaedu 就绪"
}

ensure_docker_infra() {
  if ! command -v docker &>/dev/null; then
    die "Docker 未安装，请执行: brew install colima docker docker-compose"
  fi
  if ! docker_is_available; then
    if command -v colima &>/dev/null; then
      ensure_colima
    else
      die "Docker 未运行，请先启动 Colima 或 Docker Desktop"
    fi
  fi
  if [[ ! -f "$DEPLOY_DIR/.env" ]]; then
    log "复制 .env.example -> .env"
    cp "$DEPLOY_DIR/.env.example" "$DEPLOY_DIR/.env"
  fi

  if docker_is_available && docker ps --format '{{.Names}}' 2>/dev/null | grep -q postgres; then
    ok "Docker 基础设施已运行"
    return
  fi

  log "启动 Docker 基础设施 (PostgreSQL + Redis + MinIO)..."
  compose_cmd -f "$DEPLOY_DIR/docker-compose.dev.yml" up -d
  ok "Docker 基础设施已启动"
}

start_infra() {
  local mode
  mode=$(detect_infra_mode)
  log "基础设施模式: $mode"

  if [[ "$mode" == "docker" ]]; then
    if ! docker_is_available && ! command -v colima &>/dev/null; then
      warn "Docker/Colima 不可用，降级到本地 PostgreSQL 模式"
      warn "提示: 执行 'colima start' 启用 Docker 全栈模式 (含 Redis + MinIO)"
      ensure_pg_local
      ensure_db_and_user
      warn "Redis 和 MinIO 未启动 (本地开发可选，部分功能受限)"
      return
    fi
    ensure_docker_infra
  else
    ensure_pg_local
    ensure_db_and_user
    warn "Redis 和 MinIO 未启动 (本地开发可选，部分功能受限)"
  fi
}

init_dev_db() {
  log "初始化开发数据库 (迁移 + 默认开发账号)..."
  start_infra
  cd "$SERVER_DIR"
  if [[ ! -d ".venv" ]]; then
    log "创建 Python 虚拟环境..."
    python3 -m venv .venv
    log "安装后端依赖..."
    .venv/bin/pip install -e ".[dev,ai]" -q
  fi
  if ! .venv/bin/python -c "import alembic" 2>/dev/null; then
    log "安装后端依赖..."
    .venv/bin/pip install -e ".[dev,ai]" -q
  fi
  ALLOW_DEFAULT_SEED=true .venv/bin/python -m app.shared.infrastructure.dev_setup
  ok "开发数据库初始化完成"
}

init_test_db() {
  log "初始化测试数据库 (创建库 + 扩展 + Alembic upgrade head)..."
  start_infra
  cd "$SERVER_DIR"
  if [[ ! -d ".venv" ]]; then
    log "创建 Python 虚拟环境..."
    python3 -m venv .venv
    log "安装后端依赖..."
    .venv/bin/pip install -e ".[dev,ai]" -q
  fi
  if ! .venv/bin/python -c "import alembic" 2>/dev/null; then
    log "安装后端依赖..."
    .venv/bin/pip install -e ".[dev,ai]" -q
  fi
  .venv/bin/python -m app.shared.infrastructure.test_db_setup
  ok "测试数据库初始化完成"
}

start_backend() {
  if backend_is_running; then
    skip "Backend" "已运行 (http://localhost:8000)"
    return
  fi

  local db_ok=false
  if pg_is_running 2>/dev/null; then
    db_ok=true
  elif docker_is_available && docker ps --format '{{.Names}}' 2>/dev/null | grep -q postgres; then
    db_ok=true
  fi
  if [[ "$db_ok" != "true" ]]; then
    die "PostgreSQL 未运行，请先执行 ./dev.sh infra"
  fi
  cd "$SERVER_DIR"
  if [[ ! -d ".venv" ]]; then
    log "创建 Python 虚拟环境..."
    python3 -m venv .venv
    log "安装后端依赖..."
    .venv/bin/pip install -e ".[dev,ai]" -q
  fi
  if ! .venv/bin/python -c "import uvicorn" 2>/dev/null; then
    log "安装后端依赖..."
    .venv/bin/pip install -e ".[dev,ai]" -q
  fi
  log "启动后端服务 (port 8000)..."
  .venv/bin/python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 \
    > "$LOG_DIR/backend.log" 2>&1 &
  local pid=$!
  echo "$pid" > "$LOG_DIR/backend.pid"
  ok "后端已启动 (PID: $pid)"
  log "等待后端就绪..."
  if wait_for_url http://localhost:8000/api/v1/health "Backend" 30; then
    ok "后端就绪 — http://localhost:8000"
  fi
}

restart_backend() {
  log "重启后端..."
  if [[ -f "$LOG_DIR/backend.pid" ]]; then
    kill "$(cat "$LOG_DIR/backend.pid")" 2>/dev/null || true
    rm -f "$LOG_DIR/backend.pid"
  fi
  pkill -f "uvicorn app.main:app" 2>/dev/null || true
  sleep 1

  local db_ok=false
  if pg_is_running 2>/dev/null; then db_ok=true
  elif docker_is_available && docker ps --format '{{.Names}}' 2>/dev/null | grep -q postgres; then db_ok=true
  fi
  if [[ "$db_ok" != "true" ]]; then
    die "PostgreSQL 未运行，请先执行 ./dev.sh infra"
  fi

  cd "$SERVER_DIR"
  .venv/bin/python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 \
    > "$LOG_DIR/backend.log" 2>&1 &
  local pid=$!
  echo "$pid" > "$LOG_DIR/backend.pid"
  ok "后端已重启 (PID: $pid)"
  if wait_for_url http://localhost:8000/api/v1/health "Backend" 30; then
    ok "后端就绪 — http://localhost:8000"
  fi

  # Also restart Celery if it was running
  if celery_is_running; then
    log "重启 Celery Worker..."
    pkill -f "celery.*worker" 2>/dev/null || true
    if [[ -f "$LOG_DIR/celery.pid" ]]; then rm -f "$LOG_DIR/celery.pid"; fi
    sleep 1
    start_celery
  fi
}

start_frontend() {
  if frontend_is_running; then
    skip "Frontend" "已运行 (http://localhost:3000)"
    return
  fi

  cd "$WEB_DIR"
  if [[ ! -d "node_modules" ]]; then
    log "安装前端依赖..."
    pnpm install
  fi
  log "启动前端服务 (port 3000)..."
  npx vite --port 3000 > "$LOG_DIR/frontend.log" 2>&1 &
  local pid=$!
  echo "$pid" > "$LOG_DIR/frontend.pid"
  ok "前端已启动 (PID: $pid)"
  log "等待前端就绪..."
  if wait_for_url http://localhost:3000 "Frontend" 15; then
    ok "前端就绪 — http://localhost:3000"
  fi
}

start_celery() {
  if celery_is_running; then
    skip "Celery Worker" "已运行"
    return
  fi

  local redis_ok=false
  if docker_is_available && docker ps --format '{{.Names}}' 2>/dev/null | grep -q redis; then
    redis_ok=true
  elif nc -z localhost 6379 2>/dev/null; then
    redis_ok=true
  fi
  if [[ "$redis_ok" != "true" ]]; then
    warn "Redis 未运行，Celery Worker 跳过（文档解析/向量化任务将不可用）"
    warn "请先执行 ./dev.sh infra 启动 Redis"
    return
  fi

  cd "$SERVER_DIR"
  if [[ ! -d ".venv" ]]; then
    log "创建 Python 虚拟环境..."
    python3 -m venv .venv
    .venv/bin/pip install -e ".[dev,ai]" -q
  fi
  log "启动 Celery Worker..."
  .venv/bin/python scripts/celery_worker_dev.py \
    > "$LOG_DIR/celery.log" 2>&1 &
  local pid=$!
  echo "$pid" > "$LOG_DIR/celery.pid"
  ok "Celery Worker 已启动 (PID: $pid)"
}

stop_all() {
  log "停止服务..."
  if [[ -f "$LOG_DIR/backend.pid" ]]; then
    kill "$(cat "$LOG_DIR/backend.pid")" 2>/dev/null || true
    rm -f "$LOG_DIR/backend.pid"
  fi
  pkill -f "uvicorn app.main:app" 2>/dev/null || true
  if [[ -f "$LOG_DIR/celery.pid" ]]; then
    kill "$(cat "$LOG_DIR/celery.pid")" 2>/dev/null || true
    rm -f "$LOG_DIR/celery.pid"
  fi
  pkill -f "celery.*worker" 2>/dev/null || true
  if [[ -f "$LOG_DIR/frontend.pid" ]]; then
    kill "$(cat "$LOG_DIR/frontend.pid")" 2>/dev/null || true
    rm -f "$LOG_DIR/frontend.pid"
  fi
  pkill -f "vite" 2>/dev/null || true
  if docker_is_available; then
    compose_cmd -f "$DEPLOY_DIR/docker-compose.dev.yml" down 2>/dev/null || true
  fi
  if pg_is_running 2>/dev/null; then
    "$PG_BIN/pg_ctl" -D "$PG_DIR" stop -m fast 2>/dev/null || true
    ok "本地 PostgreSQL 已停止"
  fi
  if command -v colima &>/dev/null && colima_is_running; then
    colima stop 2>/dev/null || true
    ok "Colima VM 已停止"
  fi
  ok "全部服务已停止"
}

show_status() {
  echo ""
  echo "┌──────────────────────────────────────────────┐"
  echo "│        MetaEduBase 服务状态                   │"
  echo "├──────────────────────────────────────────────┤"

  if docker_is_available && docker ps --format '{{.Names}}' 2>/dev/null | grep -q postgres; then
    echo "│  PostgreSQL    ✅ Docker (localhost:5432)      │"
  elif pg_is_running 2>/dev/null; then
    echo "│  PostgreSQL    ✅ 本地  (localhost:5432)       │"
  else
    echo "│  PostgreSQL    ❌ 未运行                      │"
  fi

  if docker_is_available && docker ps --format '{{.Names}}' 2>/dev/null | grep -q redis; then
    echo "│  Redis         ✅ Docker (localhost:6379)      │"
  else
    echo "│  Redis         — 未运行                      │"
  fi

  if docker_is_available && docker ps --format '{{.Names}}' 2>/dev/null | grep -q minio; then
    echo "│  MinIO         ✅ Docker (localhost:9000)      │"
  else
    echo "│  MinIO         — 未运行                      │"
  fi

  if backend_is_running; then
    echo "│  Backend       ✅ 运行中 (localhost:8000)     │"
  else
    echo "│  Backend       ❌ 未运行                      │"
  fi

  if celery_is_running; then
    echo "│  Celery Worker ✅ 运行中 (文档解析/向量化)     │"
  else
    echo "│  Celery Worker ❌ 未运行 (文档解析/向量化不可用) │"
  fi

  if curl -sf http://localhost:3000 >/dev/null 2>&1; then
    echo "│  Frontend      ✅ 运行中 (localhost:3000)     │"
  elif curl -sf http://localhost:3001 >/dev/null 2>&1; then
    echo "│  Frontend      ✅ 运行中 (localhost:3001)     │"
  else
    echo "│  Frontend      ❌ 未运行                      │"
  fi

  if colima_is_running; then
    echo "│  Colima VM     ✅ 运行中                      │"
  else
    echo "│  Colima VM     — 未运行                       │"
  fi

  echo "├──────────────────────────────────────────────┤"
  echo "│  开发账号: admin / admin123 (需先 init-db)     │"
  echo "│  API 文档: http://localhost:8000/docs         │"
  echo "│  前端地址: http://localhost:3000              │"
  echo "│  日志目录: .dev-logs/                         │"
  echo "└──────────────────────────────────────────────┘"
  echo ""
}

main() {
  local cmd="${1:-all}"

  case "$cmd" in
    infra)
      start_infra
      ;;
    backend)
      restart_backend
      ;;
    frontend)
      cd "$WEB_DIR"
      if [[ -f "$LOG_DIR/frontend.pid" ]]; then
        kill "$(cat "$LOG_DIR/frontend.pid")" 2>/dev/null || true
        rm -f "$LOG_DIR/frontend.pid"
      fi
      pkill -f "vite" 2>/dev/null || true
      sleep 1
      start_frontend
      ;;
    all)
      start_infra
      start_backend
      start_celery
      start_frontend
      echo ""
      show_status
      ;;
    celery)
      start_celery
      ;;
    init-db)
      init_dev_db
      ;;
    init-test-db)
      init_test_db
      ;;
    stop)
      stop_all
      ;;
    status)
      show_status
      ;;
    logs)
      local target="${2:-backend}"
      if [[ "$target" == "backend" ]]; then
        tail -f "$LOG_DIR/backend.log"
      elif [[ "$target" == "frontend" ]]; then
        tail -f "$LOG_DIR/frontend.log"
      elif [[ "$target" == "celery" ]]; then
        tail -f "$LOG_DIR/celery.log"
      else
        die "未知日志目标: $target (可选: backend, frontend, celery)"
      fi
      ;;
    *)
      echo "用法: $0 {all|infra|backend|frontend|celery|init-db|init-test-db|stop|status|logs}"
      echo ""
      echo "  all       启动全部服务 (幂等: 已运行则跳过)"
      echo "  infra     仅启动基础设施 (PostgreSQL/Redis/MinIO)"
      echo "  backend   重启后端"
      echo "  frontend  重启前端"
      echo "  celery    仅启动 Celery Worker"
      echo "  init-db   显式初始化开发数据库 (迁移 + 默认开发账号)"
      echo "  init-test-db 显式初始化测试数据库 (建库 + 扩展 + 迁移)"
      echo "  stop      停止全部服务"
      echo "  status    查看运行状态"
      echo "  logs      查看日志 (backend/frontend/celery)"
      echo ""
      echo "日常开发:"
      echo "  首次:  ./dev.sh            → 全部启动"
      echo "  改代码: 无需操作            → --reload / HMR 自动生效"
      echo "  重启后端: ./dev.sh backend  → 仅重启后端"
      echo "  下班:  ./dev.sh stop       → 停止全部"
      exit 1
      ;;
  esac
}

main "$@"
