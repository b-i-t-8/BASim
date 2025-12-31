"""
Controller Profiles for Campus Simulator.
Defines different controller brands and their specific configurations.
"""
import os
import yaml
import logging
from dataclasses import dataclass, field
from typing import Dict, Any

logger = logging.getLogger("Profiles")

@dataclass
class ControllerProfile:
    name: str
    manufacturer: str
    description: str
    device_types: Dict[str, Any] = field(default_factory=dict)
    naming_convention: str = "PascalCase" # PascalCase, camelCase, snake_case
    config_file: str = "" # Path to the config file
    protocols: list = field(default_factory=lambda: ["BACnet", "Modbus"]) # Supported protocols
    
    # Legacy support property
    @property
    def default_points(self):
        # Return VAV points as default for backward compatibility if needed
        if 'VAV' in self.device_types:
            return self.device_types['VAV'].get('points', {})
        return {}

PROFILES = {}

def load_profiles():
    """Load profiles from YAML files in the profiles directory."""
    global PROFILES
    PROFILES = {}
    
    profiles_dir = os.path.join(os.path.dirname(__file__), 'profiles')
    if not os.path.exists(profiles_dir):
        logger.warning(f"Profiles directory not found: {profiles_dir}")
        return

    for filename in os.listdir(profiles_dir):
        if filename.endswith('.yaml') or filename.endswith('.yml'):
            file_path = os.path.join(profiles_dir, filename)
            try:
                with open(file_path, 'r') as f:
                    data = yaml.safe_load(f)
                    
                profile = ControllerProfile(
                    name=data.get('name', 'Unknown'),
                    manufacturer=data.get('manufacturer', 'Unknown'),
                    description=data.get('description', ''),
                    naming_convention=data.get('naming_convention', 'PascalCase'),
                    device_types=data.get('device_types', {}),
                    config_file=filename,
                    protocols=data.get('protocols', ["BACnet", "Modbus"])
                )
                PROFILES[profile.name] = profile
                logger.info(f"Loaded profile: {profile.name} from {filename}")
            except Exception as e:
                logger.error(f"Failed to load profile from {filename}: {e}")

# Load profiles on module import
load_profiles()

def get_profile(name: str) -> ControllerProfile:
    """Get a profile by name, defaulting to Distech if not found."""
    if not PROFILES:
        load_profiles()
    
    # Default to first available if Distech not found
    default = PROFILES.get("Distech")
    if not default and PROFILES:
        default = list(PROFILES.values())[0]
        
    return PROFILES.get(name, default)

def get_random_profile() -> ControllerProfile:
    """Get a random profile."""
    import random
    if not PROFILES:
        load_profiles()
    if not PROFILES:
        return None
    return random.choice(list(PROFILES.values()))

def save_profile(profile: ControllerProfile) -> bool:
    """Save profile to its YAML file."""
    profiles_dir = os.path.join(os.path.dirname(__file__), 'profiles')
    if not profile.config_file:
        logger.error(f"Cannot save profile {profile.name}: No config file specified")
        return False
        
    file_path = os.path.join(profiles_dir, profile.config_file)
    
    # Convert dataclass to dict for YAML
    data = {
        'name': profile.name,
        'manufacturer': profile.manufacturer,
        'description': profile.description,
        'naming_convention': profile.naming_convention,
        'protocols': profile.protocols,
        'device_types': profile.device_types
    }
    
    try:
        with open(file_path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        logger.info(f"Saved profile: {profile.name} to {profile.config_file}")
        return True
    except Exception as e:
        logger.error(f"Failed to save profile {profile.name}: {e}")
        return False
