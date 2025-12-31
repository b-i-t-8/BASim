import random
import logging
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, field

from interfaces import CampusSizeConfig
from profiles import ControllerProfile, get_random_profile
from .parameters import get_simulation_parameters
from .types import CampusType
from .physics import SimpleThermalModel
from .hvac import Building, AHU, VAV, BuildingType, ZONE_NAMES, BUILDING_NAMES
from .plant import Chiller, Boiler, CoolingTower, Pump, CentralPlant
from .electrical import ElectricalMeter, Generator, UPS, SolarArray, Transformer, ElectricalSystem
from .facilities import (
    LiftStation, AerationBlower, Clarifier, UVDisinfection, WastewaterFacility,
    ServerRack, CRAC, DataCenter
)

logger = logging.getLogger("Generators")

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

class PlantGenerator:
    """Generates central plant equipment based on campus size."""
    
    def __init__(self, seed: str = None):
        self._seed = seed
    
    def generate(self, num_buildings: int, total_sq_ft: int) -> CentralPlant:
        """Generate a central plant sized for the campus."""
        if self._seed:
            random.seed(self._seed + "_plant")
        
        params = get_simulation_parameters()
        
        # Size plant based on campus
        # Rule of thumb: ~400 sq ft per ton of cooling, ~30 BTU/sq ft heating
        sqft_per_ton = params.get('gen_cooling_sqft_per_ton')
        btu_per_sqft = params.get('gen_heating_btu_per_sqft')
        
        cooling_tons_needed = total_sq_ft / sqft_per_ton
        heating_mbh_needed = (total_sq_ft * btu_per_sqft) / 1000
        
        # Create chillers (size for 50-60% each for redundancy)
        num_chillers = max(2, min(4, int(cooling_tons_needed / 400) + 1))
        chiller_size = (cooling_tons_needed * 1.2) / num_chillers
        
        chiller_eff_min = params.get('gen_chiller_efficiency_min')
        chiller_eff_max = params.get('gen_chiller_efficiency_max')
        
        chillers = []
        for i in range(num_chillers):
            chillers.append(Chiller(
                id=i + 1,
                name=f"CH-{i + 1}",
                capacity_tons=round(chiller_size + random.uniform(-50, 50), 0),
                efficiency_kw_ton=random.uniform(chiller_eff_min, chiller_eff_max)
            ))
        
        # Create boilers
        num_boilers = max(2, min(3, int(heating_mbh_needed / 1500) + 1))
        boiler_size = (heating_mbh_needed * 1.2) / num_boilers
        
        boiler_eff_min = params.get('gen_boiler_efficiency_min')
        boiler_eff_max = params.get('gen_boiler_efficiency_max')
        
        boilers = []
        for i in range(num_boilers):
            boilers.append(Boiler(
                id=i + 1,
                name=f"BLR-{i + 1}",
                capacity_mbh=round(boiler_size + random.uniform(-200, 200), 0),
                efficiency=random.uniform(boiler_eff_min, boiler_eff_max)
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
        params = get_simulation_parameters()
        solar_min_pct = params.get('gen_solar_pct_min') / 100.0
        solar_max_pct = params.get('gen_solar_pct_max') / 100.0
        
        solar_arrays = []
        solar_capacity = total_demand_kw * random.uniform(solar_min_pct, solar_max_pct)
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
            
            # Determine building type based on name or random
            b_type = BuildingType.OFFICE
            eff_factor = 1.0
            schedule = (7, 18)
            
            name_lower = display_name.lower()
            if "lab" in name_lower or "research" in name_lower:
                b_type = BuildingType.LAB
                eff_factor = 1.2 # Higher load
                schedule = (6, 20)
            elif "hospital" in name_lower or "medical" in name_lower or "clinic" in name_lower:
                b_type = BuildingType.HOSPITAL
                eff_factor = 1.5
                schedule = (0, 24) # 24/7
            elif "data" in name_lower or "server" in name_lower:
                b_type = BuildingType.DATA_CENTER
                eff_factor = 2.0
                schedule = (0, 24)
            elif "warehouse" in name_lower or "storage" in name_lower:
                b_type = BuildingType.WAREHOUSE
                eff_factor = 0.5
                schedule = (6, 16)
            elif "residential" in name_lower or "apartment" in name_lower or "hotel" in name_lower:
                b_type = BuildingType.RESIDENTIAL
                eff_factor = 0.8
                schedule = (16, 23) 
            elif "retail" in name_lower or "shop" in name_lower or "mall" in name_lower:
                b_type = BuildingType.RETAIL
                eff_factor = 1.1
                schedule = (9, 21)
            
            # Randomize schedule slightly
            if schedule != (0, 24):
                start = max(0, schedule[0] + random.randint(-1, 1))
                end = min(24, schedule[1] + random.randint(-1, 1))
                schedule = (start, end)
                
            # Randomize efficiency (Old vs New)
            if random.random() > 0.7:
                eff_factor *= 1.2 # Old building
            elif random.random() < 0.3:
                eff_factor *= 0.8 # LEED building

            bldg = Building(
                id=b_idx + 1,
                name=f"Building_{b_idx + 1}",
                display_name=display_name,
                device_instance=1000 + (b_idx * 100),
                floor_count=floor_count,
                square_footage=sq_ft,
                profile=profile,
                building_type=b_type.value,
                efficiency_factor=eff_factor,
                occupancy_schedule=schedule
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
