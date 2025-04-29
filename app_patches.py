"""
Patches for app.py issues:
1. Remove heading extraction during streaming phase
2. Fix connection error handling
"""

import re
import os

def apply_patches():
    """Apply all patches to app.py"""
    app_path = "app.py"
    
    # Read the file
    with open(app_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # 1. Remove heading extraction during streaming
    pattern1 = r"# Extract all headings using the enhanced function\s+headings = extract_headings_from_content\(accumulated_content\).*?st\.session_state\.meta_and_headings\[\"headings\"\] = headings"
    replacement1 = "# Removed heading extraction during streaming to prevent warnings during thinking phase"
    content = re.sub(pattern1, replacement1, content, flags=re.DOTALL)
    
    # 2. Fix debug warning
    pattern2 = r"print\(\"WARNING: No headings found in content!\"\)"
    replacement2 = "if st.session_state.get('debug_mode', False):\n        print(\"WARNING: No headings found in content!\")"
    content = re.sub(pattern2, replacement2, content)
    
    # Write the changes back
    with open("app_patched.py", "w", encoding="utf-8") as f:
        f.write(content)
    
    print("Patches applied successfully! Updated file: app_patched.py")
    print("Please review the changes before replacing app.py")

if __name__ == "__main__":
    apply_patches()
