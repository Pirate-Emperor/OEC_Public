import os
import time
import json
import glob
import random
import signal
import sys
import uuid
import re
import argparse
from datetime import datetime

from core_config import SYSTEM_DIRS
from storage_manager import managed_storage_operation
from storage_policy import BYTES_PER_GB, estimate_hf_repo_bytes

import torch
from transformers import pipeline

class DualLogger:
    def __init__(self, filepath):
        self.terminal = sys.stdout
        self.log_file = open(filepath, "a", buffering=1)
    def write(self, message):
        self.terminal.write(message)
        self.log_file.write(message)
        self.terminal.flush()
        self.log_file.flush()
    def flush(self):
        self.terminal.flush()
        self.log_file.flush()
        
class TheBrain:
    def __init__(self, config_path="brain_config.json"):
        log_path = os.path.join(SYSTEM_DIRS['logs'], "brain.log")
        sys.stdout = DualLogger(log_path)
        sys.stderr = sys.stdout
        
        print("\n[THE BRAIN] Initializing Master Orchestrator on A100 Node...")
        self.config_path = config_path
        
        self.jobs_dir = os.path.join(SYSTEM_DIRS['inputs'], "jobs")
        os.makedirs(self.jobs_dir, exist_ok=True)
        
        self.load_config()
        self.is_running = True

        self._setup_signals()
        self._initialize_llm()

    def _setup_signals(self):
        def handle_sig(sig, frame):
            print("\n[THE BRAIN] Shutdown signal received. Exiting gracefully...")
            self.is_running = False
            sys.exit(0)
        signal.signal(signal.SIGINT, handle_sig)
        signal.signal(signal.SIGTERM, handle_sig)

    def load_config(self):
        try:
            with open(self.config_path, 'r') as f:
                self.config = json.load(f)
            
            self.polling_interval = self.config["system_settings"]["polling_interval_seconds"]
            self.min_interval = self.config["system_settings"]["min_polling_interval"]
            self.max_interval = self.config["system_settings"]["max_polling_interval"]
            self.max_batch = self.config["system_settings"]["max_batch_size"]
            print(f"[THE BRAIN] Configuration loaded successfully.")
        except Exception as e:
            print(f"[CRITICAL] Failed to load {self.config_path}: {e}")
            sys.exit(1)

    def _initialize_llm(self):
        model_id = self.config["system_settings"]["model_id"]
        print(f"[THE BRAIN] Loading Heavy Reasoning Engine: {model_id}...")

        try:
            # Local paths are already materialized and require no network/storage admission.
            if os.path.isdir(os.path.expanduser(model_id)):
                self.llm = pipeline(
                    "text-generation",
                    model=os.path.expanduser(model_id),
                    torch_dtype=torch.bfloat16,
                    device_map="auto",
                )
            else:
                from huggingface_hub import snapshot_download

                try:
                    snapshot_download(
                        repo_id=model_id,
                        cache_dir=SYSTEM_DIRS["models"],
                        local_files_only=True,
                    )
                    print("[THE BRAIN] Reasoning model verified in local HF cache.")
                    self.llm = pipeline(
                        "text-generation",
                        model=model_id,
                        torch_dtype=torch.bfloat16,
                        device_map="auto",
                    )
                except Exception:
                    required_gb = (
                        estimate_hf_repo_bytes(model_id) / BYTES_PER_GB
                        + max(
                            0.0,
                            float(
                                os.environ.get(
                                    "AIEROS_MODEL_DOWNLOAD_SAFETY_GB",
                                    "2.0",
                                )
                            ),
                        )
                    )
                    print(
                        f"[THE BRAIN] Model cache incomplete. "
                        f"Storage admission budget: {required_gb:.2f} GB"
                    )
                    with managed_storage_operation(
                        "models",
                        required_gb=required_gb,
                        require_fresh_quota=True,
                        minimum_free_gb=float(
                            os.environ.get("AIEROS_MODEL_MIN_FREE_GB", "2.0")
                        ),
                    ):
                        self.llm = pipeline(
                            "text-generation",
                            model=model_id,
                            torch_dtype=torch.bfloat16,
                            device_map="auto",
                        )

            print("[THE BRAIN] A100 Neural Logic initialized. Ready to dream.")
        except Exception as e:
            print(f"[CRITICAL] LLM Initialization Failed: {type(e).__name__}: {e}")
            sys.exit(1)

    def get_current_job_count(self, use_case_id):
        """Counts how many pending jobs exist for a specific use case."""
        pattern = os.path.join(self.jobs_dir, f"job_{use_case_id}_*.json")
        return len(glob.glob(pattern))

    def adjust_polling_interval(self, total_deficit):
        if total_deficit == 0:
            self.polling_interval = min(self.polling_interval * 1.5, self.max_interval)
            print(f"[THE BRAIN] Queue is full. Hibernating for {int(self.polling_interval/60)} minutes.")
        elif total_deficit > 10:
            self.polling_interval = max(self.polling_interval * 0.5, self.min_interval)
            print(f"[THE BRAIN] High demand detected. Speeding polling to {int(self.polling_interval/60)} minutes.")

    def inject_randomness(self, instruction, randomness_percentage):
        if random.randint(1, 100) > randomness_percentage:
            return instruction 
            
        wildcards = self.config.get("wildcards", {})
        additions = []
        
        if wildcards.get("lighting") and random.choice([True, False]):
            additions.append(f"Use {random.choice(wildcards['lighting'])}.")
        if wildcards.get("camera") and random.choice([True, False]):
            additions.append(f"Style it as a {random.choice(wildcards['camera'])}.")
        if wildcards.get("imperfections") and random.choice([True, False]):
            additions.append(f"Include {random.choice(wildcards['imperfections'])}.")
            
        if additions:
            instruction += " Specific visual modifiers to weave into the scene: " + " ".join(additions)
            
        return instruction

    def generate_prompts(self, use_case, amount):
        niche = random.choice(self.config.get("profitable_niches", ["everyday human life"]))
        theme = random.choice(self.config.get("creative_themes", ["quiet realism"]))
        min_dur, max_dur = use_case.get("duration_range", [5.0, 10.0])
        
        base_instruction = use_case["template_instruction"].format(amount, niche, theme, min_dur, max_dur)
        instruction = self.inject_randomness(base_instruction, use_case["randomness_percentage"])
        system_prompt = self.config["system_settings"]["global_system_prompt"]
        
        user_prompt = (
            f"{instruction}\n\n"
            f"Provide EXACTLY {amount} distinct prompts. "
            "Do not include any introductory or concluding text outside of the numbered list."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            outputs = self.llm(messages, max_new_tokens=2000, temperature=0.8, top_p=0.9, return_full_text=False)
            response_text = outputs[0]['generated_text']
            
            # Strip out DeepSeek-R1 internal "thinking" blocks completely
            response_text = re.sub(r'<think>.*?</think>', '', response_text, flags=re.DOTALL)
            
            prompts = []
            for line in response_text.split('\n'):
                line = line.strip()
                # Matches "1. " or "1) "
                match = re.search(r'^\W*\d+[\.\)]\s*(.*)', line)
                
                if match:
                    raw_prompt_text = match.group(1).strip()
                    
                    # Extract the [DURATION: X] tag predicted by the LLM
                    dur_match = re.search(r'\[DURATION:\s*(\d+(?:\.\d+)?)\]', raw_prompt_text, re.IGNORECASE)
                    
                    if dur_match:
                        predicted_duration = float(dur_match.group(1))
                        # Clamp the duration to ensure it doesn't hallucinate 90 seconds and crash the A100
                        predicted_duration = max(min_dur, min(max_dur, predicted_duration))
                        # Remove the tag so it doesn't get sent to the video generator
                        clean_prompt = re.sub(r'\[DURATION:\s*(\d+(?:\.\d+)?)\]', '', raw_prompt_text, flags=re.IGNORECASE).strip()
                    else:
                        # Fallback: Assign a random duration if the LLM forgot the tag
                        predicted_duration = round(random.uniform(min_dur, max_dur), 1)
                        clean_prompt = raw_prompt_text
                        
                    clean_prompt = clean_prompt.strip('"').strip("'")
                    if len(clean_prompt) > 15: 
                        prompts.append({
                            "text": clean_prompt,
                            "duration": predicted_duration
                        })
            
            return prompts[:amount]
            
        except Exception as e:
            print(f"[THE BRAIN] Error during LLM generation: {e}")
            return []

    def run(self):
        print("\n[THE BRAIN] Orchestrator Active. Managing Asset Pipeline...")
        
        while self.is_running:
            self.load_config() 
            total_deficit = 0
            
            for use_case in self.config["use_cases"]:
                current_count = self.get_current_job_count(use_case["id"])
                target_count = use_case["target_queue_count"]
                deficit = target_count - current_count
                
                if deficit > 0:
                    print(f"\n[THE BRAIN] Deficit of {deficit} for {use_case['id']}. Initiating Micro-Batches...")
                    
                    while deficit > 0 and self.is_running:
                        batch_amount = min(deficit, self.max_batch)
                        print(f"  -> Generating chunk of {batch_amount} prompts using DeepSeek-R1...")
                        
                        new_prompts = self.generate_prompts(use_case, batch_amount)
                        
                        if not new_prompts:
                            print(f"[THE BRAIN] Warning: LLM failed to return valid prompts. Retrying next loop.")
                            break
                            
                        for prompt_data in new_prompts:
                            job_data = {
                                "prompt": prompt_data["text"],
                                "duration": prompt_data["duration"],
                                "use_case": use_case["id"],
                                "created_at": datetime.now().isoformat()
                            }
                            # Injects output_type, model_type, resolution, fps, etc.
                            job_data.update(use_case["worker_parameters"])
                            
                            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                            job_id = f"job_{use_case['id']}_{timestamp}_{uuid.uuid4().hex[:6]}.json"
                            job_path = os.path.join(self.jobs_dir, job_id)
                            
                            with open(job_path, "w") as f:
                                json.dump(job_data, f, indent=4)
                                
                            out_type = job_data.get("output_type", "video")
                            dur = job_data.get("duration", 5.0)
                            print(f"     + Queued [{out_type} | {dur}s]: {prompt_data['text'][:55]}...")
                            total_deficit += 1
                            deficit -= 1
                else:
                    print(f"[THE BRAIN] {use_case['id']} queue is healthy ({current_count}/{target_count}).")

            self.adjust_polling_interval(total_deficit)
            
            for _ in range(int(self.polling_interval)):
                if not self.is_running:
                    break
                time.sleep(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AIEROS Brain Orchestrator")
    parser.add_argument(
        "-n", "--no-proxy",
        action="store_true",
        help="Disable proxy routing (Use this when running on the Login Node)"
    )
    args = parser.parse_args()

    if args.no_proxy:
        print("[SYSTEM] '--no-proxy' flag detected. Entering Offline/Local-Only Mode.")
        os.environ["HF_HUB_OFFLINE"] = "1"
        proxies_to_remove = ["http_proxy", "https_proxy", "ftp_proxy", "HTTP_PROXY", "HTTPS_PROXY", "FTP_PROXY"]
        for p in proxies_to_remove:
            os.environ.pop(p, None)

    brain = TheBrain()
    brain.run()