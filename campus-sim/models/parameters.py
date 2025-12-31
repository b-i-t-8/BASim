import logging
import threading
from typing import Dict, Optional

# Configure logging
logger = logging.getLogger("CampusEngine")

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

        # Generation Parameters
        'gen_chiller_efficiency_min': {
            'value': 0.55,
            'min': 0.40,
            'max': 0.80,
            'unit': 'kW/ton',
            'description': 'Minimum chiller efficiency for generation',
            'category': 'generation'
        },
        'gen_chiller_efficiency_max': {
            'value': 0.70,
            'min': 0.50,
            'max': 1.20,
            'unit': 'kW/ton',
            'description': 'Maximum chiller efficiency for generation',
            'category': 'generation'
        },
        'gen_boiler_efficiency_min': {
            'value': 0.82,
            'min': 0.70,
            'max': 0.90,
            'unit': '',
            'description': 'Minimum boiler efficiency for generation',
            'category': 'generation'
        },
        'gen_boiler_efficiency_max': {
            'value': 0.92,
            'min': 0.80,
            'max': 0.99,
            'unit': '',
            'description': 'Maximum boiler efficiency for generation',
            'category': 'generation'
        },
        'gen_cooling_sqft_per_ton': {
            'value': 400.0,
            'min': 200.0,
            'max': 600.0,
            'unit': 'sq ft/ton',
            'description': 'Cooling load sizing factor',
            'category': 'generation'
        },
        'gen_heating_btu_per_sqft': {
            'value': 30.0,
            'min': 10.0,
            'max': 60.0,
            'unit': 'BTU/sq ft',
            'description': 'Heating load sizing factor',
            'category': 'generation'
        },
        'gen_solar_pct_min': {
            'value': 10.0,
            'min': 0.0,
            'max': 50.0,
            'unit': '%',
            'description': 'Minimum solar capacity percentage',
            'category': 'generation'
        },
        'gen_solar_pct_max': {
            'value': 30.0,
            'min': 0.0,
            'max': 100.0,
            'unit': '%',
            'description': 'Maximum solar capacity percentage',
            'category': 'generation'
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
