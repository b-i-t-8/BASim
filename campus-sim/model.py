"""
Campus simulation model following SOLID principles.

SRP: Each class has a single responsibility
OCP: Classes are open for extension (via inheritance) but closed for modification
LSP: Subclasses can substitute base classes
ISP: Interfaces are segregated (Updatable, PointProvider)
DIP: High-level modules depend on abstractions
"""
import os
import time
import math
import random
import threading
import logging
from abc import ABC, abstractmethod
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Protocol, Optional, Any, Tuple
from datetime import datetime, timedelta

from interfaces import Updatable, PointProvider, PointMetadataProvider, PointDefinition, CampusSizeConfig, PhysicsEngine
from weather import AlmanacOATCalculator, OATCalculator, SinusoidalOATCalculator, WeatherConditions
from profiles import ControllerProfile, get_random_profile, get_profile

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CampusEngine")


# ============== SIMULATION PARAMETERS ==============

class SimulationParameters:
    """
    Global simulation parameters that control physics behavior.
    These can be adjusted by admin users to customize the simulation.
    """
    
    # Default parameter values
    DEFAULTS = {
        # Thermal Model Parameters
        'thermal_mass': {
            'value': 1000.0,
            'min': 100.0,
            'max': 10000.0,
            'unit': 'BTU/°F',
            'description': 'Zone thermal mass (higher = slower temperature changes)',
            'category': 'thermal'
        },
        'envelope_ua': {
            'value': 10.0,
            'min': 1.0,
            'max': 100.0,
            'unit': 'BTU/hr/°F',
            'description': 'Building envelope heat transfer coefficient',
            'category': 'thermal'
        },
        'internal_gain_occupied': {
            'value': 15.0,
            'min': 0.0,
            'max': 50.0,
            'unit': 'BTU/hr',
            'description': 'Internal heat gains during occupied hours (people, lights, equipment)',
            'category': 'thermal'
        },
        'internal_gain_unoccupied': {
            'value': 2.0,
            'min': 0.0,
            'max': 20.0,
            'unit': 'BTU/hr',
            'description': 'Internal heat gains during unoccupied hours',
            'category': 'thermal'
        },
        'solar_gain_factor': {
            'value': 8.0,
            'min': 0.0,
            'max': 30.0,
            'unit': 'BTU/hr',
            'description': 'Maximum solar heat gain factor',
            'category': 'thermal'
        },
        
        # VAV Control Parameters
        'vav_damper_kp': {
            'value': 5.0,
            'min': 0.5,
            'max': 20.0,
            'unit': '',
            'description': 'VAV damper proportional gain (higher = more aggressive)',
            'category': 'control'
        },
        'vav_damper_rate': {
            'value': 5.0,
            'min': 1.0,
            'max': 20.0,
            'unit': '%/sec',
            'description': 'VAV damper movement rate',
            'category': 'control'
        },
        'vav_reheat_gain': {
            'value': 20.0,
            'min': 5.0,
            'max': 50.0,
            'unit': '%/°F',
            'description': 'Reheat valve response gain',
            'category': 'control'
        },
        'vav_reheat_max_delta': {
            'value': 20.0,
            'min': 5.0,
            'max': 40.0,
            'unit': '°F',
            'description': 'Maximum reheat temperature rise',
            'category': 'control'
        },
        
        # AHU Control Parameters
        'ahu_supply_temp_default': {
            'value': 55.0,
            'min': 45.0,
            'max': 65.0,
            'unit': '°F',
            'description': 'Default supply air temperature setpoint',
            'category': 'control'
        },
        'ahu_min_oa_pct': {
            'value': 20.0,
            'min': 10.0,
            'max': 100.0,
            'unit': '%',
            'description': 'Minimum outside air damper position',
            'category': 'control'
        },
        'ahu_fan_max_speed': {
            'value': 100.0,
            'min': 50.0,
            'max': 100.0,
            'unit': '%',
            'description': 'Maximum fan speed',
            'category': 'control'
        },
        
        # Chiller Parameters
        'chiller_min_load_pct': {
            'value': 20.0,
            'min': 10.0,
            'max': 50.0,
            'unit': '%',
            'description': 'Minimum chiller load before staging off',
            'category': 'plant'
        },
        'chiller_kw_per_ton': {
            'value': 0.6,
            'min': 0.4,
            'max': 1.2,
            'unit': 'kW/ton',
            'description': 'Chiller efficiency (lower = more efficient)',
            'category': 'plant'
        },
        'chw_supply_setpoint': {
            'value': 44.0,
            'min': 38.0,
            'max': 50.0,
            'unit': '°F',
            'description': 'Chilled water supply temperature setpoint',
            'category': 'plant'
        },
        
        # Boiler Parameters  
        'boiler_efficiency': {
            'value': 0.85,
            'min': 0.70,
            'max': 0.98,
            'unit': '',
            'description': 'Boiler thermal efficiency',
            'category': 'plant'
        },
        'hw_supply_setpoint': {
            'value': 180.0,
            'min': 140.0,
            'max': 200.0,
            'unit': '°F',
            'description': 'Hot water supply temperature setpoint',
            'category': 'plant'
        },
        
        # Weather/OAT Parameters
        'oat_daily_swing': {
            'value': 20.0,
            'min': 5.0,
            'max': 40.0,
            'unit': '°F',
            'description': 'Daily outside air temperature swing (high-low)',
            'category': 'weather'
        },
        'oat_base_temp': {
            'value': 70.0,
            'min': 30.0,
            'max': 100.0,
            'unit': '°F',
            'description': 'Base outside air temperature (daily average)',
            'category': 'weather'
        },
        'oat_noise_amplitude': {
            'value': 2.0,
            'min': 0.0,
            'max': 10.0,
            'unit': '°F',
            'description': 'Random temperature variation amplitude',
            'category': 'weather'
        },
        
        # Occupancy Schedule Parameters
        'occupancy_start_hour': {
            'value': 7.0,
            'min': 0.0,
            'max': 12.0,
            'unit': 'hour',
            'description': 'Occupancy start time (24-hour format)',
            'category': 'schedule'
        },
        'occupancy_end_hour': {
            'value': 18.0,
            'min': 12.0,
            'max': 24.0,
            'unit': 'hour',
            'description': 'Occupancy end time (24-hour format)',
            'category': 'schedule'
        },
        
        # Electrical Parameters
        'pue_target': {
            'value': 1.4,
            'min': 1.1,
            'max': 2.5,
            'unit': '',
            'description': 'Data center Power Usage Effectiveness target',
            'category': 'electrical'
        },
        'solar_efficiency': {
            'value': 0.18,
            'min': 0.10,
            'max': 0.25,
            'unit': '',
            'description': 'Solar panel efficiency',
            'category': 'electrical'
        },
        'electricity_rate': {
            'value': 0.12,
            'min': 0.05,
            'max': 0.50,
            'unit': '$/kWh',
            'description': 'Cost of electricity',
            'category': 'electrical'
        },
        
        # Fault Simulation Parameters
        'sensor_noise_level': {
            'value': 0.1,
            'min': 0.0,
            'max': 2.0,
            'unit': '°F',
            'description': 'Random noise added to temperature sensors',
            'category': 'faults'
        },
        'valve_leakage_pct': {
            'value': 0.0,
            'min': 0.0,
            'max': 20.0,
            'unit': '%',
            'description': 'Valve leakage when closed',
            'category': 'faults'
        },
        'filter_loading_rate': {
            'value': 1.0,
            'min': 0.1,
            'max': 10.0,
            'unit': 'x',
            'description': 'Multiplier for filter dirtying rate',
            'category': 'faults'
        },
    }
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """Singleton pattern for global parameters."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._params = {}
        self._unit_system = 'US'  # Default to US Customary
        self._campus_name = 'Main Campus'
        self._reset_to_defaults()
        self._initialized = True

    @property
    def unit_system(self):
        return self._unit_system

    @unit_system.setter
    def unit_system(self, value):
        if value in ['US', 'Metric']:
            self._unit_system = value
            logger.info(f"Unit system changed to {value}")

    @property
    def campus_name(self):
        return self._campus_name

    @campus_name.setter
    def campus_name(self, value):
        if value and isinstance(value, str):
            self._campus_name = value.strip()
            logger.info(f"Campus name changed to {self._campus_name}")

    def convert_temp(self, value_f: float) -> float:
        """Convert temperature based on current unit system."""
        if self._unit_system == 'US':
            return value_f
        return (value_f - 32.0) * 5.0 / 9.0

    def get_temp_unit(self) -> str:
        """Get temperature unit string."""
        return "°F" if self._unit_system == 'US' else "°C"

    def convert_flow_water(self, value_gpm: float) -> float:
        """Convert water flow (GPM -> L/s)."""
        if self._unit_system == 'US':
            return value_gpm
        return value_gpm * 0.06309

    def get_flow_water_unit(self) -> str:
        return "GPM" if self._unit_system == 'US' else "L/s"

    def convert_flow_air(self, value_cfm: float) -> float:
        """Convert air flow (CFM -> L/s)."""
        if self._unit_system == 'US':
            return value_cfm
        return value_cfm * 0.4719

    def get_flow_air_unit(self) -> str:
        return "CFM" if self._unit_system == 'US' else "L/s"

    def convert_flow_gas(self, value_cfh: float) -> float:
        """Convert gas flow (CFH -> m³/h)."""
        if self._unit_system == 'US':
            return value_cfh
        return value_cfh * 0.02832

    def get_flow_gas_unit(self) -> str:
        return "CFH" if self._unit_system == 'US' else "m³/h"

    def convert_pressure_wc(self, value_wc: float) -> float:
        """Convert pressure ("WC -> Pa)."""
        if self._unit_system == 'US':
            return value_wc
        return value_wc * 249.089

    def get_pressure_wc_unit(self) -> str:
        return '"WC' if self._unit_system == 'US' else 'Pa'

    def convert_head_ft(self, value_ft: float) -> float:
        """Convert head (ft -> m)."""
        if self._unit_system == 'US':
            return value_ft
        return value_ft * 0.3048

    def get_head_unit(self) -> str:
        return 'ft' if self._unit_system == 'US' else 'm'

    def convert_enthalpy(self, value_btu: float) -> float:
        """Convert enthalpy (BTU/lb -> kJ/kg)."""
        if self._unit_system == 'US':
            return value_btu
        return value_btu * 2.326

    def get_enthalpy_unit(self) -> str:
        return 'BTU/lb' if self._unit_system == 'US' else 'kJ/kg'

    def convert_area(self, value_sqft: float) -> float:
        """Convert area (sq ft -> m²)."""
        if self._unit_system == 'US':
            return value_sqft
        return value_sqft * 0.092903

    def get_area_unit(self) -> str:
        return 'sq ft' if self._unit_system == 'US' else 'm²'
    
    def _reset_to_defaults(self):
        """Reset all parameters to default values."""
        for key, spec in self.DEFAULTS.items():
            self._params[key] = spec['value']
    
    def get(self, key: str) -> float:
        """Get a parameter value."""
        return self._params.get(key, self.DEFAULTS.get(key, {}).get('value', 0.0))
    
    def set(self, key: str, value: float) -> bool:
        """Set a parameter value with validation."""
        if key not in self.DEFAULTS:
            return False
        spec = self.DEFAULTS[key]
        # Clamp to valid range
        value = max(spec['min'], min(spec['max'], float(value)))
        self._params[key] = value
        logger.info(f"Simulation parameter '{key}' set to {value}")
        return True
    
    def get_all(self) -> Dict[str, Dict]:
        """Get all parameters with their current values and metadata."""
        result = {}
        for key, spec in self.DEFAULTS.items():
            result[key] = {
                'value': self._params.get(key, spec['value']),
                'default': spec['value'],
                'min': spec['min'],
                'max': spec['max'],
                'unit': spec['unit'],
                'description': spec['description'],
                'category': spec['category']
            }
        return result
    
    def get_by_category(self) -> Dict[str, Dict]:
        """Get parameters grouped by category."""
        result = {}
        for key, spec in self.DEFAULTS.items():
            cat = spec['category']
            if cat not in result:
                result[cat] = {}
            result[cat][key] = {
                'value': self._params.get(key, spec['value']),
                'default': spec['value'],
                'min': spec['min'],
                'max': spec['max'],
                'unit': spec['unit'],
                'description': spec['description']
            }
        return result
    
    def set_multiple(self, params: Dict[str, float]) -> Dict[str, bool]:
        """Set multiple parameters at once."""
        results = {}
        for key, value in params.items():
            results[key] = self.set(key, value)
        return results
    
    def export(self) -> Dict[str, float]:
        """Export current parameter values for saving."""
        return dict(self._params)
    
    def import_params(self, params: Dict[str, float]) -> int:
        """Import parameter values from saved configuration."""
        count = 0
        for key, value in params.items():
            if self.set(key, value):
                count += 1
        return count
    
    def reset(self, key: str = None):
        """Reset parameter(s) to default."""
        if key is None:
            self._reset_to_defaults()
        elif key in self.DEFAULTS:
            self._params[key] = self.DEFAULTS[key]['value']


def get_simulation_parameters() -> SimulationParameters:
    """Get the global simulation parameters instance."""
    return SimulationParameters()


@dataclass
class PointOverride:
    """Represents an override on a point."""
    value: float
    priority: int = 8  # BACnet-style priority (1-16, lower = higher priority)
    timestamp: datetime = field(default_factory=datetime.now)
    expires: Optional[datetime] = None  # None = no expiration
    source: str = "manual"  # Who/what set the override
    
    def is_expired(self) -> bool:
        """Check if the override has expired."""
        if self.expires is None:
            return False
        return datetime.now() > self.expires


class OverrideManager:
    """
    Centralized override management for all points in the system.
    Supports priority-based overrides similar to BACnet priority arrays.
    """
    
    def __init__(self):
        self._overrides: Dict[str, Dict[int, PointOverride]] = {}  # point_path -> {priority -> override}
        self._lock = threading.Lock()
    
    def set_override(self, point_path: str, value: float, priority: int = 8,
                     duration_seconds: Optional[int] = None, source: str = "manual") -> bool:
        """
        Set an override on a point.
        
        Args:
            point_path: Full path to the point (e.g., "Building_1.AHU_1.VAV_1.setpoint")
            value: Override value
            priority: Priority level (1-16, lower = higher priority)
            duration_seconds: Optional duration in seconds (None = permanent)
            source: Source of the override
            
        Returns:
            True if override was set successfully
        """
        if priority < 1 or priority > 16:
            return False
            
        expires = None
        if duration_seconds:
            expires = datetime.now()
            from datetime import timedelta
            expires = expires + timedelta(seconds=duration_seconds)
        
        override = PointOverride(
            value=value,
            priority=priority,
            timestamp=datetime.now(),
            expires=expires,
            source=source
        )
        
        with self._lock:
            if point_path not in self._overrides:
                self._overrides[point_path] = {}
            self._overrides[point_path][priority] = override
            
        logger.info(f"Override set: {point_path} = {value} (priority {priority}, source: {source})")
        return True
    
    def release_override(self, point_path: str, priority: Optional[int] = None) -> bool:
        """
        Release an override on a point.
        
        Args:
            point_path: Full path to the point
            priority: Specific priority to release (None = release all)
            
        Returns:
            True if any override was released
        """
        with self._lock:
            if point_path not in self._overrides:
                return False
            
            if priority is None:
                # Release all overrides for this point
                del self._overrides[point_path]
                logger.info(f"All overrides released: {point_path}")
                return True
            elif priority in self._overrides[point_path]:
                del self._overrides[point_path][priority]
                if not self._overrides[point_path]:
                    del self._overrides[point_path]
                logger.info(f"Override released: {point_path} (priority {priority})")
                return True
        return False
    
    def get_override(self, point_path: str) -> Optional[Tuple[float, int]]:
        """
        Get the active override value for a point (highest priority non-expired).
        
        Returns:
            Tuple of (value, priority) or None if no active override
        """
        with self._lock:
            if point_path not in self._overrides:
                return None
            
            # Clean expired overrides and find highest priority
            active_overrides = {}
            for priority, override in list(self._overrides[point_path].items()):
                if override.is_expired():
                    del self._overrides[point_path][priority]
                else:
                    active_overrides[priority] = override
            
            if not active_overrides:
                del self._overrides[point_path]
                return None
            
            # Return highest priority (lowest number)
            highest_priority = min(active_overrides.keys())
            return (active_overrides[highest_priority].value, highest_priority)
    
    def get_all_overrides(self) -> Dict[str, Dict]:
        """Get all active overrides with their details."""
        result = {}
        with self._lock:
            for point_path, priorities in list(self._overrides.items()):
                active = {}
                for priority, override in list(priorities.items()):
                    if not override.is_expired():
                        active[priority] = {
                            'value': override.value,
                            'priority': override.priority,
                            'timestamp': override.timestamp.isoformat(),
                            'expires': override.expires.isoformat() if override.expires else None,
                            'source': override.source
                        }
                if active:
                    result[point_path] = active
        return result
    
    def get_point_override_info(self, point_path: str) -> Optional[Dict]:
        """Get detailed override info for a specific point."""
        with self._lock:
            if point_path not in self._overrides:
                return None
            
            result = {}
            for priority, override in self._overrides[point_path].items():
                if not override.is_expired():
                    result[priority] = {
                        'value': override.value,
                        'priority': override.priority,
                        'timestamp': override.timestamp.isoformat(),
                        'expires': override.expires.isoformat() if override.expires else None,
                        'source': override.source
                    }
            return result if result else None


# Global override manager instance
_override_manager: Optional[OverrideManager] = None

def get_override_manager() -> OverrideManager:
    """Get the global override manager instance."""
    global _override_manager
    if _override_manager is None:
        _override_manager = OverrideManager()
    return _override_manager


class DamperController(ABC):
    """
    Abstract damper controller (OCP - can extend with different control strategies).
    """
    
    @abstractmethod
    def calculate_target(self, room_temp: float, setpoint: float) -> float:
        """Calculate target damper position."""
        pass


class ProportionalDamperController(DamperController):
    """Simple proportional damper controller."""
    
    def __init__(self, k_p: float = None, gain: float = 10.0):
        self._gain = gain
    
    @property
    def _k_p(self):
        """Get Kp from simulation parameters."""
        return get_simulation_parameters().get('vav_damper_kp')
    
    def calculate_target(self, room_temp: float, setpoint: float) -> float:
        error = room_temp - setpoint
        target = error * self._k_p * self._gain
        return max(0.0, min(100.0, target))


class ThermalModel(ABC):
    """
    Abstract thermal model (OCP - can extend with different thermal models).
    """
    
    @abstractmethod
    def calculate_temp_change(self, room_temp: float, oat: float, 
                               damper_position: float, dt: float) -> float:
        """Calculate temperature change for given conditions."""
        pass


class SimpleThermalModel(ThermalModel):
    """
    Realistic thermal model for zone temperature simulation.
    Accounts for: supply air, reheat, envelope heat transfer, internal gains.
    Uses SimulationParameters for tunable values.
    """
    
    def __init__(self, thermal_mass: float = None, ua: float = None,
                 supply_air_temp: float = None, cooling_capacity: float = 50.0):
        # These can be overridden per-zone, or use global params
        self._thermal_mass_override = thermal_mass
        self._ua_override = ua
        self._supply_air_temp_override = supply_air_temp
        self._cooling_capacity = cooling_capacity
    
    @property
    def _thermal_mass(self):
        if self._thermal_mass_override is not None:
            return self._thermal_mass_override
        return get_simulation_parameters().get('thermal_mass')
    
    @property
    def _ua(self):
        if self._ua_override is not None:
            return self._ua_override
        return get_simulation_parameters().get('envelope_ua')
    
    @property
    def _supply_air_temp(self):
        if self._supply_air_temp_override is not None:
            return self._supply_air_temp_override
        return get_simulation_parameters().get('ahu_supply_temp_default')
    
    def calculate_temp_change(self, room_temp: float, oat: float,
                               damper_position: float, dt: float,
                               supply_air_temp: float = None,
                               reheat_pct: float = 0.0,
                               time_of_day: float = 0.5) -> float:
        """
        Calculate temperature change considering multiple heat transfer modes.
        
        Args:
            room_temp: Current room temperature (°F)
            oat: Outside air temperature (°F)
            damper_position: VAV damper position (0-100%)
            dt: Time step (seconds)
            supply_air_temp: Supply air temperature from AHU (°F)
            reheat_pct: Reheat valve position (0-100%)
            time_of_day: Time of day (0-1, 0.5=noon)
        """
        params = get_simulation_parameters()
        sat = supply_air_temp if supply_air_temp is not None else self._supply_air_temp
        
        # 1. Supply air cooling/heating effect
        # Airflow proportional to damper position
        cfm_fraction = damper_position / 100.0
        # Heat transfer from supply air: Q = 1.08 * CFM * ΔT
        supply_air_heat = self._cooling_capacity * cfm_fraction * (sat - room_temp) / 10.0
        
        # 2. Reheat effect (electric or hot water coil)
        # Reheat can add up to reheat_max_delta to supply air
        if reheat_pct > 0:
            reheat_delta = params.get('vav_reheat_max_delta') * (reheat_pct / 100.0)
            reheat_heat = self._cooling_capacity * cfm_fraction * reheat_delta / 10.0
        else:
            reheat_heat = 0.0
        
        # 3. Envelope heat transfer (conduction through walls/roof)
        envelope_heat = self._ua * (oat - room_temp)
        
        # 4. Internal heat gains (people, lights, equipment)
        # Varies with time of day (occupancy schedule)
        occ_start = params.get('occupancy_start_hour') / 24.0
        occ_end = params.get('occupancy_end_hour') / 24.0
        internal_gain_occ = params.get('internal_gain_occupied')
        internal_gain_unocc = params.get('internal_gain_unoccupied')
        
        if occ_start < time_of_day < occ_end:
            # Occupied hours - higher internal gains
            occ_duration = occ_end - occ_start
            occupancy = 0.5 + 0.5 * math.sin((time_of_day - occ_start) * math.pi / occ_duration)
            internal_gains = internal_gain_unocc + (internal_gain_occ - internal_gain_unocc) * occupancy
        else:
            # Unoccupied - minimal gains
            internal_gains = internal_gain_unocc
        
        # 5. Solar gains (simplified - varies with time of day)
        solar_factor = params.get('solar_gain_factor')
        if 0.25 < time_of_day < 0.75:  # Daylight hours
            solar_angle = math.sin((time_of_day - 0.25) * math.pi / 0.5)
            solar_gains = solar_factor * max(0, solar_angle) * max(0, (oat - 60) / 40)
        else:
            solar_gains = 0.0
        
        # Net heat transfer
        net_heat = supply_air_heat + reheat_heat + envelope_heat + internal_gains + solar_gains
        
        # Temperature change: ΔT = Q * dt / (thermal_mass)
        delta_t = net_heat / self._thermal_mass * dt
        
        return delta_t


@dataclass
class VAV(Updatable, PointProvider, PointMetadataProvider):
    """
    Variable Air Volume box (SRP - manages VAV state and physics).
    Implements Updatable for physics loop and PointProvider for data exposure.
    """
    id: int
    name: str
    zone_name: str = ""  # Human-friendly zone name (e.g., "Conference Room 101")
    room_temp: float = 72.0
    cooling_setpoint: float = 74.0  # Cooling setpoint (cooling starts above this)
    heating_setpoint: float = 70.0  # Heating setpoint (heating starts below this)
    discharge_air_temp: float = 55.0  # Discharge air temperature
    damper_position: float = 0.0
    cfm_max: float = 500.0  # Maximum airflow CFM
    cfm_min: float = 100.0  # Minimum airflow CFM
    reheat_valve: float = 0.0  # Reheat valve position (0-100%)
    occupancy: bool = True  # Zone occupancy status
    _thermal_model: ThermalModel = field(default_factory=SimpleThermalModel)
    _damper_controller: DamperController = field(default_factory=ProportionalDamperController)
    _point_path: str = ""  # Set by parent (e.g., "Building_1.AHU_1.VAV_1")
    profile: Optional[ControllerProfile] = None
    
    # Writable points that can be overridden
    WRITABLE_POINTS = {'cooling_setpoint', 'heating_setpoint', 'damper_position', 'reheat_valve'}
    
    @property
    def setpoint(self) -> float:
        """Effective setpoint (midpoint between heating and cooling) for backwards compatibility."""
        return (self.cooling_setpoint + self.heating_setpoint) / 2.0
    
    # Writable points that can be overridden
    WRITABLE_POINTS = {'setpoint', 'damper_position', 'reheat_valve'}
    
    def _apply_override(self, point_name: str, default_value: float) -> float:
        """Apply override if one exists for this point."""
        if not self._point_path:
            return default_value
        full_path = f"{self._point_path}.{point_name}"
        override = get_override_manager().get_override(full_path)
        if override:
            return override[0]  # Return override value
        return default_value
    
    def _get_override_status(self, point_name: str) -> Optional[int]:
        """Get override priority if point is overridden, None otherwise."""
        if not self._point_path:
            return None
        full_path = f"{self._point_path}.{point_name}"
        override = get_override_manager().get_override(full_path)
        return override[1] if override else None
    
    def update(self, oat: float, dt: float, supply_air_temp: float = 55.0, time_of_day: float = 0.5) -> None:
        """Update VAV state based on physics and control logic."""
        # Apply overrides to writable points
        effective_cooling_sp = self._apply_override('cooling_setpoint', self.cooling_setpoint)
        effective_heating_sp = self._apply_override('heating_setpoint', self.heating_setpoint)
        damper_override = self._get_override_status('damper_position')
        reheat_override = self._get_override_status('reheat_valve')
        
        # Update discharge air temp (tracks supply air with some lag)
        self.discharge_air_temp = 0.9 * self.discharge_air_temp + 0.1 * supply_air_temp
        if self.reheat_valve > 0:
            # Reheat increases discharge temp
            self.discharge_air_temp += self.reheat_valve * 0.3  # Up to 30°F reheat
        
        # Update temperature using enhanced thermal model
        delta_t = self._thermal_model.calculate_temp_change(
            self.room_temp, oat, self.damper_position, dt,
            supply_air_temp=supply_air_temp,
            reheat_pct=self.reheat_valve,
            time_of_day=time_of_day
        )
        self.room_temp += delta_t
        
        # Clamp room temp to reasonable bounds
        self.room_temp = max(55.0, min(95.0, self.room_temp))
        
        # Determine mode: cooling, heating, or deadband
        # Cooling if above cooling setpoint, heating if below heating setpoint
        cooling_error = self.room_temp - effective_cooling_sp  # Positive = needs cooling
        heating_error = effective_heating_sp - self.room_temp  # Positive = needs heating
        
        # Update damper position (skip if overridden)
        if damper_override is None:
            min_damper = (self.cfm_min / self.cfm_max) * 100.0 if self.cfm_max > 0 else 10.0
            
            if cooling_error > 0:
                # Cooling mode - increase damper to cool
                target_damper = min_damper + (cooling_error * 20)  # 20% per degree
                target_damper = min(100.0, target_damper)
            elif heating_error > 0:
                # Heating mode - damper at minimum, reheat handles it
                target_damper = min_damper
            else:
                # Deadband - maintain minimum airflow
                target_damper = min_damper
            
            # Actuator movement simulation (slow movement ~5%/sec)
            max_change = 5.0 * (dt / 5.0)  # 5% per 5 seconds
            if self.damper_position < target_damper:
                self.damper_position = min(target_damper, self.damper_position + max_change)
            elif self.damper_position > target_damper:
                self.damper_position = max(target_damper, self.damper_position - max_change)
        else:
            # Apply damper override directly
            self.damper_position = self._apply_override('damper_position', self.damper_position)
        
        # Reheat control (skip if overridden)
        if reheat_override is None:
            min_damper = (self.cfm_min / self.cfm_max) * 100.0 if self.cfm_max > 0 else 10.0
            if heating_error > 0.5 and self.damper_position <= min_damper + 5:
                # Need heating - increase reheat proportionally
                target_reheat = min(100.0, heating_error * 25)  # 25% per degree below heating setpoint
                self.reheat_valve = min(target_reheat, self.reheat_valve + 2.0)
            elif heating_error < 0 or self.damper_position > min_damper + 10:
                # Room above heating setpoint or damper open - close reheat
                self.reheat_valve = max(0.0, self.reheat_valve - 3.0)
        else:
            self.reheat_valve = self._apply_override('reheat_valve', self.reheat_valve)
        
        # Clamp values
        self.damper_position = max(0.0, min(100.0, self.damper_position))
        self.reheat_valve = max(0.0, min(100.0, self.reheat_valve))
    
    @property
    def cfm_actual(self) -> float:
        """Calculate actual CFM based on damper position."""
        cfm_range = self.cfm_max - self.cfm_min
        return self.cfm_min + (cfm_range * self.damper_position / 100.0)
    
    def get_point_definitions(self) -> List[PointDefinition]:
        """Return point metadata."""
        points = [
            PointDefinition("RoomTemp", "°F", False, "Zone Temperature", "AI", "room_temp"),
            PointDefinition("DischargeTemp", "°F", False, "Discharge Air Temp", "AI", "discharge_air_temp"),
            PointDefinition("CoolingSetpoint", "°F", True, "Cooling Setpoint", "AO", "cooling_setpoint"),
            PointDefinition("HeatingSetpoint", "°F", True, "Heating Setpoint", "AO", "heating_setpoint"),
            PointDefinition("DamperPosition", "%", True, "Damper Position Command", "AO", "damper_position"),
            PointDefinition("ReheatValve", "%", True, "Reheat Valve Command", "AO", "reheat_valve"),
            PointDefinition("Airflow", "CFM", False, "Airflow", "AI", "cfm_actual"),
            PointDefinition("Occupancy", "On/Off", False, "Occupancy Sensor", "BI", "occupancy"),
        ]
        
        if self.profile:
            # Apply naming convention
            if self.profile.naming_convention == "camelCase":
                for p in points:
                    p.name = p.name[0].lower() + p.name[1:]
            elif self.profile.naming_convention == "snake_case":
                import re
                for p in points:
                    p.name = re.sub(r'(?<!^)(?=[A-Z])', '_', p.name).lower()
            
            # Add vendor specific points
            for pt_id, pt_def in self.profile.default_points.items():
                name = pt_def['name']
                desc = pt_def['description']
                
                if any(p.name.lower() == name.lower() for p in points):
                    continue
                    
                points.append(PointDefinition(
                    name=name,
                    units="",
                    writable=False,
                    description=desc,
                    bacnet_object_type="AV",
                    internal_key=""
                ))
                
        return points

    def get_points(self) -> Dict[str, float]:
        """Return all VAV points as a dictionary."""
        return {
            'room_temp': self.room_temp,
            'discharge_air_temp': self.discharge_air_temp,
            'cooling_setpoint': self.cooling_setpoint,
            'heating_setpoint': self.heating_setpoint,
            'damper_position': self.damper_position,
            'cfm_max': self.cfm_max,
            'cfm_min': self.cfm_min,
            'cfm_actual': self.cfm_actual,
            'reheat_valve': self.reheat_valve,
            'occupancy': float(self.occupancy),
        }
    
    def get_points_with_override_status(self) -> Dict[str, Dict]:
        """Return all points with their override status."""
        result = {}
        for point_name, value in self.get_points().items():
            override_priority = self._get_override_status(point_name)
            result[point_name] = {
                'value': value,
                'overridden': override_priority is not None,
                'override_priority': override_priority,
                'writable': point_name in self.WRITABLE_POINTS
            }
        return result


# Zone name templates for random generation
ZONE_NAMES = [
    "Office", "Conference Room", "Break Room", "Storage", "IT Room",
    "Reception", "Lobby", "Restroom", "Kitchen", "Training Room",
    "Executive Office", "Open Office", "Server Room", "Mail Room",
    "Copy Room", "Hallway", "Mechanical Room", "Electrical Room",
    "Janitor Closet", "Loading Dock", "Warehouse", "Lab", "Clinic",
]

# Building name templates
BUILDING_NAMES = [
    "Main Building", "North Tower", "South Tower", "East Wing", "West Wing",
    "Administration", "Engineering", "Research Center", "Student Center",
    "Library", "Science Hall", "Arts Building", "Medical Center",
    "Parking Garage", "Recreation Center", "Dining Hall", "Technology Center",
    "Business School", "Law School", "Dormitory", "Faculty Building",
]

# Data Center naming
DATA_CENTER_NAMES = [
    "Primary Data Center", "Disaster Recovery DC", "Edge Data Center",
    "Cloud Hub", "Compute Center", "Network Operations Center"
]

# Wastewater facility naming  
WASTEWATER_NAMES = [
    "Main WWTP", "North Treatment Plant", "Reclamation Facility",
    "Water Recovery Center", "Environmental Services"
]


@dataclass
class AHU(Updatable, PointProvider, PointMetadataProvider):
    """
    Air Handling Unit (SRP - manages AHU state).
    Implements Updatable and PointProvider interfaces.
    """
    id: int
    name: str
    ahu_type: str = "VAV"  # "VAV" or "100%OA" (100% Outside Air)
    vavs: List[VAV] = field(default_factory=list)
    supply_temp: float = 55.0
    supply_temp_setpoint: float = 55.0  # Target supply air temperature
    fan_status: bool = True
    fan_speed: float = 75.0  # Fan speed percentage
    return_temp: float = 72.0  # Return air temperature
    mixed_air_temp: float = 65.0  # Mixed air temperature
    outside_air_damper: float = 20.0  # OA damper position
    filter_dp: float = 0.5  # Filter differential pressure
    cooling_valve: float = 0.0  # Cooling coil valve position
    heating_valve: float = 0.0  # Heating coil valve position
    _point_path: str = ""  # Set by parent (e.g., "Building_1.AHU_1")
    profile: Optional[ControllerProfile] = None
    
    # Writable points that can be overridden
    WRITABLE_POINTS = {'fan_status', 'fan_speed', 'outside_air_damper', 'cooling_valve', 'heating_valve', 'supply_temp_setpoint'}
    
    def _apply_override(self, point_name: str, default_value: float) -> float:
        """Apply override if one exists for this point."""
        if not self._point_path:
            return default_value
        full_path = f"{self._point_path}.{point_name}"
        override = get_override_manager().get_override(full_path)
        if override:
            return override[0]
        return default_value
    
    def _get_override_status(self, point_name: str) -> Optional[int]:
        """Get override priority if point is overridden, None otherwise."""
        if not self._point_path:
            return None
        full_path = f"{self._point_path}.{point_name}"
        override = get_override_manager().get_override(full_path)
        return override[1] if override else None
    
    def update(self, oat: float = 0.0, dt: float = 0.0, time_of_day: float = 0.5, chw_supply_temp: float = 44.0, hw_supply_temp: float = 180.0) -> None:
        """Update AHU state based on conditions with realistic thermal calculations."""
        # Check for overrides
        fan_speed_override = self._get_override_status('fan_speed')
        oa_damper_override = self._get_override_status('outside_air_damper')
        cooling_override = self._get_override_status('cooling_valve')
        heating_override = self._get_override_status('heating_valve')
        
        # Apply fan speed override
        if fan_speed_override is not None:
            self.fan_speed = self._apply_override('fan_speed', self.fan_speed)
        
        # Calculate return air temp as average of zone temps (from VAVs)
        if self.vavs:
            self.return_temp = sum(vav.room_temp for vav in self.vavs) / len(self.vavs)
        else:
            # Slowly drift return temp toward setpoint area
            self.return_temp = 0.99 * self.return_temp + 0.01 * 72.0
        
        # Economizer control (if not overridden)
        if oa_damper_override is None:
            if self.ahu_type == "100%OA":
                self.outside_air_damper = 100.0
            else:
                # Economizer: use more OA when it's cooler than return air
                min_oa = 15.0  # Minimum ventilation requirement
                if oat < self.return_temp - 2:
                    # Free cooling available - open damper more
                    # Full economizer when OA is 10°F below return
                    economizer_pct = min(100.0, min_oa + (self.return_temp - oat) * 8)
                    self.outside_air_damper = economizer_pct
                else:
                    # No free cooling - minimum OA only
                    self.outside_air_damper = min_oa
        else:
            self.outside_air_damper = self._apply_override('outside_air_damper', self.outside_air_damper)
        
        # Calculate mixed air temperature
        if self.ahu_type == "100%OA":
            self.mixed_air_temp = oat
        else:
            oa_fraction = self.outside_air_damper / 100.0
            self.mixed_air_temp = (oat * oa_fraction) + (self.return_temp * (1 - oa_fraction))
        
        # Target supply air temperature (reset based on OAT for energy savings)
        # Check for setpoint override first
        setpoint_override = self._get_override_status('supply_temp_setpoint')
        if setpoint_override is not None:
            target_supply = self._apply_override('supply_temp_setpoint', self.supply_temp_setpoint)
        else:
            # Calculate reset setpoint: warmer supply when cooler outside
            target_supply = 55.0 + max(0, (70 - oat) * 0.15)  # 55-58°F range
            target_supply = max(52.0, min(65.0, target_supply))
        
        # Store the setpoint for display
        self.supply_temp_setpoint = target_supply
        
        # Cooling coil performance (unless overridden)
        if cooling_override is None:
            if self.mixed_air_temp > target_supply + 1:
                # Need cooling - calculate valve position based on coil performance
                # Coil can typically cool air by 15-25°F at full capacity
                cooling_needed = self.mixed_air_temp - target_supply
                max_cooling = 25.0  # Max delta-T across coil
                self.cooling_valve = min(100.0, (cooling_needed / max_cooling) * 100)
            else:
                # Close cooling valve slowly
                self.cooling_valve = max(0.0, self.cooling_valve - 2.0)
        else:
            self.cooling_valve = self._apply_override('cooling_valve', self.cooling_valve)
        
        # Heating coil performance (unless overridden)
        if heating_override is None:
            if self.mixed_air_temp < target_supply - 1:
                # Need heating
                heating_needed = target_supply - self.mixed_air_temp
                max_heating = 30.0  # Max delta-T across coil
                self.heating_valve = min(100.0, (heating_needed / max_heating) * 100)
            else:
                # Close heating valve slowly
                self.heating_valve = max(0.0, self.heating_valve - 2.0)
        else:
            self.heating_valve = self._apply_override('heating_valve', self.heating_valve)
        
        # Calculate actual supply air temperature based on coil positions
        params = SimulationParameters()
        leakage = params.get('valve_leakage_pct')
        
        # Cooling effect from chilled water coil
        effective_cooling = max(self.cooling_valve, leakage)
        if effective_cooling > 0:
            coil_effectiveness = 0.85  # Typical coil effectiveness
            max_cool_delta = (self.mixed_air_temp - chw_supply_temp) * coil_effectiveness
            actual_cool_delta = max_cool_delta * (effective_cooling / 100.0)
            temp_after_cooling = self.mixed_air_temp - actual_cool_delta
        else:
            temp_after_cooling = self.mixed_air_temp
        
        # Heating effect from hot water coil
        effective_heating = max(self.heating_valve, leakage)
        if effective_heating > 0:
            max_heat_delta = (hw_supply_temp - temp_after_cooling) * 0.7  # 70% effectiveness
            actual_heat_delta = max_heat_delta * (effective_heating / 100.0) * 0.5  # Typically don't use full heating
            self.supply_temp = temp_after_cooling + actual_heat_delta
        else:
            self.supply_temp = temp_after_cooling
        
        # Add fan heat (about 1-2°F rise through fan)
        fan_heat = 1.5 * (self.fan_speed / 100.0)
        self.supply_temp += fan_heat
        
        # Clamp supply temp to reasonable bounds
        self.supply_temp = max(50.0, min(90.0, self.supply_temp))
        
        # Apply sensor noise
        params = SimulationParameters()
        noise_amp = params.get('sensor_noise_level')
        if noise_amp > 0:
            self.supply_temp += random.uniform(-noise_amp, noise_amp)
            self.return_temp += random.uniform(-noise_amp, noise_amp)
            self.mixed_air_temp += random.uniform(-noise_amp, noise_amp)
        
        # Filter DP slowly increases (simulating filter loading) - faster during occupied hours
        load_factor = 1.0 if 0.29 < time_of_day < 0.75 else 0.3
        loading_rate = params.get('filter_loading_rate')
        self.filter_dp = min(2.5, self.filter_dp + random.uniform(0, 0.0005) * dt * load_factor * loading_rate)
    
    def get_point_definitions(self) -> List[PointDefinition]:
        """Return point metadata."""
        points = [
            PointDefinition("SupplyTemp", "°F", False, "Supply Air Temperature", "AI", "supply_temp"),
            PointDefinition("ReturnTemp", "°F", False, "Return Air Temperature", "AI", "return_temp"),
            PointDefinition("MixedAirTemp", "°F", False, "Mixed Air Temperature", "AI", "mixed_air_temp"),
            PointDefinition("SupplyTempSP", "°F", True, "Supply Air Temperature Setpoint", "AO", "supply_temp_setpoint"),
            PointDefinition("FanSpeed", "%", True, "Supply Fan Speed Command", "AO", "fan_speed"),
            PointDefinition("OADamper", "%", True, "Outside Air Damper Position", "AO", "outside_air_damper"),
            PointDefinition("FanStatus", "On/Off", False, "Supply Fan Status", "BI", "fan_status"),
            PointDefinition("Enable", "On/Off", True, "AHU Enable Command", "BO", "fan_status"),
        ]
        
        if self.profile:
            # Apply naming convention
            if self.profile.naming_convention == "camelCase":
                for p in points:
                    p.name = p.name[0].lower() + p.name[1:]
            elif self.profile.naming_convention == "snake_case":
                import re
                for p in points:
                    p.name = re.sub(r'(?<!^)(?=[A-Z])', '_', p.name).lower()
            
            # Add vendor specific points (simulated as static values for now)
            for pt_id, pt_def in self.profile.default_points.items():
                name = pt_def['name']
                desc = pt_def['description']
                
                if any(p.name.lower() == name.lower() for p in points):
                    continue
                    
                points.append(PointDefinition(
                    name=name,
                    units="",
                    writable=False,
                    description=desc,
                    bacnet_object_type="AV",
                    internal_key="" # No internal key for these yet
                ))
                
        return points

    def get_points(self) -> Dict[str, float]:
        """Return AHU points."""
        return {
            'supply_temp': self.supply_temp,
            'supply_temp_setpoint': self.supply_temp_setpoint,
            'fan_status': float(self.fan_status),
            'fan_speed': self.fan_speed,
            'return_temp': self.return_temp,
            'mixed_air_temp': self.mixed_air_temp,
            'outside_air_damper': self.outside_air_damper,
            'filter_dp': self.filter_dp,
            'cooling_valve': self.cooling_valve,
            'heating_valve': self.heating_valve,
        }
    
    def get_points_with_override_status(self) -> Dict[str, Dict]:
        """Return all points with their override status."""
        result = {}
        for point_name, value in self.get_points().items():
            override_priority = self._get_override_status(point_name)
            result[point_name] = {
                'value': value,
                'overridden': override_priority is not None,
                'override_priority': override_priority,
                'writable': point_name in self.WRITABLE_POINTS
            }
        return result


@dataclass
class Building(PointProvider):
    """Building containing AHUs (SRP - manages building structure)."""
    id: int
    name: str
    display_name: str = ""  # Human-friendly building name
    ahus: List[AHU] = field(default_factory=list)
    device_instance: int = 0
    floor_count: int = 1  # Number of floors
    square_footage: int = 10000  # Building size in sq ft
    occupied: bool = False
    occupancy_schedule: Tuple[int, int] = (7, 18) # Start hour, End hour
    profile: ControllerProfile = field(default_factory=lambda: get_profile("Distech"))
    
    def __post_init__(self):
        if not self.display_name:
            self.display_name = self.name
            
    def update_occupancy(self, current_date: datetime):
        """Update occupancy status based on schedule and date."""
        # Check for override first
        override = get_override_manager().get_override(f"Building_{self.id}.Occupancy")
        if override:
            self.occupied = bool(override[0])
            return

        # Default schedule logic
        is_weekend = current_date.weekday() >= 5
        hour = current_date.hour + current_date.minute / 60.0
        
        if is_weekend:
            self.occupied = False
        else:
            start, end = self.occupancy_schedule
            self.occupied = start <= hour < end
    
    def get_points(self) -> Dict[str, float]:
        """Return all points from all AHUs and VAVs."""
        points = {f"{self.name}_Occupancy": float(self.occupied)}
        for ahu in self.ahus:
            prefix = f"{self.name}_{ahu.name}"
            for key, value in ahu.get_points().items():
                points[f"{prefix}_{key}"] = value
            for vav in ahu.vavs:
                vav_prefix = f"{prefix}_{vav.name}"
                for key, value in vav.get_points().items():
                    points[f"{vav_prefix}_{key}"] = value
        return points
    
    @property
    def vav_count(self) -> int:
        """Total VAV count across all AHUs."""
        return sum(len(ahu.vavs) for ahu in self.ahus)
    
    @property
    def oa_ahu_count(self) -> int:
        """Count of 100% OA AHUs."""
        return sum(1 for ahu in self.ahus if ahu.ahu_type == "100%OA")


# =============================================================================
# Central Plant Equipment
# =============================================================================

@dataclass
class Chiller(Updatable, PointProvider):
    """
    Centrifugal or screw chiller for producing chilled water.
    """
    id: int
    name: str
    capacity_tons: float = 500.0  # Cooling capacity in tons
    status: bool = False  # Running status
    chw_supply_temp: float = 44.0  # Chilled water supply temp (°F)
    chw_return_temp: float = 54.0  # Chilled water return temp (°F)
    chw_flow_gpm: float = 0.0  # Chilled water flow (GPM)
    condenser_water_supply_temp: float = 85.0  # Condenser water in
    condenser_water_return_temp: float = 95.0  # Condenser water out
    load_percent: float = 0.0  # Current load percentage
    kw: float = 0.0  # Power consumption
    efficiency_kw_ton: float = 0.6  # Efficiency (kW/ton)
    fault: bool = False
    _point_path: str = ""  # Set by parent (e.g., "CentralPlant.Chiller_1")
    
    # Writable points that can be overridden
    WRITABLE_POINTS = {'status', 'chw_supply_temp'}
    
    def _apply_override(self, point_name: str, default_value: float) -> float:
        """Apply override if one exists for this point."""
        if not self._point_path:
            return default_value
        full_path = f"{self._point_path}.{point_name}"
        override = get_override_manager().get_override(full_path)
        if override:
            return override[0]
        return default_value
    
    def _get_override_status(self, point_name: str) -> Optional[int]:
        """Get override priority if point is overridden, None otherwise."""
        if not self._point_path:
            return None
        full_path = f"{self._point_path}.{point_name}"
        override = get_override_manager().get_override(full_path)
        return override[1] if override else None
    
    def update(self, oat: float = 0.0, dt: float = 0.0, cooling_demand: float = 0.0) -> None:
        """Update chiller state based on demand."""
        # Apply status override
        status_override = self._get_override_status('status')
        if status_override is not None:
            self.status = bool(self._apply_override('status', float(self.status)))
        
        if self.status and not self.fault:
            # Calculate load based on demand
            max_load = self.capacity_tons
            self.load_percent = min(100.0, (cooling_demand / max_load) * 100) if max_load > 0 else 0
            
            # Calculate power consumption
            actual_tons = (self.load_percent / 100.0) * self.capacity_tons
            self.kw = actual_tons * self.efficiency_kw_ton
            
            # Calculate flows and temps
            self.chw_flow_gpm = (self.load_percent / 100.0) * (self.capacity_tons * 2.4)
            delta_t = 10.0 * (self.load_percent / 100.0)  # 10°F delta at full load
            self.chw_return_temp = self.chw_supply_temp + delta_t
            
            # Condenser water temps
            self.condenser_water_return_temp = self.condenser_water_supply_temp + (delta_t * 1.25)
        else:
            self.load_percent = 0.0
            self.kw = 0.0
            self.chw_flow_gpm = 0.0
    
    def get_points(self) -> Dict[str, float]:
        return {
            'status': float(self.status),
            'chw_supply_temp': self.chw_supply_temp,
            'chw_return_temp': self.chw_return_temp,
            'chw_flow_gpm': self.chw_flow_gpm,
            'cw_supply_temp': self.condenser_water_supply_temp,
            'cw_return_temp': self.condenser_water_return_temp,
            'load_percent': self.load_percent,
            'kw': self.kw,
            'fault': float(self.fault),
        }
    
    def get_points_with_override_status(self) -> Dict[str, Dict]:
        """Return all points with their override status."""
        result = {}
        for point_name, value in self.get_points().items():
            override_priority = self._get_override_status(point_name)
            result[point_name] = {
                'value': value,
                'overridden': override_priority is not None,
                'override_priority': override_priority,
                'writable': point_name in self.WRITABLE_POINTS
            }
        return result


@dataclass
class Boiler(Updatable, PointProvider):
    """
    Hot water or steam boiler for heating.
    """
    id: int
    name: str
    capacity_mbh: float = 2000.0  # Capacity in MBH (1000 BTU/hr)
    status: bool = False
    hw_supply_temp: float = 180.0  # Hot water supply temp (°F)
    hw_return_temp: float = 160.0  # Hot water return temp (°F)
    hw_flow_gpm: float = 0.0
    firing_rate: float = 0.0  # Firing rate percentage
    gas_flow_cfh: float = 0.0  # Gas consumption (cubic feet/hr)
    stack_temp: float = 300.0  # Exhaust stack temperature
    efficiency: float = 0.85  # Thermal efficiency
    fault: bool = False
    _point_path: str = ""  # Set by parent (e.g., "CentralPlant.Boiler_1")
    
    # Writable points that can be overridden
    WRITABLE_POINTS = {'status', 'hw_supply_temp', 'firing_rate'}
    
    def _apply_override(self, point_name: str, default_value: float) -> float:
        """Apply override if one exists for this point."""
        if not self._point_path:
            return default_value
        full_path = f"{self._point_path}.{point_name}"
        override = get_override_manager().get_override(full_path)
        if override:
            return override[0]
        return default_value
    
    def _get_override_status(self, point_name: str) -> Optional[int]:
        """Get override priority if point is overridden, None otherwise."""
        if not self._point_path:
            return None
        full_path = f"{self._point_path}.{point_name}"
        override = get_override_manager().get_override(full_path)
        return override[1] if override else None
    
    def update(self, oat: float = 0.0, dt: float = 0.0, heating_demand: float = 0.0) -> None:
        """Update boiler state based on demand."""
        # Apply status override
        status_override = self._get_override_status('status')
        if status_override is not None:
            self.status = bool(self._apply_override('status', float(self.status)))
        
        if self.status and not self.fault:
            # Calculate firing rate based on demand
            max_output = self.capacity_mbh
            self.firing_rate = min(100.0, (heating_demand / max_output) * 100) if max_output > 0 else 0
            
            # Calculate gas consumption (approx 1 CFH per 1000 BTU input)
            input_mbh = (self.firing_rate / 100.0) * self.capacity_mbh / self.efficiency
            self.gas_flow_cfh = input_mbh  # Simplified
            
            # Calculate flows and temps
            self.hw_flow_gpm = (self.firing_rate / 100.0) * (self.capacity_mbh / 10)  # Simplified
            delta_t = 20.0 * (self.firing_rate / 100.0)  # 20°F delta at full fire
            self.hw_return_temp = self.hw_supply_temp - delta_t
            
            # Stack temp varies with firing rate
            self.stack_temp = 250 + (self.firing_rate * 1.5)
        else:
            self.firing_rate = 0.0
            self.gas_flow_cfh = 0.0
            self.hw_flow_gpm = 0.0
    
    def get_points(self) -> Dict[str, float]:
        return {
            'status': float(self.status),
            'hw_supply_temp': self.hw_supply_temp,
            'hw_return_temp': self.hw_return_temp,
            'hw_flow_gpm': self.hw_flow_gpm,
            'firing_rate': self.firing_rate,
            'gas_flow_cfh': self.gas_flow_cfh,
            'stack_temp': self.stack_temp,
            'fault': float(self.fault),
        }
    
    def get_points_with_override_status(self) -> Dict[str, Dict]:
        """Return all points with their override status."""
        result = {}
        for point_name, value in self.get_points().items():
            override_priority = self._get_override_status(point_name)
            result[point_name] = {
                'value': value,
                'overridden': override_priority is not None,
                'override_priority': override_priority,
                'writable': point_name in self.WRITABLE_POINTS
            }
        return result


@dataclass
class CoolingTower(Updatable, PointProvider):
    """
    Cooling tower for rejecting heat from condenser water.
    """
    id: int
    name: str
    capacity_tons: float = 600.0  # Rejection capacity
    status: bool = False
    fan_speed: float = 0.0  # VFD speed percentage
    cw_supply_temp: float = 85.0  # To chillers
    cw_return_temp: float = 95.0  # From chillers
    cw_flow_gpm: float = 0.0
    wet_bulb_temp: float = 70.0
    approach_temp: float = 7.0  # Approach to wet bulb
    basin_temp: float = 85.0
    makeup_water_flow: float = 0.0  # Makeup water GPM
    blowdown_flow: float = 0.0
    fault: bool = False
    _point_path: str = ""  # Set by parent (e.g., "CentralPlant.CoolingTower_1")
    
    # Writable points that can be overridden
    WRITABLE_POINTS = {'status', 'fan_speed'}
    
    def _apply_override(self, point_name: str, default_value: float) -> float:
        """Apply override if one exists for this point."""
        if not self._point_path:
            return default_value
        full_path = f"{self._point_path}.{point_name}"
        override = get_override_manager().get_override(full_path)
        if override:
            return override[0]
        return default_value
    
    def _get_override_status(self, point_name: str) -> Optional[int]:
        """Get override priority if point is overridden, None otherwise."""
        if not self._point_path:
            return None
        full_path = f"{self._point_path}.{point_name}"
        override = get_override_manager().get_override(full_path)
        return override[1] if override else None
    
    def update(self, oat: float = 0.0, dt: float = 0.0, wet_bulb: float = None, 
               heat_rejection: float = 0.0) -> None:
        """Update cooling tower state."""
        if wet_bulb is not None:
            self.wet_bulb_temp = wet_bulb
        else:
            # Estimate wet bulb from OAT (simplified)
            self.wet_bulb_temp = oat - 10 - random.uniform(0, 5)
        
        # Apply status override
        status_override = self._get_override_status('status')
        if status_override is not None:
            self.status = bool(self._apply_override('status', float(self.status)))
        
        if self.status and not self.fault:
            # Check for fan speed override
            fan_speed_override = self._get_override_status('fan_speed')
            if fan_speed_override is not None:
                self.fan_speed = self._apply_override('fan_speed', self.fan_speed)
            else:
                # Calculate fan speed based on load
                max_rejection = self.capacity_tons * 15000  # BTU/hr per ton
                load_fraction = min(1.0, heat_rejection / max_rejection) if max_rejection > 0 else 0
                self.fan_speed = max(30.0, load_fraction * 100)  # Min 30% speed
            
            # Supply temp approaches wet bulb
            max_rejection = self.capacity_tons * 15000
            load_fraction = min(1.0, heat_rejection / max_rejection) if max_rejection > 0 else 0
            self.cw_supply_temp = self.wet_bulb_temp + self.approach_temp + (5 * (1 - load_fraction))
            self.basin_temp = self.cw_supply_temp
            
            # Flow based on load
            self.cw_flow_gpm = load_fraction * (self.capacity_tons * 3.0)
            
            # Makeup water (evaporation + blowdown)
            evap_rate = load_fraction * self.capacity_tons * 0.02  # ~2% per ton-hr
            self.blowdown_flow = evap_rate * 0.5
            self.makeup_water_flow = evap_rate + self.blowdown_flow
        else:
            self.fan_speed = 0.0
            self.cw_flow_gpm = 0.0
            self.makeup_water_flow = 0.0
    
    def get_points(self) -> Dict[str, float]:
        return {
            'status': float(self.status),
            'fan_speed': self.fan_speed,
            'cw_supply_temp': self.cw_supply_temp,
            'cw_return_temp': self.cw_return_temp,
            'cw_flow_gpm': self.cw_flow_gpm,
            'wet_bulb_temp': self.wet_bulb_temp,
            'basin_temp': self.basin_temp,
            'makeup_water_gpm': self.makeup_water_flow,
            'fault': float(self.fault),
        }
    
    def get_points_with_override_status(self) -> Dict[str, Dict]:
        """Return all points with their override status."""
        result = {}
        for point_name, value in self.get_points().items():
            override_priority = self._get_override_status(point_name)
            result[point_name] = {
                'value': value,
                'overridden': override_priority is not None,
                'override_priority': override_priority,
                'writable': point_name in self.WRITABLE_POINTS
            }
        return result


@dataclass  
class Pump(Updatable, PointProvider):
    """
    Centrifugal pump for water circulation.
    """
    id: int
    name: str
    pump_type: str = "CHW"  # CHW, HW, CW (chilled, hot, condenser)
    capacity_gpm: float = 500.0
    status: bool = False
    speed: float = 0.0  # VFD speed percentage
    flow_gpm: float = 0.0
    discharge_pressure: float = 0.0  # PSI
    suction_pressure: float = 0.0
    differential_pressure: float = 0.0
    kw: float = 0.0
    fault: bool = False
    _point_path: str = ""  # Set by parent (e.g., "CentralPlant.Pump_CHW_1")
    
    # Writable points that can be overridden
    WRITABLE_POINTS = {'status', 'speed'}
    
    def _apply_override(self, point_name: str, default_value: float) -> float:
        """Apply override if one exists for this point."""
        if not self._point_path:
            return default_value
        full_path = f"{self._point_path}.{point_name}"
        override = get_override_manager().get_override(full_path)
        if override:
            return override[0]
        return default_value
    
    def _get_override_status(self, point_name: str) -> Optional[int]:
        """Get override priority if point is overridden, None otherwise."""
        if not self._point_path:
            return None
        full_path = f"{self._point_path}.{point_name}"
        override = get_override_manager().get_override(full_path)
        return override[1] if override else None
    
    def update(self, oat: float = 0.0, dt: float = 0.0, demand_gpm: float = 0.0) -> None:
        """Update pump state based on demand."""
        # Apply status override
        status_override = self._get_override_status('status')
        if status_override is not None:
            self.status = bool(self._apply_override('status', float(self.status)))
        
        if self.status and not self.fault:
            # Check for speed override
            speed_override = self._get_override_status('speed')
            if speed_override is not None:
                self.speed = self._apply_override('speed', self.speed)
            else:
                # Calculate speed based on flow demand
                self.speed = min(100.0, max(30.0, (demand_gpm / self.capacity_gpm) * 100))
            
            # Calculate actual flow
            self.flow_gpm = (self.speed / 100.0) * self.capacity_gpm
            
            # Pressure follows affinity laws (P ∝ speed²)
            speed_ratio = self.speed / 100.0
            self.differential_pressure = 45.0 * (speed_ratio ** 2)  # 45 PSI at full speed
            self.discharge_pressure = self.suction_pressure + self.differential_pressure
            
            # Power follows affinity laws (kW ∝ speed³)
            max_kw = 25.0  # Max power at full speed
            self.kw = max_kw * (speed_ratio ** 3)
        else:
            self.speed = 0.0
            self.flow_gpm = 0.0
            self.differential_pressure = 0.0
            self.kw = 0.0
    
    def get_points(self) -> Dict[str, float]:
        return {
            'status': float(self.status),
            'speed': self.speed,
            'flow_gpm': self.flow_gpm,
            'discharge_psi': self.discharge_pressure,
            'suction_psi': self.suction_pressure,
            'differential_psi': self.differential_pressure,
            'kw': self.kw,
            'fault': float(self.fault),
        }
    
    def get_points_with_override_status(self) -> Dict[str, Dict]:
        """Return all points with their override status."""
        result = {}
        for point_name, value in self.get_points().items():
            override_priority = self._get_override_status(point_name)
            result[point_name] = {
                'value': value,
                'overridden': override_priority is not None,
                'override_priority': override_priority,
                'writable': point_name in self.WRITABLE_POINTS
            }
        return result


@dataclass
class CentralPlant(Updatable, PointProvider):
    """
    Central plant containing chillers, boilers, cooling towers, and pumps.
    """
    id: int
    name: str
    chillers: List[Chiller] = field(default_factory=list)
    boilers: List[Boiler] = field(default_factory=list)
    cooling_towers: List[CoolingTower] = field(default_factory=list)
    chw_pumps: List[Pump] = field(default_factory=list)  # Chilled water pumps
    hw_pumps: List[Pump] = field(default_factory=list)   # Hot water pumps
    cw_pumps: List[Pump] = field(default_factory=list)   # Condenser water pumps
    
    # Plant-level readings
    chw_supply_temp: float = 44.0
    chw_return_temp: float = 54.0
    hw_supply_temp: float = 180.0
    hw_return_temp: float = 160.0
    total_cooling_load: float = 0.0  # Tons
    total_heating_load: float = 0.0  # MBH
    total_plant_kw: float = 0.0
    
    def update(self, oat: float = 0.0, dt: float = 0.0, 
               cooling_demand: float = 0.0, heating_demand: float = 0.0) -> None:
        """Update all plant equipment based on campus demand."""
        # Determine if heating or cooling mode based on OAT
        cooling_mode = oat > 55.0
        heating_mode = oat < 60.0
        
        self.total_cooling_load = cooling_demand
        self.total_heating_load = heating_demand
        self.total_plant_kw = 0.0
        
        # Update chillers
        if cooling_mode and cooling_demand > 0:
            # Stage chillers based on demand
            num_chillers_needed = max(1, int(cooling_demand / 400) + 1)
            demand_per_chiller = cooling_demand / min(num_chillers_needed, len(self.chillers))
            
            for i, chiller in enumerate(self.chillers):
                chiller.status = i < num_chillers_needed
                chiller.update(oat, dt, demand_per_chiller if chiller.status else 0)
                self.total_plant_kw += chiller.kw
            
            # Update chilled water pumps
            total_chw_flow = sum(c.chw_flow_gpm for c in self.chillers if c.status)
            for pump in self.chw_pumps:
                pump.status = any(c.status for c in self.chillers)
                pump.update(oat, dt, total_chw_flow / max(1, len(self.chw_pumps)))
                self.total_plant_kw += pump.kw
            
            # Update cooling towers and condenser water pumps
            heat_rejection = cooling_demand * 15000  # BTU/hr
            for ct in self.cooling_towers:
                ct.status = any(c.status for c in self.chillers)
                ct.update(oat, dt, heat_rejection=heat_rejection / max(1, len(self.cooling_towers)))
            
            for pump in self.cw_pumps:
                pump.status = any(c.status for c in self.chillers)
                total_cw_flow = sum(ct.cw_flow_gpm for ct in self.cooling_towers)
                pump.update(oat, dt, total_cw_flow / max(1, len(self.cw_pumps)))
                self.total_plant_kw += pump.kw
        else:
            # Cooling off
            for chiller in self.chillers:
                chiller.status = False
                chiller.update(oat, dt, 0)
            for ct in self.cooling_towers:
                ct.status = False
                ct.update(oat, dt)
            for pump in self.chw_pumps + self.cw_pumps:
                pump.status = False
                pump.update(oat, dt, 0)
        
        # Update boilers
        if heating_mode and heating_demand > 0:
            # Stage boilers based on demand
            num_boilers_needed = max(1, int(heating_demand / 1500) + 1)
            demand_per_boiler = heating_demand / min(num_boilers_needed, len(self.boilers))
            
            for i, boiler in enumerate(self.boilers):
                boiler.status = i < num_boilers_needed
                boiler.update(oat, dt, demand_per_boiler if boiler.status else 0)
            
            # Update hot water pumps
            total_hw_flow = sum(b.hw_flow_gpm for b in self.boilers if b.status)
            for pump in self.hw_pumps:
                pump.status = any(b.status for b in self.boilers)
                pump.update(oat, dt, total_hw_flow / max(1, len(self.hw_pumps)))
                self.total_plant_kw += pump.kw
        else:
            # Heating off
            for boiler in self.boilers:
                boiler.status = False
                boiler.update(oat, dt, 0)
            for pump in self.hw_pumps:
                pump.status = False
                pump.update(oat, dt, 0)
        
        # Calculate plant supply temps (weighted average from running equipment)
        running_chillers = [c for c in self.chillers if c.status]
        if running_chillers:
            self.chw_supply_temp = sum(c.chw_supply_temp for c in running_chillers) / len(running_chillers)
            self.chw_return_temp = sum(c.chw_return_temp for c in running_chillers) / len(running_chillers)
        
        running_boilers = [b for b in self.boilers if b.status]
        if running_boilers:
            self.hw_supply_temp = sum(b.hw_supply_temp for b in running_boilers) / len(running_boilers)
            self.hw_return_temp = sum(b.hw_return_temp for b in running_boilers) / len(running_boilers)
    
    def get_points(self) -> Dict[str, float]:
        """Return all plant points."""
        points = {
            'chw_supply_temp': self.chw_supply_temp,
            'chw_return_temp': self.chw_return_temp,
            'hw_supply_temp': self.hw_supply_temp,
            'hw_return_temp': self.hw_return_temp,
            'total_cooling_tons': self.total_cooling_load,
            'total_heating_mbh': self.total_heating_load,
            'total_plant_kw': self.total_plant_kw,
        }
        
        # Add individual equipment points
        for chiller in self.chillers:
            prefix = f"{chiller.name}"
            for key, value in chiller.get_points().items():
                points[f"{prefix}_{key}"] = value
        
        for boiler in self.boilers:
            prefix = f"{boiler.name}"
            for key, value in boiler.get_points().items():
                points[f"{prefix}_{key}"] = value
        
        for ct in self.cooling_towers:
            prefix = f"{ct.name}"
            for key, value in ct.get_points().items():
                points[f"{prefix}_{key}"] = value
        
        for pump in self.chw_pumps + self.hw_pumps + self.cw_pumps:
            prefix = f"{pump.name}"
            for key, value in pump.get_points().items():
                points[f"{prefix}_{key}"] = value
        
        return points
    
    @property
    def running_chillers(self) -> int:
        return sum(1 for c in self.chillers if c.status)
    
    @property
    def running_boilers(self) -> int:
        return sum(1 for b in self.boilers if b.status)
    
    @property
    def running_cooling_towers(self) -> int:
        return sum(1 for ct in self.cooling_towers if ct.status)


# =============================================================================
# Electrical Power Management System
# =============================================================================

@dataclass
class ElectricalMeter(Updatable, PointProvider):
    """
    Electrical meter for monitoring power consumption.
    Most points are read-only (measurement devices), but power_factor can be adjusted.
    """
    id: int
    name: str
    meter_type: str = "main"  # main, submeter, solar, generator
    kw: float = 0.0  # Real power (kW)
    kvar: float = 0.0  # Reactive power (kVAR)
    kva: float = 0.0  # Apparent power (kVA)
    power_factor: float = 0.95
    voltage_a: float = 277.0  # Phase A voltage
    voltage_b: float = 277.0
    voltage_c: float = 277.0
    current_a: float = 0.0  # Phase A current
    current_b: float = 0.0
    current_c: float = 0.0
    frequency: float = 60.0
    kwh_total: float = 0.0  # Accumulated energy
    demand_kw: float = 0.0  # 15-min demand
    peak_demand_kw: float = 0.0
    _point_path: str = ""
    
    # Meters are mostly read-only (measurements)
    WRITABLE_POINTS: set = field(default_factory=set)
    
    def _apply_override(self, point_name: str, default_value: float) -> float:
        if not self._point_path:
            return default_value
        full_path = f"{self._point_path}.{point_name}"
        override = get_override_manager().get_override(full_path)
        return override[0] if override else default_value
    
    def _get_override_status(self, point_name: str) -> Optional[int]:
        if not self._point_path:
            return None
        full_path = f"{self._point_path}.{point_name}"
        override = get_override_manager().get_override(full_path)
        return override[1] if override else None
    
    def update(self, oat: float = 0.0, dt: float = 0.0, load_kw: float = 0.0) -> None:
        """Update meter readings."""
        self.kw = load_kw
        self.kvar = load_kw * math.tan(math.acos(self.power_factor))
        self.kva = math.sqrt(self.kw**2 + self.kvar**2)
        
        # Calculate currents (3-phase balanced assumption)
        if self.kva > 0:
            total_current = (self.kva * 1000) / (math.sqrt(3) * 480)  # 480V 3-phase
            self.current_a = total_current + random.uniform(-2, 2)
            self.current_b = total_current + random.uniform(-2, 2)
            self.current_c = total_current + random.uniform(-2, 2)
        
        # Voltage fluctuation
        self.voltage_a = 277.0 + random.uniform(-3, 3)
        self.voltage_b = 277.0 + random.uniform(-3, 3)
        self.voltage_c = 277.0 + random.uniform(-3, 3)
        
        # Frequency (normally very stable)
        self.frequency = 60.0 + random.uniform(-0.02, 0.02)
        
        # Accumulate energy
        self.kwh_total += (self.kw * dt) / 3600
        
        # Update demand (simplified)
        self.demand_kw = self.kw * 0.9 + self.demand_kw * 0.1
        self.peak_demand_kw = max(self.peak_demand_kw, self.demand_kw)
    
    def get_points(self) -> Dict[str, float]:
        return {
            'kw': self.kw,
            'kvar': self.kvar,
            'kva': self.kva,
            'power_factor': self.power_factor,
            'voltage_a': self.voltage_a,
            'voltage_b': self.voltage_b,
            'voltage_c': self.voltage_c,
            'current_a': self.current_a,
            'current_b': self.current_b,
            'current_c': self.current_c,
            'frequency': self.frequency,
            'kwh_total': self.kwh_total,
            'demand_kw': self.demand_kw,
            'peak_demand_kw': self.peak_demand_kw,
        }
    
    def get_points_with_override_status(self) -> Dict[str, Dict]:
        result = {}
        for point_name, value in self.get_points().items():
            override_priority = self._get_override_status(point_name)
            result[point_name] = {
                'value': value,
                'overridden': override_priority is not None,
                'override_priority': override_priority,
                'writable': point_name in self.WRITABLE_POINTS
            }
        return result


@dataclass
class Generator(Updatable, PointProvider):
    """
    Diesel or natural gas backup generator.
    """
    id: int
    name: str
    capacity_kw: float = 500.0
    fuel_type: str = "diesel"  # diesel, natural_gas
    status: str = "standby"  # standby, running, cooldown, fault
    output_kw: float = 0.0
    output_kvar: float = 0.0
    voltage: float = 480.0
    frequency: float = 60.0
    fuel_level_pct: float = 100.0
    fuel_rate_gph: float = 0.0  # Gallons per hour
    runtime_hours: float = 0.0
    coolant_temp: float = 180.0
    oil_pressure_psi: float = 45.0
    battery_voltage: float = 24.0
    fault: bool = False
    _point_path: str = ""
    
    # Writable points (start/stop command, output target)
    WRITABLE_POINTS = {'status'}
    
    def _apply_override(self, point_name: str, default_value: float) -> float:
        if not self._point_path:
            return default_value
        full_path = f"{self._point_path}.{point_name}"
        override = get_override_manager().get_override(full_path)
        return override[0] if override else default_value
    
    def _get_override_status(self, point_name: str) -> Optional[int]:
        if not self._point_path:
            return None
        full_path = f"{self._point_path}.{point_name}"
        override = get_override_manager().get_override(full_path)
        return override[1] if override else None
    
    def update(self, oat: float = 0.0, dt: float = 0.0, 
               load_kw: float = 0.0, start_command: bool = False) -> None:
        """Update generator state."""
        # Check for status override (1=running, 0=standby)
        status_override = self._get_override_status('status')
        if status_override is not None:
            override_val = self._apply_override('status', 0)
            if override_val >= 1:
                self.status = "running"
            else:
                self.status = "standby"
        elif start_command and self.status == "standby" and not self.fault:
            self.status = "running"
        
        if self.status == "running" and not self.fault:
            # Calculate output based on load
            self.output_kw = min(load_kw, self.capacity_kw)
            load_pct = self.output_kw / self.capacity_kw if self.capacity_kw > 0 else 0
            
            # Fuel consumption (approx 7 gal/hr per 100kW for diesel)
            self.fuel_rate_gph = (self.output_kw / 100) * 7
            self.fuel_level_pct = max(0, self.fuel_level_pct - (self.fuel_rate_gph * dt / 3600) / 5)
            
            # Engine parameters
            self.coolant_temp = 180 + (load_pct * 30) + random.uniform(-5, 5)
            self.oil_pressure_psi = 45 + (load_pct * 10) + random.uniform(-2, 2)
            self.voltage = 480 + random.uniform(-5, 5)
            self.frequency = 60.0 + random.uniform(-0.1, 0.1)
            
            self.runtime_hours += dt / 3600
        else:
            self.output_kw = 0.0
            self.fuel_rate_gph = 0.0
            self.coolant_temp = oat + 10
    
    def get_points(self) -> Dict[str, float]:
        return {
            'status': {'standby': 0, 'running': 1, 'cooldown': 2, 'fault': 3}.get(self.status, 0),
            'output_kw': self.output_kw,
            'voltage': self.voltage,
            'frequency': self.frequency,
            'fuel_level_pct': self.fuel_level_pct,
            'fuel_rate_gph': self.fuel_rate_gph,
            'runtime_hours': self.runtime_hours,
            'coolant_temp': self.coolant_temp,
            'oil_pressure_psi': self.oil_pressure_psi,
            'battery_voltage': self.battery_voltage,
            'fault': float(self.fault),
        }
    
    def get_points_with_override_status(self) -> Dict[str, Dict]:
        result = {}
        for point_name, value in self.get_points().items():
            override_priority = self._get_override_status(point_name)
            result[point_name] = {
                'value': value,
                'overridden': override_priority is not None,
                'override_priority': override_priority,
                'writable': point_name in self.WRITABLE_POINTS
            }
        return result


@dataclass
class UPS(Updatable, PointProvider):
    """
    Uninterruptible Power Supply system.
    """
    id: int
    name: str
    capacity_kva: float = 100.0
    status: str = "online"  # online, battery, bypass, fault
    load_kw: float = 0.0
    load_pct: float = 0.0
    input_voltage: float = 480.0
    output_voltage: float = 480.0
    battery_voltage: float = 540.0  # DC bus voltage
    battery_pct: float = 100.0
    battery_runtime_min: float = 30.0
    battery_temp: float = 77.0
    efficiency: float = 0.94
    fault: bool = False
    _point_path: str = ""
    
    # UPS status can be overridden (force to bypass, etc.)
    WRITABLE_POINTS = {'status'}
    
    def _apply_override(self, point_name: str, default_value: float) -> float:
        if not self._point_path:
            return default_value
        full_path = f"{self._point_path}.{point_name}"
        override = get_override_manager().get_override(full_path)
        return override[0] if override else default_value
    
    def _get_override_status(self, point_name: str) -> Optional[int]:
        if not self._point_path:
            return None
        full_path = f"{self._point_path}.{point_name}"
        override = get_override_manager().get_override(full_path)
        return override[1] if override else None
    
    def update(self, oat: float = 0.0, dt: float = 0.0, 
               load_kw: float = 0.0, utility_available: bool = True) -> None:
        """Update UPS state."""
        self.load_kw = load_kw
        self.load_pct = (load_kw / (self.capacity_kva * 0.9)) * 100 if self.capacity_kva > 0 else 0
        
        if not utility_available and self.status == "online":
            self.status = "battery"
        elif utility_available and self.status == "battery":
            self.status = "online"
        
        if self.status == "battery":
            # Discharge battery
            discharge_rate = load_kw / 10  # Simplified
            self.battery_pct = max(0, self.battery_pct - (discharge_rate * dt / 3600))
            self.battery_voltage = 400 + (self.battery_pct * 1.4)
        else:
            # Charge battery
            if self.battery_pct < 100:
                self.battery_pct = min(100, self.battery_pct + (dt / 3600) * 5)
            self.battery_voltage = 540 + random.uniform(-5, 5)
        
        # Calculate runtime
        if load_kw > 0:
            self.battery_runtime_min = (self.battery_pct / 100) * 30 * (self.capacity_kva / max(1, load_kw))
        
        self.battery_temp = 77 + (self.load_pct * 0.1) + random.uniform(-2, 2)
        self.input_voltage = 480 + random.uniform(-5, 5)
        self.output_voltage = 480 + random.uniform(-2, 2)
    
    def get_points(self) -> Dict[str, float]:
        return {
            'status': {'online': 0, 'battery': 1, 'bypass': 2, 'fault': 3}.get(self.status, 0),
            'load_kw': self.load_kw,
            'load_pct': self.load_pct,
            'input_voltage': self.input_voltage,
            'output_voltage': self.output_voltage,
            'battery_voltage': self.battery_voltage,
            'battery_pct': self.battery_pct,
            'battery_runtime_min': self.battery_runtime_min,
            'battery_temp': self.battery_temp,
            'fault': float(self.fault),
        }
    
    def get_points_with_override_status(self) -> Dict[str, Dict]:
        result = {}
        for point_name, value in self.get_points().items():
            override_priority = self._get_override_status(point_name)
            result[point_name] = {
                'value': value,
                'overridden': override_priority is not None,
                'override_priority': override_priority,
                'writable': point_name in self.WRITABLE_POINTS
            }
        return result


@dataclass
class SolarArray(Updatable, PointProvider):
    """
    Photovoltaic solar array system.
    """
    id: int
    name: str
    capacity_kw: float = 100.0  # Peak DC capacity
    num_panels: int = 400
    output_kw: float = 0.0
    output_kwh_today: float = 0.0
    output_kwh_total: float = 0.0
    dc_voltage: float = 0.0
    dc_current: float = 0.0
    ac_voltage: float = 480.0
    inverter_efficiency: float = 0.96
    irradiance_w_m2: float = 0.0  # Solar irradiance
    panel_temp: float = 77.0
    status: str = "producing"  # producing, offline, fault
    fault: bool = False
    _point_path: str = ""
    
    # Solar mostly read-only but can be curtailed
    WRITABLE_POINTS = {'status'}
    
    def _apply_override(self, point_name: str, default_value: float) -> float:
        if not self._point_path:
            return default_value
        full_path = f"{self._point_path}.{point_name}"
        override = get_override_manager().get_override(full_path)
        return override[0] if override else default_value
    
    def _get_override_status(self, point_name: str) -> Optional[int]:
        if not self._point_path:
            return None
        full_path = f"{self._point_path}.{point_name}"
        override = get_override_manager().get_override(full_path)
        return override[1] if override else None
    
    def update(self, oat: float = 0.0, dt: float = 0.0, 
               time_of_day: float = 0.5, cloud_cover: float = 0.0) -> None:
        """Update solar array output based on conditions."""
        # Check for status override (0=offline to curtail)
        status_override = self._get_override_status('status')
        if status_override is not None:
            override_val = self._apply_override('status', 1)
            if override_val == 0:
                self.status = "offline"
                self.output_kw = 0.0
                return
        
        if self.fault:
            self.status = "fault"
            self.output_kw = 0.0
            return
        
        # Calculate irradiance based on time of day (simplified)
        # Peak at noon (0.5), zero at night
        if 0.25 < time_of_day < 0.75:  # Daylight hours
            sun_angle = math.sin((time_of_day - 0.25) * 2 * math.pi)
            base_irradiance = 1000 * max(0, sun_angle)  # Max 1000 W/m²
            self.irradiance_w_m2 = base_irradiance * (1 - cloud_cover * 0.8)
        else:
            self.irradiance_w_m2 = 0.0
        
        # Panel temperature affects efficiency
        self.panel_temp = oat + (self.irradiance_w_m2 / 50) + random.uniform(-3, 3)
        temp_coefficient = 1 - max(0, (self.panel_temp - 77) * 0.004)  # -0.4%/°C above 77°F
        
        # Calculate output
        efficiency = (self.irradiance_w_m2 / 1000) * temp_coefficient * self.inverter_efficiency
        self.output_kw = self.capacity_kw * efficiency
        
        # DC side
        if self.output_kw > 0:
            self.dc_voltage = 400 + (self.irradiance_w_m2 / 10)
            self.dc_current = (self.output_kw * 1000) / max(1, self.dc_voltage)
            self.status = "producing"
        else:
            self.dc_voltage = 0.0
            self.dc_current = 0.0
            self.status = "offline"
        
        # Accumulate energy
        self.output_kwh_today += (self.output_kw * dt) / 3600
        self.output_kwh_total += (self.output_kw * dt) / 3600
    
    def get_points(self) -> Dict[str, float]:
        return {
            'status': {'producing': 1, 'offline': 0, 'fault': 2}.get(self.status, 0),
            'output_kw': self.output_kw,
            'output_kwh_today': self.output_kwh_today,
            'output_kwh_total': self.output_kwh_total,
            'dc_voltage': self.dc_voltage,
            'dc_current': self.dc_current,
            'ac_voltage': self.ac_voltage,
            'irradiance_w_m2': self.irradiance_w_m2,
            'panel_temp': self.panel_temp,
            'fault': float(self.fault),
        }
    
    def get_points_with_override_status(self) -> Dict[str, Dict]:
        result = {}
        for point_name, value in self.get_points().items():
            override_priority = self._get_override_status(point_name)
            result[point_name] = {
                'value': value,
                'overridden': override_priority is not None,
                'override_priority': override_priority,
                'writable': point_name in self.WRITABLE_POINTS
            }
        return result


@dataclass
class Transformer(Updatable, PointProvider):
    """
    Electrical transformer.
    """
    id: int
    name: str
    capacity_kva: float = 1000.0
    primary_voltage: float = 13800.0  # 13.8kV typical utility
    secondary_voltage: float = 480.0
    load_kva: float = 0.0
    load_pct: float = 0.0
    winding_temp: float = 65.0
    oil_temp: float = 55.0
    tap_position: int = 0  # -5 to +5 typically
    status: str = "energized"
    fault: bool = False
    _point_path: str = ""
    
    # Tap position is adjustable
    WRITABLE_POINTS = {'tap_position'}
    
    def _apply_override(self, point_name: str, default_value: float) -> float:
        if not self._point_path:
            return default_value
        full_path = f"{self._point_path}.{point_name}"
        override = get_override_manager().get_override(full_path)
        return override[0] if override else default_value
    
    def _get_override_status(self, point_name: str) -> Optional[int]:
        if not self._point_path:
            return None
        full_path = f"{self._point_path}.{point_name}"
        override = get_override_manager().get_override(full_path)
        return override[1] if override else None
    
    def update(self, oat: float = 0.0, dt: float = 0.0, load_kva: float = 0.0) -> None:
        """Update transformer state."""
        # Check for tap position override
        tap_override = self._get_override_status('tap_position')
        if tap_override is not None:
            self.tap_position = int(self._apply_override('tap_position', self.tap_position))
        
        self.load_kva = load_kva
        self.load_pct = (load_kva / self.capacity_kva) * 100 if self.capacity_kva > 0 else 0
        
        # Temperature rise based on load (simplified)
        temp_rise = (self.load_pct / 100) ** 2 * 50  # Max 50°C rise at full load
        self.winding_temp = oat + temp_rise + 20 + random.uniform(-2, 2)
        self.oil_temp = oat + (temp_rise * 0.7) + 10 + random.uniform(-2, 2)
        
        # Secondary voltage varies with tap and load
        tap_adjustment = self.tap_position * 0.025  # 2.5% per tap
        load_drop = (self.load_pct / 100) * 0.02  # 2% drop at full load
        self.secondary_voltage = 480 * (1 + tap_adjustment - load_drop)
    
    def get_points(self) -> Dict[str, float]:
        return {
            'load_kva': self.load_kva,
            'load_pct': self.load_pct,
            'primary_voltage': self.primary_voltage,
            'secondary_voltage': self.secondary_voltage,
            'winding_temp': self.winding_temp,
            'oil_temp': self.oil_temp,
            'tap_position': self.tap_position,
            'fault': float(self.fault),
        }
    
    def get_points_with_override_status(self) -> Dict[str, Dict]:
        result = {}
        for point_name, value in self.get_points().items():
            override_priority = self._get_override_status(point_name)
            result[point_name] = {
                'value': value,
                'overridden': override_priority is not None,
                'override_priority': override_priority,
                'writable': point_name in self.WRITABLE_POINTS
            }
        return result


@dataclass
class ElectricalSystem(Updatable, PointProvider):
    """
    Complete electrical power management system.
    """
    id: int
    name: str
    main_meter: ElectricalMeter = None
    submeters: List[ElectricalMeter] = field(default_factory=list)
    generators: List[Generator] = field(default_factory=list)
    ups_systems: List[UPS] = field(default_factory=list)
    solar_arrays: List[SolarArray] = field(default_factory=list)
    transformers: List[Transformer] = field(default_factory=list)
    
    # System totals
    total_demand_kw: float = 0.0
    total_generation_kw: float = 0.0
    solar_production_kw: float = 0.0
    grid_import_kw: float = 0.0
    utility_available: bool = True
    
    def __post_init__(self):
        if self.main_meter is None:
            self.main_meter = ElectricalMeter(id=0, name="Main_Meter", meter_type="main")
    
    def update(self, oat: float = 0.0, dt: float = 0.0, 
               campus_load_kw: float = 0.0, time_of_day: float = 0.5) -> None:
        """Update all electrical equipment."""
        self.total_demand_kw = campus_load_kw
        
        # Update solar arrays
        self.solar_production_kw = 0.0
        cloud_cover = random.uniform(0, 0.4)  # Variable cloud cover
        for solar in self.solar_arrays:
            solar.update(oat, dt, time_of_day, cloud_cover)
            self.solar_production_kw += solar.output_kw
        
        # Grid import = demand - solar
        self.grid_import_kw = max(0, campus_load_kw - self.solar_production_kw)
        
        # Update main meter
        self.main_meter.update(oat, dt, self.grid_import_kw)
        
        # Update submeters (distribute load)
        if self.submeters:
            load_per_meter = campus_load_kw / len(self.submeters)
            for meter in self.submeters:
                meter.update(oat, dt, load_per_meter + random.uniform(-10, 10))
        
        # Update transformers
        for xfmr in self.transformers:
            xfmr.update(oat, dt, self.grid_import_kw * 1.05)  # kVA > kW
        
        # Update UPS systems
        for ups in self.ups_systems:
            ups_load = campus_load_kw / max(1, len(self.ups_systems)) * 0.3  # 30% critical load
            ups.update(oat, dt, ups_load, self.utility_available)
        
        # Update generators (standby unless utility fails)
        self.total_generation_kw = 0.0
        for gen in self.generators:
            gen.update(oat, dt, start_command=not self.utility_available)
            self.total_generation_kw += gen.output_kw
    
    def get_points(self) -> Dict[str, float]:
        points = {
            'total_demand_kw': self.total_demand_kw,
            'total_generation_kw': self.total_generation_kw,
            'solar_production_kw': self.solar_production_kw,
            'grid_import_kw': self.grid_import_kw,
            'utility_available': float(self.utility_available),
        }
        
        # Add main meter points
        for key, value in self.main_meter.get_points().items():
            points[f"Main_{key}"] = value
        
        # Add equipment points
        for meter in self.submeters:
            for key, value in meter.get_points().items():
                points[f"{meter.name}_{key}"] = value
        
        for gen in self.generators:
            for key, value in gen.get_points().items():
                points[f"{gen.name}_{key}"] = value
        
        for ups in self.ups_systems:
            for key, value in ups.get_points().items():
                points[f"{ups.name}_{key}"] = value
        
        for solar in self.solar_arrays:
            for key, value in solar.get_points().items():
                points[f"{solar.name}_{key}"] = value
        
        for xfmr in self.transformers:
            for key, value in xfmr.get_points().items():
                points[f"{xfmr.name}_{key}"] = value
        
        return points


# =============================================================================
# Wastewater Treatment Facility
# =============================================================================

@dataclass
class LiftStation(Updatable, PointProvider):
    """
    Wastewater lift station with pumps.
    """
    id: int
    name: str
    num_pumps: int = 2
    wet_well_level_ft: float = 5.0
    wet_well_capacity_gal: float = 5000.0
    pump_status: List[bool] = field(default_factory=list)
    pump_runtime_hrs: List[float] = field(default_factory=list)
    flow_gpm: float = 0.0
    discharge_pressure_psi: float = 0.0
    kw: float = 0.0
    fault: bool = False
    _point_path: str = ""
    
    # Pumps can be manually controlled
    WRITABLE_POINTS = {'pump_1_status', 'pump_2_status', 'pump_3_status'}
    
    def _apply_override(self, point_name: str, default_value: float) -> float:
        if not self._point_path:
            return default_value
        full_path = f"{self._point_path}.{point_name}"
        override = get_override_manager().get_override(full_path)
        return override[0] if override else default_value
    
    def _get_override_status(self, point_name: str) -> Optional[int]:
        if not self._point_path:
            return None
        full_path = f"{self._point_path}.{point_name}"
        override = get_override_manager().get_override(full_path)
        return override[1] if override else None
    
    def __post_init__(self):
        if not self.pump_status:
            self.pump_status = [False] * self.num_pumps
        if not self.pump_runtime_hrs:
            self.pump_runtime_hrs = [0.0] * self.num_pumps
    
    def update(self, oat: float = 0.0, dt: float = 0.0, inflow_gpm: float = 100.0) -> None:
        """Update lift station based on inflow."""
        # Wet well level changes with inflow/outflow
        inflow_ft3 = (inflow_gpm * dt / 60) / 7.48  # Convert to cubic feet
        self.wet_well_level_ft += inflow_ft3 / 100  # Simplified geometry
        
        # Start/stop pumps based on level (or override)
        running_pumps = 0
        for i in range(self.num_pumps):
            pump_override = self._get_override_status(f'pump_{i+1}_status')
            if pump_override is not None:
                self.pump_status[i] = bool(self._apply_override(f'pump_{i+1}_status', float(self.pump_status[i])))
            else:
                if self.wet_well_level_ft > 7.0 and not self.pump_status[i]:
                    self.pump_status[i] = True
                elif self.wet_well_level_ft < 3.0 and self.pump_status[i]:
                    self.pump_status[i] = False
            
            if self.pump_status[i]:
                running_pumps += 1
                self.pump_runtime_hrs[i] += dt / 3600
        
        # Calculate outflow and power
        self.flow_gpm = running_pumps * 150  # 150 GPM per pump
        outflow_ft3 = (self.flow_gpm * dt / 60) / 7.48
        self.wet_well_level_ft = max(1.0, self.wet_well_level_ft - outflow_ft3 / 100)
        
        self.discharge_pressure_psi = 25 + (running_pumps * 5)
        self.kw = running_pumps * 7.5  # 7.5 kW per pump
    
    def get_points(self) -> Dict[str, float]:
        points = {
            'wet_well_level_ft': self.wet_well_level_ft,
            'flow_gpm': self.flow_gpm,
            'discharge_pressure_psi': self.discharge_pressure_psi,
            'kw': self.kw,
            'pumps_running': sum(self.pump_status),
            'fault': float(self.fault),
        }
        for i, running in enumerate(self.pump_status):
            points[f'pump_{i+1}_status'] = float(running)
            points[f'pump_{i+1}_runtime_hrs'] = self.pump_runtime_hrs[i]
        return points
    
    def get_points_with_override_status(self) -> Dict[str, Dict]:
        result = {}
        for point_name, value in self.get_points().items():
            override_priority = self._get_override_status(point_name)
            result[point_name] = {
                'value': value,
                'overridden': override_priority is not None,
                'override_priority': override_priority,
                'writable': point_name in self.WRITABLE_POINTS
            }
        return result


@dataclass
class AerationBlower(Updatable, PointProvider):
    """
    Blower for wastewater aeration basins.
    """
    id: int
    name: str
    capacity_scfm: float = 2000.0  # Standard cubic feet per minute
    status: bool = False
    speed_pct: float = 0.0
    output_scfm: float = 0.0
    discharge_pressure_psi: float = 0.0
    inlet_temp: float = 70.0
    discharge_temp: float = 200.0
    motor_amps: float = 0.0
    kw: float = 0.0
    vibration_ips: float = 0.0  # inches per second
    fault: bool = False
    _point_path: str = ""
    
    # Blower status and speed can be controlled
    WRITABLE_POINTS = {'status', 'speed_pct'}
    
    def _apply_override(self, point_name: str, default_value: float) -> float:
        if not self._point_path:
            return default_value
        full_path = f"{self._point_path}.{point_name}"
        override = get_override_manager().get_override(full_path)
        return override[0] if override else default_value
    
    def _get_override_status(self, point_name: str) -> Optional[int]:
        if not self._point_path:
            return None
        full_path = f"{self._point_path}.{point_name}"
        override = get_override_manager().get_override(full_path)
        return override[1] if override else None
    
    def update(self, oat: float = 0.0, dt: float = 0.0, do_demand: float = 0.5) -> None:
        """Update blower based on dissolved oxygen demand."""
        # Check for status override
        status_override = self._get_override_status('status')
        if status_override is not None:
            self.status = bool(self._apply_override('status', float(self.status)))
        
        if self.status and not self.fault:
            # Check for speed override
            speed_override = self._get_override_status('speed_pct')
            if speed_override is not None:
                self.speed_pct = self._apply_override('speed_pct', self.speed_pct)
            else:
                # VFD speed based on DO demand (0-1)
                self.speed_pct = 40 + (do_demand * 60)  # 40-100% speed
            
            self.output_scfm = self.capacity_scfm * (self.speed_pct / 100)
            
            # Discharge pressure
            self.discharge_pressure_psi = 7 + (self.speed_pct / 100) * 3
            
            # Temperature rise
            self.inlet_temp = oat
            self.discharge_temp = oat + 100 + (self.speed_pct / 100) * 50
            
            # Power (follows affinity laws)
            max_kw = 150
            self.kw = max_kw * (self.speed_pct / 100) ** 3
            self.motor_amps = (self.kw * 1000) / (480 * math.sqrt(3) * 0.9)
            
            # Vibration
            self.vibration_ips = 0.05 + random.uniform(0, 0.03)
        else:
            self.speed_pct = 0.0
            self.output_scfm = 0.0
            self.kw = 0.0
    
    def get_points(self) -> Dict[str, float]:
        return {
            'status': float(self.status),
            'speed_pct': self.speed_pct,
            'output_scfm': self.output_scfm,
            'discharge_pressure_psi': self.discharge_pressure_psi,
            'inlet_temp': self.inlet_temp,
            'discharge_temp': self.discharge_temp,
            'motor_amps': self.motor_amps,
            'kw': self.kw,
            'vibration_ips': self.vibration_ips,
            'fault': float(self.fault),
        }
    
    def get_points_with_override_status(self) -> Dict[str, Dict]:
        result = {}
        for point_name, value in self.get_points().items():
            override_priority = self._get_override_status(point_name)
            result[point_name] = {
                'value': value,
                'overridden': override_priority is not None,
                'override_priority': override_priority,
                'writable': point_name in self.WRITABLE_POINTS
            }
        return result


@dataclass
class Clarifier(Updatable, PointProvider):
    """
    Wastewater clarifier/settler.
    """
    id: int
    name: str
    diameter_ft: float = 60.0
    clarifier_type: str = "primary"  # primary, secondary
    flow_mgd: float = 0.0  # Million gallons per day
    sludge_blanket_ft: float = 2.0
    drive_motor_amps: float = 5.0
    torque_pct: float = 20.0
    skimmer_status: bool = True
    effluent_tss_mg_l: float = 15.0  # Total suspended solids
    sras_flow_gpm: float = 0.0  # Sludge flow
    fault: bool = False
    _point_path: str = ""
    
    # Skimmer can be controlled
    WRITABLE_POINTS = {'skimmer_status', 'sras_flow_gpm'}
    
    def _apply_override(self, point_name: str, default_value: float) -> float:
        if not self._point_path:
            return default_value
        full_path = f"{self._point_path}.{point_name}"
        override = get_override_manager().get_override(full_path)
        return override[0] if override else default_value
    
    def _get_override_status(self, point_name: str) -> Optional[int]:
        if not self._point_path:
            return None
        full_path = f"{self._point_path}.{point_name}"
        override = get_override_manager().get_override(full_path)
        return override[1] if override else None
    
    def update(self, oat: float = 0.0, dt: float = 0.0, influent_flow_mgd: float = 1.0) -> None:
        """Update clarifier state."""
        self.flow_mgd = influent_flow_mgd
        
        # Sludge blanket rises with flow
        self.sludge_blanket_ft = 1.5 + (influent_flow_mgd * 0.8) + random.uniform(-0.2, 0.2)
        
        # Drive torque varies with sludge
        self.torque_pct = 15 + (self.sludge_blanket_ft * 5) + random.uniform(-3, 3)
        self.drive_motor_amps = 4 + (self.torque_pct / 100) * 6
        
        # Effluent quality
        self.effluent_tss_mg_l = 10 + (influent_flow_mgd * 5) + random.uniform(-3, 3)
        
        # Sludge removal (check for override)
        sras_override = self._get_override_status('sras_flow_gpm')
        if sras_override is not None:
            self.sras_flow_gpm = self._apply_override('sras_flow_gpm', self.sras_flow_gpm)
        else:
            self.sras_flow_gpm = 50 + (self.sludge_blanket_ft * 20)
    
    def get_points(self) -> Dict[str, float]:
        return {
            'flow_mgd': self.flow_mgd,
            'sludge_blanket_ft': self.sludge_blanket_ft,
            'drive_motor_amps': self.drive_motor_amps,
            'torque_pct': self.torque_pct,
            'skimmer_status': float(self.skimmer_status),
            'effluent_tss_mg_l': self.effluent_tss_mg_l,
            'sras_flow_gpm': self.sras_flow_gpm,
            'fault': float(self.fault),
        }
    
    def get_points_with_override_status(self) -> Dict[str, Dict]:
        result = {}
        for point_name, value in self.get_points().items():
            override_priority = self._get_override_status(point_name)
            result[point_name] = {
                'value': value,
                'overridden': override_priority is not None,
                'override_priority': override_priority,
                'writable': point_name in self.WRITABLE_POINTS
            }
        return result


@dataclass
class UVDisinfection(Updatable, PointProvider):
    """
    UV disinfection system for effluent.
    """
    id: int
    name: str
    num_banks: int = 4
    lamps_per_bank: int = 16
    status: bool = True
    flow_mgd: float = 0.0
    uv_intensity_pct: float = 100.0
    uv_transmittance_pct: float = 65.0
    lamp_hours: float = 0.0
    lamp_life_remaining_pct: float = 100.0
    kw: float = 0.0
    effluent_ecoli_mpn: float = 10.0  # MPN/100mL
    fault: bool = False
    _point_path: str = ""
    
    # UV system status and intensity controllable
    WRITABLE_POINTS = {'status', 'uv_intensity_pct'}
    
    def _apply_override(self, point_name: str, default_value: float) -> float:
        if not self._point_path:
            return default_value
        full_path = f"{self._point_path}.{point_name}"
        override = get_override_manager().get_override(full_path)
        return override[0] if override else default_value
    
    def _get_override_status(self, point_name: str) -> Optional[int]:
        if not self._point_path:
            return None
        full_path = f"{self._point_path}.{point_name}"
        override = get_override_manager().get_override(full_path)
        return override[1] if override else None
    
    def update(self, oat: float = 0.0, dt: float = 0.0, flow_mgd: float = 1.0) -> None:
        """Update UV system."""
        self.flow_mgd = flow_mgd
        
        # Check for status override
        status_override = self._get_override_status('status')
        if status_override is not None:
            self.status = bool(self._apply_override('status', float(self.status)))
        
        if self.status and not self.fault:
            # Lamp aging
            self.lamp_hours += dt / 3600
            self.lamp_life_remaining_pct = max(0, 100 - (self.lamp_hours / 80))  # 8000 hr life
            
            # Check for intensity override
            intensity_override = self._get_override_status('uv_intensity_pct')
            if intensity_override is not None:
                self.uv_intensity_pct = self._apply_override('uv_intensity_pct', self.uv_intensity_pct)
            else:
                # Intensity degrades with age
                self.uv_intensity_pct = 100 * (self.lamp_life_remaining_pct / 100) ** 0.5
            
            # Power consumption
            self.kw = self.num_banks * self.lamps_per_bank * 0.4  # 400W per lamp
            
            # Disinfection effectiveness
            dose_factor = self.uv_intensity_pct / 100
            self.effluent_ecoli_mpn = 200 * (1 - dose_factor * 0.95) + random.uniform(0, 10)
        else:
            self.kw = 0.0
            self.effluent_ecoli_mpn = 2000  # High if not disinfecting
    
    def get_points(self) -> Dict[str, float]:
        return {
            'status': float(self.status),
            'flow_mgd': self.flow_mgd,
            'uv_intensity_pct': self.uv_intensity_pct,
            'uv_transmittance_pct': self.uv_transmittance_pct,
            'lamp_hours': self.lamp_hours,
            'lamp_life_remaining_pct': self.lamp_life_remaining_pct,
            'kw': self.kw,
            'effluent_ecoli_mpn': self.effluent_ecoli_mpn,
            'fault': float(self.fault),
        }
    
    def get_points_with_override_status(self) -> Dict[str, Dict]:
        result = {}
        for point_name, value in self.get_points().items():
            override_priority = self._get_override_status(point_name)
            result[point_name] = {
                'value': value,
                'overridden': override_priority is not None,
                'override_priority': override_priority,
                'writable': point_name in self.WRITABLE_POINTS
            }
        return result


@dataclass
class WastewaterFacility(Updatable, PointProvider):
    """
    Complete wastewater treatment facility.
    """
    id: int
    name: str
    display_name: str = ""
    lift_stations: List[LiftStation] = field(default_factory=list)
    blowers: List[AerationBlower] = field(default_factory=list)
    clarifiers: List[Clarifier] = field(default_factory=list)
    uv_systems: List[UVDisinfection] = field(default_factory=list)
    
    # Process parameters
    influent_flow_mgd: float = 1.0
    effluent_flow_mgd: float = 0.95
    influent_bod_mg_l: float = 200.0  # Biochemical oxygen demand
    effluent_bod_mg_l: float = 10.0
    dissolved_oxygen_mg_l: float = 2.0
    ph: float = 7.2
    total_kw: float = 0.0
    
    def __post_init__(self):
        if not self.display_name:
            self.display_name = self.name
    
    def update(self, oat: float = 0.0, dt: float = 0.0) -> None:
        """Update entire facility."""
        self.total_kw = 0.0
        
        # Influent varies with time
        base_flow = 1.0 + random.uniform(-0.2, 0.2)
        self.influent_flow_mgd = base_flow
        
        # Update lift stations
        for ls in self.lift_stations:
            ls.update(oat, dt, self.influent_flow_mgd * 694)  # MGD to GPM
            self.total_kw += ls.kw
        
        # Update blowers based on DO
        do_demand = 0.5 + random.uniform(-0.1, 0.1)
        for blower in self.blowers:
            blower.update(oat, dt, do_demand)
            self.total_kw += blower.kw
        
        # Update clarifiers
        for clarifier in self.clarifiers:
            clarifier.update(oat, dt, self.influent_flow_mgd / max(1, len(self.clarifiers)))
        
        # Update UV
        for uv in self.uv_systems:
            uv.update(oat, dt, self.influent_flow_mgd)
            self.total_kw += uv.kw
        
        # Process results
        self.effluent_flow_mgd = self.influent_flow_mgd * 0.95
        self.dissolved_oxygen_mg_l = 2.0 + sum(b.output_scfm for b in self.blowers) / 5000
        self.effluent_bod_mg_l = max(5, 200 - self.dissolved_oxygen_mg_l * 50)
        self.ph = 7.0 + random.uniform(-0.3, 0.3)
    
    def get_points(self) -> Dict[str, float]:
        points = {
            'influent_flow_mgd': self.influent_flow_mgd,
            'effluent_flow_mgd': self.effluent_flow_mgd,
            'influent_bod_mg_l': self.influent_bod_mg_l,
            'effluent_bod_mg_l': self.effluent_bod_mg_l,
            'dissolved_oxygen_mg_l': self.dissolved_oxygen_mg_l,
            'ph': self.ph,
            'total_kw': self.total_kw,
        }
        
        for ls in self.lift_stations:
            for key, value in ls.get_points().items():
                points[f"{ls.name}_{key}"] = value
        
        for blower in self.blowers:
            for key, value in blower.get_points().items():
                points[f"{blower.name}_{key}"] = value
        
        for clarifier in self.clarifiers:
            for key, value in clarifier.get_points().items():
                points[f"{clarifier.name}_{key}"] = value
        
        for uv in self.uv_systems:
            for key, value in uv.get_points().items():
                points[f"{uv.name}_{key}"] = value
        
        return points


# =============================================================================
# Data Center
# =============================================================================

@dataclass
class ServerRack(Updatable, PointProvider):
    """
    Data center server rack.
    """
    id: int
    name: str
    num_servers: int = 42  # U capacity
    it_load_kw: float = 10.0
    inlet_temp: float = 68.0
    outlet_temp: float = 95.0
    pdu_a_kw: float = 5.0
    pdu_b_kw: float = 5.0
    pdu_a_amps: float = 0.0
    pdu_b_amps: float = 0.0
    utilization_pct: float = 60.0
    fault: bool = False
    _point_path: str = ""
    
    # Server load is mostly read-only (can't control servers via BMS)
    WRITABLE_POINTS: set = field(default_factory=set)
    
    def _apply_override(self, point_name: str, default_value: float) -> float:
        if not self._point_path:
            return default_value
        full_path = f"{self._point_path}.{point_name}"
        override = get_override_manager().get_override(full_path)
        return override[0] if override else default_value
    
    def _get_override_status(self, point_name: str) -> Optional[int]:
        if not self._point_path:
            return None
        full_path = f"{self._point_path}.{point_name}"
        override = get_override_manager().get_override(full_path)
        return override[1] if override else None
    
    def update(self, oat: float = 0.0, dt: float = 0.0, 
               supply_air_temp: float = 65.0, load_factor: float = 1.0) -> None:
        """Update rack based on conditions."""
        # IT load varies slightly
        self.it_load_kw = 10 * load_factor * (0.9 + random.uniform(0, 0.2))
        
        # Split across PDUs
        self.pdu_a_kw = self.it_load_kw * 0.5 + random.uniform(-0.5, 0.5)
        self.pdu_b_kw = self.it_load_kw - self.pdu_a_kw
        
        # Calculate amps (208V single phase typical)
        self.pdu_a_amps = (self.pdu_a_kw * 1000) / 208
        self.pdu_b_amps = (self.pdu_b_kw * 1000) / 208
        
        # Temperature rise
        self.inlet_temp = supply_air_temp + random.uniform(-2, 2)
        delta_t = self.it_load_kw * 2  # Roughly 2°F per kW
        self.outlet_temp = self.inlet_temp + delta_t
        
        # Server utilization
        self.utilization_pct = 50 + random.uniform(0, 40)
    
    def get_points(self) -> Dict[str, float]:
        return {
            'it_load_kw': self.it_load_kw,
            'inlet_temp': self.inlet_temp,
            'outlet_temp': self.outlet_temp,
            'pdu_a_kw': self.pdu_a_kw,
            'pdu_b_kw': self.pdu_b_kw,
            'pdu_a_amps': self.pdu_a_amps,
            'pdu_b_amps': self.pdu_b_amps,
            'utilization_pct': self.utilization_pct,
            'fault': float(self.fault),
        }
    
    def get_points_with_override_status(self) -> Dict[str, Dict]:
        result = {}
        for point_name, value in self.get_points().items():
            override_priority = self._get_override_status(point_name)
            result[point_name] = {
                'value': value,
                'overridden': override_priority is not None,
                'override_priority': override_priority,
                'writable': point_name in self.WRITABLE_POINTS
            }
        return result


@dataclass
class CRAC(Updatable, PointProvider):
    """
    Computer Room Air Conditioner.
    """
    id: int
    name: str
    capacity_tons: float = 20.0
    status: bool = True
    supply_air_temp: float = 55.0
    return_air_temp: float = 75.0
    supply_air_humidity_pct: float = 50.0
    return_air_humidity_pct: float = 45.0
    fan_speed_pct: float = 75.0
    cooling_output_pct: float = 50.0
    compressor_status: bool = True
    kw: float = 0.0
    discharge_pressure_psi: float = 250.0
    suction_pressure_psi: float = 70.0
    fault: bool = False
    _point_path: str = ""
    
    # CRAC units have controllable points
    WRITABLE_POINTS = {'status', 'supply_air_temp', 'fan_speed_pct'}
    
    def _apply_override(self, point_name: str, default_value: float) -> float:
        if not self._point_path:
            return default_value
        full_path = f"{self._point_path}.{point_name}"
        override = get_override_manager().get_override(full_path)
        return override[0] if override else default_value
    
    def _get_override_status(self, point_name: str) -> Optional[int]:
        if not self._point_path:
            return None
        full_path = f"{self._point_path}.{point_name}"
        override = get_override_manager().get_override(full_path)
        return override[1] if override else None
    
    def update(self, oat: float = 0.0, dt: float = 0.0, 
               heat_load_kw: float = 50.0, setpoint: float = 68.0) -> None:
        """Update CRAC based on heat load."""
        # Check for status override
        status_override = self._get_override_status('status')
        if status_override is not None:
            self.status = bool(self._apply_override('status', float(self.status)))
        
        if self.status and not self.fault:
            # Cooling required
            required_tons = heat_load_kw / 3.517  # kW to tons
            self.cooling_output_pct = min(100, (required_tons / self.capacity_tons) * 100)
            
            # Check for fan speed override
            fan_override = self._get_override_status('fan_speed_pct')
            if fan_override is not None:
                self.fan_speed_pct = self._apply_override('fan_speed_pct', self.fan_speed_pct)
            else:
                # Fan speed follows load
                self.fan_speed_pct = 50 + (self.cooling_output_pct / 2)
            
            # Check for supply temp override
            temp_override = self._get_override_status('supply_air_temp')
            if temp_override is not None:
                self.supply_air_temp = self._apply_override('supply_air_temp', self.supply_air_temp)
            else:
                # Supply temp tracks setpoint
                self.supply_air_temp = setpoint - 10 + (self.cooling_output_pct / 100) * 5
            
            # Return temp based on delta T
            self.return_air_temp = self.supply_air_temp + (heat_load_kw / 2)
            
            # Power consumption
            self.kw = (self.cooling_output_pct / 100) * self.capacity_tons * 1.2
            
            # Refrigerant pressures
            self.discharge_pressure_psi = 220 + (self.cooling_output_pct / 100) * 80
            self.suction_pressure_psi = 65 + (oat - 70) * 0.5
            
            # Humidity control
            self.supply_air_humidity_pct = 45 + random.uniform(-5, 5)
            self.return_air_humidity_pct = self.supply_air_humidity_pct + random.uniform(0, 10)
        else:
            self.cooling_output_pct = 0
            self.fan_speed_pct = 0
            self.kw = 0
    
    def get_points(self) -> Dict[str, float]:
        return {
            'status': float(self.status),
            'supply_air_temp': self.supply_air_temp,
            'return_air_temp': self.return_air_temp,
            'supply_air_humidity_pct': self.supply_air_humidity_pct,
            'return_air_humidity_pct': self.return_air_humidity_pct,
            'fan_speed_pct': self.fan_speed_pct,
            'cooling_output_pct': self.cooling_output_pct,
            'compressor_status': float(self.compressor_status),
            'kw': self.kw,
            'discharge_pressure_psi': self.discharge_pressure_psi,
            'suction_pressure_psi': self.suction_pressure_psi,
            'fault': float(self.fault),
        }
    
    def get_points_with_override_status(self) -> Dict[str, Dict]:
        result = {}
        for point_name, value in self.get_points().items():
            override_priority = self._get_override_status(point_name)
            result[point_name] = {
                'value': value,
                'overridden': override_priority is not None,
                'override_priority': override_priority,
                'writable': point_name in self.WRITABLE_POINTS
            }
        return result


@dataclass
class DataCenter(Updatable, PointProvider):
    """
    Complete data center facility.
    """
    id: int
    name: str
    display_name: str = ""
    server_racks: List[ServerRack] = field(default_factory=list)
    crac_units: List[CRAC] = field(default_factory=list)
    ups_systems: List[UPS] = field(default_factory=list)
    pdu_total_kw: float = 0.0
    
    # Data center metrics
    total_it_load_kw: float = 0.0
    total_cooling_kw: float = 0.0
    pue: float = 1.5  # Power Usage Effectiveness
    average_inlet_temp: float = 68.0
    average_outlet_temp: float = 85.0
    total_kw: float = 0.0
    tier_level: int = 3  # Tier 1-4
    
    def __post_init__(self):
        if not self.display_name:
            self.display_name = self.name
    
    def update(self, oat: float = 0.0, dt: float = 0.0) -> None:
        """Update entire data center."""
        # Calculate supply air temp from CRACs
        supply_temps = [c.supply_air_temp for c in self.crac_units if c.status]
        avg_supply = sum(supply_temps) / len(supply_temps) if supply_temps else 65.0
        
        # Update server racks
        self.total_it_load_kw = 0.0
        inlet_temps = []
        outlet_temps = []
        
        for rack in self.server_racks:
            rack.update(oat, dt, avg_supply)
            self.total_it_load_kw += rack.it_load_kw
            inlet_temps.append(rack.inlet_temp)
            outlet_temps.append(rack.outlet_temp)
        
        if inlet_temps:
            self.average_inlet_temp = sum(inlet_temps) / len(inlet_temps)
            self.average_outlet_temp = sum(outlet_temps) / len(outlet_temps)
        
        # Update CRAC units
        self.total_cooling_kw = 0.0
        heat_per_crac = self.total_it_load_kw / max(1, len(self.crac_units))
        
        for crac in self.crac_units:
            crac.update(oat, dt, heat_per_crac)
            self.total_cooling_kw += crac.kw
        
        # Update UPS
        for ups in self.ups_systems:
            ups_load = self.total_it_load_kw / max(1, len(self.ups_systems))
            ups.update(oat, dt, ups_load)
        
        # Calculate PUE
        self.total_kw = self.total_it_load_kw + self.total_cooling_kw
        self.pue = self.total_kw / max(1, self.total_it_load_kw)
    
    def get_points(self) -> Dict[str, float]:
        points = {
            'total_it_load_kw': self.total_it_load_kw,
            'total_cooling_kw': self.total_cooling_kw,
            'total_kw': self.total_kw,
            'pue': self.pue,
            'average_inlet_temp': self.average_inlet_temp,
            'average_outlet_temp': self.average_outlet_temp,
        }
        
        for rack in self.server_racks:
            for key, value in rack.get_points().items():
                points[f"{rack.name}_{key}"] = value
        
        for crac in self.crac_units:
            for key, value in crac.get_points().items():
                points[f"{crac.name}_{key}"] = value
        
        for ups in self.ups_systems:
            for key, value in ups.get_points().items():
                points[f"{ups.name}_{key}"] = value
        
        return points


class PlantGenerator:
    """Generates central plant equipment based on campus size."""
    
    def __init__(self, seed: str = None):
        self._seed = seed
    
    def generate(self, num_buildings: int, total_sq_ft: int) -> CentralPlant:
        """Generate a central plant sized for the campus."""
        if self._seed:
            random.seed(self._seed + "_plant")
        
        # Size plant based on campus
        # Rule of thumb: ~400 sq ft per ton of cooling, ~30 BTU/sq ft heating
        cooling_tons_needed = total_sq_ft / 400
        heating_mbh_needed = (total_sq_ft * 30) / 1000
        
        # Create chillers (size for 50-60% each for redundancy)
        num_chillers = max(2, min(4, int(cooling_tons_needed / 400) + 1))
        chiller_size = (cooling_tons_needed * 1.2) / num_chillers
        
        chillers = []
        for i in range(num_chillers):
            chillers.append(Chiller(
                id=i + 1,
                name=f"CH-{i + 1}",
                capacity_tons=round(chiller_size + random.uniform(-50, 50), 0),
                efficiency_kw_ton=random.uniform(0.55, 0.7)
            ))
        
        # Create boilers
        num_boilers = max(2, min(3, int(heating_mbh_needed / 1500) + 1))
        boiler_size = (heating_mbh_needed * 1.2) / num_boilers
        
        boilers = []
        for i in range(num_boilers):
            boilers.append(Boiler(
                id=i + 1,
                name=f"BLR-{i + 1}",
                capacity_mbh=round(boiler_size + random.uniform(-200, 200), 0),
                efficiency=random.uniform(0.82, 0.92)
            ))
        
        # Create cooling towers
        num_towers = num_chillers  # One per chiller typically
        tower_size = (cooling_tons_needed * 1.25) / num_towers  # 25% larger for heat rejection
        
        cooling_towers = []
        for i in range(num_towers):
            cooling_towers.append(CoolingTower(
                id=i + 1,
                name=f"CT-{i + 1}",
                capacity_tons=round(tower_size + random.uniform(-50, 50), 0)
            ))
        
        # Create pumps
        chw_pumps = []
        for i in range(max(2, num_chillers)):
            chw_pumps.append(Pump(
                id=i + 1,
                name=f"CHWP-{i + 1}",
                pump_type="CHW",
                capacity_gpm=round(cooling_tons_needed * 2.4 / num_chillers, 0)
            ))
        
        hw_pumps = []
        for i in range(max(2, num_boilers)):
            hw_pumps.append(Pump(
                id=i + 1,
                name=f"HWP-{i + 1}",
                pump_type="HW",
                capacity_gpm=round(heating_mbh_needed / 10, 0)
            ))
        
        cw_pumps = []
        for i in range(max(2, num_chillers)):
            cw_pumps.append(Pump(
                id=i + 1,
                name=f"CWP-{i + 1}",
                pump_type="CW",
                capacity_gpm=round(cooling_tons_needed * 3.0 / num_chillers, 0)
            ))
        
        plant = CentralPlant(
            id=1,
            name="Central_Plant",
            chillers=chillers,
            boilers=boilers,
            cooling_towers=cooling_towers,
            chw_pumps=chw_pumps,
            hw_pumps=hw_pumps,
            cw_pumps=cw_pumps
        )
        
        logger.info(f"Generated Central Plant: {num_chillers} chillers, {num_boilers} boilers, "
                   f"{num_towers} cooling towers")
        
        return plant


class ElectricalSystemGenerator:
    """Generates electrical power system based on campus size."""
    
    def __init__(self, seed: str = None):
        self._seed = seed
    
    def generate(self, total_demand_kw: float) -> ElectricalSystem:
        """Generate electrical system sized for campus."""
        if self._seed:
            random.seed(self._seed + "_electrical")
        
        # Main meter
        main_meter = ElectricalMeter(id=0, name="Main_Meter", meter_type="main")
        
        # Submeters for major loads
        submeters = []
        num_submeters = max(2, min(6, int(total_demand_kw / 500)))
        for i in range(num_submeters):
            submeters.append(ElectricalMeter(
                id=i + 1,
                name=f"Submeter_{i + 1}",
                meter_type="submeter"
            ))
        
        # Backup generators (N+1 redundancy)
        generators = []
        gen_capacity = total_demand_kw * 0.8  # 80% of peak for emergency
        num_generators = max(1, min(3, int(gen_capacity / 500) + 1))
        gen_size = gen_capacity / num_generators
        
        for i in range(num_generators):
            generators.append(Generator(
                id=i + 1,
                name=f"GEN-{i + 1}",
                capacity_kw=round(gen_size + random.uniform(-50, 50), 0),
                fuel_type="diesel"
            ))
        
        # UPS systems for critical loads
        ups_systems = []
        num_ups = max(1, min(4, int(total_demand_kw / 300)))
        
        for i in range(num_ups):
            ups_systems.append(UPS(
                id=i + 1,
                name=f"UPS-{i + 1}",
                capacity_kva=round(100 + random.uniform(0, 200), 0)
            ))
        
        # Solar arrays (if campus has space)
        solar_arrays = []
        solar_capacity = total_demand_kw * random.uniform(0.1, 0.3)  # 10-30% solar
        num_arrays = max(1, min(4, int(solar_capacity / 100)))
        
        for i in range(num_arrays):
            solar_arrays.append(SolarArray(
                id=i + 1,
                name=f"Solar_Array_{i + 1}",
                capacity_kw=round(solar_capacity / num_arrays, 0),
                num_panels=int((solar_capacity / num_arrays) * 3)  # ~330W per panel
            ))
        
        # Main transformer
        transformers = [Transformer(
            id=1,
            name="Main_Transformer",
            capacity_kva=round(total_demand_kw * 1.25, 0),  # 25% margin
            primary_voltage=13800.0,
            secondary_voltage=480.0
        )]
        
        system = ElectricalSystem(
            id=1,
            name="Electrical_System",
            main_meter=main_meter,
            submeters=submeters,
            generators=generators,
            ups_systems=ups_systems,
            solar_arrays=solar_arrays,
            transformers=transformers
        )
        
        logger.info(f"Generated Electrical System: {num_generators} generators, "
                   f"{num_ups} UPS, {num_arrays} solar arrays")
        
        return system


class WastewaterFacilityGenerator:
    """Generates wastewater treatment facility."""
    
    def __init__(self, seed: str = None):
        self._seed = seed
    
    def generate(self, num_buildings: int) -> WastewaterFacility:
        """Generate wastewater facility sized for campus."""
        if self._seed:
            random.seed(self._seed + "_wastewater")
        
        # Estimate flow: ~100 GPD per person, ~20 people per 1000 sq ft
        # For simplicity, base on building count
        design_flow_mgd = max(0.5, num_buildings * 0.2)
        
        # Lift stations
        lift_stations = []
        num_lifts = max(1, min(3, num_buildings // 3))
        for i in range(num_lifts):
            lift_stations.append(LiftStation(
                id=i + 1,
                name=f"LS-{i + 1}",
                num_pumps=2
            ))
        
        # Aeration blowers
        blowers = []
        num_blowers = max(2, min(4, int(design_flow_mgd * 2)))
        for i in range(num_blowers):
            blowers.append(AerationBlower(
                id=i + 1,
                name=f"Blower-{i + 1}",
                capacity_scfm=round(1500 + random.uniform(-200, 500), 0),
                status=i < num_blowers - 1  # N-1 running
            ))
        
        # Clarifiers
        clarifiers = []
        clarifiers.append(Clarifier(
            id=1,
            name="Primary_Clarifier",
            diameter_ft=round(40 + design_flow_mgd * 10, 0),
            clarifier_type="primary"
        ))
        clarifiers.append(Clarifier(
            id=2,
            name="Secondary_Clarifier",
            diameter_ft=round(50 + design_flow_mgd * 10, 0),
            clarifier_type="secondary"
        ))
        
        # UV disinfection
        uv_systems = [UVDisinfection(
            id=1,
            name="UV_System",
            num_banks=max(2, int(design_flow_mgd * 2)),
            lamps_per_bank=16
        )]
        
        # Pick a random name
        display_name = random.choice(WASTEWATER_NAMES)
        
        facility = WastewaterFacility(
            id=1,
            name="Wastewater_Facility",
            display_name=display_name,
            lift_stations=lift_stations,
            blowers=blowers,
            clarifiers=clarifiers,
            uv_systems=uv_systems
        )
        
        logger.info(f"Generated Wastewater Facility: {num_lifts} lift stations, "
                   f"{num_blowers} blowers, {len(clarifiers)} clarifiers")
        
        return facility


class DataCenterGenerator:
    """Generates data center facility."""
    
    def __init__(self, seed: str = None):
        self._seed = seed
    
    def generate(self, size: str = "medium") -> DataCenter:
        """Generate data center of specified size."""
        if self._seed:
            random.seed(self._seed + "_datacenter")
        
        # Size determines number of racks
        size_config = {
            "small": {"racks": 10, "cracs": 2, "ups": 2},
            "medium": {"racks": 30, "cracs": 6, "ups": 4},
            "large": {"racks": 80, "cracs": 16, "ups": 8}
        }
        config = size_config.get(size, size_config["medium"])
        
        # Server racks
        server_racks = []
        for i in range(config["racks"]):
            row = chr(65 + (i // 10))  # A, B, C...
            position = (i % 10) + 1
            server_racks.append(ServerRack(
                id=i + 1,
                name=f"Rack_{row}{position:02d}",
                it_load_kw=round(8 + random.uniform(0, 8), 1)
            ))
        
        # CRAC units
        crac_units = []
        for i in range(config["cracs"]):
            crac_units.append(CRAC(
                id=i + 1,
                name=f"CRAC-{i + 1}",
                capacity_tons=round(15 + random.uniform(0, 10), 0)
            ))
        
        # UPS systems
        ups_systems = []
        for i in range(config["ups"]):
            ups_systems.append(UPS(
                id=i + 1,
                name=f"DC_UPS-{i + 1}",
                capacity_kva=round(200 + random.uniform(0, 100), 0)
            ))
        
        # Pick a random name
        display_name = random.choice(DATA_CENTER_NAMES)
        
        dc = DataCenter(
            id=1,
            name="Data_Center",
            display_name=display_name,
            server_racks=server_racks,
            crac_units=crac_units,
            ups_systems=ups_systems,
            tier_level=3 if size == "large" else 2
        )
        
        logger.info(f"Generated Data Center ({size}): {config['racks']} racks, "
                   f"{config['cracs']} CRACs, {config['ups']} UPS")
        
        return dc


# OATCalculator classes moved to weather.py to support almanac data
# Keeping imports for backward compatibility if needed, but implementation is now in weather.py


class CampusType(Enum):
    UNIVERSITY = "University"
    CORPORATE = "Corporate"
    HOSPITAL = "Hospital"
    DATA_CENTER = "Data Center"
    MIXED_USE = "Mixed Use"

class CampusModelGenerator:
    """
    Generates campus model structure (SRP - only handles model generation).
    Separated from CampusEngine for single responsibility.
    """
    
    def __init__(self, config: CampusSizeConfig, seed: str = None, 
                 building_names: List[str] = None, campus_type: CampusType = CampusType.UNIVERSITY):
        self._config = config
        self._seed = seed
        self._building_names = building_names or []
        self._campus_type = campus_type
    
    def generate(self) -> List[Building]:
        """Generate buildings based on configuration with variance."""
        if self._seed:
            random.seed(self._seed)
        
        logger.info(
            f"Generating Campus: Type={self._campus_type.value}, Size={self._config.name}, "
            f"Bldgs={self._config.num_buildings}, "
            f"AHUs={self._config.num_ahus_per_building}, "
            f"VAVs={self._config.num_vavs_per_ahu}"
        )
        
        # Shuffle name lists for variety
        available_building_names = BUILDING_NAMES.copy()
        random.shuffle(available_building_names)
        available_zone_names = ZONE_NAMES.copy()
        
        # Adjust names based on campus type
        if self._campus_type == CampusType.HOSPITAL:
            available_building_names = ["Main Hospital", "Emergency Wing", "Outpatient Center", "Research Lab", "Medical Office", "Parking Garage", "Central Utility Plant"]
            available_zone_names = ["Patient Room", "Operating Room", "ICU", "Lab", "Office", "Waiting Area", "Corridor"]
        elif self._campus_type == CampusType.CORPORATE:
            available_building_names = ["Headquarters", "Sales Office", "R&D Center", "Cafeteria", "Conference Center", "Parking Garage"]
            available_zone_names = ["Open Office", "Conference Room", "Executive Office", "Break Room", "Lobby", "Server Room"]
        elif self._campus_type == CampusType.DATA_CENTER:
            available_building_names = ["Data Hall A", "Data Hall B", "NOC", "Admin Building", "Power Plant"]
            available_zone_names = ["Data Hall", "Meet-Me Room", "NOC", "Office", "Battery Room"]
        elif self._campus_type == CampusType.MIXED_USE:
            available_building_names = ["Office Tower", "Residential Block", "Retail Center", "Hotel", "Gym", "Parking Garage", "Cinema", "Medical Clinic"]
            available_zone_names = ["Apartment", "Office", "Shop", "Room", "Lobby", "Corridor"]
        
        buildings = []
        for b_idx in range(self._config.num_buildings):
            # Use custom name if provided, otherwise pick from random pool
            if b_idx < len(self._building_names) and self._building_names[b_idx]:
                display_name = self._building_names[b_idx]
            elif b_idx < len(available_building_names):
                display_name = available_building_names[b_idx]
            else:
                display_name = f"Building {b_idx + 1}"
            
            # Randomize building characteristics
            floor_count = random.randint(1, 5)
            sq_ft = random.randint(5000, 50000) * floor_count
            
            # Assign a random controller profile to this building
            profile = get_random_profile()
            
            bldg = Building(
                id=b_idx + 1,
                name=f"Building_{b_idx + 1}",
                display_name=display_name,
                device_instance=1000 + (b_idx * 100),
                floor_count=floor_count,
                square_footage=sq_ft,
                profile=profile
            )
            
            # Determine how many 100% OA AHUs (usually 1-2 per building for fresh air)
            # Hospitals have more 100% OA units
            oa_ratio = 3
            if self._campus_type == CampusType.HOSPITAL:
                oa_ratio = 1 # Mostly 100% OA
            
            num_oa_ahus = random.randint(0, max(1, self._config.num_ahus_per_building // oa_ratio))
            
            for a_idx in range(self._config.num_ahus_per_building):
                # Determine AHU type
                is_oa_ahu = a_idx < num_oa_ahus
                ahu_type = "100%OA" if is_oa_ahu else "VAV"
                ahu_name = f"OA_AHU_{a_idx + 1}" if is_oa_ahu else f"AHU_{a_idx + 1}"
                
                ahu = AHU(
                    id=a_idx + 1, 
                    name=ahu_name,
                    ahu_type=ahu_type,
                    fan_speed=random.uniform(60.0, 90.0),
                    filter_dp=random.uniform(0.3, 0.8)
                )
                
                # 100% OA AHUs don't have VAVs - they provide fresh air to the building
                if not is_oa_ahu:
                    # Add VAVs with variance
                    num_vavs = self._config.num_vavs_per_ahu + random.randint(-2, 2)
                    num_vavs = max(1, num_vavs)  # At least 1 VAV
                    
                    for v_idx in range(num_vavs):
                        # Pick a random zone name
                        zone_name = random.choice(available_zone_names)
                        floor = random.randint(1, floor_count)
                        room_num = 100 * floor + random.randint(1, 50)
                        
                        # Create VAV with variance in characteristics
                        cfm_max = random.randint(300, 800)
                        cfm_min = int(cfm_max * random.uniform(0.15, 0.3))
                        setpoint = random.uniform(70.0, 74.0)
                        
                        # Different thermal characteristics based on zone type
                        if "Server" in zone_name or "IT" in zone_name or "Data Hall" in zone_name:
                            thermal_mass = random.uniform(500, 800)  # Faster response
                            setpoint = random.uniform(65.0, 68.0)  # Cooler setpoint
                        elif "Warehouse" in zone_name or "Loading" in zone_name:
                            thermal_mass = random.uniform(1500, 2500)  # Slower response
                        elif "Operating Room" in zone_name:
                            setpoint = random.uniform(62.0, 66.0) # Cold ORs
                            cfm_min = int(cfm_max * 0.5) # High air change rate
                        else:
                            thermal_mass = random.uniform(800, 1200)
                        
                        thermal_model = SimpleThermalModel(thermal_mass=thermal_mass)
                        
                        # Create VAV with separate heating/cooling setpoints (typically 4°F deadband)
                        cooling_sp = round(setpoint + 2.0, 1)  # Cooling setpoint 2°F above midpoint
                        heating_sp = round(setpoint - 2.0, 1)  # Heating setpoint 2°F below midpoint
                        
                        vav = VAV(
                            id=v_idx + 1, 
                            name=f"VAV_{v_idx + 1}",
                            zone_name=f"{zone_name} {room_num}",
                            room_temp=setpoint + random.uniform(-3.0, 3.0),
                            cooling_setpoint=cooling_sp,
                            heating_setpoint=heating_sp,
                            discharge_air_temp=55.0 + random.uniform(-2.0, 5.0),
                            cfm_max=cfm_max,
                            cfm_min=cfm_min,
                            damper_position=random.uniform(20.0, 60.0),
                            reheat_valve=random.uniform(0.0, 20.0),
                            occupancy=random.random() > 0.3,  # 70% occupied initially
                            _thermal_model=thermal_model
                        )
                        ahu.vavs.append(vav)
                
                bldg.ahus.append(ahu)
            
            buildings.append(bldg)
        
        return buildings

class ScenarioType(Enum):
    NORMAL = "Normal"
    RAINSTORM = "Rainstorm"
    WINDSTORM = "Windstorm"
    THUNDERSTORM = "Thunderstorm"
    SNOW = "Snow"

class ScenarioManager:
    """
    Manages active scenarios (weather events, disasters) that override normal physics.
    """
    def __init__(self, engine):
        self._engine = engine
        self._active_scenario = ScenarioType.NORMAL
        self._scenario_start_time = 0
        self._scenario_duration = 0
        self._auto_change_frequency = 0 # Seconds, 0 = disabled
        self._last_auto_change = time.time()
    
    def start_scenario(self, scenario_type: ScenarioType, duration: int = 300):
        """Start a specific scenario for a duration in seconds."""
        self._active_scenario = scenario_type
        self._scenario_start_time = time.time()
        self._scenario_duration = duration
        logger.info(f"Started scenario: {scenario_type.value} for {duration} seconds")
        
        # Reset any previous effects immediately
        if self._engine.electrical_system:
            self._engine.electrical_system.utility_available = True

    def update(self):
        """Update scenario state and apply effects."""
        # Auto scenario change logic
        if self._auto_change_frequency > 0:
            if time.time() - self._last_auto_change > self._auto_change_frequency:
                self._last_auto_change = time.time()
                # Pick a random scenario
                # 70% chance of NORMAL, 30% chance of something else
                if random.random() < 0.7:
                    new_scenario = ScenarioType.NORMAL
                else:
                    options = [s for s in ScenarioType if s != ScenarioType.NORMAL]
                    new_scenario = random.choice(options)
                
                # Start new scenario (or switch to normal)
                if new_scenario == ScenarioType.NORMAL:
                    self.stop_scenario()
                else:
                    self.start_scenario(new_scenario, duration=self._auto_change_frequency)

        if self._active_scenario == ScenarioType.NORMAL:
            return

        elapsed = time.time() - self._scenario_start_time
        if elapsed > self._scenario_duration:
            self.stop_scenario()
            return

        # Apply scenario effects
        if self._active_scenario == ScenarioType.SNOW:
            # Override OAT to freezing (20-30F)
            self._engine._oat = 25.0 + math.sin(elapsed / 20) * 2.0
        
        elif self._active_scenario == ScenarioType.RAINSTORM:
            # Heavy rain - moderate cooling, no power issues
            # Drop temp to ~60-65F
            target_temp = 62.0
            if self._engine._oat > target_temp:
                self._engine._oat -= 0.5  # Gradual cooling
            
            # Increase humidity (implied by cooling load increase in future)
            
        elif self._active_scenario == ScenarioType.WINDSTORM:
            # High winds - erratic temperature readings (wind chill)
            noise = random.uniform(-3.0, 3.0)
            self._engine._oat += noise
            
            # Power flickers (brief outages) due to lines swaying
            if random.random() < 0.08: # 8% chance per tick
                if self._engine.electrical_system:
                    self._engine.electrical_system.utility_available = False
            else:
                if self._engine.electrical_system:
                    self._engine.electrical_system.utility_available = True

        elif self._active_scenario == ScenarioType.THUNDERSTORM:
            # Severe storm - Power outage
            # Grid failure after 15 seconds
            if elapsed > 15:
                if self._engine.electrical_system:
                    self._engine.electrical_system.utility_available = False
            
            # Rapid temp drop
            self._engine._oat -= 0.2  # Fast drop per tick

    def stop_scenario(self):
        """Stop the current scenario."""
        self._active_scenario = ScenarioType.NORMAL
        if self._engine.electrical_system:
            self._engine.electrical_system.utility_available = True
        logger.info("Scenario ended, returning to normal operation")
        
    @property
    def active_scenario(self) -> str:
        return self._active_scenario.value


class CampusEngine(PhysicsEngine):
    """
    Main campus simulation engine (SRP - orchestrates physics simulation only).
    Depends on abstractions (DIP) - OATCalculator, CampusModelGenerator.
    """
    
    def __init__(self, 
                 config: CampusSizeConfig = None,
                 oat_calculator: OATCalculator = None,
                 model_generator: CampusModelGenerator = None,
                 location_name: str = None,
                 campus_type: str = "University"):
        # Configuration with defaults (DIP - dependencies can be injected)
        self._config = config or CampusSizeConfig.from_string(
            os.environ.get("CAMPUS_SIZE", "Small")
        )
        # Use AlmanacOATCalculator by default for realistic weather
        self._oat_calculator = oat_calculator or AlmanacOATCalculator()
        self._weather = WeatherConditions(oat=70.0, humidity=50.0, wet_bulb=60.0, dew_point=50.0, enthalpy=25.0)
        self._oat = 70.0 # Keep for backward compatibility
        
        self._simulation_speed: float = float(os.environ.get("SIMULATION_SPEED", "1.0"))
        self._geo_lat: float = float(os.environ.get("GEO_LAT", "36.16"))
        self._geo_lon: float = float(os.environ.get("GEO_LON", "-86.78"))
        self._location_name: str = location_name or os.environ.get("LOCATION_NAME", "Nashville, TN")
        self._seed: str = os.environ.get("SEED", "")
        
        # Determine campus type
        try:
            self._campus_type = CampusType(campus_type)
        except ValueError:
            self._campus_type = CampusType.UNIVERSITY
        
        # Generate model
        generator = model_generator or CampusModelGenerator(
            self._config, 
            self._seed if self._seed else None,
            campus_type=self._campus_type
        )
        self._buildings: List[Building] = generator.generate()
        
        # Generate central plant based on campus size
        total_sq_ft = sum(b.square_footage for b in self._buildings)
        plant_generator = PlantGenerator(self._seed if self._seed else None)
        self._central_plant: CentralPlant = plant_generator.generate(
            len(self._buildings), total_sq_ft
        )
        
        # Generate electrical system
        estimated_demand_kw = total_sq_ft / 50 + self._central_plant.total_plant_kw  # ~20W/sq ft + plant
        elec_generator = ElectricalSystemGenerator(self._seed if self._seed else None)
        self._electrical_system: ElectricalSystem = elec_generator.generate(estimated_demand_kw)
        
        # Generate wastewater facility (if campus is medium or larger)
        if self._config.num_buildings >= 3:
            ww_generator = WastewaterFacilityGenerator(self._seed if self._seed else None)
            self._wastewater_facility: WastewaterFacility = ww_generator.generate(self._config.num_buildings)
        else:
            self._wastewater_facility = None
        
        # Generate data center (if campus has enough IT load)
        if self._config.num_buildings >= 2:
            dc_size = "small" if self._config.num_buildings < 5 else "medium" if self._config.num_buildings < 8 else "large"
            dc_generator = DataCenterGenerator(self._seed if self._seed else None)
            self._data_center: DataCenter = dc_generator.generate(dc_size)
        else:
            self._data_center = None
        
        self._oat: float = 70.0
        self._time_of_day: float = 0.5  # Noon
        self._simulation_date = datetime(2024, 1, 1, 12, 0, 0) # Start at noon Jan 1st
        self._running = False
        self._thread = None
        self._lock = threading.Lock()
        
        # Scenario Manager
        self._scenario_manager = ScenarioManager(self)
        
        # Set up point paths for override support
        self._setup_point_paths()
    
    def _setup_point_paths(self):
        """Set up _point_path for all equipment to enable override support."""
        # Buildings, AHUs, VAVs
        for building in self._buildings:
            building_path = f"Building_{building.id}"
            for ahu in building.ahus:
                ahu._point_path = f"{building_path}.AHU_{ahu.id}"
                ahu.profile = building.profile
                for vav in ahu.vavs:
                    vav._point_path = f"{building_path}.AHU_{ahu.id}.VAV_{vav.id}"
                    vav.profile = building.profile
        
        # Central Plant
        if self._central_plant:
            plant_path = "CentralPlant"
            for chiller in self._central_plant.chillers:
                chiller._point_path = f"{plant_path}.{chiller.name}"
            for boiler in self._central_plant.boilers:
                boiler._point_path = f"{plant_path}.{boiler.name}"
            for ct in self._central_plant.cooling_towers:
                ct._point_path = f"{plant_path}.{ct.name}"
            for pump in self._central_plant.chw_pumps + self._central_plant.hw_pumps + self._central_plant.cw_pumps:
                pump._point_path = f"{plant_path}.{pump.name}"
        
        # Electrical System
        if self._electrical_system:
            elec_path = "Electrical"
            if self._electrical_system.main_meter:
                self._electrical_system.main_meter._point_path = f"{elec_path}.{self._electrical_system.main_meter.name}"
            for meter in self._electrical_system.submeters:
                meter._point_path = f"{elec_path}.{meter.name}"
            for gen in self._electrical_system.generators:
                gen._point_path = f"{elec_path}.{gen.name}"
            for ups in self._electrical_system.ups_systems:
                ups._point_path = f"{elec_path}.{ups.name}"
            for solar in self._electrical_system.solar_arrays:
                solar._point_path = f"{elec_path}.{solar.name}"
            for xfmr in self._electrical_system.transformers:
                xfmr._point_path = f"{elec_path}.{xfmr.name}"
        
        # Wastewater Facility
        if self._wastewater_facility:
            ww_path = "Wastewater"
            for ls in self._wastewater_facility.lift_stations:
                ls._point_path = f"{ww_path}.{ls.name}"
            for blower in self._wastewater_facility.blowers:
                blower._point_path = f"{ww_path}.{blower.name}"
            for clarifier in self._wastewater_facility.clarifiers:
                clarifier._point_path = f"{ww_path}.{clarifier.name}"
            for uv in self._wastewater_facility.uv_systems:
                uv._point_path = f"{ww_path}.{uv.name}"
        
        # Data Center
        if self._data_center:
            dc_path = f"DataCenter.{self._data_center.name}"
            for rack in self._data_center.server_racks:
                rack._point_path = f"{dc_path}.{rack.name}"
            for crac in self._data_center.crac_units:
                crac._point_path = f"{dc_path}.{crac.name}"
            for ups in self._data_center.ups_systems:
                ups._point_path = f"{dc_path}.{ups.name}"
        
        logger.info("Point paths configured for override support")
    
    @property
    def buildings(self) -> List[Building]:
        """Get all buildings in the campus."""
        return self._buildings
    
    @property
    def central_plant(self) -> CentralPlant:
        """Get the central plant."""
        return self._central_plant
    
    @property
    def electrical_system(self) -> ElectricalSystem:
        """Get the electrical power system."""
        return self._electrical_system
    
    @property
    def wastewater_facility(self) -> WastewaterFacility:
        """Get the wastewater treatment facility."""
        return self._wastewater_facility
    
    @property
    def data_center(self) -> DataCenter:
        """Get the data center."""
        return self._data_center
    
    @property
    def oat(self) -> float:
        """Get current outside air temperature."""
        return self._weather.oat

    @property
    def humidity(self) -> float:
        """Get current relative humidity (%)."""
        return self._weather.humidity

    @property
    def wet_bulb(self) -> float:
        """Get current wet bulb temperature (F)."""
        return self._weather.wet_bulb

    @property
    def dew_point(self) -> float:
        """Get current dew point temperature (F)."""
        return self._weather.dew_point

    @property
    def enthalpy(self) -> float:
        """Get current enthalpy (BTU/lb)."""
        return self._weather.enthalpy
    
    @property
    def time_of_day(self) -> float:
        """Get current time of day (0-1, 0=midnight, 0.5=noon)."""
        return self._time_of_day
    
    @property
    def simulation_speed(self) -> float:
        """Get simulation speed multiplier."""
        return self._simulation_speed
    
    @property
    def config(self) -> CampusSizeConfig:
        """Get current campus configuration."""
        return self._config
    
    @property
    def geo_lat(self) -> float:
        """Get campus latitude."""
        return self._geo_lat
    
    @property
    def geo_lon(self) -> float:
        """Get campus longitude."""
        return self._geo_lon
    
    @property
    def location_name(self) -> str:
        """Get campus location name."""
        return self._location_name
    
    @property
    def seed(self) -> str:
        """Get current seed."""
        return self._seed
    
    def reconfigure(self, num_buildings: int = None, num_ahus: int = None, 
                    num_vavs: int = None, latitude: float = None,
                    longitude: float = None, location_name: str = None,
                    simulation_speed: float = None, seed: str = None,
                    building_names: List[str] = None, campus_type: str = None) -> dict:
        """
        Reconfigure the campus simulation dynamically.
        Returns the new configuration.
        """
        with self._lock:
            # Update location
            if latitude is not None:
                self._geo_lat = latitude
            if longitude is not None:
                self._geo_lon = longitude
            if location_name is not None:
                self._location_name = location_name
            if simulation_speed is not None:
                self._simulation_speed = max(0.1, min(100.0, simulation_speed))
            
            # Check if we need to regenerate the model
            needs_regen = False
            new_buildings = num_buildings if num_buildings is not None else self._config.num_buildings
            new_ahus = num_ahus if num_ahus is not None else self._config.num_ahus_per_building
            new_vavs = num_vavs if num_vavs is not None else self._config.num_vavs_per_ahu
            
            new_campus_type = self._campus_type
            if campus_type:
                try:
                    new_campus_type = CampusType(campus_type)
                except ValueError:
                    pass

            if (new_buildings != self._config.num_buildings or
                new_ahus != self._config.num_ahus_per_building or
                new_vavs != self._config.num_vavs_per_ahu or
                seed is not None or
                building_names is not None or
                new_campus_type != self._campus_type):
                needs_regen = True
            
            if needs_regen:
                # Update config
                self._config = CampusSizeConfig(
                    name="Custom",
                    num_buildings=max(1, min(5, new_buildings)),
                    num_ahus_per_building=max(1, min(20, new_ahus)),
                    num_vavs_per_ahu=max(1, min(50, new_vavs))
                )
                
                # Update seed
                if seed is not None:
                    self._seed = seed
                
                # Update type
                self._campus_type = new_campus_type

                # Regenerate model
                generator = CampusModelGenerator(
                    self._config,
                    self._seed if self._seed else None,
                    building_names=building_names,
                    campus_type=self._campus_type
                )
                self._buildings = generator.generate()
                
                # Regenerate plant for new campus size
                total_sq_ft = sum(b.square_footage for b in self._buildings)
                plant_generator = PlantGenerator(self._seed if self._seed else None)
                self._central_plant = plant_generator.generate(
                    len(self._buildings), total_sq_ft
                )
                
                # Regenerate electrical system
                estimated_demand_kw = total_sq_ft / 50 + self._central_plant.total_plant_kw
                elec_generator = ElectricalSystemGenerator(self._seed if self._seed else None)
                self._electrical_system = elec_generator.generate(estimated_demand_kw)
                
                # Regenerate wastewater (if medium+ campus)
                if self._config.num_buildings >= 3:
                    ww_generator = WastewaterFacilityGenerator(self._seed if self._seed else None)
                    self._wastewater_facility = ww_generator.generate(self._config.num_buildings)
                else:
                    self._wastewater_facility = None
                
                # Regenerate data center
                if self._config.num_buildings >= 2:
                    dc_size = "small" if self._config.num_buildings < 5 else "medium" if self._config.num_buildings < 8 else "large"
                    dc_generator = DataCenterGenerator(self._seed if self._seed else None)
                    self._data_center = dc_generator.generate(dc_size)
                else:
                    self._data_center = None
                
                # Reset point paths after regeneration
                self._setup_point_paths()
                
                logger.info(f"Campus regenerated: {self._config.num_buildings} buildings, "
                           f"{self._config.num_ahus_per_building} AHUs, "
                           f"{self._config.num_vavs_per_ahu} VAVs")
            elif building_names:
                # Just update building names without regenerating
                for i, name in enumerate(building_names):
                    if i < len(self._buildings) and name:
                        self._buildings[i].display_name = name
            
            return self.get_config()
    
    def trigger_scenario(self, scenario_name: str, duration: int = 300) -> str:
        """Trigger a specific scenario."""
        try:
            scenario_type = ScenarioType(scenario_name)
            self._scenario_manager.start_scenario(scenario_type, duration)
            return f"Started scenario: {scenario_name}"
        except ValueError:
            return f"Unknown scenario: {scenario_name}"
            
    def get_config(self) -> dict:
        """Get current configuration as dictionary."""
        # Collect building details
        buildings_info = []
        for bldg in self._buildings:
            ahu_info = []
            for ahu in bldg.ahus:
                ahu_info.append({
                    'id': ahu.id,
                    'name': ahu.name,
                    'type': ahu.ahu_type,
                    'vav_count': len(ahu.vavs)
                })
            buildings_info.append({
                'id': bldg.id,
                'name': bldg.name,
                'display_name': bldg.display_name,
                'floor_count': bldg.floor_count,
                'square_footage': bldg.square_footage,
                'ahu_count': len(bldg.ahus),
                'vav_count': bldg.vav_count,
                'oa_ahu_count': bldg.oa_ahu_count,
                'ahus': ahu_info
            })
        
        return {
            'active_scenario': self._scenario_manager.active_scenario,
            'auto_scenario_frequency': self._scenario_manager._auto_change_frequency,
            'campus_type': self._campus_type.value,
            'num_buildings': self._config.num_buildings,
            'num_ahus': self._config.num_ahus_per_building,
            'num_vavs': self._config.num_vavs_per_ahu,
            'latitude': self._geo_lat,
            'longitude': self._geo_lon,
            'location_name': self._location_name,
            'simulation_speed': self._simulation_speed,
            'seed': self._seed,
            'buildings': buildings_info,
            'plant': {
                'num_chillers': len(self._central_plant.chillers),
                'num_boilers': len(self._central_plant.boilers),
                'num_cooling_towers': len(self._central_plant.cooling_towers),
                'num_chw_pumps': len(self._central_plant.chw_pumps),
                'num_hw_pumps': len(self._central_plant.hw_pumps),
                'num_cw_pumps': len(self._central_plant.cw_pumps),
            },
            'electrical': {
                'num_generators': len(self._electrical_system.generators),
                'num_ups': len(self._electrical_system.ups_systems),
                'num_solar_arrays': len(self._electrical_system.solar_arrays),
                'solar_capacity_kw': sum(s.capacity_kw for s in self._electrical_system.solar_arrays),
            },
            'wastewater': {
                'enabled': self._wastewater_facility is not None,
                'display_name': self._wastewater_facility.display_name if self._wastewater_facility else None,
                'num_lift_stations': len(self._wastewater_facility.lift_stations) if self._wastewater_facility else 0,
                'num_blowers': len(self._wastewater_facility.blowers) if self._wastewater_facility else 0,
            } if self._wastewater_facility else {'enabled': False},
            'data_center': {
                'enabled': self._data_center is not None,
                'display_name': self._data_center.display_name if self._data_center else None,
                'num_racks': len(self._data_center.server_racks) if self._data_center else 0,
                'num_cracs': len(self._data_center.crac_units) if self._data_center else 0,
                'tier_level': self._data_center.tier_level if self._data_center else 0,
            } if self._data_center else {'enabled': False},
        }
        
    def start(self) -> None:
        """Start the physics simulation."""
        self._running = True
        self._thread = threading.Thread(target=self._physics_loop, daemon=True)
        self._thread.start()
        logger.info("Physics Engine Started")
        
    def stop(self) -> None:
        """Stop the physics simulation."""
        self._running = False
        if self._thread:
            self._thread.join()
        logger.info("Physics Engine Stopped")

    def set_simulation_date(self, new_date: datetime) -> None:
        """Set the simulation date and time."""
        with self._lock:
            self._simulation_date = new_date
            self._update_oat() # Update OAT immediately for the new time
            logger.info(f"Simulation date set to {new_date}")

    def _physics_loop(self) -> None:
        """Main physics simulation loop with realistic thermal and power calculations."""
        while self._running:
            start_time = time.time()
            
            dt = 5.0 * self._simulation_speed
            self._simulation_date += timedelta(seconds=dt)
            
            self._update_oat()
            
            # Update active scenario (may override OAT or other params)
            self._scenario_manager.update()
            
            # Update Building Occupancy
            for bldg in self._buildings:
                bldg.update_occupancy(self._simulation_date)
            
            # Get plant temperatures for AHU coil calculations
            chw_supply = self._central_plant.chw_supply_temp
            hw_supply = self._central_plant.hw_supply_temp
            
            # Calculate campus cooling/heating demand from AHU valve positions
            total_cooling_demand = 0.0  # Tons
            total_heating_demand = 0.0  # MBH
            total_reheat_demand = 0.0   # MBH from VAV reheat
            total_ahu_kw = 0.0          # Fan power
            
            for bldg in self._buildings:
                for ahu in bldg.ahus:
                    # Update AHU with plant temperatures and time of day
                    ahu.update(self._oat, dt, time_of_day=self._time_of_day,
                              chw_supply_temp=chw_supply, hw_supply_temp=hw_supply)
                    
                    # Calculate cooling load from coil (tons = GPM * ΔT / 24)
                    if ahu.cooling_valve > 0:
                        # Estimate flow based on valve position
                        coil_gpm = 30 * (ahu.cooling_valve / 100.0)  # ~30 GPM at full open
                        delta_t = min(10, (ahu.mixed_air_temp - ahu.supply_temp))
                        cooling_tons = coil_gpm * delta_t / 24.0
                        total_cooling_demand += max(0, cooling_tons)
                    
                    # Calculate heating load from AHU coil
                    if ahu.heating_valve > 0:
                        coil_mbh = 500 * (ahu.heating_valve / 100.0)  # ~500 MBH capacity per AHU
                        total_heating_demand += coil_mbh
                    
                    # Fan power: approximately 0.5-1 HP per 1000 CFM, ~0.75 kW per HP
                    fan_hp = len(ahu.vavs) * 0.3  # ~300 CFM per VAV, 0.5 HP per 1000 CFM
                    fan_kw = fan_hp * 0.75 * (ahu.fan_speed / 100.0) ** 3  # Affinity laws
                    total_ahu_kw += fan_kw
                    
                    # Update VAVs with AHU supply temp
                    for vav in ahu.vavs:
                        vav.update(self._oat, dt, supply_air_temp=ahu.supply_temp, 
                                  time_of_day=self._time_of_day)
                        
                        # Calculate reheat load from VAV
                        if vav.reheat_valve > 0:
                            # Reheat coil ~10 MBH capacity per VAV
                            reheat_mbh = 10 * (vav.reheat_valve / 100.0)
                            total_reheat_demand += reheat_mbh
            
            # Total heating includes AHU coils and VAV reheat
            total_heating_demand += total_reheat_demand
            
            # Update central plant with campus demand
            self._central_plant.update(
                self._oat, dt, 
                cooling_demand=total_cooling_demand,
                heating_demand=total_heating_demand
            )
            
            # Calculate total campus electrical load
            total_campus_kw = self._central_plant.total_plant_kw + total_ahu_kw
            
            # Building loads vary with time of day (occupancy)
            total_sq_ft = sum(b.square_footage for b in self._buildings)
            
            # Lighting: ~1.0 W/sq ft during occupied, 0.2 W/sq ft unoccupied
            # Equipment: ~1.5 W/sq ft during occupied, 0.3 W/sq ft unoccupied
            if 0.29 < self._time_of_day < 0.75:  # ~7am to 6pm
                occupancy = 0.3 + 0.7 * math.sin((self._time_of_day - 0.29) * math.pi / 0.46)
            else:
                occupancy = 0.1
            
            lighting_kw = total_sq_ft * (0.2 + 0.8 * occupancy) / 1000.0
            equipment_kw = total_sq_ft * (0.3 + 1.2 * occupancy) / 1000.0
            total_campus_kw += lighting_kw + equipment_kw
            
            # Add data center load (24/7 constant IT load)
            if self._data_center:
                self._data_center.update(self._oat, dt)
                total_campus_kw += self._data_center.total_kw
            
            # Add wastewater load (24/7 with some variation)
            if self._wastewater_facility:
                self._wastewater_facility.update(self._oat, dt)
                total_campus_kw += self._wastewater_facility.total_kw
            
            # Update electrical system with time of day for solar calculation
            self._electrical_system.update(self._oat, dt, total_campus_kw, self._time_of_day)
            
            sleep_time = 5.0 / self._simulation_speed
            elapsed = time.time() - start_time
            if sleep_time > elapsed:
                time.sleep(sleep_time - elapsed)
                
    def _update_oat(self) -> None:
        """Update outside air temperature and time of day."""
        # Calculate seconds from start of year for OAT calc
        start_of_year = datetime(self._simulation_date.year, 1, 1)
        seconds_from_start = (self._simulation_date - start_of_year).total_seconds()
        day_of_year = self._simulation_date.timetuple().tm_yday
        
        self._weather = self._oat_calculator.calculate_conditions(seconds_from_start, self._geo_lat, day_of_year)
        self._oat = self._weather.oat # Sync legacy field
        
        # Update time of day (0-1 where 0=midnight, 0.5=noon)
        total_seconds = self._simulation_date.hour * 3600 + self._simulation_date.minute * 60 + self._simulation_date.second
        self._time_of_day = total_seconds / 86400.0
    
    def get_all_points(self) -> Dict[str, float]:
        """Get all points from the entire campus."""
        points = {
            'Campus_OAT': self._weather.oat, 
            'Campus_Humidity': self._weather.humidity,
            'Campus_WetBulb': self._weather.wet_bulb,
            'Campus_DewPoint': self._weather.dew_point,
            'Campus_Enthalpy': self._weather.enthalpy,
            'Time_Of_Day': self._time_of_day
        }
        for bldg in self._buildings:
            points.update(bldg.get_points())
        # Add plant points
        plant_points = self._central_plant.get_points()
        for key, value in plant_points.items():
            points[f"Plant_{key}"] = value
        # Add electrical system points
        elec_points = self._electrical_system.get_points()
        for key, value in elec_points.items():
            points[f"Electrical_{key}"] = value
        # Add wastewater points
        if self._wastewater_facility:
            ww_points = self._wastewater_facility.get_points()
            for key, value in ww_points.items():
                points[f"Wastewater_{key}"] = value
        # Add data center points
        if self._data_center:
            dc_points = self._data_center.get_points()
            for key, value in dc_points.items():
                points[f"DataCenter_{key}"] = value
        return points

