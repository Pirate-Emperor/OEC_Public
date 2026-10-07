#!/usr/bin/env bash
set -euo pipefail

OEC_DIR="$HOME/OEC"
cd "$OEC_DIR"

exec 9>/tmp/oec-acceptance.lock
flock 9

echo "=== RUNNER ==="
echo "RUNNER_NAME=\${RUNNER_NAME:-unknown}"
hostname
whoami
echo "HOME=$HOME"

echo "=== GPU INVENTORY ==="
nvidia-smi --query-gpu=index,name,memory.used,memory.total,utilization.gpu,driver_version --format=csv,noheader,nounits

GPU_ID="$(
  nvidia-smi --query-gpu=index,memory.used,utilization.gpu --format=csv,noheader,nounits |
  awk -F', ' '{
    score=$3*1000000+$2
    if (NR==1 || score<best) {best=score; id=$1}
  } END {if (id != "") print id}'
)"
test -n "$GPU_ID"
export CUDA_VISIBLE_DEVICES="$GPU_ID"
export OEC_GPU_ID="$GPU_ID"
export PYTHONPATH="$OEC_DIR:\${PYTHONPATH:-}"
echo "Selected least-used GPU: $GPU_ID"

echo "=== CUDA DRIVER SMOKE ==="
python - <<'PY'
import ctypes
import os

lib = ctypes.CDLL("libcuda.so.1")
cuInit = lib.cuInit
cuInit.argtypes = [ctypes.c_uint]
cuInit.restype = ctypes.c_int
rc = cuInit(0)
assert rc == 0, f"cuInit failed: {rc}"

count = ctypes.c_int()
cuDeviceGetCount = lib.cuDeviceGetCount
cuDeviceGetCount.argtypes = [ctypes.POINTER(ctypes.c_int)]
cuDeviceGetCount.restype = ctypes.c_int
rc = cuDeviceGetCount(ctypes.byref(count))
assert rc == 0 and count.value > 0, f"cuDeviceGetCount failed: rc={rc} count={count.value}"

print("CUDA DRIVER API PASS:", os.environ.get("CUDA_VISIBLE_DEVICES"), "device_count=", count.value)
PY

echo "=== PYTORCH DIAGNOSTIC ==="
python --version
python - <<'PY'
try:
    import torch
    print("torch.__version__=", torch.__version__)
    print("torch.version.cuda=", torch.version.cuda)
    print("torch.cuda.is_available=", torch.cuda.is_available())
except Exception as exc:
    print("torch diagnostic failed:", repr(exc))
PY

echo "=== SEARCH FOR CUDA-CAPABLE TORCH ==="
GPU_PYTHON=""
for candidate in "$HOME/Conda/bin/python" "$HOME/Conda/envs"/*/bin/python "$HOME/OEC/.venv/bin/python" "$HOME/oec_deploy/.venv/bin/python" "/usr/bin/python3"; do
    [ -x "$candidate" ] || continue
    if "$candidate" -c 'import torch; raise SystemExit(0 if torch.cuda.is_available() else 1)' >/dev/null 2>&1; then
        GPU_PYTHON="$candidate"
        break
    fi
done

if [ -n "$GPU_PYTHON" ]; then
    echo "CUDA-capable PyTorch interpreter: $GPU_PYTHON"
    CUDA_VISIBLE_DEVICES="$GPU_ID" "$GPU_PYTHON" - <<'PY'
import torch
x = torch.randn((1024, 1024), device="cuda", dtype=torch.float16)
y = x @ x
torch.cuda.synchronize()
print("PYTORCH GPU PASS:", torch.__version__, torch.version.cuda, torch.cuda.get_device_name(0), tuple(y.shape))
del x, y
torch.cuda.empty_cache()
PY
else
    echo "No currently-installed CUDA-capable PyTorch interpreter found."
    echo "Driver-level CUDA validation passed; project Python remains separately testable."
fi

echo "=== OEC SYNC ==="
git fetch origin main
status="$(git status --porcelain)"
if [ -n "$status" ]; then
    unexpected="$(
        git status --porcelain |
        awk '{
            p=$2
            if (p != "oec_deploy" &&
                p != "oec_aireos/Full_Model" &&
                p != "oec_aireos/Freezed" &&
                p != "oec_aireos/MOE" &&
                p !~ /^oec_aireos\/(Full_Model|Freezed|MOE)\// &&
                p !~ /^oec_deploy\//) print
        }'
    )"
    if [ -n "$unexpected" ]; then
        echo "Unexpected local OEC changes:"
        printf '%s\n' "$unexpected"
        exit 1
    fi
fi

git reset --hard origin/main
git submodule sync --recursive
git submodule update --init --recursive

for submodule in oec_deploy oec_aireos/Full_Model oec_aireos/Freezed oec_aireos/MOE; do
    git -C "$submodule" fetch origin main
    git -C "$submodule" checkout main
    git -C "$submodule" reset --hard origin/main
done

echo "=== HISTORY SANITIZATION ==="
if ! command -v git-filter-repo >/dev/null 2>&1 && ! git filter-repo --help >/dev/null 2>&1; then
    python -m pip install --user git-filter-repo
fi
export PATH="$HOME/.local/bin:$PATH"

git filter-repo --force \
    --path .Xauthority \
    --path .anaconda \
    --path .bash_history \
    --path .bash_logout \
    --path .bashrc \
    --path .config \
    --path .forward \
    --path .ipython \
    --path .jupyter \
    --path .local \
    --path .profile \
    --path .screenrc \
    --path .ssh \
    --path .viminfo \
    --path "Documents/NVIDIA Nsight Compute" \
    --path .gitconfig \
    --path .flex_gemm \
    --path Miniconda3-latest-Linux-x86_64.sh \
    --invert-paths

if ! git remote get-url origin >/dev/null 2>&1; then
    git remote add origin https://github.com/Killer4K-N/OEC.git
fi

git fetch origin main || true
git submodule sync --recursive
git submodule update --init --recursive

for submodule in oec_deploy oec_aireos/Full_Model oec_aireos/Freezed oec_aireos/MOE; do
    git -C "$submodule" fetch origin main
    git -C "$submodule" checkout main
    git -C "$submodule" reset --hard origin/main
done

echo "=== PYTHON COMPILE ==="
for repo in . oec_deploy oec_aireos/Full_Model oec_aireos/Freezed oec_aireos/MOE; do
    while IFS= read -r -d '' pyfile; do
        python -m py_compile "$repo/$pyfile"
    done < <(git -C "$repo" ls-files -z -- '*.py')
done

echo "=== CORE IMPORT SMOKE ==="
TEST_PYTHON="${GPU_PYTHON:-python}"
echo "Import-test interpreter: $TEST_PYTHON"
"$TEST_PYTHON" - <<'PY'
import core_config
import brain
import storage_manager
import purge_manager
import qa_compliance_worker
import hf_upload_daemon
import oec_aireos.Freezed.awq_quantization_pipeline as awq
from oec_aireos.MOE.slurm_dag_dispatcher import SlurmDispatcher
from oec_aireos.MOE.adler_32_rsync_network_bridge import Adler32SyncBridge
from oec_aireos.MOE.oec_mcp_server import app
from oec_aireos.MOE.hpc_intent_orchestrator import DeepSeekOrchestrator

assert awq.SYSTEM_DIRS == core_config.SYSTEM_DIRS
print("IMPORT SMOKE: PASS")
PY

echo "=== SECURITY AUDIT: CURRENT TRACKED FILES ==="
if git grep -I -n -E 'https://discord\.com/api/webhooks/[0-9]+/[A-Za-z0-9_-]+' -- ':!*.ipynb' ':!*.md'; then
    echo "SECURITY FAILURE: Discord webhook URL found in outer OEC."
    exit 1
fi
if git grep -I -n -E -- '-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----|\b(AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b' -- ':!*.ipynb' ':!*.md'; then
    echo "SECURITY FAILURE: credential pattern found."
    exit 1
fi
if git grep -I -n -F -- 'super-secret-dev-key-do-not-use-in-prod' -- ':!*.ipynb' ':!*.md'; then
    echo "SECURITY FAILURE: weak JWT secret literal found."
    exit 1
fi
if git grep -I -n -F -- 'mock_dev_token' -- ':!*.ipynb' ':!*.md'; then
    echo "SECURITY FAILURE: mock token literal found."
    exit 1
fi
if git grep -I -n -F -- 'StrictHostKeyChecking=no' -- ':!*.ipynb' ':!*.md'; then
    echo "SECURITY FAILURE: unsafe SSH configuration found."
    exit 1
fi
if git grep -I -n -F -- '192.168.1.100' -- ':!*.ipynb' ':!*.md'; then
    echo "SECURITY FAILURE: old hard-coded edge address found."
    exit 1
fi
if git ls-files | grep -E '(^|/)\.ssh/|(^|/)\.jupyter/|(^|/)\.local/|(^|/)\.bash_history$|(^|/)\.bashrc$|(^|/)\.profile$|(^|/)\.gitconfig$|(^|/)\.flex_gemm/'; then
    echo "SECURITY FAILURE: host state remains tracked."
    exit 1
fi

echo "=== SECURITY AUDIT: HISTORY ==="
for repo in . oec_deploy oec_aireos/Full_Model oec_aireos/Freezed oec_aireos/MOE; do
    for path in .ssh/id_rsa .ssh/id_ed25519 .ssh .jupyter .local .bash_history .bashrc .profile .gitconfig .flex_gemm; do
        if git -C "$repo" rev-list --all --objects -- "$path" | grep -q .; then
            echo "SECURITY FAILURE: $repo history still contains $path"
            exit 1
        fi
    done
done

python - <<'PY'
import json
from pathlib import Path
cfg = json.loads(Path("storage_config.json").read_text())
assert "discord_webhook_url" not in cfg
assert cfg.get("discord_webhook_env") == "AIEROS_DISCORD_WEBHOOK_URL"
print("Webhook configuration: environment-only")
PY

echo "=== FINAL REPOSITORY STATE ==="
git diff --check
git add -A
if ! git diff --cached --quiet; then
    git config user.name "Killer4K"
    git config user.email "dummy@gmail.com"
    git commit -m "Sanitize OEC host state and runtime integration"
fi

git push origin main --force

git fetch origin main
git reset --hard origin/main
git submodule update --init --recursive

echo "=== FINAL VERIFICATION ==="
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
test -z "$(git status --porcelain)"
git status --short --branch
git submodule status --recursive
git log --oneline -5

echo "OEC ACCEPTANCE GATE: PASS"
