"""
Protocol Registrars following SOLID principles.
Separates the responsibility of registering points from the main application logic.
"""
from abc import ABC, abstractmethod
from typing import Any
import logging

from servers import ModbusServer, BACnetServer
from models import CampusEngine
from interfaces import PointMetadataProvider

logger = logging.getLogger("Registrars")

class ProtocolRegistrar(ABC):
    """Abstract base class for protocol registrars."""
    
    def __init__(self, engine: CampusEngine):
        self._engine = engine
        
    @abstractmethod
    async def register(self, server: Any) -> None:
        """Register points to the server."""
        pass

class ModbusRegistrar(ProtocolRegistrar):
    """Registers points to Modbus server."""
    
    async def register(self, server: ModbusServer) -> None:
        eng = self._engine
        # ... (rest of logic) ...

        
        # === BUILDINGS (VFDs Only) ===
        for bldg in eng.buildings:
            for ahu in bldg.ahus:
                prefix = f"{bldg.name}_{ahu.name}"
                
                # Only VFD related points for AHUs
                server.register_point(f"{prefix}_FanSpeed", ahu.fan_speed, writable=True)
                server.register_point(f"{prefix}_FanStatus", float(ahu.fan_status))
                server.register_point(f"{prefix}_Enable", float(ahu.fan_status), writable=True)
                
                # No VAVs in Modbus (typically BACnet/MSTP)

        # === CENTRAL PLANT (Industrial/VFDs) ===
        plant = eng.central_plant
        if plant:
            # Chillers (Often have Modbus interface)
            for ch in plant.chillers:
                prefix = f"Chiller_{ch.id}"
                server.register_point(f"{prefix}_Status", float(ch.status))
                server.register_point(f"{prefix}_Enable", float(ch.status), writable=True)
                server.register_point(f"{prefix}_CHWSupply", ch.chw_supply_temp)
                server.register_point(f"{prefix}_CHWReturn", ch.chw_return_temp)
                server.register_point(f"{prefix}_CHWSetpoint", ch.chw_supply_temp, writable=True)
                server.register_point(f"{prefix}_Load", ch.load_percent)
                server.register_point(f"{prefix}_kW", ch.kw)
                server.register_point(f"{prefix}_Fault", float(ch.fault))
            
            # Boilers
            for b in plant.boilers:
                prefix = f"Boiler_{b.id}"
                server.register_point(f"{prefix}_Status", float(b.status))
                server.register_point(f"{prefix}_Enable", float(b.status), writable=True)
                server.register_point(f"{prefix}_HWSupply", b.hw_supply_temp)
                server.register_point(f"{prefix}_HWReturn", b.hw_return_temp)
                server.register_point(f"{prefix}_HWSetpoint", b.hw_supply_temp, writable=True)
                server.register_point(f"{prefix}_FiringRate", b.firing_rate)
                server.register_point(f"{prefix}_kW", b.gas_flow_cfh * 0.03)
            
            # Cooling Towers (VFDs)
            for ct in plant.cooling_towers:
                prefix = f"CoolingTower_{ct.id}"
                server.register_point(f"{prefix}_Status", float(ct.status))
                server.register_point(f"{prefix}_Enable", float(ct.status), writable=True)
                server.register_point(f"{prefix}_FanSpeed", ct.fan_speed, writable=True)
            
            # Pumps (VFDs)
            all_pumps = plant.chw_pumps + plant.hw_pumps + plant.cw_pumps
            for p in all_pumps:
                prefix = f"Pump_{p.id}"
                server.register_point(f"{prefix}_Status", float(p.status == 'running'))
                server.register_point(f"{prefix}_Enable", float(p.status == 'running'), writable=True)
                server.register_point(f"{prefix}_Speed", p.speed, writable=True)
                server.register_point(f"{prefix}_kW", p.kw)

        # === ELECTRICAL SYSTEM (Modbus is King) ===
        elec = eng.electrical_system
        if elec:
            server.register_point("Electrical_MainMeter_kW", elec.total_demand_kw)
            server.register_point("Electrical_MainMeter_kWh", elec.main_meter.kwh_total)
            if hasattr(elec, 'solar_production_kw'):
                server.register_point("Electrical_Solar_kW", elec.solar_production_kw)
            
            for ups in elec.ups_systems:
                prefix = f"UPS_{ups.id}"
                server.register_point(f"{prefix}_Status", float(ups.status == 'online'))
                server.register_point(f"{prefix}_Load", ups.load_pct)
                server.register_point(f"{prefix}_Battery", ups.battery_pct)
            
            for gen in elec.generators:
                prefix = f"Generator_{gen.id}"
                server.register_point(f"{prefix}_Status", float(gen.status == 'running'))
                server.register_point(f"{prefix}_Enable", float(gen.status == 'running'), writable=True)
                server.register_point(f"{prefix}_Output_kW", gen.output_kw)
                server.register_point(f"{prefix}_FuelLevel", gen.fuel_level_pct)

        # === DATA CENTER (Industrial) ===
        dc = eng.data_center
        if dc and dc.enabled:
            server.register_point("DataCenter_TotalLoad_kW", dc.total_it_load_kw)
            server.register_point("DataCenter_PUE", dc.pue)
            
            for crac in dc.crac_units:
                prefix = f"CRAC_{crac.id}"
                server.register_point(f"{prefix}_Status", float(crac.status == 'running'))
                server.register_point(f"{prefix}_Enable", float(crac.status == 'running'), writable=True)
                server.register_point(f"{prefix}_SupplyTemp", crac.supply_air_temp)
                server.register_point(f"{prefix}_SupplyTempSP", crac.supply_air_setpoint, writable=True)
                server.register_point(f"{prefix}_FanSpeed", crac.fan_speed_pct, writable=True)

        # === WASTEWATER (Industrial) ===
        ww = eng.wastewater_facility
        if ww and ww.enabled:
            server.register_point("Wastewater_InfluentFlow", ww.influent_flow_mgd)
            server.register_point("Wastewater_EffluentFlow", ww.effluent_flow_mgd)
            server.register_point("Wastewater_DO", ww.dissolved_oxygen_mg_l)
            
            for blower in ww.blowers:
                prefix = f"Blower_{blower.id}"
                server.register_point(f"{prefix}_Status", float(blower.status == 'running'))
                server.register_point(f"{prefix}_Enable", float(blower.status == 'running'), writable=True)
                server.register_point(f"{prefix}_Speed", blower.speed_pct, writable=True)
                server.register_point(f"{prefix}_Output", blower.output_scfm)

class BACnetRegistrar(ProtocolRegistrar):
    """Registers points to BACnet server."""
    
    async def register(self, server: BACnetServer) -> None:
        eng = self._engine
        
        # === CAMPUS LEVEL ===
        server.register_point("Campus_OAT", eng.oat, object_type='AI',
                              point_path="campus/oat")
        server.register_point("Campus_Humidity", eng.humidity, object_type='AI',
                              point_path="campus/humidity")
        server.register_point("Campus_WetBulb", eng.wet_bulb, object_type='AI',
                              point_path="campus/wet_bulb")
        server.register_point("Campus_DewPoint", eng.dew_point, object_type='AI',
                              point_path="campus/dew_point")
        server.register_point("Campus_Enthalpy", eng.enthalpy, object_type='AI',
                              point_path="campus/enthalpy")
        
        # === BUILDINGS ===
        for bldg in eng.buildings:
            bldg_path = f"building_{bldg.id}"
            
            # Building Occupancy
            server.register_point(f"{bldg.name}_Occupancy", float(bldg.occupied),
                                  object_type='BI', point_path=f"{bldg_path}/occupancy")
            
            for ahu in bldg.ahus:
                ahu_path = f"{bldg_path}/ahu_{ahu.id}"
                
                # AHU points
                if hasattr(ahu, 'get_point_definitions') and hasattr(ahu, 'get_points'):
                    points_def = ahu.get_point_definitions()
                    points_val = ahu.get_points()
                    
                    for p_def in points_def:
                        val = 0.0
                        if p_def.internal_key and p_def.internal_key in points_val:
                            val = points_val[p_def.internal_key]
                        
                        # Construct point path
                        path_suffix = p_def.name.lower()
                        
                        server.register_point(
                            f"{bldg.name}_{ahu.name}_{p_def.name}",
                            val,
                            object_type=p_def.bacnet_object_type,
                            writable=p_def.writable,
                            point_path=f"{ahu_path}/{path_suffix}"
                        )
                
                # VAV points
                for vav in ahu.vavs:
                    vav_path = f"{ahu_path}/vav_{vav.id}"
                    prefix = f"{bldg.name}_{ahu.name}_{vav.name}"
                    
                    if hasattr(vav, 'get_point_definitions') and hasattr(vav, 'get_points'):
                        points_def = vav.get_point_definitions()
                        points_val = vav.get_points()
                        
                        for p_def in points_def:
                            val = 0.0
                            if p_def.internal_key and p_def.internal_key in points_val:
                                val = points_val[p_def.internal_key]
                            
                            path_suffix = p_def.name.lower()
                            
                            server.register_point(
                                f"{prefix}_{p_def.name}",
                                val,
                                object_type=p_def.bacnet_object_type,
                                writable=p_def.writable,
                                point_path=f"{vav_path}/{path_suffix}"
                            )
