import os
import getpass
import subprocess
import shutil

# ==============================================================================
# CORE_CONFIG.PY
# Centralized utility for Storage, Proxies, and Authentication.
# ==============================================================================

def load_env_file():
    """Reads ~/.env and loads values into os.environ, expanding only OEC path variables."""
    env_path = os.path.expanduser("~/.env")
    path_keys = {
        "AIEROS_BASE_DIR",
        "AIEROS_MODELS_DIR",
        "AIEROS_DATASETS_DIR",
        "AIEROS_CACHE_DIR",
        "AIEROS_OUTPUTS_DIR",
        "AIEROS_INPUTS_DIR",
        "AIEROS_LOGS_DIR",
    }

    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("'").strip('"')
                    if key in path_keys:
                        val = os.path.expanduser(os.path.expandvars(val))
                    os.environ[key] = val
        print(f"[CORE] Secrets & Config loaded successfully from {env_path}")
    else:
        print(f"[CORE] No .env file found at {env_path}. Using hardcoded defaults.")

# Execute immediately so the rest of the script can use the loaded variables
load_env_file()

# 1. DYNAMIC DIRECTORY MAPPING
# Uses .env variables if present; otherwise falls back to defaults.
BASE_DIR = os.path.expanduser(os.environ.get("AIEROS_BASE_DIR", "~"))
SYSTEM_DIRS = {
    'models': os.path.expanduser(os.environ.get("AIEROS_MODELS_DIR", f"{BASE_DIR}/aireos_models")),
    'datasets': os.path.expanduser(os.environ.get("AIEROS_DATASETS_DIR", f"{BASE_DIR}/aireos_dataset")),
    'cache': os.path.expanduser(os.environ.get("AIEROS_CACHE_DIR", f"{BASE_DIR}/aireos_cache")),
    'outputs': os.path.expanduser(os.environ.get("AIEROS_OUTPUTS_DIR", f"{BASE_DIR}/aireos_output")),
    'inputs': os.path.expanduser(os.environ.get("AIEROS_INPUTS_DIR", f"{BASE_DIR}/aireos_input")),
    'logs': os.path.expanduser(os.environ.get("AIEROS_LOGS_DIR", f"{BASE_DIR}/aireos_logs"))
}

def map_storage():
    """Forces all HF and Torch caches to the designated AIEROS storage."""
    os.environ["HF_HOME"] = SYSTEM_DIRS['models']
    os.environ["AUDIOCRAFT_CACHE_DIR"] = SYSTEM_DIRS['models']
    os.environ["HF_DATASETS_CACHE"] = SYSTEM_DIRS['datasets']
    os.environ["TMPDIR"] = SYSTEM_DIRS['cache']
    os.environ["TMP"] = SYSTEM_DIRS['cache']
    os.environ["TEMP"] = SYSTEM_DIRS['cache']

    for path in SYSTEM_DIRS.values():
        os.makedirs(path, exist_ok=True)
    
    os.makedirs(os.path.join(SYSTEM_DIRS['outputs'], "videos"), exist_ok=True)
    os.makedirs(os.path.join(SYSTEM_DIRS['outputs'], "audio"), exist_ok=True)

# 2. DYNAMIC PROXY CONFIGURATION
def set_hpc_proxies():
    """Sets proxy variables for backend downloading."""
    proxy_url = os.environ.get("AIEROS_PROXY_URL", "http://proxy-gt.gt.aireos:9090")
    proxies = [
        "http_proxy", "https_proxy", "ftp_proxy", 
        "HTTP_PROXY", "HTTPS_PROXY", "FTP_PROXY"
    ]
    for p in proxies:
        os.environ[p] = proxy_url
    
    os.environ["HF_HUB_USE_XET"] = "0"
    os.environ["HF_HUB_DISABLE_XET"] = "1"
    os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"
    
    # Give the HPC proxy 120 seconds to respond instead of the default 10 seconds
    os.environ["HF_HUB_ETAG_TIMEOUT"] = "120"
    os.environ["HF_HUB_DOWNLOAD_TIMEOUT"] = "120"
    
    conda_prefix = os.environ.get("CONDA_PREFIX", "")
    if conda_prefix:
        os.environ["PKG_CONFIG_PATH"] = f"{conda_prefix}/lib/pkgconfig"

# 3. SECURE CREDENTIAL MANAGEMENT
def authenticate_huggingface(interactive=True):
    """Logs into HuggingFace seamlessly via .env token, skipping the prompt if valid."""
    from huggingface_hub import login
    hf_token = os.environ.get("HF_TOKEN")
    
    if hf_token and hf_token.startswith("hf_"):
        print("[CORE] Valid Hugging Face token detected in environment. Authenticating...")
        login(token=hf_token)
        os.environ["SECURE_HF_TOKEN"] = "AUTHENTICATED"
        return

    if os.environ.get("SECURE_HF_TOKEN") == "AUTHENTICATED":
        return
        
    print("\n[SECURE AUTHENTICATION REQUIRED]")
    if interactive:
        print("No 'HF_TOKEN' found in ~/.env. Please paste your Hugging Face 'Write' token below.")
        try:
            manual_token = getpass.getpass(prompt="HF Token: ")
            if manual_token.startswith("hf_"):
                login(token=manual_token)
                os.environ["SECURE_HF_TOKEN"] = "AUTHENTICATED"
                print("Successfully logged into Hugging Face securely.")
            else:
                print("WARNING: Token does not appear to be valid (should start with 'hf_').")
        except Exception as e:
            print(f"\nAuthentication skipped or failed: {e}")
    else:
        print("Running in non-interactive mode. Please ensure token is provided in .env.")

# 4. UPLOAD QUEUE CONFIGURATION
UPLOAD_BATCH_SIZE_GB = float(os.environ.get("AIEROS_UPLOAD_BATCH_GB", "5.0"))
HF_DATASET_REPO = os.environ.get("AIEROS_HF_DATASET_REPO", "YourHFUsername/AIEROS-Asset-Factory")
QUEUE_DB_PATH = os.path.join(SYSTEM_DIRS['outputs'], "upload_queue.db")

# 5. INITIALIZATION EXECUTION
def initialize_environment(interactive=False):
    """Runs all setup protocols explicitly."""
    map_storage()
    set_hpc_proxies()
    authenticate_huggingface(interactive=interactive)
    clear_system_trash()
    print("[CORE] Storage, Proxies, and Auth initialized successfully.")

def clear_system_trash():
    """Wipes hidden system and Jupyter trash bins to free up disk space."""
    trash_paths = [
        os.path.expanduser("~/.local/share/Trash/files"),
        os.path.expanduser("~/.local/share/Trash/info"),
        os.path.expanduser("~/.jupyter/lab/workspaces") # Jupyter temp workspace junk
    ]
    for path in trash_paths:
        if os.path.exists(path):
            try:
                for item in os.listdir(path):
                    item_path = os.path.join(path, item)
                    if os.path.isdir(item_path): shutil.rmtree(item_path)
                    else: os.remove(item_path)
                print(f"[CORE] Cleaned trash at {path}")
            except Exception as e:
                print(f"[CORE] Could not clean {path}: {e}")
                
# Auto-configure storage and proxy environment when imported by workers.
# Destructive cleanup remains explicit via initialize_environment() so imports
# have no filesystem-deletion side effects.
map_storage()
set_hpc_proxies()