from dataclasses import dataclass, field
from typing import List, Dict, Optional
import random
import math

from interfaces import Updatable, PointProvider
from .overrides import get_override_manager
from .electrical import UPS

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
    supply_air_setpoint: float = 68.0
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
    WRITABLE_POINTS = {'status', 'supply_air_temp', 'fan_speed_pct', 'supply_air_setpoint'}
    
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

    def get_effective_value(self, point_name: str) -> float:
        """Get the effective value of a point, considering overrides."""
        val = getattr(self, point_name)
        return self._apply_override(point_name, val)
    
    def update(self, oat: float = 0.0, dt: float = 0.0, 
               heat_load_kw: float = 50.0, setpoint: float = 68.0) -> None:
        """Update CRAC based on heat load."""
        # Check for status override
        status_override = self._get_override_status('status')
        if status_override is not None:
            self.status = bool(self._apply_override('status', float(self.status)))
        
        # Check for setpoint override
        setpoint_override = self._get_override_status('supply_air_setpoint')
        if setpoint_override is not None:
            self.supply_air_setpoint = self._apply_override('supply_air_setpoint', self.supply_air_setpoint)
        else:
            self.supply_air_setpoint = setpoint

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
                self.supply_air_temp = self.supply_air_setpoint - 10 + (self.cooling_output_pct / 100) * 5
            
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
