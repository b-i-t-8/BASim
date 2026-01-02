"""
Campus Simulation Main Entry Point

Refactored to follow SOLID principles:
- SRP: Each class has a single responsibility
- OCP: Protocol servers can be extended without modification  
- LSP: All servers implement ProtocolServer interface
- ISP: Interfaces are segregated (ProtocolServer, Updatable, PointProvider)
- DIP: High-level orchestrator depends on abstractions
"""
__version__ = "0.0.5"

import asyncio
import logging
import sys
import os
from typing import List

# Add web module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'web'))

from models import CampusEngine, get_simulation_parameters
from servers import ModbusServer, BACnetServer, BACnetSCHub
from interfaces import ProtocolServer
from web.app import WebServer
from registrars import ModbusRegistrar, BACnetRegistrar

# Configure Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger("Main")




    

    



class PointSynchronizer:
    """
    Synchronizes point values from engine to protocol servers (SRP).
    Separates synchronization logic from main orchestration.
    """
    
    def __init__(self, engine: CampusEngine):
        self._engine = engine
    
    def sync_to_modbus(self, server: ModbusServer) -> None:
        """Sync all point values to Modbus server."""
        eng = self._engine
        params = get_simulation_parameters()
        
        # === BUILDINGS (VFDs Only) ===
        for bldg in eng.buildings:
            for ahu in bldg.ahus:
                prefix = f"{bldg.name}_{ahu.name}"
                
                # Only VFD related points for AHUs
                server.update_point(f"{prefix}_FanSpeed", ahu.fan_speed)
                server.update_point(f"{prefix}_FanStatus", float(ahu.fan_status))
                server.update_point(f"{prefix}_Enable", float(ahu.fan_status))
                
                # No VAVs in Modbus

        # === CENTRAL PLANT (Industrial/VFDs) ===
        plant = eng.central_plant
        if plant:
            # Chillers
            for ch in plant.chillers:
                prefix = f"Chiller_{ch.id}"
                server.update_point(f"{prefix}_Status", float(ch.status))
                server.update_point(f"{prefix}_Enable", float(ch.status))
                server.update_point(f"{prefix}_CHWSupply", params.convert_temp(ch.chw_supply_temp))
                server.update_point(f"{prefix}_CHWReturn", params.convert_temp(ch.chw_return_temp))
                server.update_point(f"{prefix}_CHWSetpoint", params.convert_temp(ch.chw_supply_temp))
                server.update_point(f"{prefix}_Load", ch.load_percent)
                server.update_point(f"{prefix}_kW", ch.kw)
                server.update_point(f"{prefix}_Fault", float(ch.fault))
            
            # Boilers
            for b in plant.boilers:
                prefix = f"Boiler_{b.id}"
                server.update_point(f"{prefix}_Status", float(b.status))
                server.update_point(f"{prefix}_Enable", float(b.status))
                server.update_point(f"{prefix}_HWSupply", params.convert_temp(b.hw_supply_temp))
                server.update_point(f"{prefix}_HWReturn", params.convert_temp(b.hw_return_temp))
                server.update_point(f"{prefix}_HWSetpoint", params.convert_temp(b.hw_supply_temp))
                server.update_point(f"{prefix}_FiringRate", b.firing_rate)
                server.update_point(f"{prefix}_kW", b.gas_flow_cfh * 0.03)
            
            # Cooling Towers
            for ct in plant.cooling_towers:
                prefix = f"CoolingTower_{ct.id}"
                server.update_point(f"{prefix}_Status", float(ct.status))
                server.update_point(f"{prefix}_Enable", float(ct.status))
                server.update_point(f"{prefix}_FanSpeed", ct.fan_speed)
            
            # Pumps
            all_pumps = plant.chw_pumps + plant.hw_pumps + plant.cw_pumps
            for p in all_pumps:
                prefix = f"Pump_{p.id}"
                server.update_point(f"{prefix}_Status", float(p.status == 'running'))
                server.update_point(f"{prefix}_Enable", float(p.status == 'running'))
                server.update_point(f"{prefix}_Speed", p.speed)
                server.update_point(f"{prefix}_kW", p.kw)

        # === ELECTRICAL SYSTEM ===
        elec = eng.electrical_system
        if elec:
            server.update_point("Electrical_MainMeter_kW", elec.total_demand_kw)
            server.update_point("Electrical_MainMeter_kWh", elec.main_meter.kwh_total)
            if hasattr(elec, 'solar_production_kw'):
                server.update_point("Electrical_Solar_kW", elec.solar_production_kw)
            
            for ups in elec.ups_systems:
                prefix = f"UPS_{ups.id}"
                server.update_point(f"{prefix}_Status", float(ups.status == 'online'))
                server.update_point(f"{prefix}_Load", ups.load_pct)
                server.update_point(f"{prefix}_Battery", ups.battery_pct)
            
            for gen in elec.generators:
                prefix = f"Generator_{gen.id}"
                server.update_point(f"{prefix}_Status", float(gen.status == 'running'))
                server.update_point(f"{prefix}_Enable", float(gen.status == 'running'))
                server.update_point(f"{prefix}_Output_kW", gen.output_kw)
                server.update_point(f"{prefix}_FuelLevel", gen.fuel_level_pct)

        # === DATA CENTER ===
        dc = eng.data_center
        if dc:
            server.update_point("DataCenter_TotalLoad_kW", dc.total_it_load_kw)
            server.update_point("DataCenter_PUE", dc.pue)
            
            for crac in dc.crac_units:
                prefix = f"CRAC_{crac.id}"
                server.update_point(f"{prefix}_Status", float(crac.status == 'running'))
                server.update_point(f"{prefix}_Enable", float(crac.status == 'running'))
                server.update_point(f"{prefix}_SupplyTemp", params.convert_temp(crac.supply_air_temp))
                server.update_point(f"{prefix}_SupplyTempSP", params.convert_temp(crac.supply_air_setpoint))
                server.update_point(f"{prefix}_FanSpeed", crac.fan_speed_pct)

        # === WASTEWATER ===
        ww = eng.wastewater_facility
        if ww:
            server.update_point("Wastewater_InfluentFlow", ww.influent_flow_mgd)
            server.update_point("Wastewater_EffluentFlow", ww.effluent_flow_mgd)
            server.update_point("Wastewater_DO", ww.dissolved_oxygen_mg_l)
            
            for blower in ww.blowers:
                prefix = f"Blower_{blower.id}"
                server.update_point(f"{prefix}_Status", float(blower.status == 'running'))
                server.update_point(f"{prefix}_Enable", float(blower.status == 'running'))
                server.update_point(f"{prefix}_Speed", blower.speed_pct)
                server.update_point(f"{prefix}_Output", params.convert_flow_air(blower.output_scfm))
    
    def sync_to_bacnet(self, server: BACnetServer) -> None:
        """Sync all point values to BACnet server."""
        eng = self._engine
        params = get_simulation_parameters()
        
        # Campus level
        server.update_point("Campus_OAT", params.convert_temp(eng.oat))
        
        # Buildings
        for bldg in eng.buildings:
            for ahu in bldg.ahus:
                prefix = f"{bldg.name}_{ahu.name}"
                server.update_point(f"{prefix}_SupplyTemp", params.convert_temp(ahu.supply_temp))
                server.update_point(f"{prefix}_ReturnTemp", params.convert_temp(ahu.return_temp))
                server.update_point(f"{prefix}_MixedAirTemp", params.convert_temp(ahu.mixed_air_temp))
                server.update_point(f"{prefix}_SupplyTempSP", params.convert_temp(ahu.supply_temp_setpoint))
                server.update_point(f"{prefix}_FanSpeed", ahu.fan_speed)
                server.update_point(f"{prefix}_OADamper", ahu.outside_air_damper)
                server.update_point(f"{prefix}_FanStatus", float(ahu.fan_status))
                server.update_point(f"{prefix}_Enable", float(ahu.fan_status))
                
                for vav in ahu.vavs:
                    vav_prefix = f"{prefix}_{vav.name}"
                    server.update_point(f"{vav_prefix}_RoomTemp", params.convert_temp(vav.room_temp))
                    server.update_point(f"{vav_prefix}_CoolingSP", params.convert_temp(vav.cooling_setpoint))
                    server.update_point(f"{vav_prefix}_HeatingSP", params.convert_temp(vav.heating_setpoint))
                    server.update_point(f"{vav_prefix}_DamperPos", vav.damper_position)
                    server.update_point(f"{vav_prefix}_ReheatValve", vav.reheat_valve)
                    server.update_point(f"{vav_prefix}_Airflow", params.convert_flow_air(vav.airflow_cfm))
                    server.update_point(f"{vav_prefix}_Occupied", float(vav.occupied))
        
        # Central Plant
        plant = eng.central_plant
        if plant:
            for ch in plant.chillers:
                prefix = f"Chiller_{ch.id}"
                server.update_point(f"{prefix}_Status", float(ch.status))
                server.update_point(f"{prefix}_Enable", float(ch.status))
                server.update_point(f"{prefix}_CHWSupply", params.convert_temp(ch.chw_supply_temp))
                server.update_point(f"{prefix}_CHWReturn", params.convert_temp(ch.chw_return_temp))
                server.update_point(f"{prefix}_Load", ch.load_percent)
                server.update_point(f"{prefix}_kW", ch.kw)
                server.update_point(f"{prefix}_Fault", float(ch.fault))
            
            for b in plant.boilers:
                prefix = f"Boiler_{b.id}"
                server.update_point(f"{prefix}_Status", float(b.status))
                server.update_point(f"{prefix}_Enable", float(b.status))
                server.update_point(f"{prefix}_HWSupply", params.convert_temp(b.hw_supply_temp))
                server.update_point(f"{prefix}_HWReturn", params.convert_temp(b.hw_return_temp))
                server.update_point(f"{prefix}_FiringRate", b.firing_rate)
                server.update_point(f"{prefix}_kW", b.gas_flow_cfh * 0.03)
            
            for ct in plant.cooling_towers:
                prefix = f"CoolingTower_{ct.id}"
                server.update_point(f"{prefix}_Status", float(ct.status))
                server.update_point(f"{prefix}_Enable", float(ct.status))
                server.update_point(f"{prefix}_CWSupply", params.convert_temp(ct.cw_supply_temp))
                server.update_point(f"{prefix}_CWReturn", params.convert_temp(ct.cw_return_temp))
                server.update_point(f"{prefix}_FanSpeed", ct.fan_speed)
            
            all_pumps = plant.chw_pumps + plant.hw_pumps + plant.cw_pumps
            for p in all_pumps:
                prefix = f"Pump_{p.id}"
                server.update_point(f"{prefix}_Status", float(p.status == 'running'))
                server.update_point(f"{prefix}_Enable", float(p.status == 'running'))
                server.update_point(f"{prefix}_Speed", p.speed)
                server.update_point(f"{prefix}_Flow", params.convert_flow_water(p.flow_gpm))
                server.update_point(f"{prefix}_kW", p.kw)
        
        # Electrical
        elec = eng.electrical_system
        if elec:
            server.update_point("Electrical_MainMeter_kW", elec.total_demand_kw)
            server.update_point("Electrical_MainMeter_kWh", elec.total_energy_kwh)
            if hasattr(elec, 'solar_production_kw'):
                server.update_point("Electrical_Solar_kW", elec.solar_production_kw)
            
            for ups in elec.ups_units:
                prefix = f"UPS_{ups.id}"
                server.update_point(f"{prefix}_Status", float(ups.status == 'online'))
                server.update_point(f"{prefix}_Load", ups.load_pct)
                server.update_point(f"{prefix}_Battery", ups.battery_pct)
            
            for gen in elec.generators:
                prefix = f"Generator_{gen.id}"
                server.update_point(f"{prefix}_Status", float(gen.status == 'running'))
                server.update_point(f"{prefix}_Enable", float(gen.status == 'running'))
                server.update_point(f"{prefix}_Output_kW", gen.output_kw)
                server.update_point(f"{prefix}_FuelLevel", gen.fuel_level_pct)
        
        # Data Center
        dc = eng.data_center
        if dc and dc.enabled:
            server.update_point("DataCenter_TotalLoad_kW", dc.total_it_load_kw)
            server.update_point("DataCenter_PUE", dc.pue)
            
            for crac in dc.crac_units:
                prefix = f"CRAC_{crac.id}"
                server.update_point(f"{prefix}_Status", float(crac.status == 'running'))
                server.update_point(f"{prefix}_Enable", float(crac.status == 'running'))
                server.update_point(f"{prefix}_SupplyTemp", params.convert_temp(crac.supply_air_temp))
                server.update_point(f"{prefix}_SupplyTempSP", params.convert_temp(crac.supply_air_setpoint))
                server.update_point(f"{prefix}_FanSpeed", crac.fan_speed_pct)
        
        # Wastewater
        ww = eng.wastewater_facility
        if ww and ww.enabled:
            server.update_point("Wastewater_InfluentFlow", ww.influent_flow_mgd)
            server.update_point("Wastewater_EffluentFlow", ww.effluent_flow_mgd)
            server.update_point("Wastewater_DO", ww.dissolved_oxygen_mg_l)
            
            for blower in ww.blowers:
                prefix = f"Blower_{blower.id}"
                server.update_point(f"{prefix}_Status", float(blower.status == 'running'))
                server.update_point(f"{prefix}_Enable", float(blower.status == 'running'))
                server.update_point(f"{prefix}_Speed", blower.speed_pct)
                server.update_point(f"{prefix}_Output", blower.output_scfm)


class CampusSimulator:
    """
    Main orchestrator (SRP - only coordinates components).
    Depends on abstractions via dependency injection (DIP).
    """
    
    def __init__(self, 
                 engine: CampusEngine,
                 modbus_server: ModbusServer,
                 bacnet_server: BACnetServer = None,
                 web_server: WebServer = None,
                 bacnet_sc_hub: BACnetSCHub = None):
        self._engine = engine
        self._modbus = modbus_server
        self._bacnet = bacnet_server
        self._web = web_server
        self._bacnet_sc = bacnet_sc_hub
        
        # Use specialized registrars (SRP)
        self._modbus_registrar = ModbusRegistrar(engine)
        self._bacnet_registrar = BACnetRegistrar(engine)
        
        self._synchronizer = PointSynchronizer(engine)
    
    async def initialize(self) -> None:
        """Initialize all components."""
        logger.info("Initializing Campus Simulator...")
        
        # Start physics engine
        self._engine.start()
        
        # Register points to all servers
        await self._modbus_registrar.register(self._modbus)
        if self._bacnet:
            await self._bacnet_registrar.register(self._bacnet)
        
        # Start protocol servers
        self._modbus.start()
        if self._bacnet:
            self._bacnet.start()
        if self._bacnet_sc:
            self._bacnet_sc.start()
        
        # Start web server if configured
        if self._web:
            self._web.start()
        
        logger.info("Campus Simulator initialized")
    
    async def run(self) -> None:
        """Run the main synchronization loop."""
        logger.info("Entering Main Sync Loop")
        
        await self._sync_loop()
    
    async def _sync_loop(self) -> None:
        """Main synchronization loop."""
        while True:
            # Sync values to all protocol servers
            self._synchronizer.sync_to_modbus(self._modbus)
            if self._bacnet:
                self._synchronizer.sync_to_bacnet(self._bacnet)
            
            await asyncio.sleep(1)
    
    def stop(self) -> None:
        """Stop all components."""
        logger.info("Stopping Campus Simulator...")
        self._engine.stop()
        self._modbus.stop()
        if self._bacnet:
            self._bacnet.stop()
        if self._bacnet_sc:
            self._bacnet_sc.stop()
        if self._web:
            self._web.stop()
        logger.info("Campus Simulator stopped")


def create_override_callback(engine):
    """Create an override callback that applies overrides to the engine."""
    from models import get_override_manager
    
    def apply_override(point_path: str, value: float, priority: int = 8):
        """Apply an override via the override manager."""
        manager = get_override_manager()
        manager.set_override(point_path, value, priority)
        logger.info(f"Override applied: {point_path} = {value} @ priority {priority}")
    
    return apply_override


async def main():
    """Application entry point."""
    import os
    
    # Create components (DIP - dependencies are injected)
    engine = CampusEngine()
    
    # Create override callback for write operations
    override_callback = create_override_callback(engine)
    
    modbus = ModbusServer(host="0.0.0.0", port=5020)
    web = WebServer(engine, host="0.0.0.0", port=8080)
    
    # BACnet/SC hub with engine reference for real data and write support
    bacnet_sc = BACnetSCHub(host="0.0.0.0", port=8443, engine=engine, override_callback=override_callback)
    
    # BACnet/IP requires host networking - make it optional
    bacnet = None
    if os.environ.get("ENABLE_BACNET", "false").lower() == "true":
        bacnet = BACnetServer(device_name="CampusGateway", device_id=9999, override_callback=override_callback)
    
    # Create and run simulator
    simulator = CampusSimulator(engine, modbus, bacnet, web, bacnet_sc)
    
    try:
        await simulator.initialize()
        await simulator.run()
    except KeyboardInterrupt:
        simulator.stop()


if __name__ == "__main__":
    asyncio.run(main())
