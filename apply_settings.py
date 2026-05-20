import os
import json

base_dir = r"c:\Users\MOON\OneDrive - 중앙대학교 병원\Individual\hospital\Claude Code"

for item in os.listdir(base_dir):
    full_path = os.path.join(base_dir, item)
    if os.path.isdir(full_path) and not item.startswith("."):
        # Check if it has a python file
        has_python = False
        try:
            for f in os.listdir(full_path):
                if f.endswith(".py"):
                    has_python = True
                    break
        except Exception:
            continue
            
        if has_python:
            vscode_dir = os.path.join(full_path, ".vscode")
            os.makedirs(vscode_dir, exist_ok=True)
            settings_path = os.path.join(vscode_dir, "settings.json")
            
            # Check if there is a venv folder name preference
            venv_name = ".venv"
            if os.path.exists(os.path.join(full_path, "venv")):
                venv_name = "venv"
                
            settings = {}
            if os.path.exists(settings_path):
                try:
                    with open(settings_path, "r", encoding="utf-8") as f:
                        settings = json.load(f)
                except Exception:
                    pass
            
            settings["python.defaultInterpreterPath"] = f"${{workspaceFolder}}/{venv_name}/Scripts/python.exe"
            settings["python.terminal.activateEnvironment"] = True
            
            with open(settings_path, "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=4)
            print(f"Updated {settings_path}")

# Also update root
root_vscode = os.path.join(base_dir, ".vscode")
os.makedirs(root_vscode, exist_ok=True)
root_settings = os.path.join(root_vscode, "settings.json")
settings = {}
if os.path.exists(root_settings):
    try:
        with open(root_settings, "r", encoding="utf-8") as f:
            settings = json.load(f)
    except Exception:
        pass
settings["python.defaultInterpreterPath"] = "${workspaceFolder}/.venv/Scripts/python.exe"
settings["python.terminal.activateEnvironment"] = True
with open(root_settings, "w", encoding="utf-8") as f:
    json.dump(settings, f, indent=4)
print(f"Updated {root_settings}")
