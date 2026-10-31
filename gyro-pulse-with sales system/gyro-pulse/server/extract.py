import os
import re

# Read the code.md file
with open('code.md', 'r', encoding='utf-8') as f:
    content = f.read()

# Split by file markers
pattern = r'## File: (\d+) (gyro/[^\n]+)\n```?\n(.*?)\n```?(?=\n## File: |\Z)'
matches = re.findall(pattern, content, re.DOTALL)

for idx, (num, filepath, file_content) in enumerate(matches):
    # Remove any trailing backticks and extra whitespace
    file_content = file_content.strip()
    # If the filepath starts with 'gyro/', ensure the folder exists
    full_path = os.path.join(os.getcwd(), filepath)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, 'w', encoding='utf-8') as out:
        out.write(file_content)
    print(f"Created: {filepath}")

print("\n✅ All files have been recreated.")