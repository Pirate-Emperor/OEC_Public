import os
import time
import json
import sqlite3
from PIL import Image, ImageDraw, ImageText
import subprocess

# Import config to get exact paths
from core_config import SYSTEM_DIRS, QUEUE_DB_PATH

print("--- QA VERIFICATION INJECTOR ---")

# 1. Create a dummy "Video" (Actually just an image named .mp4 for the test)
dummy_vid_path = os.path.join(SYSTEM_DIRS['outputs'], "videos", "test_qa_fake_video.mp4")
dummy_json_path = os.path.join(SYSTEM_DIRS['outputs'], "videos", "test_qa_fake_video_info.json")

print("1. Generating fake watermarked video frame...")
# Create a red image with a massive fake watermark text to trigger a rejection
img = Image.new('RGB', (1024, 576), color = (255, 0, 0))
d = ImageDraw.Draw(img)
d.text((100, 200), "SHUTTERSTOCK WATERMARK LOGO TEST", fill=(255,255,255))
img.save("temp_frame.jpg")

# Use FFmpeg to turn the 1 frame into a 3 second fake video
try:
    subprocess.run([
        "ffmpeg", "-y", "-loop", "1", "-i", "temp_frame.jpg", 
        "-c:v", "libx264", "-t", "3", "-pix_fmt", "yuv420p", dummy_vid_path
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    os.remove("temp_frame.jpg")
except Exception as e:
    print(f"Failed to create fake video (is FFmpeg installed?): {e}")
    exit(1)

# 2. Create the dummy JSON metadata
metadata = {
    "output_type": "video",
    "model_type": "ltx-2.3-22b",
    "file_name": "test_qa_fake_video.mp4",
    "prompt": "Test video with watermark"
}
with open(dummy_json_path, 'w') as f:
    json.dump(metadata, f)

# 3. Inject it into the Queue Database
print(f"2. Injecting into database at {QUEUE_DB_PATH}...")
total_size = os.path.getsize(dummy_vid_path) + os.path.getsize(dummy_json_path)

with sqlite3.connect(QUEUE_DB_PATH) as conn:
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO assets (asset_path, json_path, total_size_bytes, status) VALUES (?, ?, ?, 'PENDING_QA')",
        (dummy_vid_path, dummy_json_path, total_size)
    )
    conn.commit()

print("\n✅ Injection Complete!")
print("Now, open a terminal and run this command to watch the QA node catch it in real-time:")
print(f"tail -f {os.path.join(SYSTEM_DIRS['outputs'], 'qa_worker.log')}")