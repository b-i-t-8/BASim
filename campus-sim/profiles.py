"""
Controller Profiles for Campus Simulator.
Defines different controller brands and their specific configurations.
"""
from dataclasses import dataclass, field
from typing import Dict, Any

@dataclass
class ControllerProfile:
    name: str
    manufacturer: str
    description: str
    default_points: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    naming_convention: str = "PascalCase" # PascalCase, camelCase, snake_case

# Define default profiles
PROFILES = {
    "Alerton": ControllerProfile(
        name="Alerton",
        manufacturer="Alerton",
        description="Alerton Compass/Ascent based controllers",
        naming_convention="PascalCase",
        default_points={
            "AV-1": {"name": "OccupancyMode", "description": "Occupancy Mode Enum"},
            "AV-2": {"name": "EffectiveSetpoint", "description": "Effective Setpoint"},
        }
    ),
    "Delta": ControllerProfile(
        name="Delta",
        manufacturer="Delta Controls",
        description="Delta enteliBUS/enteliZON controllers",
        naming_convention="camelCase",
        default_points={
             "BV-1": {"name": "netSensorStatus", "description": "Network Sensor Status"},
             "AV-1": {"name": "activeSetpoint", "description": "Active Setpoint"},
        }
    ),
    "Distech": ControllerProfile(
        name="Distech",
        manufacturer="Distech Controls",
        description="Distech Eclypse series",
        naming_convention="camelCase",
        default_points={
            "AV-99": {"name": "nciSetpoint", "description": "Network Configuration Input"},
            "AV-100": {"name": "nvoSpaceTemp", "description": "Network Variable Output"},
        }
    ),
    "Honeywell": ControllerProfile(
        name="Honeywell",
        manufacturer="Honeywell",
        description="Honeywell CIPer Model 50",
        naming_convention="PascalCase",
        default_points={
            "AV-10": {"name": "EffSetpoint", "description": "Effective Setpoint"},
            "AV-11": {"name": "OccSchedule", "description": "Occupancy Schedule"},
        }
    ),
    "JCI": ControllerProfile(
        name="JCI",
        manufacturer="Johnson Controls",
        description="Metasys FEC/FAC controllers",
        naming_convention="PascalCase",
        default_points={
            "AV-3001": {"name": "ZN-T", "description": "Zone Temperature"},
            "AV-3002": {"name": "ZN-SP", "description": "Zone Setpoint"},
        }
    )
}

def get_profile(name: str) -> ControllerProfile:
    """Get a profile by name, defaulting to Distech if not found."""
    return PROFILES.get(name, PROFILES["Distech"])

def get_random_profile() -> ControllerProfile:
    """Get a random profile."""
    import random
    return random.choice(list(PROFILES.values()))
