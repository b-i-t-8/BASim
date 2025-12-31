from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import random
from enum import Enum

from interfaces import Updatable, PointProvider, PointMetadataProvider, PointDefinition
from profiles import ControllerProfile, get_profile
from .parameters import get_simulation_parameters, SimulationParameters
from .overrides import get_override_manager
from .physics import ThermalModel, SimpleThermalModel, DamperController, ProportionalDamperController

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
    "Innovation Hub", "Alumni Center", "Graduate Hall", "Undergraduate Hall",
    "Physics Lab", "Chemistry Lab", "Biology Lab", "Mathematics Hall",
    "Computer Science Building", "Robotics Lab", "AI Research Center",
    "Humanities Building", "Social Sciences Hall", "Language Center",
    "Music Conservatory", "Theater Arts Center", "Design Studio",
    "Architecture Hall", "Urban Planning Center", "Sustainability Center",
    "Energy Research Lab", "Materials Science Building", "Nanotech Center",
    "Bioinformatics Lab", "Genomics Center", "Neuroscience Institute",
    "Psychology Building", "Education School", "Nursing School",
    "Pharmacy School", "Public Health School", "Veterinary Center",
    "Agricultural Hall", "Forestry Building", "Marine Science Center",
    "Observatory", "Planetarium", "Museum", "Art Gallery",
    "Concert Hall", "Stadium", "Arena", "Gymnasium",
    "Aquatic Center", "Tennis Center", "Track and Field Complex",
    "Welcome Center", "Admissions Office", "Registrar Office",
    "Financial Aid Office", "Career Center", "Counseling Center",
    "Health Services", "Police Station", "Fire Station",
    "Maintenance Building", "Warehouse", "Central Plant",
    "Power Station", "Water Treatment Plant", "Recycling Center"
]

class BuildingType(Enum):
    OFFICE = "Office"
    LAB = "Lab"
    CLASSROOM = "Classroom"
    HOSPITAL = "Hospital"
    DATA_CENTER = "Data Center"
    WAREHOUSE = "Warehouse"
    RESIDENTIAL = "Residential"
    RETAIL = "Retail"

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

    def get_effective_value(self, point_name: str) -> float:
        """Get the effective value of a point, considering overrides."""
        val = getattr(self, point_name)
        return self._apply_override(point_name, val)
    
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
            # Get points configuration for VAV
            profile_points = {}
            if 'VAV' in self.profile.device_types:
                profile_points = self.profile.device_types['VAV'].get('points', {})
            elif hasattr(self.profile, 'default_points'):
                profile_points = self.profile.default_points

            # 1. Create a map of internal_key -> profile_point_data
            mapped_points = {}
            for name, data in profile_points.items():
                mapping = data.get('mapping')
                if mapping:
                    mapped_points[mapping] = {
                        'name': name,
                        'description': data.get('description'),
                        'units': data.get('units'),
                        'writable': data.get('writable'),
                        'type': data.get('type')
                    }

            # 2. Update standard points
            for p in points:
                if p.internal_key in mapped_points:
                    mp = mapped_points[p.internal_key]
                    p.name = mp['name']
                    if mp['description']: p.description = mp['description']
                    if mp['units']: p.units = mp['units']
                    if mp['type']: p.bacnet_object_type = mp['type']
                    # Writable status might be enforced by physics, but we can update metadata
                    if mp['writable'] is not None: p.writable = mp['writable']
                else:
                    # Fallback to naming convention
                    if self.profile.naming_convention == "camelCase":
                        p.name = p.name[0].lower() + p.name[1:]
                    elif self.profile.naming_convention == "snake_case":
                        import re
                        p.name = re.sub(r'(?<!^)(?=[A-Z])', '_', p.name).lower()
            
            # 3. Add vendor specific points (those without mapping)
            for name, pt_def in profile_points.items():
                if pt_def.get('mapping'):
                    continue
                    
                desc = pt_def.get('description', '')
                units = pt_def.get('units', '')
                pt_type = pt_def.get('type', 'AV')
                writable = pt_def.get('writable', False)
                
                if any(p.name.lower() == name.lower() for p in points):
                    continue
                    
                points.append(PointDefinition(
                    name=name,
                    units=units,
                    writable=writable,
                    description=desc,
                    bacnet_object_type=pt_type,
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

    def get_effective_value(self, point_name: str) -> float:
        """Get the effective value of a point, considering overrides."""
        val = getattr(self, point_name)
        return self._apply_override(point_name, val)
    
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
            # Get points configuration for AHU
            profile_points = {}
            if 'AHU' in self.profile.device_types:
                profile_points = self.profile.device_types['AHU'].get('points', {})
            
            # 1. Create a map of internal_key -> profile_point_data
            mapped_points = {}
            for name, data in profile_points.items():
                mapping = data.get('mapping')
                if mapping:
                    mapped_points[mapping] = {
                        'name': name,
                        'description': data.get('description'),
                        'units': data.get('units'),
                        'writable': data.get('writable'),
                        'type': data.get('type')
                    }

            # 2. Update standard points
            for p in points:
                if p.internal_key in mapped_points:
                    mp = mapped_points[p.internal_key]
                    p.name = mp['name']
                    if mp['description']: p.description = mp['description']
                    if mp['units']: p.units = mp['units']
                    if mp['type']: p.bacnet_object_type = mp['type']
                    if mp['writable'] is not None: p.writable = mp['writable']
                else:
                    # Fallback to naming convention
                    if self.profile.naming_convention == "camelCase":
                        p.name = p.name[0].lower() + p.name[1:]
                    elif self.profile.naming_convention == "snake_case":
                        import re
                        p.name = re.sub(r'(?<!^)(?=[A-Z])', '_', p.name).lower()
            
            # 3. Add vendor specific points (those without mapping)
            for name, pt_def in profile_points.items():
                if pt_def.get('mapping'):
                    continue
                    
                desc = pt_def.get('description', '')
                units = pt_def.get('units', '')
                pt_type = pt_def.get('type', 'AV')
                writable = pt_def.get('writable', False)
                
                if any(p.name.lower() == name.lower() for p in points):
                    continue
                    
                points.append(PointDefinition(
                    name=name,
                    units=units,
                    writable=writable,
                    description=desc,
                    bacnet_object_type=pt_type,
                    internal_key=""
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
    building_type: str = "Office"
    efficiency_factor: float = 1.0
    profile: ControllerProfile = field(default_factory=lambda: get_profile("Distech"))
    
    def __post_init__(self):
        if not self.display_name:
            self.display_name = self.name
            
    def get_load_kw(self) -> float:
        """Calculate building electrical load (lighting + plug load)."""
        # Base densities (W/sq ft)
        lighting_density = 1.0 * self.efficiency_factor
        equip_density = 1.5 * self.efficiency_factor
        
        if self.occupied:
            occupancy_pct = 0.9 + random.uniform(-0.1, 0.1)
        else:
            occupancy_pct = 0.1 + random.uniform(0, 0.05)
            
        lighting_kw = self.square_footage * (0.2 + (lighting_density - 0.2) * occupancy_pct) / 1000.0
        equipment_kw = self.square_footage * (0.3 + (equip_density - 0.3) * occupancy_pct) / 1000.0
        
        return lighting_kw + equipment_kw

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
            if start < end:
                self.occupied = start <= hour < end
            else:
                # Overnight schedule (e.g. 22 to 6)
                self.occupied = hour >= start or hour < end
    
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
