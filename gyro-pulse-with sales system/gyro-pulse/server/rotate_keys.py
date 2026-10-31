import os
import re
import secrets
import shutil
from datetime import datetime

ENV_FILE = ".env"

def rotate_secret_keys(env_path=ENV_FILE):
    if not os.path.exists(env_path):
        print(f"❌ Error: Could not find '{env_path}' file in the current directory.")
        return

    # 1. Create a timestamped backup copy
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{env_path}.bak_{timestamp}"
    shutil.copyfile(env_path, backup_path)
    print(f"📦 Backup created: {backup_path}")

    # 2. Generate new 32-byte hex keys for all security tokens
    keys_to_update = {
        "SECRET_KEY": secrets.token_hex(32),
        "JWT_SECRET_KEY": secrets.token_hex(32),
        "SALES_API_KEY": secrets.token_hex(32)
    }

    # 3. Read current file content
    with open(env_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # 4. Update the first instance of each key & strip duplicate declarations
    updated_lines = []
    seen_keys = set()

    for line in lines:
        matched_key = None
        for key in keys_to_update:
            if re.match(rf"^\s*{key}\s*=", line):
                matched_key = key
                break

        if matched_key:
            if matched_key not in seen_keys:
                updated_lines.append(f"{matched_key}={keys_to_update[matched_key]}\n")
                seen_keys.add(matched_key)
            # Duplicate occurrences are skipped cleanly
        else:
            updated_lines.append(line)

    # 5. Append any keys that didn't exist in the file previously
    for key, new_val in keys_to_update.items():
        if key not in seen_keys:
            updated_lines.append(f"{key}={new_val}\n")

    # 6. Write back to .env
    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(updated_lines)

    print("✅ Successfully rotated SECRET_KEY, JWT_SECRET_KEY, and SALES_API_KEY in .env!")

if __name__ == "__main__":
    rotate_secret_keys()