import sys
import os
import json

# Function to validate .ly_state/ directory integrity
def validate_ly_state_integrity():
    ly_state_dir = ".ly_state"
    if not os.path.exists(ly_state_dir):
        return {"status": "error", "message": f"{ly_state_dir} directory not found"}
    
    expected_files = ["session", "memory", "logs"]
    found_files = []
    
    for dir_name in os.listdir(ly_state_dir):
        if dir_name in expected_files:
            found_files.append(dir_name)
    
    if set(found_files) == set(expected_files):
        return {"status": "success", "message": "All files present and accounted for in .ly_state/"}
    else:
        return {"status": "error", "message": "Missing files in .ly_state/"}

# Execute the validation
result = validate_ly_state_integrity()
if result["status"] == "success":
    print("Validation successful: " + result["message"])
else:
    print("Error: " + result["message"])
    sys.exit(1)
