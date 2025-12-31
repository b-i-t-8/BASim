from dataclasses import dataclass, field
from typing import List, Dict, Optional
import random
import math

from interfaces import Updatable, PointProvider
from .overrides import get_override_manager

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
        
        # Check for status override
        status_override = self._get_override_status('status')
        if status_override is not None:
            override_val = self._apply_override('status', 0)
            if override_val == 1:
                self.status = "battery"
            elif override_val == 2:
                self.status = "bypass"
            else:
                self.status = "online"
        elif not utility_available and self.status == "online":
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
            gen.update(oat, dt, load_kw=self.total_demand_kw, start_command=not self.utility_available)
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
