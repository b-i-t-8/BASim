"""
Flask Web GUI for Campus Simulator.
Provides a real-time dashboard and REST API for monitoring and control.
"""
import os
import random
import logging
import json
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, jsonify, request, redirect, url_for, flash, Response
from flask_cors import CORS
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

from models import CampusEngine, get_simulation_parameters

logger = logging.getLogger("WebGUI")

# Famous world locations for random generation
WORLD_LOCATIONS = [
    {"name": "New York, USA", "lat": 40.71, "lon": -74.01},
    {"name": "London, UK", "lat": 51.51, "lon": -0.13},
    {"name": "Tokyo, Japan", "lat": 35.68, "lon": 139.69},
    {"name": "Sydney, Australia", "lat": -33.87, "lon": 151.21},
    {"name": "Dubai, UAE", "lat": 25.20, "lon": 55.27},
    {"name": "Singapore", "lat": 1.35, "lon": 103.82},
    {"name": "Paris, France", "lat": 48.86, "lon": 2.35},
    {"name": "Toronto, Canada", "lat": 43.65, "lon": -79.38},
    {"name": "Mumbai, India", "lat": 19.08, "lon": 72.88},
    {"name": "São Paulo, Brazil", "lat": -23.55, "lon": -46.63},
    {"name": "Berlin, Germany", "lat": 52.52, "lon": 13.41},
    {"name": "Seoul, South Korea", "lat": 37.57, "lon": 126.98},
    {"name": "Mexico City, Mexico", "lat": 19.43, "lon": -99.13},
    {"name": "Cairo, Egypt", "lat": 30.04, "lon": 31.24},
    {"name": "Moscow, Russia", "lat": 55.76, "lon": 37.62},
    {"name": "Bangkok, Thailand", "lat": 13.76, "lon": 100.50},
    {"name": "Lagos, Nigeria", "lat": 6.52, "lon": 3.38},
    {"name": "Istanbul, Turkey", "lat": 41.01, "lon": 28.98},
    {"name": "Buenos Aires, Argentina", "lat": -34.60, "lon": -58.38},
    {"name": "Cape Town, South Africa", "lat": -33.93, "lon": 18.42},
    {"name": "Amsterdam, Netherlands", "lat": 52.37, "lon": 4.90},
    {"name": "Stockholm, Sweden", "lat": 59.33, "lon": 18.07},
    {"name": "Helsinki, Finland", "lat": 60.17, "lon": 24.94},
    {"name": "Reykjavik, Iceland", "lat": 64.15, "lon": -21.94},
    {"name": "Auckland, New Zealand", "lat": -36.85, "lon": 174.76},
    {"name": "Denver, USA", "lat": 39.74, "lon": -104.99},
    {"name": "Phoenix, USA", "lat": 33.45, "lon": -112.07},
    {"name": "Miami, USA", "lat": 25.76, "lon": -80.19},
    {"name": "Seattle, USA", "lat": 47.61, "lon": -122.33},
    {"name": "Nashville, USA", "lat": 36.16, "lon": -86.78},
]


def get_season(date):
    day = date.timetuple().tm_yday
    if 80 <= day < 172: return "Spring"
    if 172 <= day < 264: return "Summer"
    if 264 <= day < 355: return "Autumn"
    return "Winter"


def generate_random_config(seed: str = None) -> dict:
    """Generate random campus configuration from seed."""
    if seed:
        random.seed(seed)
    
    # Pick random location
    location = random.choice(WORLD_LOCATIONS)
    
    # Generate random campus size
    num_buildings = random.randint(1, 20)
    num_ahus = random.randint(2, 8)
    num_vavs = random.randint(3, 15)
    simulation_speed = round(random.uniform(0.5, 5.0), 1)
    
    return {
        'num_buildings': num_buildings,
        'num_ahus': num_ahus,
        'num_vavs': num_vavs,
        'latitude': location['lat'],
        'longitude': location['lon'],
        'location_name': location['name'],
        'simulation_speed': simulation_speed,
        'seed': seed or ''
    }


class User(UserMixin):
    """Simple user model (SRP - just user data)."""
    
    def __init__(self, id: str, username: str, password_hash: str, role: str = "viewer"):
        self.id = id
        self.username = username
        self.password_hash = password_hash
        self.role = role  # "admin" or "viewer"
    
    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class UserStore:
    """
    Simple in-memory user store (SRP - just user storage).
    In production, replace with database.
    """
    
    def __init__(self):
        self._users = {}
        # Default users - passwords from env or defaults
        admin_pass = os.environ.get("ADMIN_PASSWORD", "admin123")
        viewer_pass = os.environ.get("VIEWER_PASSWORD", "viewer123")
        
        self.add_user("1", "admin", admin_pass, "admin")
        self.add_user("2", "viewer", viewer_pass, "viewer")
    
    def add_user(self, id: str, username: str, password: str, role: str = "viewer"):
        self._users[id] = User(id, username, generate_password_hash(password), role)
        self._users[username] = self._users[id]  # Index by username too
    
    def get_by_id(self, user_id: str) -> User:
        return self._users.get(user_id)
    
    def get_by_username(self, username: str) -> User:
        return self._users.get(username)


def create_app(engine: CampusEngine) -> Flask:
    """
    Factory function to create Flask app with injected engine (DIP).
    """
    app = Flask(__name__, 
                template_folder='templates',
                static_folder='static')
    
    # Configuration
    app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")
    app.config['engine'] = engine
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    
    CORS(app, supports_credentials=True)
    
    # Setup Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    login_manager.login_message = 'Please log in to access the dashboard.'
    
    # User store
    user_store = UserStore()
    app.config['user_store'] = user_store
    
    @login_manager.user_loader
    def load_user(user_id):
        return user_store.get_by_id(user_id)
    
    # --- Auth Routes ---
    
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        """Login page and handler."""
        if current_user.is_authenticated:
            return redirect(url_for('index'))
        
        if request.method == 'POST':
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            remember = request.form.get('remember', False)
            
            user = user_store.get_by_username(username)
            
            if user and user.check_password(password):
                login_user(user, remember=bool(remember))
                logger.info(f"User '{username}' logged in")
                next_page = request.args.get('next')
                return redirect(next_page or url_for('index'))
            else:
                flash('Invalid username or password', 'error')
                logger.warning(f"Failed login attempt for '{username}'")
        
        return render_template('login.html')
    
    @app.route('/logout')
    @login_required
    def logout():
        """Logout handler."""
        logger.info(f"User '{current_user.username}' logged out")
        logout_user()
        flash('You have been logged out.', 'info')
        return redirect(url_for('login'))
    
    # --- Web Routes ---
    
    @app.route('/')
    @login_required
    def index():
        """Render main dashboard."""
        return render_template('index.html', user=current_user)

    @app.route('/docs')
    @login_required
    def docs_page():
        """Render documentation page."""
        return render_template('docs.html', user=current_user)

    @app.route('/readme')
    @login_required
    def readme_page():
        """Render README.md content."""
        try:
            with open('README.md', 'r') as f:
                content = f.read()
        except Exception as e:
            content = f"Error reading README.md: {str(e)}"
        return render_template('readme.html', user=current_user, content=content)
    
    @app.route('/docs/<path:doc_path>')
    @login_required
    def docs_file(doc_path):
        """Serve markdown docs from the docs/ folder."""
        import os
        # Only allow .md files from docs folder
        if not doc_path.endswith('.md'):
            return "Not found", 404
        
        safe_path = os.path.join('docs', os.path.basename(doc_path))
        try:
            with open(safe_path, 'r') as f:
                content = f.read()
        except FileNotFoundError:
            return "Document not found", 404
        except Exception as e:
            content = f"Error reading {doc_path}: {str(e)}"
        
        return render_template('readme.html', user=current_user, content=content)
    
    # --- REST API Routes (protected) ---
    
    def api_login_required(f):
        """Decorator for API routes - returns JSON error instead of redirect."""
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated:
                return jsonify({'error': 'Authentication required'}), 401
            return f(*args, **kwargs)
        return decorated
    
    @app.route('/api/status')
    @api_login_required
    def get_status():
        """Get overall simulation status."""
        eng = app.config['engine']
        params = get_simulation_parameters()
        plant = eng.central_plant
        elec = eng.electrical_system
        
        status = {
            'oat': round(params.convert_temp(eng.oat), 2),
            'humidity': round(eng.humidity, 1),
            'wet_bulb': round(params.convert_temp(eng.wet_bulb), 1),
            'dew_point': round(params.convert_temp(eng.dew_point), 1),
            'enthalpy': round(params.convert_enthalpy(eng.enthalpy), 1),
            'unit_system': params.unit_system,
            'campus_name': params.campus_name,
            'temp_unit': params.get_temp_unit(),
            'flow_water_unit': params.get_flow_water_unit(),
            'flow_air_unit': params.get_flow_air_unit(),
            'flow_gas_unit': params.get_flow_gas_unit(),
            'pressure_wc_unit': params.get_pressure_wc_unit(),
            'head_unit': params.get_head_unit(),
            'enthalpy_unit': params.get_enthalpy_unit(),
            'area_unit': params.get_area_unit(),
            'time_of_day': round(eng.time_of_day, 4),
            'simulation_date': eng._simulation_date.strftime("%Y-%m-%d %H:%M:%S"),
            'season': get_season(eng._simulation_date),
            'simulation_speed': eng.simulation_speed,
            'active_scenario': eng._scenario_manager._active_scenario.value,
            'auto_scenario_frequency': eng._scenario_manager._auto_change_frequency,
            'num_buildings': len(eng.buildings),
            'total_ahus': sum(len(b.ahus) for b in eng.buildings),
            'total_vavs': sum(
                len(ahu.vavs) 
                for b in eng.buildings 
                for ahu in b.ahus
            ),
            'plant_summary': {
                'running_chillers': plant.running_chillers,
                'running_boilers': plant.running_boilers,
                'running_cooling_towers': plant.running_cooling_towers,
                'total_cooling_tons': round(plant.total_cooling_load, 1),
                'total_heating_mbh': round(plant.total_heating_load, 1),
                'total_plant_kw': round(plant.total_plant_kw, 1),
                'chw_supply_temp': round(plant.chw_supply_temp, 1),
                'hw_supply_temp': round(plant.hw_supply_temp, 1),
            },
            'electrical_summary': {
                'total_demand_kw': round(elec.total_demand_kw, 1),
                'grid_import_kw': round(elec.grid_import_kw, 1),
                'solar_production_kw': round(elec.solar_production_kw, 1),
                'utility_available': elec.utility_available,
            }
        }
        
        # Add wastewater summary if enabled
        if eng.wastewater_facility:
            ww = eng.wastewater_facility
            status['wastewater_summary'] = {
                'enabled': True,
                'display_name': ww.display_name,
                'influent_flow_mgd': round(ww.influent_flow_mgd, 2),
                'total_kw': round(ww.total_kw, 1),
            }
        else:
            status['wastewater_summary'] = {'enabled': False}
        
        # Add data center summary if enabled
        if eng.data_center:
            dc = eng.data_center
            status['datacenter_summary'] = {
                'enabled': True,
                'display_name': dc.display_name,
                'total_it_load_kw': round(dc.total_it_load_kw, 1),
                'pue': round(dc.pue, 2),
            }
        else:
            status['datacenter_summary'] = {'enabled': False}
        
        return jsonify(status)
    
    @app.route('/api/plant')
    @api_login_required
    def get_plant():
        """Get central plant status."""
        eng = app.config['engine']
        params = get_simulation_parameters()
        plant = eng.central_plant
        
        chillers = []
        for ch in plant.chillers:
            chillers.append({
                'id': ch.id,
                'point_path': ch._point_path,
                'name': ch.name,
                'status': bool(ch.get_effective_value('status')),
                'capacity_tons': ch.capacity_tons,
                'load_percent': round(ch.load_percent, 1),
                'chw_supply_temp': round(params.convert_temp(ch.get_effective_value('chw_supply_temp')), 1),
                'chw_return_temp': round(params.convert_temp(ch.chw_return_temp), 1),
                'chw_flow_gpm': round(params.convert_flow_water(ch.chw_flow_gpm), 0),
                'kw': round(ch.kw, 1),
                'fault': ch.fault
            })
        
        boilers = []
        for blr in plant.boilers:
            boilers.append({
                'id': blr.id,
                'point_path': blr._point_path,
                'name': blr.name,
                'status': bool(blr.get_effective_value('status')),
                'capacity_mbh': blr.capacity_mbh,
                'firing_rate': round(blr.get_effective_value('firing_rate'), 1),
                'hw_supply_temp': round(params.convert_temp(blr.get_effective_value('hw_supply_temp')), 1),
                'hw_return_temp': round(params.convert_temp(blr.hw_return_temp), 1),
                'hw_flow_gpm': round(params.convert_flow_water(blr.hw_flow_gpm), 0),
                'gas_flow_cfh': round(params.convert_flow_gas(blr.gas_flow_cfh), 0),
                'fault': blr.fault
            })
        
        cooling_towers = []
        for ct in plant.cooling_towers:
            cooling_towers.append({
                'id': ct.id,
                'point_path': ct._point_path,
                'name': ct.name,
                'status': bool(ct.get_effective_value('status')),
                'capacity_tons': ct.capacity_tons,
                'fan_speed': round(ct.get_effective_value('fan_speed'), 1),
                'cw_supply_temp': round(params.convert_temp(ct.cw_supply_temp), 1),
                'cw_return_temp': round(params.convert_temp(ct.cw_return_temp), 1),
                'cw_flow_gpm': round(params.convert_flow_water(ct.cw_flow_gpm), 0),
                'wet_bulb_temp': round(params.convert_temp(ct.wet_bulb_temp), 1),
                'fault': ct.fault
            })
        
        pumps = []
        for pump in plant.chw_pumps + plant.hw_pumps + plant.cw_pumps:
            pumps.append({
                'id': pump.id,
                'point_path': pump._point_path,
                'name': pump.name,
                'pump_type': pump.pump_type,
                'status': bool(pump.get_effective_value('status')),
                'speed': round(pump.get_effective_value('speed'), 1),
                'flow_gpm': round(params.convert_flow_water(pump.flow_gpm), 0),
                'head_ft': round(params.convert_head_ft(pump.differential_pressure * 2.31), 1),
                'differential_psi': round(pump.differential_pressure, 1),
                'kw': round(pump.kw, 1),
                'fault': pump.fault
            })
        
        return jsonify({
            'name': plant.name,
            'chw_supply_temp': round(params.convert_temp(plant.chw_supply_temp), 1),
            'chw_return_temp': round(params.convert_temp(plant.chw_return_temp), 1),
            'hw_supply_temp': round(params.convert_temp(plant.hw_supply_temp), 1),
            'hw_return_temp': round(params.convert_temp(plant.hw_return_temp), 1),
            'total_cooling_tons': round(plant.total_cooling_load, 1),
            'total_heating_mbh': round(plant.total_heating_load, 1),
            'total_plant_kw': round(plant.total_plant_kw, 1),
            'chillers': chillers,
            'boilers': boilers,
            'cooling_towers': cooling_towers,
            'pumps': pumps
        })
    
    @app.route('/api/electrical')
    @api_login_required
    def get_electrical():
        """Get electrical power system status."""
        eng = app.config['engine']
        params = get_simulation_parameters()
        elec = eng.electrical_system
        
        return jsonify({
            'total_demand_kw': round(elec.total_demand_kw, 1),
            'grid_import_kw': round(elec.grid_import_kw, 1),
            'solar_production_kw': round(elec.solar_production_kw, 1),
            'total_generation_kw': round(elec.total_generation_kw, 1),
            'utility_available': elec.utility_available,
            'main_meter': {
                'kw': round(elec.main_meter.kw, 1),
                'kvar': round(elec.main_meter.kvar, 1),
                'kva': round(elec.main_meter.kva, 1),
                'power_factor': round(elec.main_meter.power_factor, 3),
                'voltage_a': round(elec.main_meter.voltage_a, 1),
                'voltage_b': round(elec.main_meter.voltage_b, 1),
                'voltage_c': round(elec.main_meter.voltage_c, 1),
                'frequency': round(elec.main_meter.frequency, 2),
                'kwh_total': round(elec.main_meter.kwh_total, 1),
                'demand_kw': round(elec.main_meter.demand_kw, 1),
                'peak_demand_kw': round(elec.main_meter.peak_demand_kw, 1),
            },
            'generators': [{
                'id': g.id,
                'point_path': g._point_path,
                'name': g.name,
                'capacity_kw': g.capacity_kw,
                'status': g.status,
                'output_kw': round(g.output_kw, 1),
                'fuel_level_pct': round(g.fuel_level_pct, 1),
                'runtime_hours': round(g.runtime_hours, 1),
                'fault': g.fault
            } for g in elec.generators],
            'ups_systems': [{
                'id': u.id,
                'point_path': u._point_path,
                'name': u.name,
                'capacity_kva': u.capacity_kva,
                'status': u.status,
                'load_kw': round(u.load_kw, 1),
                'load_pct': round(u.load_pct, 1),
                'battery_pct': round(u.battery_pct, 1),
                'battery_runtime_min': round(u.battery_runtime_min, 1),
                'fault': u.fault
            } for u in elec.ups_systems],
            'solar_arrays': [{
                'id': s.id,
                'point_path': s._point_path,
                'name': s.name,
                'capacity_kw': s.capacity_kw,
                'status': s.status,
                'output_kw': round(s.output_kw, 1),
                'output_kwh_today': round(s.output_kwh_today, 1),
                'irradiance_w_m2': round(s.irradiance_w_m2, 0),
                'panel_temp': round(params.convert_temp(s.panel_temp), 1),
            } for s in elec.solar_arrays],
            'transformers': [{
                'id': t.id,
                'name': t.name,
                'capacity_kva': t.capacity_kva,
                'load_pct': round(t.load_pct, 1),
                'secondary_voltage': round(t.secondary_voltage, 1),
                'winding_temp': round(params.convert_temp(t.winding_temp), 1),
                'oil_temp': round(params.convert_temp(t.oil_temp), 1),
            } for t in elec.transformers]
        })
    
    @app.route('/api/wastewater')
    @api_login_required
    def get_wastewater():
        """Get wastewater treatment facility status."""
        eng = app.config['engine']
        ww = eng.wastewater_facility
        
        if not ww:
            return jsonify({'enabled': False})
        
        return jsonify({
            'enabled': True,
            'name': ww.name,
            'display_name': ww.display_name,
            'influent_flow_mgd': round(ww.influent_flow_mgd, 2),
            'effluent_flow_mgd': round(ww.effluent_flow_mgd, 2),
            'influent_bod_mg_l': round(ww.influent_bod_mg_l, 1),
            'effluent_bod_mg_l': round(ww.effluent_bod_mg_l, 1),
            'dissolved_oxygen_mg_l': round(ww.dissolved_oxygen_mg_l, 2),
            'ph': round(ww.ph, 2),
            'total_kw': round(ww.total_kw, 1),
            'lift_stations': [{
                'id': ls.id,
                'point_path': ls._point_path,
                'name': ls.name,
                'wet_well_level_ft': round(params.convert_head_ft(ls.wet_well_level_ft), 2),
                'flow_gpm': round(params.convert_flow_water(ls.flow_gpm), 0),
                'pumps_running': sum(ls.pump_status),
                'kw': round(ls.kw, 1),
            } for ls in ww.lift_stations],
            'blowers': [{
                'id': b.id,
                'point_path': b._point_path,
                'name': b.name,
                'status': b.status,
                'speed_pct': round(b.speed_pct, 1),
                'output_scfm': round(params.convert_flow_air(b.output_scfm), 0),
                'kw': round(b.kw, 1),
                'discharge_temp': round(params.convert_temp(b.discharge_temp), 1),
            } for b in ww.blowers],
            'clarifiers': [{
                'id': c.id,
                'point_path': c._point_path,
                'name': c.name,
                'clarifier_type': c.clarifier_type,
                'flow_mgd': round(c.flow_mgd, 2),
                'sludge_blanket_ft': round(params.convert_head_ft(c.sludge_blanket_ft), 2),
                'torque_pct': round(c.torque_pct, 1),
                'effluent_tss_mg_l': round(c.effluent_tss_mg_l, 1),
            } for c in ww.clarifiers],
            'uv_systems': [{
                'id': uv.id,
                'point_path': uv._point_path,
                'name': uv.name,
                'status': uv.status,
                'uv_intensity_pct': round(uv.uv_intensity_pct, 1),
                'lamp_life_remaining_pct': round(uv.lamp_life_remaining_pct, 1),
                'kw': round(uv.kw, 1),
                'effluent_ecoli_mpn': round(uv.effluent_ecoli_mpn, 0),
            } for uv in ww.uv_systems]
        })
    
    @app.route('/api/datacenter')
    @api_login_required
    def get_datacenter():
        """Get data center status."""
        eng = app.config['engine']
        params = get_simulation_parameters()
        dc = eng.data_center
        
        if not dc:
            return jsonify({'enabled': False})
        
        return jsonify({
            'enabled': True,
            'name': dc.name,
            'display_name': dc.display_name,
            'tier_level': dc.tier_level,
            'total_it_load_kw': round(dc.total_it_load_kw, 1),
            'total_cooling_kw': round(dc.total_cooling_kw, 1),
            'total_kw': round(dc.total_kw, 1),
            'pue': round(dc.pue, 2),
            'average_inlet_temp': round(params.convert_temp(dc.average_inlet_temp), 1),
            'average_outlet_temp': round(params.convert_temp(dc.average_outlet_temp), 1),
            'server_racks': [{
                'id': r.id,
                'name': r.name,
                'it_load_kw': round(r.it_load_kw, 1),
                'inlet_temp': round(params.convert_temp(r.inlet_temp), 1),
                'outlet_temp': round(params.convert_temp(r.outlet_temp), 1),
                'utilization_pct': round(r.utilization_pct, 1),
                'pdu_a_kw': round(r.pdu_a_kw, 1),
                'pdu_b_kw': round(r.pdu_b_kw, 1),
            } for r in dc.server_racks],
            'crac_units': [{
                'id': c.id,
                'point_path': c._point_path,
                'name': c.name,
                'status': bool(c.get_effective_value('status')),
                'capacity_tons': c.capacity_tons,
                'supply_air_temp': round(params.convert_temp(c.get_effective_value('supply_air_temp')), 1),
                'return_air_temp': round(params.convert_temp(c.return_air_temp), 1),
                'cooling_output_pct': round(c.cooling_output_pct, 1),
                'fan_speed_pct': round(c.get_effective_value('fan_speed_pct'), 1),
                'kw': round(c.kw, 1),
            } for c in dc.crac_units],
            'ups_systems': [{
                'id': u.id,
                'name': u.name,
                'status': u.status,
                'load_pct': round(u.load_pct, 1),
                'battery_pct': round(u.battery_pct, 1),
                'battery_runtime_min': round(u.battery_runtime_min, 1),
            } for u in dc.ups_systems]
        })
    
    @app.route('/api/buildings')
    @api_login_required
    def get_buildings():
        """Get all buildings summary."""
        eng = app.config['engine']
        params = get_simulation_parameters()
        buildings = []
        for bldg in eng.buildings:
            buildings.append({
                'id': bldg.id,
                'name': bldg.name,
                'display_name': bldg.display_name,
                'device_instance': bldg.device_instance,
                'floor_count': bldg.floor_count,
                'square_footage': round(params.convert_area(bldg.square_footage), 0),
                'num_ahus': len(bldg.ahus),
                'num_vavs': bldg.vav_count,
                'num_oa_ahus': bldg.oa_ahu_count
            })
        return jsonify(buildings)
    
    @app.route('/api/buildings/<int:building_id>')
    @api_login_required
    def get_building(building_id: int):
        """Get detailed building data."""
        eng = app.config['engine']
        params = get_simulation_parameters()
        for bldg in eng.buildings:
            if bldg.id == building_id:
                ahus = []
                for ahu in bldg.ahus:
                    vavs = []
                    for vav in ahu.vavs:
                        vavs.append({
                            'id': vav.id,
                            'point_path': vav._point_path,
                            'name': vav.name,
                            'zone_name': vav.zone_name,
                            'room_temp': round(params.convert_temp(vav.room_temp), 2),
                            'discharge_air_temp': round(params.convert_temp(vav.discharge_air_temp), 2),
                            'cooling_setpoint': round(params.convert_temp(vav.get_effective_value('cooling_setpoint')), 2),
                            'heating_setpoint': round(params.convert_temp(vav.get_effective_value('heating_setpoint')), 2),
                            'damper_position': round(vav.damper_position, 2),
                            'cfm_max': round(params.convert_flow_air(vav.cfm_max), 0),
                            'cfm_min': round(params.convert_flow_air(vav.cfm_min), 0),
                            'cfm_actual': round(params.convert_flow_air(vav.cfm_actual), 0),
                            'reheat_valve': round(vav.reheat_valve, 2),
                            'occupancy': vav.occupancy
                        })
                    ahus.append({
                        'id': ahu.id,
                        'point_path': ahu._point_path,
                        'name': ahu.name,
                        'ahu_type': ahu.ahu_type,
                        'supply_temp': round(params.convert_temp(ahu.supply_temp), 2),
                        'supply_temp_setpoint': round(params.convert_temp(ahu.get_effective_value('supply_temp_setpoint')), 2),
                        'fan_status': ahu.fan_status,
                        'fan_speed': round(ahu.fan_speed, 2),
                        'return_temp': round(params.convert_temp(ahu.return_temp), 2),
                        'mixed_air_temp': round(params.convert_temp(ahu.mixed_air_temp), 2),
                        'outside_air_damper': round(ahu.outside_air_damper, 2),
                        'filter_dp': round(params.convert_pressure_wc(ahu.filter_dp), 2),
                        'cooling_valve': round(ahu.cooling_valve, 2),
                        'heating_valve': round(ahu.heating_valve, 2),
                        'vavs': vavs
                    })
                return jsonify({
                    'id': bldg.id,
                    'name': bldg.name,
                    'display_name': bldg.display_name,
                    'device_instance': bldg.device_instance,
                    'floor_count': bldg.floor_count,
                    'square_footage': round(params.convert_area(bldg.square_footage), 0),
                    'ahus': ahus
                })
        return jsonify({'error': 'Building not found'}), 404
    
    @app.route('/api/buildings/<int:building_id>/ahus/<int:ahu_id>')
    @api_login_required
    def get_ahu(building_id: int, ahu_id: int):
        """Get detailed AHU data."""
        eng = app.config['engine']
        for bldg in eng.buildings:
            if bldg.id == building_id:
                for ahu in bldg.ahus:
                    if ahu.id == ahu_id:
                        vavs = [{
                            'id': vav.id,
                            'name': vav.name,
                            'room_temp': round(vav.room_temp, 2),
                            'discharge_air_temp': round(vav.discharge_air_temp, 2),
                            'cooling_setpoint': round(vav.get_effective_value('cooling_setpoint'), 2),
                            'heating_setpoint': round(vav.get_effective_value('heating_setpoint'), 2),
                            'damper_position': round(vav.damper_position, 2),
                            'cfm_actual': round(vav.cfm_actual, 0),
                            'reheat_valve': round(vav.reheat_valve, 2),
                            'occupancy': vav.occupancy
                        } for vav in ahu.vavs]
                        return jsonify({
                            'id': ahu.id,
                            'name': ahu.name,
                            'supply_temp': round(ahu.supply_temp, 2),
                            'fan_status': ahu.fan_status,
                            'vavs': vavs
                        })
        return jsonify({'error': 'AHU not found'}), 404
    
    @app.route('/api/buildings/<int:building_id>/ahus/<int:ahu_id>/vavs/<int:vav_id>', 
               methods=['GET', 'PATCH'])
    @api_login_required
    def vav_endpoint(building_id: int, ahu_id: int, vav_id: int):
        """Get or update VAV data."""
        eng = app.config['engine']
        
        # Find the VAV
        target_vav = None
        for bldg in eng.buildings:
            if bldg.id == building_id:
                for ahu in bldg.ahus:
                    if ahu.id == ahu_id:
                        for vav in ahu.vavs:
                            if vav.id == vav_id:
                                target_vav = vav
                                break
        
        if not target_vav:
            return jsonify({'error': 'VAV not found'}), 404
        
        if request.method == 'PATCH':
            # Only admins can modify setpoints
            if current_user.role != 'admin':
                return jsonify({'error': 'Admin access required to modify setpoints'}), 403
            
            # Update setpoints if provided
            data = request.get_json()
            if 'cooling_setpoint' in data:
                target_vav.cooling_setpoint = float(data['cooling_setpoint'])
                logger.info(f"User '{current_user.username}' updated VAV {vav_id} cooling setpoint to {target_vav.cooling_setpoint}")
            if 'heating_setpoint' in data:
                target_vav.heating_setpoint = float(data['heating_setpoint'])
                logger.info(f"User '{current_user.username}' updated VAV {vav_id} heating setpoint to {target_vav.heating_setpoint}")
        
        return jsonify({
            'id': target_vav.id,
            'name': target_vav.name,
            'room_temp': round(target_vav.room_temp, 2),
            'discharge_air_temp': round(target_vav.discharge_air_temp, 2),
            'cooling_setpoint': round(target_vav.get_effective_value('cooling_setpoint'), 2),
            'heating_setpoint': round(target_vav.get_effective_value('heating_setpoint'), 2),
            'damper_position': round(target_vav.damper_position, 2),
            'cfm_actual': round(target_vav.cfm_actual, 0),
            'reheat_valve': round(target_vav.reheat_valve, 2),
            'occupancy': target_vav.occupancy
        })
    
    @app.route('/api/points')
    @api_login_required
    def get_all_points():
        """Get all points as flat list (for integration)."""
        eng = app.config['engine']
        return jsonify(eng.get_all_points())
    
    @app.route('/api/user')
    @api_login_required
    def get_current_user():
        """Get current user info."""
        return jsonify({
            'username': current_user.username,
            'role': current_user.role
        })
    
    # --- Admin Configuration Routes ---
    
    def admin_required(f):
        """Decorator for admin-only routes."""
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated:
                return jsonify({'error': 'Authentication required'}), 401
            if current_user.role != 'admin':
                return jsonify({'error': 'Admin access required'}), 403
            return f(*args, **kwargs)
        return decorated
    
    @app.route('/admin')
    @app.route('/admin/')
    @login_required
    def admin_page():
        """Redirect to config page."""
        return redirect(url_for('admin_config'))

    @app.route('/admin/config')
    @login_required
    def admin_config():
        """Render admin configuration page."""
        if current_user.role != 'admin':
            flash('Admin access required', 'error')
            return redirect(url_for('index'))
        return render_template('admin.html', user=current_user, active_page='config')

    @app.route('/admin/simulation')
    @login_required
    def admin_simulation():
        """Render admin simulation parameters page."""
        if current_user.role != 'admin':
            flash('Admin access required', 'error')
            return redirect(url_for('index'))
        return render_template('admin.html', user=current_user, active_page='simulation')

    @app.route('/admin/profiles')
    @login_required
    def admin_profiles():
        """Render admin device profiles page."""
        if current_user.role != 'admin':
            flash('Admin access required', 'error')
            return redirect(url_for('index'))
        return render_template('admin.html', user=current_user, active_page='profiles')

    @app.route('/admin/profiles/<profile_id>')
    @login_required
    def admin_profile_detail(profile_id):
        """Render admin device profiles page with specific profile selected."""
        if current_user.role != 'admin':
            flash('Admin access required', 'error')
            return redirect(url_for('index'))
            
        # Resolve profile ID case-insensitively
        from profiles import PROFILES
        resolved_id = profile_id
        for pid in PROFILES.keys():
            if pid.lower() == profile_id.lower():
                resolved_id = pid
                break
                
        return render_template('admin.html', user=current_user, active_page='profiles', active_profile=resolved_id)
    
    @app.route('/api/admin/config', methods=['GET'])
    @admin_required
    def get_config():
        """Get current campus configuration."""
        eng = app.config['engine']
        return jsonify(eng.get_config())
    
    @app.route('/api/admin/config', methods=['POST'])
    @admin_required
    def update_config():
        """Update campus configuration."""
        eng = app.config['engine']
        data = request.get_json()
        
        try:
            new_config = eng.reconfigure(
                num_buildings=data.get('num_buildings'),
                num_ahus=data.get('num_ahus'),
                num_vavs=data.get('num_vavs'),
                latitude=data.get('latitude'),
                longitude=data.get('longitude'),
                location_name=data.get('location_name'),
                simulation_speed=data.get('simulation_speed'),
                seed=data.get('seed'),
                building_names=data.get('building_names'),
                campus_type=data.get('campus_type')
            )
            logger.info(f"Admin '{current_user.username}' updated campus config")
            return jsonify({'success': True, 'config': new_config})
        except Exception as e:
            logger.error(f"Config update failed: {e}")
            return jsonify({'error': str(e)}), 400
            
    @app.route('/api/admin/scenario', methods=['POST'])
    @admin_required
    def trigger_scenario():
        """Trigger a simulation scenario."""
        eng = app.config['engine']
        data = request.get_json()
        
        # Handle auto-frequency update
        auto_frequency = data.get('auto_frequency')
        if auto_frequency is not None:
            try:
                eng._scenario_manager._auto_change_frequency = int(auto_frequency)
                return jsonify({'success': True, 'message': f"Auto-scenario frequency set to {auto_frequency}s"})
            except ValueError:
                return jsonify({'error': 'Invalid frequency value'}), 400

        scenario_name = data.get('scenario')
        duration = int(data.get('duration', 300))
        
        if not scenario_name:
            return jsonify({'error': 'Scenario name required'}), 400
            
        result = eng.trigger_scenario(scenario_name, duration)
        logger.info(f"Admin '{current_user.username}' triggered scenario: {scenario_name}")
        return jsonify({'message': result})
    
    @app.route('/api/admin/date', methods=['POST'])
    @admin_required
    def set_date():
        """Set the simulation date."""
        eng = app.config['engine']
        data = request.get_json()
        
        date_str = data.get('date')
        if not date_str:
            return jsonify({'error': 'Date required'}), 400
            
        try:
            # Parse date string (expected format: YYYY-MM-DDTHH:MM)
            new_date = datetime.fromisoformat(date_str)
            eng.set_simulation_date(new_date)
            logger.info(f"Admin '{current_user.username}' set simulation date to {new_date}")
            return jsonify({'success': True, 'message': f"Date set to {new_date}"})
        except ValueError as e:
            return jsonify({'error': f'Invalid date format: {e}'}), 400

    @app.route('/api/admin/generate', methods=['POST'])
    @admin_required
    def generate_random():
        """Generate random configuration from seed."""
        data = request.get_json()
        seed = data.get('seed', '')
        
        # Generate random config
        random_config = generate_random_config(seed if seed else None)
        
        # Apply it
        eng = app.config['engine']
        new_config = eng.reconfigure(
            num_buildings=random_config['num_buildings'],
            num_ahus=random_config['num_ahus'],
            num_vavs=random_config['num_vavs'],
            latitude=random_config['latitude'],
            longitude=random_config['longitude'],
            location_name=random_config['location_name'],
            simulation_speed=random_config['simulation_speed'],
            seed=seed
        )
        
        logger.info(f"Admin '{current_user.username}' generated random campus with seed '{seed}': {new_config}")
        return jsonify({'success': True, 'config': new_config})
    
    @app.route('/api/admin/locations')
    @admin_required
    def get_locations():
        """Get list of available world locations."""
        return jsonify(WORLD_LOCATIONS)
    
    @app.route('/api/admin/export', methods=['GET'])
    @admin_required
    def export_campus():
        """
        Export the full campus configuration as a JSON file.
        Includes all settings needed to recreate the campus.
        """
        eng = app.config['engine']
        config = eng.get_config()
        
        # Build the export data structure
        export_data = {
            'version': '1.1',
            'exported_at': datetime.now().isoformat(),
            'exported_by': current_user.username,
            'config': {
                'num_buildings': config['num_buildings'],
                'num_ahus': config['num_ahus'],
                'num_vavs': config['num_vavs'],
                'latitude': config['latitude'],
                'longitude': config['longitude'],
                'location_name': config['location_name'],
                'simulation_speed': config['simulation_speed'],
                'seed': config['seed'],
            },
            'building_names': [b['display_name'] for b in config.get('buildings', [])],
        }
        
        # Get current overrides
        from models import get_override_manager, get_simulation_parameters
        manager = get_override_manager()
        overrides = manager.get_all_overrides()
        export_data['overrides'] = overrides
        
        # Get simulation parameters
        sim_params = get_simulation_parameters()
        export_data['simulation_parameters'] = sim_params.export()
        
        logger.info(f"Admin '{current_user.username}' exported campus configuration")
        
        response = Response(
            json.dumps(export_data, indent=2),
            mimetype='application/json',
            headers={'Content-Disposition': f'attachment; filename=basim-campus-{datetime.now().strftime("%Y%m%d-%H%M%S")}.json'}
        )
        return response
    
    @app.route('/api/admin/import', methods=['POST'])
    @admin_required
    def import_campus():
        """
        Import a campus configuration from JSON.
        Recreates the campus with all saved settings.
        """
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Validate version
        version = data.get('version', '1.0')
        if version not in ['1.0', '1.1']:
            return jsonify({'error': f'Unsupported file version: {version}'}), 400
        
        config = data.get('config', {})
        building_names = data.get('building_names', [])
        overrides = data.get('overrides', {})
        simulation_parameters = data.get('simulation_parameters', {})
        
        try:
            eng = app.config['engine']
            
            # Apply the configuration
            new_config = eng.reconfigure(
                num_buildings=config.get('num_buildings'),
                num_ahus=config.get('num_ahus'),
                num_vavs=config.get('num_vavs'),
                latitude=config.get('latitude'),
                longitude=config.get('longitude'),
                location_name=config.get('location_name'),
                simulation_speed=config.get('simulation_speed'),
                seed=config.get('seed'),
                building_names=building_names if building_names else None
            )
            
            # Restore overrides
            from models import get_override_manager, get_simulation_parameters
            manager = get_override_manager()
            
            override_count = 0
            for point_path, priorities in overrides.items():
                for priority_str, override_info in priorities.items():
                    priority = int(priority_str)
                    manager.set_override(
                        point_path=point_path,
                        value=override_info['value'],
                        priority=priority,
                        source=f"imported by {current_user.username}"
                    )
                    override_count += 1
            
            # Restore simulation parameters (v1.1+)
            params_count = 0
            if simulation_parameters:
                sim_params = get_simulation_parameters()
                params_count = sim_params.import_params(simulation_parameters)
            
            logger.info(f"Admin '{current_user.username}' imported campus configuration with {override_count} overrides and {params_count} simulation parameters")
            return jsonify({
                'success': True,
                'config': new_config,
                'overrides_restored': override_count,
                'parameters_restored': params_count
            })
            
        except Exception as e:
            logger.error(f"Campus import failed: {e}")
            return jsonify({'error': str(e)}), 400
    
    # --- Simulation Parameters API ---
    
    @app.route('/api/admin/simulation-params', methods=['GET'])
    @admin_required
    def get_simulation_params():
        """Get all simulation parameters with current values and metadata."""
        from models import get_simulation_parameters
        params = get_simulation_parameters()
        return jsonify({
            'parameters': params.get_all(),
            'by_category': params.get_by_category()
        })
    
    @app.route('/api/admin/simulation-params', methods=['POST'])
    @admin_required
    def update_simulation_params():
        """Update simulation parameters."""
        from models import get_simulation_parameters
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        params = get_simulation_parameters()
        results = params.set_multiple(data)
        
        success_count = sum(1 for v in results.values() if v)
        logger.info(f"Admin '{current_user.username}' updated {success_count} simulation parameters")
        
        return jsonify({
            'success': True,
            'results': results,
            'updated_count': success_count
        })

    @app.route('/api/admin/units', methods=['GET', 'POST'])
    @login_required
    def handle_units():
        params = get_simulation_parameters()
        if request.method == 'POST':
            if not current_user.role == 'admin':
                return jsonify({'error': 'Unauthorized'}), 403
            
            data = request.json
            new_unit = data.get('unit_system')
            if new_unit in ['US', 'Metric']:
                params.unit_system = new_unit
                return jsonify({'success': True, 'unit_system': params.unit_system})
            return jsonify({'error': 'Invalid unit system'}), 400
            
        return jsonify({'unit_system': params.unit_system})

    @app.route('/api/admin/campus', methods=['GET', 'POST'])
    @login_required
    def handle_campus_name():
        params = get_simulation_parameters()
        if request.method == 'POST':
            if not current_user.role == 'admin':
                return jsonify({'error': 'Unauthorized'}), 403
            
            data = request.json
            new_name = data.get('campus_name')
            if new_name:
                params.campus_name = new_name
                return jsonify({'success': True, 'campus_name': params.campus_name})
            return jsonify({'error': 'Invalid campus name'}), 400
            
        return jsonify({'campus_name': params.campus_name})
    
    @app.route('/api/admin/simulation-params/reset', methods=['POST'])
    @admin_required
    def reset_simulation_params():
        """Reset simulation parameters to defaults."""
        from models import get_simulation_parameters
        data = request.get_json() or {}
        key = data.get('key')  # Optional: reset specific key
        
        params = get_simulation_parameters()
        params.reset(key)
        
        if key:
            logger.info(f"Admin '{current_user.username}' reset simulation parameter '{key}' to default")
        else:
            logger.info(f"Admin '{current_user.username}' reset all simulation parameters to defaults")
        
        return jsonify({
            'success': True,
            'parameters': params.get_all()
        })

    @app.route('/api/admin/profiles', methods=['GET'])
    @login_required
    def get_profiles():
        """Get available controller profiles."""
        logger.info(f"API Request: get_profiles by {current_user.username}")
        from profiles import PROFILES
        # Convert to list of dicts for JSON
        profiles_list = []
        for key, p in PROFILES.items():
            profiles_list.append({
                'id': key,
                'name': p.name,
                'manufacturer': p.manufacturer,
                'description': p.description,
                'naming_convention': p.naming_convention,
                'device_types': p.device_definitions or {},
                'config_file': p.config_file,
                'protocols': p.protocols
            })
        
        # Sort alphabetically by name
        profiles_list.sort(key=lambda x: x['name'])
        
        logger.info(f"Returning {len(profiles_list)} profiles. First: {profiles_list[0]['name']} with {len(profiles_list[0]['device_types'])} device types")
        return jsonify(profiles_list)

    @app.route('/api/admin/profiles/<profile_id>', methods=['POST'])
    @login_required
    def update_profile(profile_id):
        """Update profile metadata (description, protocols)."""
        from profiles import PROFILES, save_profile
        
        if profile_id not in PROFILES:
            return jsonify({'error': 'Profile not found'}), 404
            
        profile = PROFILES[profile_id]
        data = request.get_json()
        
        if 'description' in data:
            profile.description = data['description']
            
        if 'protocols' in data:
            profile.protocols = data['protocols']
            
        if save_profile(profile):
            return jsonify({'success': True, 'message': f'Updated {profile.name}'})
        else:
            return jsonify({'error': 'Failed to save profile'}), 500

    @app.route('/api/admin/profiles/<profile_id>/device-types', methods=['POST'])
    @login_required
    def add_device_type(profile_id):
        """Add a new device type to a profile."""
        from profiles import PROFILES, save_profile
        
        if profile_id not in PROFILES:
            return jsonify({'error': 'Profile not found'}), 404
            
        data = request.get_json()
        device_type = data.get('device_type')
        description = data.get('description', '')
        
        if not device_type:
            return jsonify({'error': 'Device type name is required'}), 400
            
        profile = PROFILES[profile_id]
        
        if device_type in profile.device_definitions:
            return jsonify({'error': 'Device type already exists'}), 400
            
        # Initialize new device type structure
        profile.device_definitions[device_type] = {
            'description': description,
            'defaults': {},
            'points': {}
        }
        
        if save_profile(profile):
            return jsonify({'success': True, 'message': f'Added {device_type} to {profile.name}'})
        else:
            return jsonify({'error': 'Failed to save profile'}), 500

    @app.route('/api/admin/profiles/<profile_id>/device-types/<device_type_id>', methods=['PUT'])
    @login_required
    def update_device_type(profile_id, device_type_id):
        """Update an existing device type in a profile."""
        from profiles import PROFILES, save_profile
        
        if profile_id not in PROFILES:
            return jsonify({'error': 'Profile not found'}), 404
            
        profile = PROFILES[profile_id]
        
        if device_type_id not in profile.device_definitions:
            return jsonify({'error': 'Device type not found'}), 404
            
        data = request.get_json()
        description = data.get('description')
        points = data.get('points')
        
        if description is not None:
            profile.device_definitions[device_type_id]['description'] = description
            
        if points is not None:
            # Validate points structure if necessary
            profile.device_definitions[device_type_id]['points'] = points
            
        if save_profile(profile):
            return jsonify({'success': True, 'message': f'Updated {device_type_id} in {profile.name}'})
        else:
            return jsonify({'error': 'Failed to save profile'}), 500

    @app.route('/api/admin/profiles/<profile_id>/yaml', methods=['GET'])
    @login_required
    def get_profile_yaml(profile_id):
        """Get raw YAML content for a profile."""
        from profiles import PROFILES
        import os
        
        if profile_id not in PROFILES:
            return jsonify({'error': 'Profile not found'}), 404
            
        profile = PROFILES[profile_id]
        
        # Construct full path
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(base_dir, 'profiles', profile.config_file)
        
        if not profile.config_file or not os.path.exists(config_path):
            return jsonify({'error': 'Config file not found'}), 404
            
        try:
            with open(config_path, 'r') as f:
                content = f.read()
            return jsonify({'yaml': content})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/admin/profiles/<profile_id>/yaml', methods=['POST'])
    @login_required
    def save_profile_yaml(profile_id):
        """Save raw YAML content for a profile."""
        from profiles import PROFILES, load_profiles
        import os
        import yaml
        
        if profile_id not in PROFILES:
            return jsonify({'error': 'Profile not found'}), 404
            
        profile = PROFILES[profile_id]
        if not profile.config_file:
            return jsonify({'error': 'No config file associated with this profile'}), 400
            
        # Construct full path
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(base_dir, 'profiles', profile.config_file)
            
        data = request.get_json()
        content = data.get('yaml')
        
        if content is None:
            return jsonify({'error': 'No content provided'}), 400
            
        # Validate YAML
        try:
            yaml.safe_load(content)
        except yaml.YAMLError as e:
            return jsonify({'error': f'Invalid YAML: {str(e)}'}), 400
            
        try:
            with open(config_path, 'w') as f:
                f.write(content)
            
            # Reload profiles to apply changes
            load_profiles()
            
            return jsonify({'success': True, 'message': 'Profile updated successfully'})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/admin/controllers', methods=['GET'])
    @login_required
    def get_controllers():
        """Get available controllers."""
        from profiles import CONTROLLERS, load_controllers
        
        # Ensure loaded
        if not CONTROLLERS:
            load_controllers()
            
        controllers_list = []
        for key, c in CONTROLLERS.items():
            controllers_list.append({
                'name': c.name,
                'manufacturer': c.manufacturer,
                'description': c.description,
                'inputs': c.inputs,
                'outputs': c.outputs
            })
            
        # Sort by manufacturer then name
        controllers_list.sort(key=lambda x: (x['manufacturer'], x['name']))
        return jsonify(controllers_list)

    @app.route('/api/admin/controllers', methods=['POST'])
    @login_required
    def save_controller_api():
        """Save or update a controller."""
        from profiles import save_controller
        
        data = request.get_json()
        name = data.get('name')
        manufacturer = data.get('manufacturer')
        description = data.get('description', '')
        inputs = int(data.get('inputs', 0))
        outputs = int(data.get('outputs', 0))
        
        if not name or not manufacturer:
            return jsonify({'error': 'Name and Manufacturer are required'}), 400
            
        success = save_controller(name, manufacturer, description, inputs, outputs)
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Failed to save controller'}), 500

    @app.route('/api/admin/controllers/<model_name>', methods=['DELETE'])
    @login_required
    def delete_controller_api(model_name):
        """Delete a controller."""
        from profiles import delete_controller
        
        success = delete_controller(model_name)
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Failed to delete controller'}), 500

    
    # --- Override Management API ---
    
    @app.route('/api/overrides')
    @api_login_required
    def get_overrides():
        """Get all active overrides."""
        from models import get_override_manager
        manager = get_override_manager()
        overrides = manager.get_all_overrides()
        return jsonify({
            'overrides': overrides,
            'count': len(overrides)
        })
    
    @app.route('/api/override/set', methods=['POST'])
    @admin_required
    def set_override():
        """
        Set an override on a point.
        
        Request body:
        {
            "point_path": "Building_1.AHU_1.VAV_1.setpoint",
            "value": 72.0,
            "priority": 8,  // optional, 1-16 (lower = higher priority)
            "duration_seconds": 3600  // optional, null for permanent
        }
        """
        from models import get_override_manager
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body required'}), 400
        
        point_path = data.get('point_path')
        value = data.get('value')
        
        if not point_path:
            return jsonify({'error': 'point_path is required'}), 400
        if value is None:
            return jsonify({'error': 'value is required'}), 400
        
        try:
            value = float(value)
        except (ValueError, TypeError):
            return jsonify({'error': 'value must be a number'}), 400
        
        priority = data.get('priority', 8)
        duration = data.get('duration_seconds')
        
        try:
            priority = int(priority)
            if priority < 1 or priority > 16:
                return jsonify({'error': 'priority must be between 1 and 16'}), 400
        except (ValueError, TypeError):
            return jsonify({'error': 'priority must be an integer'}), 400
        
        if duration is not None:
            try:
                duration = int(duration)
            except (ValueError, TypeError):
                return jsonify({'error': 'duration_seconds must be an integer'}), 400
        
        manager = get_override_manager()
        source = f"user:{current_user.username}"
        
        success = manager.set_override(
            point_path=point_path,
            value=value,
            priority=priority,
            duration_seconds=duration,
            source=source
        )
        
        if success:
            logger.info(f"Override set by {current_user.username}: {point_path} = {value}")
            return jsonify({
                'success': True,
                'point_path': point_path,
                'value': value,
                'priority': priority,
                'duration_seconds': duration
            })
        else:
            return jsonify({'error': 'Failed to set override'}), 500
    
    @app.route('/api/override/release', methods=['POST'])
    @admin_required
    def release_override():
        """
        Release an override on a point.
        
        Request body:
        {
            "point_path": "Building_1.AHU_1.VAV_1.setpoint",
            "priority": 8  // optional, null to release all priorities
        }
        """
        from models import get_override_manager
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body required'}), 400
        
        point_path = data.get('point_path')
        if not point_path:
            return jsonify({'error': 'point_path is required'}), 400
        
        priority = data.get('priority')
        if priority is not None:
            try:
                priority = int(priority)
            except (ValueError, TypeError):
                return jsonify({'error': 'priority must be an integer'}), 400
        
        manager = get_override_manager()
        success = manager.release_override(point_path, priority)
        
        if success:
            logger.info(f"Override released by {current_user.username}: {point_path}")
            return jsonify({
                'success': True,
                'point_path': point_path,
                'released': True
            })
        else:
            return jsonify({
                'success': False,
                'point_path': point_path,
                'message': 'No override found for this point'
            })
    
    @app.route('/api/override/info/<path:point_path>')
    @api_login_required
    def get_override_info(point_path):
        """Get detailed override info for a specific point."""
        from models import get_override_manager
        manager = get_override_manager()
        info = manager.get_point_override_info(point_path)
        
        if info:
            return jsonify({
                'point_path': point_path,
                'overridden': True,
                'overrides': info
            })
        else:
            return jsonify({
                'point_path': point_path,
                'overridden': False
            })
    
    # --- Protocol Integration Page ---
    
    @app.route('/protocols')
    @login_required
    def protocols_page():
        """Render protocol integration info page."""
        return render_template('protocols.html', user=current_user)
    
    @app.route('/topology')
    @login_required
    def topology_page():
        """Render network topology / riser diagram page."""
        return render_template('topology.html', user=current_user)
    

    
    @app.route('/api/protocols')
    @api_login_required
    def get_protocols():
        """Get protocol server connection information."""
        eng = app.config['engine']
        
        # Get hostname for connection info
        hostname = request.host.split(':')[0]
        if hostname in ('localhost', '127.0.0.1'):
            hostname = 'localhost'
        
        # Build point list from engine
        points = []
        
        # Add campus-level points
        points.append({
            'name': 'Campus_OAT',
            'description': 'Outside Air Temperature',
            'unit': '°F',
            'type': 'float',
            'writable': False,
            'modbus_register': 0,
            'bacnet_object': 'AV:1'
        })
        
        register_counter = 1
        bacnet_counter = 2
        
        for bldg in eng.buildings:
            for ahu in bldg.ahus:
                # AHU points
                if hasattr(ahu, 'get_point_definitions'):
                    for p_def in ahu.get_point_definitions():
                        points.append({
                            'name': f'{bldg.name}_{ahu.name}_{p_def.name}',
                            'description': p_def.description or f'{bldg.display_name} {ahu.name} {p_def.name}',
                            'unit': p_def.units,
                            'type': 'float',
                            'writable': p_def.writable,
                            'modbus_register': register_counter,
                            'bacnet_object': f'{p_def.bacnet_object_type}:{bacnet_counter}'
                        })
                        register_counter += 1
                        bacnet_counter += 1
                
                for vav in ahu.vavs:
                    # VAV points
                    if hasattr(vav, 'get_point_definitions'):
                        for p_def in vav.get_point_definitions():
                            points.append({
                                'name': f'{bldg.name}_{ahu.name}_{vav.name}_{p_def.name}',
                                'description': p_def.description or f'{vav.zone_name} {p_def.name}',
                                'unit': p_def.units,
                                'type': 'float',
                                'writable': p_def.writable,
                                'modbus_register': register_counter,
                                'bacnet_object': f'{p_def.bacnet_object_type}:{bacnet_counter}'
                            })
                            register_counter += 1
                            bacnet_counter += 1
        
        # Build BACnet network topology
        # Each building gets a BACnet/IP device, each AHU gets an MS/TP controller
        bacnet_devices = []
        bacnet_networks = []
        
        # Network 1: BACnet/IP backbone
        ip_network = {
            'network_number': 1,
            'network_type': 'BACnet/IP',
            'description': 'IP backbone network',
            'subnet': f'{hostname}/24',
            'bbmd': f'{hostname}:47808',
            'devices': []
        }
        
        # Campus Gateway Router (bridges all networks)
        gateway_device = {
            'device_id': 9999,
            'device_name': 'BASim-Router',
            'device_type': 'Router/Gateway',
            'vendor': 'BASim',
            'model': 'BASIM-RTR-1000',
            'network_type': 'BACnet/IP',
            'network_number': 1,
            'mac_address': f'{hostname}:47808',
            'ip_address': hostname,
            'port': 47808,
            'description': 'Main BACnet router - bridges IP, MS/TP, and SC networks',
            'routed_networks': [1, 2, 3, 100],
            'objects': [
                {'type': 'AV', 'instance': 1, 'name': 'Campus_OAT', 'description': 'Outside Air Temperature'}
            ]
        }
        bacnet_devices.append(gateway_device)
        ip_network['devices'].append(9999)
        
        # Central Plant Controller (BACnet/IP)
        plant_device = {
            'device_id': 1000,
            'device_name': 'CentralPlant-BAS',
            'device_type': 'Building Controller',
            'vendor': 'BASim',
            'model': 'BASIM-BC-500',
            'network_type': 'BACnet/IP',
            'network_number': 1,
            'mac_address': f'{hostname}:47809',
            'ip_address': hostname,
            'port': 47809,
            'description': 'Central plant supervisory controller',
            'objects': []
        }
        
        # Add plant objects
        plant_obj_counter = 1
        plant_device['objects'].extend([
            {'type': 'AI', 'instance': plant_obj_counter, 'name': 'CHW_Supply_Temp', 'description': 'Chilled Water Supply'},
            {'type': 'AI', 'instance': plant_obj_counter + 1, 'name': 'CHW_Return_Temp', 'description': 'Chilled Water Return'},
            {'type': 'AI', 'instance': plant_obj_counter + 2, 'name': 'HW_Supply_Temp', 'description': 'Hot Water Supply'},
            {'type': 'AI', 'instance': plant_obj_counter + 3, 'name': 'HW_Return_Temp', 'description': 'Hot Water Return'},
            {'type': 'AO', 'instance': 1, 'name': 'CHW_Setpoint', 'description': 'CHW Supply Setpoint'},
            {'type': 'AO', 'instance': 2, 'name': 'HW_Setpoint', 'description': 'HW Supply Setpoint'},
            {'type': 'BO', 'instance': 1, 'name': 'Chiller_1_Enable', 'description': 'Chiller 1 Enable Command'},
            {'type': 'BI', 'instance': 1, 'name': 'Chiller_1_Status', 'description': 'Chiller 1 Run Status'},
        ])
        bacnet_devices.append(plant_device)
        ip_network['devices'].append(1000)
        
        # Electrical System Controller (BACnet/SC - Secure Connect)
        sc_network = {
            'network_number': 100,
            'network_type': 'BACnet/SC',
            'description': 'Secure Connect network for cloud/remote access',
            'hub_uri': f'wss://{hostname}/bacnet-sc',
            'security': 'TLS 1.3, Certificate-based authentication',
            'devices': []
        }
        
        elec_device = {
            'device_id': 5000,
            'device_name': 'Electrical-Monitor',
            'device_type': 'Power Monitor',
            'vendor': 'BASim',
            'model': 'BASIM-PWR-100',
            'network_type': 'BACnet/SC',
            'network_number': 100,
            'hub_connection': f'wss://{hostname}/bacnet-sc',
            'uuid': 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
            'description': 'Electrical metering and monitoring (secure cloud connection)',
            'objects': [
                {'type': 'AI', 'instance': 1, 'name': 'Main_Meter_kW', 'description': 'Main Meter Power'},
                {'type': 'AI', 'instance': 2, 'name': 'Main_Meter_kWh', 'description': 'Main Meter Energy'},
                {'type': 'AI', 'instance': 3, 'name': 'Solar_Production_kW', 'description': 'Solar Production'},
                {'type': 'AI', 'instance': 4, 'name': 'Grid_Import_kW', 'description': 'Grid Import Power'},
                {'type': 'BI', 'instance': 1, 'name': 'Generator_Status', 'description': 'Emergency Generator Running'},
                {'type': 'BO', 'instance': 1, 'name': 'Generator_Enable', 'description': 'Emergency Generator Start'},
            ]
        }
        bacnet_devices.append(elec_device)
        sc_network['devices'].append(5000)
        
        # MS/TP Networks (one per building)
        mstp_networks = []
        building_device_base = 2000
        ahu_device_base = 3000
        vav_device_base = 10000
        
        for bldg_idx, bldg in enumerate(eng.buildings):
            # Create MS/TP network for this building
            mstp_net_num = 2 + bldg_idx
            mstp_network = {
                'network_number': mstp_net_num,
                'network_type': 'BACnet MS/TP',
                'description': f'{bldg.display_name} field bus',
                'baud_rate': 76800,
                'max_master': 127,
                'max_info_frames': 1,
                'router_mac': 0,
                'devices': []
            }
            
            # Building Controller (MS/TP master, also has IP)
            bldg_device_id = building_device_base + bldg.id
            
            # Determine vendor/model from profile
            vendor = 'BASim'
            model = 'BASIM-BC-200'
            if hasattr(bldg, 'profile') and bldg.profile:
                vendor = bldg.profile.manufacturer
                model = f"{bldg.profile.name} BC-200"
            
            bldg_device = {
                'device_id': bldg_device_id,
                'device_name': f'{bldg.name}-BAS',
                'device_type': 'Building Controller',
                'vendor': vendor,
                'model': model,
                'network_type': 'BACnet/IP + MS/TP',
                'network_number': 1,
                'mstp_network': mstp_net_num,
                'mstp_mac': 0,
                'mac_address': f'{hostname}:{47810 + bldg_idx}',
                'ip_address': hostname,
                'port': 47810 + bldg_idx,
                'description': f'{bldg.display_name} supervisory controller (routes to MS/TP network {mstp_net_num})',
                'objects': [
                    {'type': 'AV', 'instance': 1, 'name': f'{bldg.name}_OAT', 'description': 'Local Outside Air Temp'},
                    {'type': 'AI', 'instance': 1, 'name': f'{bldg.name}_Demand_kW', 'description': 'Building Demand'},
                ]
            }
            bacnet_devices.append(bldg_device)
            ip_network['devices'].append(bldg_device_id)
            mstp_network['devices'].append(bldg_device_id)
            
            # AHU Controllers (MS/TP)
            for ahu_idx, ahu in enumerate(bldg.ahus):
                ahu_device_id = ahu_device_base + (bldg.id * 100) + ahu.id
                ahu_mac = ahu_idx + 1  # MS/TP MAC addresses 1-127
                
                # Determine vendor/model from profile
                vendor = 'BASim'
                model = 'BASIM-AHU-100'
                if hasattr(bldg, 'profile') and bldg.profile:
                    vendor = bldg.profile.manufacturer
                    model = f"{bldg.profile.name} AHU-100"
                
                ahu_device = {
                    'device_id': ahu_device_id,
                    'device_name': f'{bldg.name}-{ahu.name}',
                    'device_type': 'AHU Controller',
                    'vendor': vendor,
                    'model': model,
                    'network_type': 'BACnet MS/TP',
                    'network_number': mstp_net_num,
                    'mstp_mac': ahu_mac,
                    'max_master': 127,
                    'baud_rate': 76800,
                    'description': f'{ahu.name} ({ahu.ahu_type}) controller',
                    'objects': [
                        {'type': 'AI', 'instance': 1, 'name': 'Supply_Air_Temp', 'description': 'Supply Air Temperature'},
                        {'type': 'AI', 'instance': 2, 'name': 'Return_Air_Temp', 'description': 'Return Air Temperature'},
                        {'type': 'AI', 'instance': 3, 'name': 'Mixed_Air_Temp', 'description': 'Mixed Air Temperature'},
                        {'type': 'AO', 'instance': 1, 'name': 'Supply_Temp_Setpoint', 'description': 'Supply Temp Setpoint'},
                        {'type': 'AO', 'instance': 2, 'name': 'Fan_Speed_Cmd', 'description': 'Fan Speed Command'},
                        {'type': 'AO', 'instance': 3, 'name': 'OA_Damper_Cmd', 'description': 'Outside Air Damper'},
                        {'type': 'AO', 'instance': 4, 'name': 'Cooling_Valve_Cmd', 'description': 'Cooling Valve'},
                        {'type': 'AO', 'instance': 5, 'name': 'Heating_Valve_Cmd', 'description': 'Heating Valve'},
                        {'type': 'BI', 'instance': 1, 'name': 'Fan_Status', 'description': 'Supply Fan Status'},
                        {'type': 'BI', 'instance': 2, 'name': 'Filter_Alarm', 'description': 'Dirty Filter Alarm'},
                        {'type': 'BO', 'instance': 1, 'name': 'Fan_Enable', 'description': 'Supply Fan Enable'},
                        {'type': 'BV', 'instance': 1, 'name': 'Occ_Mode', 'description': 'Occupied Mode'},
                    ]
                }
                bacnet_devices.append(ahu_device)
                mstp_network['devices'].append(ahu_device_id)
                
                # VAV Controllers (MS/TP, addressed under AHU)
                for vav_idx, vav in enumerate(ahu.vavs):
                    vav_device_id = vav_device_base + (bldg.id * 1000) + (ahu.id * 100) + vav.id
                    vav_mac = 10 + (ahu_idx * 20) + vav_idx  # VAV MACs start at 10
                    
                    # Determine vendor/model from profile
                    vendor = 'BASim'
                    model = 'BASIM-VAV-50'
                    if hasattr(bldg, 'profile') and bldg.profile:
                        vendor = bldg.profile.manufacturer
                        model = f"{bldg.profile.name} VAV-50"
                    
                    vav_device = {
                        'device_id': vav_device_id,
                        'device_name': f'{bldg.name}-{ahu.name}-{vav.name}',
                        'device_type': 'VAV Controller',
                        'vendor': vendor,
                        'model': model,
                        'network_type': 'BACnet MS/TP',
                        'network_number': mstp_net_num,
                        'mstp_mac': vav_mac,
                        'max_master': 127,
                        'baud_rate': 76800,
                        'description': f'{vav.zone_name} VAV box controller',
                        'objects': [
                            {'type': 'AI', 'instance': 1, 'name': 'Room_Temp', 'description': 'Zone Temperature'},
                            {'type': 'AI', 'instance': 2, 'name': 'Discharge_Temp', 'description': 'Discharge Air Temp'},
                            {'type': 'AI', 'instance': 3, 'name': 'Airflow_CFM', 'description': 'Airflow'},
                            {'type': 'AO', 'instance': 1, 'name': 'Cooling_Setpoint', 'description': 'Cooling Setpoint'},
                            {'type': 'AO', 'instance': 2, 'name': 'Heating_Setpoint', 'description': 'Heating Setpoint'},
                            {'type': 'AO', 'instance': 3, 'name': 'Damper_Cmd', 'description': 'Damper Position Command'},
                            {'type': 'AO', 'instance': 4, 'name': 'Reheat_Cmd', 'description': 'Reheat Valve Command'},
                            {'type': 'BI', 'instance': 1, 'name': 'Occ_Sensor', 'description': 'Occupancy Sensor'},
                            {'type': 'BV', 'instance': 1, 'name': 'Occ_Override', 'description': 'Occupancy Override'},
                        ]
                    }
                    bacnet_devices.append(vav_device)
                    mstp_network['devices'].append(vav_device_id)
            
            mstp_networks.append(mstp_network)
        
        bacnet_networks = [ip_network, sc_network] + mstp_networks
        
        # Build Modbus network topology
        # Modbus TCP gateway routes to RTU devices on RS-485 networks
        modbus_devices = []
        modbus_networks = []
        
        # Modbus TCP Gateway (routes to RTU networks)
        tcp_gateway = {
            'unit_id': 1,
            'device_name': 'BASim-ModbusTCP-Gateway',
            'device_type': 'TCP/RTU Gateway',
            'vendor': 'BASim',
            'model': 'BASIM-MBTCP-GW100',
            'network_type': 'Modbus TCP',
            'ip_address': hostname,
            'port': 5020,
            'description': 'Modbus TCP to RTU gateway - bridges TCP to serial RS-485 networks',
            'routed_networks': [1, 2, 3],  # RTU network numbers
            'registers': [
                {'address': 0, 'name': 'Gateway_Status', 'type': 'HR', 'description': 'Gateway operational status'},
                {'address': 1, 'name': 'OAT_Raw', 'type': 'HR', 'description': 'Outside Air Temperature x100'},
                {'address': 2, 'name': 'RTU_Net1_Status', 'type': 'HR', 'description': 'RTU Network 1 comm status'},
                {'address': 3, 'name': 'RTU_Net2_Status', 'type': 'HR', 'description': 'RTU Network 2 comm status'},
            ]
        }
        modbus_devices.append(tcp_gateway)
        
        # Central Plant RTU Controller
        plant_rtu = {
            'unit_id': 10,
            'device_name': 'CentralPlant-RTU',
            'device_type': 'Plant Controller',
            'vendor': 'BASim',
            'model': 'BASIM-RTU-500',
            'network_type': 'Modbus RTU',
            'network_number': 1,
            'serial_port': '/dev/ttyRS485-1',
            'baud_rate': 19200,
            'parity': 'N',
            'data_bits': 8,
            'stop_bits': 1,
            'description': 'Central plant Modbus RTU controller',
            'registers': [
                {'address': 100, 'name': 'CHW_Supply_Temp', 'type': 'IR', 'description': 'Chilled water supply temp x100'},
                {'address': 101, 'name': 'CHW_Return_Temp', 'type': 'IR', 'description': 'Chilled water return temp x100'},
                {'address': 102, 'name': 'HW_Supply_Temp', 'type': 'IR', 'description': 'Hot water supply temp x100'},
                {'address': 103, 'name': 'HW_Return_Temp', 'type': 'IR', 'description': 'Hot water return temp x100'},
                {'address': 200, 'name': 'CHW_Setpoint', 'type': 'HR', 'description': 'CHW supply setpoint x100'},
                {'address': 201, 'name': 'HW_Setpoint', 'type': 'HR', 'description': 'HW supply setpoint x100'},
                {'address': 0, 'name': 'Chiller_1_Enable', 'type': 'CO', 'description': 'Chiller 1 enable coil'},
                {'address': 0, 'name': 'Chiller_1_Status', 'type': 'DI', 'description': 'Chiller 1 running status'},
            ]
        }
        modbus_devices.append(plant_rtu)
        
        # Power Meter RTU
        power_rtu = {
            'unit_id': 20,
            'device_name': 'PowerMeter-RTU',
            'device_type': 'Power Monitor',
            'vendor': 'BASim',
            'model': 'BASIM-PWR-RTU',
            'network_type': 'Modbus RTU',
            'network_number': 1,
            'serial_port': '/dev/ttyRS485-1',
            'baud_rate': 19200,
            'parity': 'N',
            'data_bits': 8,
            'stop_bits': 1,
            'description': 'Electrical power meter (shared RS-485 bus with plant)',
            'registers': [
                {'address': 300, 'name': 'Main_Meter_kW', 'type': 'IR', 'description': 'Main meter power x10'},
                {'address': 302, 'name': 'Main_Meter_kWh', 'type': 'IR', 'description': 'Main meter energy (32-bit)'},
                {'address': 304, 'name': 'Power_Factor', 'type': 'IR', 'description': 'Power factor x1000'},
                {'address': 306, 'name': 'Voltage_AN', 'type': 'IR', 'description': 'Phase A-N voltage x10'},
                {'address': 308, 'name': 'Current_A', 'type': 'IR', 'description': 'Phase A current x100'},
            ]
        }
        modbus_devices.append(power_rtu)
        
        # RTU Network 1 - Plant/Utility
        rtu_network_1 = {
            'network_number': 1,
            'network_type': 'Modbus RTU (RS-485)',
            'description': 'Plant & Utility equipment network',
            'serial_port': '/dev/ttyRS485-1',
            'baud_rate': 19200,
            'parity': 'None',
            'data_bits': 8,
            'stop_bits': 1,
            'termination': '120Ω',
            'max_devices': 32,
            'devices': [10, 20]  # Unit IDs
        }
        modbus_networks.append(rtu_network_1)
        
        # Building RTU networks (one per building)
        building_unit_base = 100
        ahu_unit_base = 50
        
        for bldg_idx, bldg in enumerate(eng.buildings):
            rtu_net_num = 2 + bldg_idx
            
            # Create RTU network for this building
            rtu_network = {
                'network_number': rtu_net_num,
                'network_type': 'Modbus RTU (RS-485)',
                'description': f'{bldg.display_name} field devices network',
                'serial_port': f'/dev/ttyRS485-{rtu_net_num}',
                'baud_rate': 9600,
                'parity': 'Even',
                'data_bits': 8,
                'stop_bits': 1,
                'termination': '120Ω',
                'max_devices': 32,
                'devices': []
            }
            
            # Building Controller RTU
            bldg_unit_id = building_unit_base + bldg.id
            bldg_rtu = {
                'unit_id': bldg_unit_id,
                'device_name': f'{bldg.name}-RTU',
                'device_type': 'Building Controller',
                'vendor': 'BASim',
                'model': 'BASIM-RTU-200',
                'network_type': 'Modbus RTU',
                'network_number': rtu_net_num,
                'serial_port': f'/dev/ttyRS485-{rtu_net_num}',
                'baud_rate': 9600,
                'parity': 'E',
                'description': f'{bldg.display_name} supervisory RTU controller',
                'registers': [
                    {'address': 0, 'name': 'Building_Demand_kW', 'type': 'IR', 'description': 'Building demand x10'},
                    {'address': 2, 'name': 'OA_Temp', 'type': 'IR', 'description': 'Local OAT x100'},
                    {'address': 4, 'name': 'OA_Humidity', 'type': 'IR', 'description': 'OA Humidity x10'},
                ]
            }
            modbus_devices.append(bldg_rtu)
            rtu_network['devices'].append(bldg_unit_id)
            
            # AHU RTU Controllers
            for ahu_idx, ahu in enumerate(bldg.ahus):
                ahu_unit_id = ahu_unit_base + (bldg.id * 10) + ahu.id
                
                ahu_rtu = {
                    'unit_id': ahu_unit_id,
                    'device_name': f'{bldg.name}-{ahu.name}-RTU',
                    'device_type': 'AHU Controller',
                    'vendor': 'BASim',
                    'model': 'BASIM-RTU-100',
                    'network_type': 'Modbus RTU',
                    'network_number': rtu_net_num,
                    'serial_port': f'/dev/ttyRS485-{rtu_net_num}',
                    'baud_rate': 9600,
                    'parity': 'E',
                    'description': f'{ahu.name} ({ahu.ahu_type}) RTU controller',
                    'registers': [
                        {'address': 0, 'name': 'Supply_Air_Temp', 'type': 'IR', 'description': 'SAT x100'},
                        {'address': 1, 'name': 'Return_Air_Temp', 'type': 'IR', 'description': 'RAT x100'},
                        {'address': 2, 'name': 'Mixed_Air_Temp', 'type': 'IR', 'description': 'MAT x100'},
                        {'address': 3, 'name': 'Fan_Status', 'type': 'DI', 'description': 'Supply fan status'},
                        {'address': 10, 'name': 'Supply_Setpoint', 'type': 'HR', 'description': 'SAT setpoint x100'},
                        {'address': 11, 'name': 'Fan_Speed_Cmd', 'type': 'HR', 'description': 'Fan speed % x100'},
                        {'address': 12, 'name': 'OA_Damper_Cmd', 'type': 'HR', 'description': 'OA damper % x100'},
                        {'address': 13, 'name': 'Cooling_Valve', 'type': 'HR', 'description': 'Cooling valve % x100'},
                        {'address': 14, 'name': 'Heating_Valve', 'type': 'HR', 'description': 'Heating valve % x100'},
                        {'address': 0, 'name': 'Fan_Enable', 'type': 'CO', 'description': 'Supply fan enable'},
                    ]
                }
                modbus_devices.append(ahu_rtu)
                rtu_network['devices'].append(ahu_unit_id)
                
                # VAV RTU Controllers (I/O expanders on same bus)
                for vav_idx, vav in enumerate(ahu.vavs):
                    vav_unit_id = 200 + (bldg.id * 100) + (ahu.id * 10) + vav.id
                    
                    vav_rtu = {
                        'unit_id': vav_unit_id,
                        'device_name': f'{bldg.name}-{ahu.name}-{vav.name}-RTU',
                        'device_type': 'VAV Controller',
                        'vendor': 'BASim',
                        'model': 'BASIM-RTU-VAV',
                        'network_type': 'Modbus RTU',
                        'network_number': rtu_net_num,
                        'serial_port': f'/dev/ttyRS485-{rtu_net_num}',
                        'baud_rate': 9600,
                        'parity': 'E',
                        'description': f'{vav.zone_name} VAV RTU controller',
                        'registers': [
                            {'address': 0, 'name': 'Room_Temp', 'type': 'IR', 'description': 'Zone temp x100'},
                            {'address': 1, 'name': 'Discharge_Temp', 'type': 'IR', 'description': 'Discharge temp x100'},
                            {'address': 2, 'name': 'Airflow', 'type': 'IR', 'description': 'CFM'},
                            {'address': 10, 'name': 'Cooling_SP', 'type': 'HR', 'description': 'Cooling setpoint x100'},
                            {'address': 11, 'name': 'Heating_SP', 'type': 'HR', 'description': 'Heating setpoint x100'},
                            {'address': 12, 'name': 'Damper_Cmd', 'type': 'HR', 'description': 'Damper % x100'},
                            {'address': 0, 'name': 'Occ_Sensor', 'type': 'DI', 'description': 'Occupancy'},
                        ]
                    }
                    modbus_devices.append(vav_rtu)
                    rtu_network['devices'].append(vav_unit_id)
            
            modbus_networks.append(rtu_network)
        
        # Build protocol info with enhanced BACnet and Modbus data
        protocol_info = {
            'modbus': {
                'enabled': True,
                'protocol': 'Modbus TCP/RTU Gateway',
                'host': hostname,
                'port': 5020,
                'unit_id': 1,
                'device_name': 'BASim-ModbusTCP-Gateway',
                'description': 'Modbus TCP gateway routing to RTU field devices on RS-485 networks',
                'networks': modbus_networks,
                'devices': modbus_devices,
                'device_count': len(modbus_devices),
                'network_topology': {
                    'tcp_devices': len([d for d in modbus_devices if d.get('network_type') == 'Modbus TCP']),
                    'rtu_devices': len([d for d in modbus_devices if d.get('network_type') == 'Modbus RTU']),
                },
                'register_types': {
                    'HR': 'Holding Registers (FC 3/6/16) - Read/Write',
                    'IR': 'Input Registers (FC 4) - Read Only',
                    'CO': 'Coils (FC 1/5/15) - Read/Write',
                    'DI': 'Discrete Inputs (FC 2) - Read Only'
                },
                'data_format': 'Values scaled by 100 (divide by 100 for actual value)',
                'example_read': f'mbpoll -m tcp -a 1 -r 0 -c 10 {hostname} -p 5020',
                'example_python': f'''from pymodbus.client import ModbusTcpClient
client = ModbusTcpClient('{hostname}', port=5020)
client.connect()

# Read from TCP gateway (Unit ID 1)
result = client.read_holding_registers(0, 10, slave=1)

# Read from Plant RTU via gateway (Unit ID 10)
plant = client.read_input_registers(100, 4, slave=10)
chw_supply = plant.registers[0] / 100.0

# Read from Building AHU RTU (Unit ID 51)
ahu = client.read_input_registers(0, 3, slave=51)
sat = ahu.registers[0] / 100.0'''
            },
            'bacnet': {
                'enabled': True,
                'protocol': 'BACnet/IP',
                'host': hostname,
                'port': 47808,
                'device_id': 9999,
                'device_name': 'BASim-Router',
                'description': 'BACnet/IP router with MS/TP and BACnet/SC networks',
                'networks': bacnet_networks,
                'devices': bacnet_devices,
                'device_count': len(bacnet_devices),
                'network_topology': {
                    'ip_devices': len([d for d in bacnet_devices if 'BACnet/IP' in d.get('network_type', '')]),
                    'mstp_devices': len([d for d in bacnet_devices if d.get('network_type') == 'BACnet MS/TP']),
                    'sc_devices': len([d for d in bacnet_devices if d.get('network_type') == 'BACnet/SC']),
                },
                'object_types': 'AI, AO, AV, BI, BO, BV objects per device',
                'example_whois': f'bacnet-client whois {hostname}',
                'example_read': f'bacnet-client read {hostname} 9999 analog-value 1 present-value',
                'example_python': f'''from bacpypes.app import BIPSimpleApplication
# Discover devices on network
# bacnet-client whois {hostname}
# Read from Building Controller (Device 2001)
# bacnet-client read {hostname} 2001 analog-input 1 present-value'''
            },
            'bacnet_sc': {
                'enabled': True,
                'protocol': 'BACnet/SC (Secure Connect)',
                'hub_uri': f'wss://{hostname}/bacnet-sc',
                'security': 'TLS 1.3 with X.509 certificates',
                'description': 'BACnet Secure Connect for cloud and remote access',
                'features': [
                    'End-to-end encryption',
                    'Certificate-based authentication', 
                    'NAT traversal',
                    'Cloud connectivity'
                ],
                'devices': [d for d in bacnet_devices if d.get('network_type') == 'BACnet/SC']
            },

            'rest_api': {
                'enabled': True,
                'protocol': 'REST API',
                'base_url': f'https://{hostname}/api',
                'authentication': 'Session cookie (login required)',
                'description': 'REST API for web integration',
                'endpoints': [
                    {'method': 'GET', 'path': '/api/status', 'description': 'System status and OAT'},
                    {'method': 'GET', 'path': '/api/buildings', 'description': 'List all buildings'},
                    {'method': 'GET', 'path': '/api/buildings/{id}', 'description': 'Building details with AHUs and VAVs'},
                    {'method': 'GET', 'path': '/api/plant', 'description': 'Central plant status'},
                    {'method': 'GET', 'path': '/api/electrical', 'description': 'Electrical system status'},
                    {'method': 'POST', 'path': '/api/override/set', 'description': 'Set point override'},
                    {'method': 'POST', 'path': '/api/override/release', 'description': 'Release override'},
                ]
            },
            'points': points,
            'total_points': len(points)
        }
        
        return jsonify(protocol_info)
    
    @app.route('/api/bacnet-sc/config')
    @api_login_required
    def download_bacnet_sc_config():
        """
        Generate and download BACnet SC client connection package.
        Returns a ZIP file containing certificates and connection info for secure BACnet/SC connections.
        """
        import io
        import zipfile
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.backends import default_backend
        
        hostname = request.host.split(':')[0]
        if hostname in ('localhost', '127.0.0.1'):
            hostname = 'sim.hill.coffee'
        
        # Generate a unique client ID for this download
        client_id = f"client-{datetime.now().strftime('%Y%m%d%H%M%S')}-{random.randint(1000,9999)}"
        
        # Generate CA private key and certificate (self-signed for demo)
        ca_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        
        ca_name = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "BASim"),
            x509.NameAttribute(NameOID.COMMON_NAME, "BASim BACnet/SC CA"),
        ])
        
        ca_cert = (
            x509.CertificateBuilder()
            .subject_name(ca_name)
            .issuer_name(ca_name)
            .public_key(ca_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.utcnow())
            .not_valid_after(datetime(2030, 12, 31))
            .add_extension(
                x509.BasicConstraints(ca=True, path_length=None),
                critical=True,
            )
            .sign(ca_key, hashes.SHA256(), default_backend())
        )
        
        # Generate client private key and certificate (signed by CA)
        client_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        
        client_name = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "BASim Client"),
            x509.NameAttribute(NameOID.COMMON_NAME, client_id),
        ])
        
        client_cert = (
            x509.CertificateBuilder()
            .subject_name(client_name)
            .issuer_name(ca_name)
            .public_key(client_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.utcnow())
            .not_valid_after(datetime(2026, 12, 31))
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None),
                critical=True,
            )
            .add_extension(
                x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH]),
                critical=False,
            )
            .sign(ca_key, hashes.SHA256(), default_backend())
        )
        
        # Serialize certificates and keys to PEM format
        ca_cert_pem = ca_cert.public_bytes(serialization.Encoding.PEM).decode('utf-8')
        client_cert_pem = client_cert.public_bytes(serialization.Encoding.PEM).decode('utf-8')
        client_key_pem = client_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ).decode('utf-8')
        
        # Create connection info README
        readme_content = f'''BASim BACnet/SC Client Connection Package
==========================================

Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Client ID: {client_id}

CONNECTION INFORMATION
----------------------
Hub URI:        wss://{hostname}/bacnet-sc
Hub Device ID:  9999
Hub UUID:       ba51m-0000-0000-0000-000000000001

For standard BACnet/IP (non-secure):
  Address:      {hostname}
  Port:         47808
  Device ID:    9999

INCLUDED FILES
--------------
ca.pem          - CA certificate (Self-signed root for testing)
client.pem      - Client certificate (Signed by ca.pem)
client-key.pem  - Client private key
connection.ini  - Connection parameters

YABE SETUP (BACnet/SC)
----------------------
1. Open YABE (Yet Another BACnet Explorer)
2. Click "Add device" (Green Plus icon)
3. Select "BACnet/SC" tab
4. Enter Hub URL: wss://{hostname}/bacnet-sc
5. Leave certificates blank (Open Hub mode)
6. Click Connect

NOTE: The simulator runs in "Open Hub" mode and does not enforce client 
certificate validation. The provided certificates are for testing client 
configuration only.

SECURITY NOTE
-------------
This package contains a private key. Keep client-key.pem secure.
For production use, always use certificates issued by your organization's PKI.
'''

        # Create INI-style connection config
        connection_ini = f'''[BACnet/SC]
; BACnet Secure Connect Configuration
HubURI=wss://{hostname}/bacnet-sc
HubDeviceID=9999
HubUUID=ba51m-0000-0000-0000-000000000001
ClientID={client_id}
CACertificate=ca.pem
ClientCertificate=client.pem
ClientPrivateKey=client-key.pem
TLSVersion=1.3

[BACnet/IP]
; Standard BACnet/IP Configuration (no encryption)
Address={hostname}
Port=47808
DeviceID=9999
Network=1

[Device]
; Client device settings
VendorID=999
VendorName=BASim
'''
        
        # Create ZIP file in memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('README.txt', readme_content)
            zf.writestr('ca.pem', ca_cert_pem)
            zf.writestr('client.pem', client_cert_pem)
            zf.writestr('client-key.pem', client_key_pem)
            zf.writestr('connection.ini', connection_ini)
        
        zip_buffer.seek(0)
        
        logger.info(f"User '{current_user.username}' downloaded BACnet/SC client package (client_id={client_id})")
        
        response = Response(
            zip_buffer.getvalue(),
            mimetype='application/zip',
            headers={'Content-Disposition': f'attachment; filename=basim-bacnet-sc-{client_id}.zip'}
        )
        return response
    
    return app


class WebServer:
    """
    Web server wrapper following ProtocolServer pattern (SRP).
    """
    
    def __init__(self, engine: CampusEngine, host: str = "0.0.0.0", port: int = 8080):
        self._engine = engine
        self._host = host
        self._port = port
        self._app = None
        self._thread = None
    
    def start(self) -> None:
        """Start the web server in a background thread."""
        import threading
        
        self._app = create_app(self._engine)
        self._thread = threading.Thread(
            target=self._run_server,
            daemon=True
        )
        self._thread.start()
        logger.info(f"Web GUI started on http://{self._host}:{self._port}")
    
    def _run_server(self) -> None:
        """Run Flask server."""
        # Use werkzeug directly for threaded operation
        from werkzeug.serving import make_server
        self._server = make_server(self._host, self._port, self._app, threaded=True)
        self._server.serve_forever()
    
    def stop(self) -> None:
        """Stop the web server."""
        if hasattr(self, '_server'):
            self._server.shutdown()
        logger.info("Web server stopped")
