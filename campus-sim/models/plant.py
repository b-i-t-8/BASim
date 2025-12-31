from dataclasses import dataclass, field
from typing import List, Dict, Optional
import random

from interfaces import Updatable, PointProvider
from .overrides import get_override_manager

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

    def get_effective_value(self, point_name: str) -> float:
        """Get the effective value of a point, considering overrides."""
        val = getattr(self, point_name)
        return self._apply_override(point_name, val)
    
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

    def get_effective_value(self, point_name: str) -> float:
        """Get the effective value of a point, considering overrides."""
        val = getattr(self, point_name)
        return self._apply_override(point_name, val)
    
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

    def get_effective_value(self, point_name: str) -> float:
        """Get the effective value of a point, considering overrides."""
        val = getattr(self, point_name)
        return self._apply_override(point_name, val)
    
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

    def get_effective_value(self, point_name: str) -> float:
        """Get the effective value of a point, considering overrides."""
        val = getattr(self, point_name)
        return self._apply_override(point_name, val)
    
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
