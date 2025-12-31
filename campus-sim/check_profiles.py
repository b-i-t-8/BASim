
import sys
import os
import logging

# Configure logging to stdout
logging.basicConfig(level=logging.INFO)

# Add current dir to path
sys.path.append(os.getcwd())

try:
    import profiles
    print(f"Profiles loaded: {len(profiles.PROFILES)}")
    for name, p in profiles.PROFILES.items():
        print(f"Profile: {name}")
        print(f"  Device Types: {list(p.device_types.keys())}")
        if 'VAV' in p.device_types:
            print(f"  VAV Defaults: {p.device_types['VAV'].get('defaults', {}).keys()}")
except Exception as e:
    print(f"Error: {e}")
