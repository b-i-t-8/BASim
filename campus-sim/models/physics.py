from abc import ABC, abstractmethod
import math
from .parameters import get_simulation_parameters

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
