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
    input_types: list = field(default_factory=list)
    output_types: list = field(default_factory=list)

    
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
TEMPLATES = {}

def load_templates():
    """Load standard templates from YAML files."""
    global TEMPLATES
    TEMPLATES = {}
    
    templates_dir = os.path.join(os.path.dirname(__file__), 'profiles', 'templates')
    if not os.path.exists(templates_dir):
        logger.warning(f"Templates directory not found: {templates_dir}")
        try:
            os.makedirs(templates_dir)
            logger.info("Created templates directory")
        except:
            pass
        return

    for filename in os.listdir(templates_dir):
        if filename.endswith('.yaml') or filename.endswith('.yml'):
            file_path = os.path.join(templates_dir, filename)
            try:
                with open(file_path, 'r') as f:
                    data = yaml.safe_load(f)
                    
                if 'templates' in data:
                    for tmpl_name, tmpl_data in data['templates'].items():
                        TEMPLATES[tmpl_name] = tmpl_data
                    logger.info(f"Loaded {len(data['templates'])} templates from {filename}")
            except Exception as e:
                logger.error(f"Failed to load templates from {filename}: {e}")

def load_controllers():
    """Load controller definitions from YAML files in the controllers directory."""
    global CONTROLLERS
    CONTROLLERS = {}
    
    controllers_dir = os.path.join(os.path.dirname(__file__), 'profiles', 'controllers')
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
                        outputs=model_data.get('outputs', 0),
                        input_types=model_data.get('input_types', []),
                        output_types=model_data.get('output_types', [])
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
    
    # Load foundational data
    if not TEMPLATES:
        load_templates()
    
    # Ensure controllers are loaded first
    if not CONTROLLERS:
        load_controllers()
    
    profiles_dir = os.path.join(os.path.dirname(__file__), 'profiles', 'equipment')
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
                
                # Apply templates if specified
                for device_id, device_data in defs.items():
                    if 'template' in device_data:
                        template_name = device_data['template']
                        if template_name in TEMPLATES:
                            template = TEMPLATES[template_name]
                            
                            # Merge checks
                            # 1. Inherit description if missing
                            if 'description' not in device_data:
                                device_data['description'] = template.get('description', '')
                                
                            # 2. Inherit/Merge Points
                            if 'points' not in device_data:
                                device_data['points'] = {}
                                
                            for pt_key, pt_tmpl in template.get('points', {}).items():
                                # Look for existing mapping by checking 'mapping' field in device_data['points']
                                # OR check if the point key exists directly
                                
                                # Strategy: The template defines "internal keys" (e.g. room_temp).
                                # The implementation might use "ZoneTemp" as the key, with "mapping: room_temp".
                                # We need to ensure the implementation supports all required template points.
                                
                                found = False
                                for impl_pt_name, impl_pt_data in device_data['points'].items():
                                    if impl_pt_data.get('mapping') == pt_key:
                                        # Inject template metadata (tags, units) if missing in implementation
                                        if 'haystack_tags' not in impl_pt_data and 'haystack_tags' in pt_tmpl:
                                            impl_pt_data['haystack_tags'] = pt_tmpl['haystack_tags']
                                        if 'units' not in impl_pt_data and 'units' in pt_tmpl:
                                            impl_pt_data['units'] = pt_tmpl['units']
                                        if 'description' not in impl_pt_data and 'label' in pt_tmpl: # label -> desc
                                            impl_pt_data['description'] = pt_tmpl['label']
                                            
                                        found = True
                                        break
                                
                                if not found and pt_tmpl.get('required', False):
                                    # Option A: Auto-create the point using the internal key as the name
                                    # Option B: Log a warning (Passive)
                                    # Let's go with Option A for rapid prototyping, but map it to a "Virtual" address if undefined?
                                    # Actually, let's just add it so the simulator logic works, even if address is missing.
                                    
                                    new_pt = {
                                        'description': pt_tmpl.get('label', ''),
                                        'units': pt_tmpl.get('units', ''),
                                        'type': pt_tmpl.get('type', 'AI'),
                                        'haystack_tags': pt_tmpl.get('haystack_tags', []),
                                        'mapping': pt_key,
                                        'writable': pt_tmpl.get('writable', False)
                                    }
                                    if 'default' in pt_tmpl:
                                        new_pt['value'] = pt_tmpl['default']
                                        
                                    device_data['points'][pt_key] = new_pt

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

def save_templates():
    """Save the templates back to the templates definition file."""
    templates_dir = os.path.join(os.path.dirname(__file__), 'profiles', 'templates')
    file_path = os.path.join(templates_dir, 'haystack_definitions.yaml')
    
    try:
        data = {'templates': TEMPLATES}
        with open(file_path, 'w') as f:
            yaml.dump(data, f, sort_keys=False, default_flow_style=False)
        logger.info(f"Saved templates to {file_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to save templates: {e}")
        return False

def save_profile(profile: ControllerProfile) -> bool:
    """Save profile to its YAML file."""
    profiles_dir = os.path.join(os.path.dirname(__file__), 'profiles', 'equipment')
    if not os.path.exists(profiles_dir):
        os.makedirs(profiles_dir)
        
    if not profile.config_file:
        # Generate filename from manufacturer if not specified
        safe_manufacturer = profile.manufacturer.lower().replace(' ', '_')
        profile.config_file = f"{safe_manufacturer}.yaml"
        
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

def create_profile(name: str, manufacturer: str, description: str) -> tuple[bool, str]:
    """Create a new profile. Returns (success, message)."""
    profiles_dir = os.path.join(os.path.dirname(__file__), 'profiles', 'equipment')
    if not os.path.exists(profiles_dir):
        os.makedirs(profiles_dir)

    # Check for existing manufacturer (fuzzy match logic from save_controller)
    for filename in os.listdir(profiles_dir):
        if filename.endswith('.yaml') or filename.endswith('.yml'):
            file_path = os.path.join(profiles_dir, filename)
            try:
                with open(file_path, 'r') as f:
                    data = yaml.safe_load(f) or {}
                
                existing_mfg = data.get('manufacturer', '')
                if existing_mfg and (existing_mfg.lower() == manufacturer.lower() or 
                                     existing_mfg.lower() in manufacturer.lower() or 
                                     manufacturer.lower() in existing_mfg.lower()):
                    return False, f"Manufacturer '{existing_mfg}' already exists in {filename}"
            except:
                continue

    # Create new profile object
    profile = ControllerProfile(
        name=name,
        manufacturer=manufacturer,
        description=description,
        device_definitions={}
    )
    
    # Save it (will generate config_file)
    if save_profile(profile):
        PROFILES[profile.name] = profile
        return True, f"Created profile {name}"
    return False, "Failed to save profile"

def save_controller(model_name: str, manufacturer: str, description: str, inputs: int, outputs: int):
    """Save or update a controller definition."""
    controllers_dir = os.path.join(os.path.dirname(__file__), 'profiles', 'controllers')
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
    controllers_dir = os.path.join(os.path.dirname(__file__), 'profiles', 'controllers')
    
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
