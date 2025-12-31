import os
import time
import threading
import logging
import random
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any

from interfaces import CampusSizeConfig, PhysicsEngine
from weather import AlmanacOATCalculator, OATCalculator, WeatherConditions
from .types import CampusType, ScenarioType
from .hvac import Building
from .plant import CentralPlant
from .electrical import ElectricalSystem
from .facilities import WastewaterFacility, DataCenter
from .generators import (
    CampusModelGenerator, PlantGenerator, ElectricalSystemGenerator,
    WastewaterFacilityGenerator, DataCenterGenerator
)
from .scenarios import ScenarioManager

logger = logging.getLogger("CampusEngine")

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

    def _update_oat(self):
        """Update Outside Air Temperature based on time and location."""
        day_of_year = self._simulation_date.timetuple().tm_yday
        current_time = self._simulation_date.timestamp()
        
        self._weather = self._oat_calculator.calculate_conditions(
            current_time, 
            self._geo_lat, 
            day_of_year
        )
        self._oat = self._weather.oat
        
        # Update time of day (0-1)
        hour = self._simulation_date.hour + self._simulation_date.minute / 60.0
        self._time_of_day = hour / 24.0

    def _physics_loop(self) -> None:
        """Main physics simulation loop with realistic thermal and power calculations."""
        while self._running:
            start_time = time.time()
            
            with self._lock:
                dt = 5.0 * self._simulation_speed
                self._simulation_date += timedelta(seconds=dt)
                
                self._update_oat()
                
                # Update active scenario (may override OAT or other params)
                self._scenario_manager.update()
                
            # Update Building Occupancy
            for b in self._buildings:
                if b.occupied:
                    occupied_buildings += 1                # Get plant temperatures for AHU coil calculations
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
                
                # Update Central Plant
                self._central_plant.update(self._oat, dt, 
                                          cooling_demand=total_cooling_demand,
                                          heating_demand=total_heating_demand)
                
                # Update Wastewater Facility (if present)
                ww_kw = 0.0
                if self._wastewater_facility:
                    self._wastewater_facility.update(self._oat, dt)
                    ww_kw = self._wastewater_facility.total_kw
                
                # Update Data Center (if present)
                dc_kw = 0.0
                if self._data_center:
                    self._data_center.update(self._oat, dt)
                    dc_kw = self._data_center.total_kw
                
                # Update Electrical System
                # Total demand = Plant + AHUs + Lighting/Plug Loads + Wastewater + Data Center
                
                # Estimate lighting/plug loads based on occupancy
                base_load_kw = sum(b.square_footage for b in self._buildings) * 0.001 # 1 W/sq ft base
                occupied_load_kw = 0.0
                for b in self._buildings:
                    if b.occupied:
                        occupied_load_kw += b.square_footage * 0.0015 # Additional 1.5 W/sq ft when occupied
                
                total_demand_kw = (
                    self._central_plant.total_plant_kw + 
                    total_ahu_kw + 
                    base_load_kw + 
                    occupied_load_kw +
                    ww_kw +
                    dc_kw
                )
                
                if self._electrical_system:
                    self._electrical_system.update(self._oat, dt, total_demand_kw)
            
            # Sleep to maintain simulation speed
            elapsed = time.time() - start_time
            sleep_time = max(0.01, 1.0 / self._simulation_speed - elapsed)
            time.sleep(sleep_time)
