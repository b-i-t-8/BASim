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
class ControllerModel:
    name: str
    manufacturer: str
    description: str
    inputs: int = 0
    outputs: int = 0
    
@dataclass
class ControllerProfile:
    name: str
    manufacturer: str
    description: str
    device_definitions: Dict[str, Any] = field(default_factory=dict)
    naming_convention: str = "PascalCase" # PascalCase, camelCase, snake_case
    config_file: str = "" # Path to the config file
    protocols: list = field(default_factory=lambda: ["BACnet", "Modbus"]) # Supported protocols
    
    # Legacy support property
    @property
    def default_points(self):
        # Return VAV points as default for backward compatibility if needed
        if 'VAV' in self.device_definitions:
            return self.device_definitions['VAV'].get('points', {})
        # Fallback to other VAV types
        for key in self.device_definitions:
            if key.startswith('VAV'):
                return self.device_definitions[key].get('points', {})
        return {}

CONTROLLERS = {}
PROFILES = {}

def load_controllers():
    """Load controller definitions from YAML files in the controllers directory."""
    global CONTROLLERS
    CONTROLLERS = {}
    
    controllers_dir = os.path.join(os.path.dirname(__file__), 'controllers')
    if not os.path.exists(controllers_dir):
        logger.warning(f"Controllers directory not found: {controllers_dir}")
        return

    for filename in os.listdir(controllers_dir):
        if filename.endswith('.yaml') or filename.endswith('.yml'):
            file_path = os.path.join(controllers_dir, filename)
            try:
                with open(file_path, 'r') as f:
                    data = yaml.safe_load(f)
                    
                manufacturer = data.get('manufacturer', 'Unknown')
                models = data.get('models', {})
                
                for model_name, model_data in models.items():
                    controller = ControllerModel(
                        name=model_name,
                        manufacturer=manufacturer,
                        description=model_data.get('description', ''),
                        inputs=model_data.get('inputs', 0),
                        outputs=model_data.get('outputs', 0)
                    )
                    # Key by "Manufacturer_Model" to avoid collisions, or just Model if unique enough
                    # Let's use just Model name for now as they seem unique enough in our set
                    CONTROLLERS[model_name] = controller
                    
                logger.info(f"Loaded {len(models)} controllers from {filename}")
            except Exception as e:
                logger.error(f"Failed to load controllers from {filename}: {e}")

def load_profiles():
    """Load profiles from YAML files in the profiles directory."""
    global PROFILES
    PROFILES = {}
    
    # Ensure controllers are loaded first
    if not CONTROLLERS:
        load_controllers()
    
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
                    
                # Support both new and legacy keys
                defs = data.get('device_definitions', data.get('device_types', {}))
                
                profile = ControllerProfile(
                    name=data.get('name', 'Unknown'),
                    manufacturer=data.get('manufacturer', 'Unknown'),
                    description=data.get('description', ''),
                    naming_convention=data.get('naming_convention', 'PascalCase'),
                    device_definitions=defs,
                    config_file=filename,
                    protocols=data.get('protocols', ["BACnet", "Modbus"])
                )
                PROFILES[profile.name] = profile
                logger.info(f"Loaded profile: {profile.name} from {filename}")
            except Exception as e:
                logger.error(f"Failed to load profile from {filename}: {e}")

# Load profiles on module import
load_profiles()

def get_controller(model_name: str) -> ControllerModel:
    """Get a controller model by name."""
    if not CONTROLLERS:
        load_controllers()
    return CONTROLLERS.get(model_name)

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
        'device_definitions': profile.device_definitions
    }
    
    try:
        with open(file_path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        logger.info(f"Saved profile: {profile.name} to {profile.config_file}")
        return True
    except Exception as e:
        logger.error(f"Failed to save profile {profile.name}: {e}")
        return False

def save_controller(model_name: str, manufacturer: str, description: str, inputs: int, outputs: int):
    """Save or update a controller definition."""
    controllers_dir = os.path.join(os.path.dirname(__file__), 'controllers')
    if not os.path.exists(controllers_dir):
        os.makedirs(controllers_dir)
        
    # Find existing file for manufacturer or create new one
    target_file = None
    
    # Normalize manufacturer name for filename
    safe_manufacturer = manufacturer.lower().replace(' ', '_')
    default_filename = f"{safe_manufacturer}.yaml"
    
    # Check existing files
    for filename in os.listdir(controllers_dir):
        if filename.endswith('.yaml') or filename.endswith('.yml'):
            file_path = os.path.join(controllers_dir, filename)
            try:
                with open(file_path, 'r') as f:
                    data = yaml.safe_load(f) or {}
                
                # Check if this file belongs to the manufacturer
                # Loose matching to handle cases like "Delta" vs "Delta Controls"
                file_mfg = data.get('manufacturer', '')
                if file_mfg == manufacturer or file_mfg in manufacturer or manufacturer in file_mfg:
                    target_file = filename
                    # Update manufacturer name to match exactly what we found if it's close
                    manufacturer = file_mfg 
                    break
            except:
                continue
    
    if not target_file:
        target_file = default_filename
        
    file_path = os.path.join(controllers_dir, target_file)
    
    # Load existing data or initialize
    data = {}
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            data = yaml.safe_load(f) or {}
            
    if 'manufacturer' not in data:
        data['manufacturer'] = manufacturer
        
    if 'models' not in data:
        data['models'] = {}
        
    # Update model
    data['models'][model_name] = {
        'description': description,
        'inputs': inputs,
        'outputs': outputs
    }
    
    # Save back
    with open(file_path, 'w') as f:
        yaml.dump(data, f, sort_keys=False)
        
    # Reload
    load_controllers()
    return True

def delete_controller(model_name: str):
    """Delete a controller definition."""
    controllers_dir = os.path.join(os.path.dirname(__file__), 'controllers')
    
    for filename in os.listdir(controllers_dir):
        if filename.endswith('.yaml') or filename.endswith('.yml'):
            file_path = os.path.join(controllers_dir, filename)
            try:
                with open(file_path, 'r') as f:
                    data = yaml.safe_load(f) or {}
                
                if 'models' in data and model_name in data['models']:
                    del data['models'][model_name]
                    
                    with open(file_path, 'w') as f:
                        yaml.dump(data, f, sort_keys=False)
                    
                    load_controllers()
                    return True
            except:
                continue
    return False
