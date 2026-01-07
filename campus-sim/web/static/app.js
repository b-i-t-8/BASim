// BASim Dashboard - Table-based UI with inline overrides

const API_BASE = '';
let currentBuilding = null;
let currentView = 'building';
let refreshInterval = null;
let currentUser = null;
let activeOverrides = {};
let currentTempUnit = '°F';
let currentFlowWaterUnit = 'GPM';
let currentFlowAirUnit = 'CFM';
let currentFlowGasUnit = 'CFH';
let currentPressureWCUnit = '"WC';
let currentHeadUnit = 'ft';
let currentEnthalpyUnit = 'BTU/lb';
let currentAreaUnit = 'sq ft';

// Theme Management
function initTheme() {
    const savedTheme = localStorage.getItem('basim-theme') || 'ocean';
    setTheme(savedTheme, false);
}

function setTheme(theme, save = true) {
    document.documentElement.setAttribute('data-theme', theme);
    if (save) {
        localStorage.setItem('basim-theme', theme);
    }
    // Update active state in dropdown
    document.querySelectorAll('.theme-option').forEach(opt => {
        opt.classList.toggle('active', opt.dataset.theme === theme);
    });
    // Close dropdown
    const switcher = document.getElementById('theme-switcher');
    if (switcher) switcher.classList.remove('open');
}

function toggleThemeMenu() {
    const switcher = document.getElementById('theme-switcher');
    if (switcher) {
        switcher.classList.toggle('open');
    }
}

function toggleMobileMenu() {
    const menu = document.getElementById('user-menu');
    const btn = document.querySelector('.mobile-menu-btn');
    if (menu) {
        menu.classList.toggle('open');
        if (btn) btn.classList.toggle('active');
    }
}

// Close menus when clicking outside
document.addEventListener('click', (e) => {
    // Theme switcher
    const switcher = document.getElementById('theme-switcher');
    if (switcher && !switcher.contains(e.target) && !e.target.closest('.theme-btn')) {
        switcher.classList.remove('open');
    }
    
    // Mobile menu
    const menu = document.getElementById('user-menu');
    const btn = document.querySelector('.mobile-menu-btn');
    if (menu && menu.classList.contains('open') && !menu.contains(e.target) && !btn.contains(e.target)) {
        menu.classList.remove('open');
        if (btn) btn.classList.remove('active');
    }
});

// Initialize dashboard
document.addEventListener('DOMContentLoaded', async () => {
    initTheme();
    await loadUserInfo();
    loadStatus();
    await loadBuildings();
    loadOverrides();
    
    // Handle initial URL hash
    handleHashChange();

    // Listen for hash changes
    window.addEventListener('hashchange', handleHashChange);
    
    // Auto-refresh every 2 seconds
    refreshInterval = setInterval(() => {
        loadStatus();
        loadOverrides();
        refreshCurrentView();
    }, 2000);
});

function handleHashChange() {
    const hash = window.location.hash.slice(1); // Remove #
    if (!hash) {
        // Default to dashboard
        const dashBtn = document.querySelector('.dashboard-tab');
        if (dashBtn) {
            selectDashboard(dashBtn);
        }
        return;
    }

    const parts = hash.split('/');
    const type = parts[0];
    const id = parts[1];

    if (type === 'dashboard') {
        const btn = document.querySelector('.dashboard-tab');
        if (btn) selectDashboard(btn);
    } else if (type === 'building' && id) {
        const btn = document.querySelector(`.view-nav button[data-id="${id}"]`);
        if (btn) {
            selectBuilding(id, btn, false);
        }
    } else {
        // Facility
        const btn = document.querySelector(`.view-nav .${type}-tab`);
        if (btn) {
            selectFacility(type, btn, false);
        }
    }
}

function refreshCurrentView() {
    if (currentView === 'dashboard') loadDashboardData();
    else if (currentView === 'plant') loadPlantData();
    else if (currentView === 'electrical') loadElectricalData();
    else if (currentView === 'datacenter') loadDataCenterData();
    else if (currentView === 'wastewater') loadWastewaterData();
    else if (currentBuilding) loadBuildingData(currentBuilding);
}

// ============== DASHBOARD VIEW ==============

async function loadDashboardData() {
    try {
        // We need data from all buildings to compute aggregates
        // This is inefficient (N+1 queries) but fine for a prototype/simulator
        const buildingsResp = await apiRequest(`${API_BASE}/api/buildings`);
        if (!buildingsResp) return;
        const buildingsList = await buildingsResp.json();
        
        const plantResp = await apiRequest(`${API_BASE}/api/plant`);
        const plant = plantResp ? await plantResp.json() : {};

        let totalTemp = 0;
        let tempCount = 0;
        let hotSpots = [];
        let coldSpots = [];
        
        // Fetch details for each building
        // Parallel fetch for speed
        const promises = buildingsList.map(b => apiRequest(`${API_BASE}/api/buildings/${b.id}`).then(r => r.json()));
        const buildings = await Promise.all(promises);
        
        buildings.forEach(b => {
            b.ahus.forEach(ahu => {
                if (ahu.vavs) {
                    ahu.vavs.forEach(vav => {
                        const temp = vav.room_temp;
                        if (typeof temp === 'number') {
                            totalTemp += temp;
                            tempCount++;
                            
                            if (temp > 76.0) hotSpots.push({ name: `${b.name}/${vav.name}`, val: temp });
                            if (temp < 68.0) coldSpots.push({ name: `${b.name}/${vav.name}`, val: temp });
                        }
                    });
                }
            });
        });
        
        // Update KPI Cards
        const avgTemp = tempCount > 0 ? (totalTemp / tempCount).toFixed(1) : '--';
        const comfortScore = tempCount > 0 ? Math.round(((tempCount - hotSpots.length - coldSpots.length) / tempCount) * 100) : 100;
        
        document.getElementById('kpi-hot-count').textContent = hotSpots.length;
        document.getElementById('kpi-cold-count').textContent = coldSpots.length;
        document.getElementById('kpi-avg-temp').textContent = avgTemp;
        document.getElementById('kpi-comfort-score').textContent = `${comfortScore}%`;
        document.getElementById('kpi-plant-load').textContent = plant.total_cooling_tons?.toFixed(0) || '--';
        
        // Render Lists
        renderKpiList('kpi-hot-list', hotSpots.sort((a,b) => b.val - a.val).slice(0, 10)); // Top 10 hot
        renderKpiList('kpi-cold-list', coldSpots.sort((a,b) => a.val - b.val).slice(0, 10)); // Top 10 cold
        
    } catch (error) { console.error('Failed to load dashboard data:', error); }
}

function renderKpiList(elementId, items) {
    const list = document.getElementById(elementId);
    if (!list) return;
    list.innerHTML = items.length === 0 ? '<li>None</li>' : 
        items.map(item => `<li><span>${item.name}</span><strong>${item.val.toFixed(1)}°</strong></li>`).join('');
}

// API request with auth handling
async function apiRequest(url, options = {}) {
    try {
        const response = await fetch(url, { ...options, credentials: 'same-origin' });
        if (response.status === 401) { window.location.href = '/login'; return null; }
        if (response.status === 403) { alert('Admin privileges required.'); return null; }
        return response;
    } catch (error) {
        console.error('API request failed:', error);
        return null;
    }
}

async function loadUserInfo() {
    try {
        const response = await apiRequest(`${API_BASE}/api/user`);
        if (response && response.ok) currentUser = await response.json();
    } catch (error) { console.error('Failed to load user info:', error); }
}

async function loadStatus() {
    try {
        const response = await apiRequest(`${API_BASE}/api/status`);
        if (!response) return;
        const data = await response.json();
        
        document.getElementById('oat').textContent = data.oat.toFixed(1);
        if (document.getElementById('humidity')) document.getElementById('humidity').textContent = data.humidity.toFixed(1);
        if (document.getElementById('wet-bulb')) document.getElementById('wet-bulb').textContent = data.wet_bulb.toFixed(1);
        if (document.getElementById('dew-point')) document.getElementById('dew-point').textContent = data.dew_point.toFixed(1);
        if (document.getElementById('enthalpy')) document.getElementById('enthalpy').textContent = data.enthalpy.toFixed(1);

        if (data.temp_unit) {
            currentTempUnit = data.temp_unit;
            currentFlowWaterUnit = data.flow_water_unit || 'GPM';
            currentFlowAirUnit = data.flow_air_unit || 'CFM';
            currentFlowGasUnit = data.flow_gas_unit || 'CFH';
            currentPressureWCUnit = data.pressure_wc_unit || '"WC';
            currentHeadUnit = data.head_unit || 'ft';
            currentEnthalpyUnit = data.enthalpy_unit || 'BTU/lb';
            currentAreaUnit = data.area_unit || 'sq ft';
            
            document.querySelectorAll('.temp-unit').forEach(el => {
                el.textContent = data.temp_unit;
            });
            document.querySelectorAll('.enthalpy-unit').forEach(el => {
                el.textContent = currentEnthalpyUnit;
            });
        }

        if (document.getElementById('sim-date')) {
            document.getElementById('sim-date').textContent = data.simulation_date;
            document.title = `BASim - ${data.campus_name || 'Campus'}`;
        }
        if (document.getElementById('sim-season')) document.getElementById('sim-season').textContent = data.season;
        document.getElementById('sim-speed').textContent = data.simulation_speed;
        document.getElementById('num-buildings').textContent = data.num_buildings;
        document.getElementById('total-vavs').textContent = data.total_vavs;
        
        if (data.plant_summary) {
            document.getElementById('plant-kw').textContent = data.plant_summary.total_plant_kw.toFixed(0);
            document.getElementById('cooling-load').textContent = data.plant_summary.total_cooling_tons.toFixed(0);
        }

        // Update active scenario
        if (data.active_scenario) {
            document.querySelectorAll('.scenario-btn').forEach(btn => {
                if (btn.dataset.scenario === data.active_scenario) {
                    btn.classList.add('active');
                } else {
                    btn.classList.remove('active');
                }
            });
        }
    } catch (error) { console.error('Failed to load status:', error); }
}

async function triggerScenario(scenario) {
    try {
        const response = await apiRequest(`${API_BASE}/api/admin/scenario`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ scenario: scenario })
        });
        
        if (response && response.ok) {
            // Optimistic update
            document.querySelectorAll('.scenario-btn').forEach(btn => {
                if (btn.dataset.scenario === scenario) {
                    btn.classList.add('active');
                } else {
                    btn.classList.remove('active');
                }
            });
        }
    } catch (error) {
        console.error('Failed to trigger scenario:', error);
    }
}

async function loadOverrides() {
    try {
        const response = await apiRequest(`${API_BASE}/api/overrides`);
        if (!response || !response.ok) return;
        const data = await response.json();
        activeOverrides = data.overrides || {};
        updateOverrideCount();
    } catch (error) { console.error('Failed to load overrides:', error); }
}

function updateOverrideCount() {
    const count = Object.keys(activeOverrides).length;
    const countEl = document.getElementById('override-count');
    if (countEl) {
        countEl.textContent = count;
        countEl.style.display = count > 0 ? 'inline' : 'none';
    }
}

function isOverridden(pointPath) {
    return activeOverrides.hasOwnProperty(pointPath);
}

function getOverrideValue(pointPath) {
    if (!isOverridden(pointPath)) return null;
    const priorities = activeOverrides[pointPath];
    const lowestPriority = Math.min(...Object.keys(priorities).map(Number));
    return priorities[lowestPriority].value;
}

// Load buildings list
async function loadBuildings() {
    try {
        const response = await apiRequest(`${API_BASE}/api/buildings`);
        if (!response) return;
        const buildings = await response.json();
        
        const statusResp = await apiRequest(`${API_BASE}/api/status`);
        const status = statusResp ? await statusResp.json() : {};
        
        const nav = document.getElementById('view-nav');
        if (!nav) return; // Guard for old HTML
        nav.innerHTML = '';
        
        // Dashboard Tab
        const dashBtn = document.createElement('button');
        dashBtn.className = 'dashboard-tab';
        dashBtn.innerHTML = `<span class="tab-icon">[DASH]</span><span class="tab-name">Overview</span>`;
        dashBtn.onclick = () => { window.location.hash = '#dashboard'; };
        nav.appendChild(dashBtn);

        // Facility tabs
        const tabs = [
            { id: 'plant', icon: '[PLT]', name: 'Central Plant', info: 'Chillers & Boilers' },
            { id: 'electrical', icon: '[PWR]', name: 'Electrical', info: 'Power & Solar' }
        ];
        
        if (status.datacenter_summary?.enabled) {
            tabs.push({ id: 'datacenter', icon: '[DC]', name: 'Data Center', info: status.datacenter_summary.display_name });
        }
        if (status.wastewater_summary?.enabled) {
            tabs.push({ id: 'wastewater', icon: '[WW]', name: 'Wastewater', info: status.wastewater_summary.display_name });
        }
        
        tabs.forEach(tab => {
            const btn = document.createElement('button');
            btn.className = `${tab.id}-tab`;
            btn.innerHTML = `<span class="tab-icon">${tab.icon}</span><span class="tab-name">${tab.name}</span>`;
            btn.onclick = () => { window.location.hash = `#${tab.id}`; };
            nav.appendChild(btn);
        });
        
        // Building tabs
        buildings.forEach(b => {
            const btn = document.createElement('button');
            btn.dataset.id = b.id;
            btn.innerHTML = `<span class="tab-icon">[BLD]</span><span class="tab-name">${b.display_name || b.name}</span>`;
            btn.onclick = () => { window.location.hash = `#building/${b.id}`; };
            nav.appendChild(btn);
        });
    } catch (error) { console.error('Failed to load buildings:', error); }
}

function selectDashboard(btn) {
    updateNavSelection(btn);
    currentView = 'dashboard';
    currentBuilding = null;
    
    document.getElementById('dashboard-view').style.display = 'block';
    document.getElementById('content-view').style.display = 'none';
    
    loadDashboardData();
}

function selectFacility(facility, btn, updateUrl = true) {
    updateNavSelection(btn);
    currentView = facility;
    currentBuilding = null;
    
    document.getElementById('dashboard-view').style.display = 'none';
    document.getElementById('content-view').style.display = 'block';
    
    if (updateUrl) {
        window.location.hash = `#${facility}`;
    }
    
    if (facility === 'plant') loadPlantData();
    else if (facility === 'electrical') loadElectricalData();
    else if (facility === 'datacenter') loadDataCenterData();
    else if (facility === 'wastewater') loadWastewaterData();
}

function selectBuilding(buildingId, btn, updateUrl = true) {
    updateNavSelection(btn);
    currentView = 'building';
    currentBuilding = buildingId;
    
    document.getElementById('dashboard-view').style.display = 'none';
    document.getElementById('content-view').style.display = 'block';
    
    if (updateUrl) {
        window.location.hash = `#building/${buildingId}`;
    }

    loadBuildingData(buildingId);
}

function updateNavSelection(activeBtn) {
    document.querySelectorAll('.view-nav button').forEach(b => b.classList.remove('active'));
    if (activeBtn) activeBtn.classList.add('active');
}

// ============== BUILDING VIEW ==============

async function loadBuildingData(buildingId) {
    try {
        const response = await apiRequest(`${API_BASE}/api/buildings/${buildingId}`);
        if (!response) return;
        const building = await response.json();
        document.getElementById('content-view').innerHTML = renderBuilding(building);
    } catch (error) { console.error('Failed to load building data:', error); }
}

function renderBuilding(building) {
    const isAdmin = currentUser?.role === 'admin';
    
    let html = `
        <div class="view-header">
            <h2>${building.display_name}</h2>
            <div class="view-meta">
                <span>${building.square_footage?.toLocaleString() || 'N/A'} ${currentAreaUnit}</span>
                <span>${building.floor_count || 1} floors</span>
            </div>
        </div>
    `;
    
    building.ahus.forEach(ahu => {
        const isOA = ahu.ahu_type === '100%OA';
        const ahuPath = ahu.point_path;
        
        html += `
            <div class="section">
                <div class="section-header">
                    <h3>${ahu.name}</h3>
                    <span class="tag ${isOA ? 'tag-green' : 'tag-blue'}">${isOA ? '100% OA' : 'VAV System'}</span>
                </div>
                <table class="data-table">
                    <thead>
                        <tr><th>Status</th><th>Supply SP</th><th>Supply</th><th>Return</th><th>Mixed</th><th>Fan Speed</th><th>OA Damper</th><th>Filter ΔP</th></tr>
                    </thead>
                    <tbody>
                        <tr>
                            <td>${clickablePoint(ahuPath + '.fan_status', ahu.fan_status, '', 'Enable', isAdmin, true, '', true)}</td>
                            <td>${clickablePoint(ahuPath + '.supply_temp_setpoint', ahu.supply_temp_setpoint, currentTempUnit, 'Supply Setpoint', isAdmin, true)}</td>
                            <td>${clickablePoint(ahuPath + '.supply_temp', ahu.supply_temp, currentTempUnit, 'Supply Temp', isAdmin, false)}</td>
                            <td>${clickablePoint(ahuPath + '.return_temp', ahu.return_temp, currentTempUnit, 'Return Temp', isAdmin, false)}</td>
                            <td>${clickablePoint(ahuPath + '.mixed_air_temp', ahu.mixed_air_temp, currentTempUnit, 'Mixed Air Temp', isAdmin, false)}</td>
                            <td><div class="bar-cell">${clickablePoint(ahuPath + '.fan_speed', ahu.fan_speed, '%', 'Fan Speed', isAdmin, true)}<div class="mini-bar"><div class="mini-fill" style="width:${ahu.fan_speed || 0}%"></div></div></div></td>
                            <td><div class="bar-cell">${clickablePoint(ahuPath + '.outside_air_damper', ahu.outside_air_damper, '%', 'OA Damper', isAdmin, true)}<div class="mini-bar"><div class="mini-fill" style="width:${ahu.outside_air_damper || 0}%"></div></div></div></td>
                            <td>${clickablePoint(ahuPath + '.filter_dp', ahu.filter_dp, currentPressureWCUnit, 'Filter ΔP', isAdmin, false)}</td>
                        </tr>
                    </tbody>
                </table>
        `;
        
        if (!isOA && ahu.vavs?.length > 0) {
            html += `
                <div class="subsection">
                    <h4>VAV Boxes (${ahu.vavs.length})</h4>
                    <div class="device-grid">
                        ${ahu.vavs.map(vav => renderDeviceCard(building.id, ahu.id, vav, isAdmin)).join('')}
                    </div>
                </div>
            `;
        }
        
        html += '</div>';
    });
    
    return html;
}

function renderDeviceCard(buildingId, ahuId, vav, isAdmin) {
    const path = vav.point_path;
    const temp = vav.room_temp;
    const setpoint = vav.effective_setpoint || vav.cooling_setpoint;
    const damperPct = vav.damper_position?.toFixed(0) || 0;
    const reheatPct = vav.reheat_valve?.toFixed(0) || 0;
    const airflow = vav.cfm_actual?.toFixed(0) || '--';
    
    // Determine status color
    let tempClass = 'temp-ok';
    if (temp > (vav.cooling_setpoint + 2)) tempClass = 'temp-hot';
    else if (temp < (vav.heating_setpoint - 2)) tempClass = 'temp-cold';

    return `
        <div class="device-card">
            <div class="device-header">
                <span class="device-name">${vav.zone_name || vav.name}</span>
                <span class="device-status">${vav.occupancy ? 'OCC' : 'UNOCC'}</span>
            </div>
            
            <div class="device-main-metrics">
                <div class="metric-large">
                    <div class="metric-value ${tempClass}">
                        ${clickablePoint(path + '.room_temp', temp, '', 'Room Temp', isAdmin, false)}<span style="font-size:0.5em">°</span>
                    </div>
                    <div class="metric-label">Room Temp</div>
                </div>
                <div class="metric-large">
                    <div class="metric-value" style="color:var(--text-dim)">
                        ${setpoint?.toFixed(1) || '--'}<span style="font-size:0.5em">°</span>
                    </div>
                    <div class="metric-label">Setpoint</div>
                </div>
            </div>
            
            <div class="device-details">
                <div class="detail-row">
                    <span>Flow:</span>
                    <span>${airflow} ${currentFlowAirUnit}</span>
                </div>
                <div class="detail-row">
                    <span>Damper:</span>
                    <span>${clickablePoint(path + '.damper_position', damperPct, '%', 'Damper', isAdmin, true)}</span>
                </div>
                <div class="detail-row">
                    <span>Reheat:</span>
                    <span>${clickablePoint(path + '.reheat_valve', reheatPct, '%', 'Reheat', isAdmin, true)}</span>
                </div>
                <div class="detail-row">
                    <span>Mode:</span>
                    <span>${vav.occupancy_mode || 'Auto'}</span>
                </div>
            </div>
            
            <div class="mini-bar" style="margin-top:8px">
                <div class="mini-fill" style="width:${damperPct}%; background:var(--primary-dim)"></div>
            </div>
        </div>
    `;
}

// ============== CENTRAL PLANT VIEW ==============

async function loadPlantData() {
    try {
        const response = await apiRequest(`${API_BASE}/api/plant`);
        if (!response) return;
        const plant = await response.json();
        document.getElementById('content-view').innerHTML = renderPlant(plant);
    } catch (error) { console.error('Failed to load plant data:', error); }
}

function renderPlant(plant) {
    const isAdmin = currentUser?.role === 'admin';
    
    let html = `
        <div class="view-header">
            <h2>CENTRAL PLANT</h2>
            <div class="view-stats">
                <div class="stat"><span class="stat-value">${plant.total_cooling_tons?.toFixed(0) || '0'}</span><span class="stat-label">Cooling Tons</span></div>
                <div class="stat"><span class="stat-value">${plant.total_heating_mbh?.toFixed(0) || '0'}</span><span class="stat-label">Heating MBH</span></div>
                <div class="stat"><span class="stat-value">${plant.total_plant_kw?.toFixed(0) || '0'}</span><span class="stat-label">Plant kW</span></div>
            </div>
        </div>
        
        <div class="section">
            <h3>CHILLERS</h3>
            <table class="data-table">
                <thead>
                    <tr><th>Name</th><th>Status</th><th>CHW Supply</th><th>CHW Return</th><th>Flow</th><th>Load</th><th>kW</th></tr>
                </thead>
                <tbody>
                    ${plant.chillers.map(ch => renderChillerRow(ch, isAdmin)).join('')}
                </tbody>
            </table>
        </div>
        
        <div class="section">
            <h3>BOILERS</h3>
            <table class="data-table">
                <thead>
                    <tr><th>Name</th><th>Status</th><th>HW Supply</th><th>HW Return</th><th>Flow</th><th>Firing</th><th>Gas ${currentFlowGasUnit}</th></tr>
                </thead>
                <tbody>
                    ${plant.boilers.map(b => renderBoilerRow(b, isAdmin)).join('')}
                </tbody>
            </table>
        </div>
        
        <div class="section">
            <h3>COOLING TOWERS</h3>
            <table class="data-table">
                <thead>
                    <tr><th>Name</th><th>Status</th><th>CW Supply</th><th>CW Return</th><th>Flow</th><th>Fan</th><th>Wet Bulb</th></tr>
                </thead>
                <tbody>
                    ${plant.cooling_towers.map(ct => renderCoolingTowerRow(ct, isAdmin)).join('')}
                </tbody>
            </table>
        </div>
        
        <div class="section">
            <h3>PUMPS</h3>
            <table class="data-table">
                <thead>
                    <tr><th>Name</th><th>Type</th><th>Status</th><th>Speed</th><th>Flow</th><th>Head</th><th>kW</th></tr>
                </thead>
                <tbody>
                    ${plant.pumps.map(p => renderPumpRow(p, isAdmin)).join('')}
                </tbody>
            </table>
        </div>
    `;
    
    return html;
}

function renderChillerRow(ch, isAdmin) {
    const path = ch.point_path;
    return `
        <tr>
            <td><strong>${ch.name}</strong></td>
            <td>${clickablePoint(path + '.status', ch.status, '', 'Enable', isAdmin, true, '', true)}</td>
            <td>${clickablePoint(path + '.chw_supply_temp', ch.chw_supply_temp, currentTempUnit, 'CHW Setpoint', isAdmin, true)}</td>
            <td>${ch.chw_return_temp?.toFixed(1) || '--'}${currentTempUnit}</td>
            <td>${ch.chw_flow_gpm?.toFixed(0) || '0'} ${currentFlowWaterUnit}</td>
            <td><div class="bar-cell"><span>${ch.load_percent?.toFixed(0) || '0'}%</span><div class="mini-bar"><div class="mini-fill chiller" style="width:${ch.load_percent || 0}%"></div></div></div></td>
            <td>${ch.kw?.toFixed(1) || '0'}</td>
        </tr>
    `;
}

function renderBoilerRow(b, isAdmin) {
    const path = b.point_path;
    return `
        <tr>
            <td><strong>${b.name}</strong></td>
            <td>${clickablePoint(path + '.status', b.status, '', 'Enable', isAdmin, true, '', true)}</td>
            <td>${clickablePoint(path + '.hw_supply_temp', b.hw_supply_temp, currentTempUnit, 'HW Setpoint', isAdmin, true)}</td>
            <td>${b.hw_return_temp?.toFixed(1) || '--'}${currentTempUnit}</td>
            <td>${b.hw_flow_gpm?.toFixed(0) || '0'} ${currentFlowWaterUnit}</td>
            <td><div class="bar-cell"><span>${b.firing_rate?.toFixed(0) || '0'}%</span><div class="mini-bar"><div class="mini-fill boiler" style="width:${b.firing_rate || 0}%"></div></div></div></td>
            <td>${b.gas_flow_cfh?.toFixed(0) || '0'} ${currentFlowGasUnit}</td>
        </tr>
    `;
}

function renderCoolingTowerRow(ct, isAdmin) {
    const path = ct.point_path;
    return `
        <tr>
            <td><strong>${ct.name}</strong></td>
            <td>${clickablePoint(path + '.status', ct.status, '', 'Status', isAdmin, true, '', true)}</td>
            <td>${clickablePoint(path + '.cw_supply_temp', ct.cw_supply_temp, currentTempUnit, 'CW Setpoint', isAdmin, false)}</td>
            <td>${ct.cw_return_temp?.toFixed(1) || '--'}${currentTempUnit}</td>
            <td>${ct.cw_flow_gpm?.toFixed(0) || '0'} ${currentFlowWaterUnit}</td>
            <td><div class="bar-cell">${clickablePoint(path + '.fan_speed', ct.fan_speed, '%', 'Fan Speed', isAdmin, true)}<div class="mini-bar"><div class="mini-fill tower" style="width:${ct.fan_speed || 0}%"></div></div></div></td>
            <td>${ct.wet_bulb_temp?.toFixed(1) || '--'}${currentTempUnit}</td>
        </tr>
    `;
}

function renderPumpRow(p, isAdmin) {
    const path = p.point_path;
    return `
        <tr>
            <td><strong>${p.name}</strong></td>
            <td><span class="tag tag-${p.pump_type?.toLowerCase() || 'default'}">${p.pump_type || 'N/A'}</span></td>
            <td>${clickablePoint(path + '.status', p.status, '', 'Status', isAdmin, true, '', true)}</td>
            <td>${clickablePoint(path + '.speed', p.speed, '%', 'Speed', isAdmin, true)}</td>
            <td>${p.flow_gpm?.toFixed(0) || '0'} ${currentFlowWaterUnit}</td>
            <td>${p.head_ft?.toFixed(1) || '--'} ${currentHeadUnit}</td>
            <td>${p.kw?.toFixed(1) || '0'}</td>
        </tr>
    `;
}

// ============== ELECTRICAL VIEW ==============

async function loadElectricalData() {
    try {
        const response = await apiRequest(`${API_BASE}/api/electrical`);
        if (!response) return;
        const elec = await response.json();
        document.getElementById('content-view').innerHTML = renderElectrical(elec);
    } catch (error) { console.error('Failed to load electrical data:', error); }
}

function renderElectrical(elec) {
    const isAdmin = currentUser?.role === 'admin';
    const m = elec.main_meter || {};
    
    let html = `
        <div class="view-header">
            <h2>ELECTRICAL POWER SYSTEM</h2>
            <div class="view-stats">
                <div class="stat"><span class="stat-value">${elec.total_demand_kw.toFixed(0)}</span><span class="stat-label">Total kW</span></div>
                <div class="stat"><span class="stat-value">${elec.solar_production_kw.toFixed(0)}</span><span class="stat-label">Solar kW</span></div>
                <div class="stat"><span class="stat-value">${elec.grid_import_kw.toFixed(0)}</span><span class="stat-label">Grid kW</span></div>
                <div class="stat"><span class="stat-value">${m.power_factor?.toFixed(2) || '--'}</span><span class="stat-label">PF</span></div>
            </div>
        </div>
        
        <div class="section">
            <h3>MAIN METER</h3>
            <table class="data-table">
                <thead><tr><th>Point</th><th>Value</th></tr></thead>
                <tbody>
                    ${pointRow('electrical/main_meter/kw', 'Real Power', m.kw, 'kW', false)}
                    ${pointRow('electrical/main_meter/kva', 'Apparent Power', m.kva, 'kVA', false)}
                    ${pointRow('electrical/main_meter/pf', 'Power Factor', m.power_factor, '', false)}
                    ${pointRow('electrical/main_meter/voltage_a', 'Voltage A', m.voltage_a, 'V', false)}
                    ${pointRow('electrical/main_meter/voltage_b', 'Voltage B', m.voltage_b, 'V', false)}
                    ${pointRow('electrical/main_meter/voltage_c', 'Voltage C', m.voltage_c, 'V', false)}
                    ${pointRow('electrical/main_meter/freq', 'Frequency', m.frequency, 'Hz', false)}
                    ${pointRow('electrical/main_meter/kwh', 'Energy Total', m.kwh_total ? (m.kwh_total/1000).toFixed(1) : null, 'MWh', false)}
                </tbody>
            </table>
        </div>
        
        <div class="section">
            <h3>SOLAR ARRAYS</h3>
            <table class="data-table">
                <thead><tr><th>Name</th><th>Output</th><th>Capacity</th><th>Irradiance</th><th>Panel Temp</th><th>Today</th></tr></thead>
                <tbody>
                    ${elec.solar_arrays.map(s => renderSolarRow(s, isAdmin)).join('')}
                </tbody>
            </table>
        </div>
        
        <div class="section">
            <h3>UPS SYSTEMS</h3>
            <table class="data-table">
                <thead><tr><th>Name</th><th>Status</th><th>Capacity</th><th>Load</th><th>Battery</th><th>Runtime</th></tr></thead>
                <tbody>
                    ${elec.ups_systems.map(u => renderUPSRow(u, isAdmin)).join('')}
                </tbody>
            </table>
        </div>
        
        <div class="section">
            <h3>GENERATORS</h3>
            <table class="data-table">
                <thead><tr><th>Name</th><th>Status</th><th>Output</th><th>Capacity</th><th>Fuel</th><th>Runtime</th></tr></thead>
                <tbody>
                    ${elec.generators.map(g => renderGeneratorRow(g, isAdmin)).join('')}
                </tbody>
            </table>
        </div>
        
        <div class="section">
            <h3>TRANSFORMERS</h3>
            <table class="data-table">
                <thead><tr><th>Name</th><th>Capacity</th><th>Load</th><th>Voltage</th><th>Oil Temp</th><th>Winding Temp</th></tr></thead>
                <tbody>
                    ${elec.transformers.map(t => `
                        <tr>
                            <td><strong>${t.name}</strong></td>
                            <td>${t.capacity_kva} kVA</td>
                            <td><div class="bar-cell"><span>${t.load_pct.toFixed(0)}%</span><div class="mini-bar"><div class="mini-fill" style="width:${t.load_pct}%"></div></div></div></td>
                            <td>${t.secondary_voltage?.toFixed(0) || '--'} V</td>
                            <td>${t.oil_temp?.toFixed(1) || '--'}${currentTempUnit}</td>
                            <td>${t.winding_temp?.toFixed(1) || '--'}${currentTempUnit}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
    `;
    
    return html;
}

function renderSolarRow(s, isAdmin) {
    const path = s.point_path;
    const pct = s.capacity_kw > 0 ? (s.output_kw / s.capacity_kw * 100) : 0;
    return `
        <tr>
            <td><strong>${s.name}</strong></td>
            <td><div class="bar-cell">${clickablePoint(path + '.output_kw', s.output_kw, ' kW', 'Output', isAdmin, false)}<div class="mini-bar"><div class="mini-fill solar" style="width:${pct}%"></div></div></div></td>
            <td>${s.capacity_kw} kW</td>
            <td>${s.irradiance_w_m2?.toFixed(0) || '0'} W/m²</td>
            <td>${s.panel_temp?.toFixed(1) || '--'}${currentTempUnit}</td>
            <td>${s.output_kwh_today?.toFixed(1) || '0'} kWh</td>
        </tr>
    `;
}

function renderUPSRow(u, isAdmin) {
    const path = u.point_path;
    const batteryClass = u.battery_pct < 30 ? 'low' : '';
    return `
        <tr>
            <td><strong>${u.name}</strong></td>
            <td>${clickablePoint(path + '.status', u.status, '', 'Status', isAdmin, true, '', true)}</td>
            <td>${u.capacity_kva} kVA</td>
            <td><div class="bar-cell"><span>${u.load_pct?.toFixed(0) || '0'}%</span><div class="mini-bar"><div class="mini-fill" style="width:${u.load_pct || 0}%"></div></div></div></td>
            <td><div class="bar-cell ${batteryClass}"><span>${u.battery_pct?.toFixed(0) || '0'}%</span><div class="mini-bar"><div class="mini-fill battery" style="width:${u.battery_pct || 0}%"></div></div></div></td>
            <td>${u.battery_runtime_min?.toFixed(0) || '--'} min</td>
        </tr>
    `;
}

function renderGeneratorRow(g, isAdmin) {
    const path = g.point_path;
    return `
        <tr>
            <td><strong>${g.name}</strong></td>
            <td>${clickablePoint(path + '.status', g.status, '', 'Enable', isAdmin, true, '', true)}</td>
            <td>${g.output_kw?.toFixed(1) || '0'} kW</td>
            <td>${g.capacity_kw} kW</td>
            <td><div class="bar-cell"><span>${g.fuel_level_pct?.toFixed(0) || '--'}%</span><div class="mini-bar"><div class="mini-fill fuel" style="width:${g.fuel_level_pct || 0}%"></div></div></div></td>
            <td>${g.runtime_hours?.toFixed(0) || '0'} hrs</td>
        </tr>
    `;
}

// ============== DATA CENTER VIEW ==============

async function loadDataCenterData() {
    try {
        const response = await apiRequest(`${API_BASE}/api/datacenter`);
        if (!response) return;
        const dc = await response.json();
        document.getElementById('content-view').innerHTML = renderDataCenter(dc);
    } catch (error) { console.error('Failed to load data center data:', error); }
}

function renderDataCenter(dc) {
    if (!dc.enabled) return '<div class="view-header"><h2>Data Center not enabled</h2></div>';
    
    const isAdmin = currentUser?.role === 'admin';
    
    let html = `
        <div class="view-header">
            <h2>${dc.display_name}</h2>
            <div class="view-stats">
                <div class="stat"><span class="stat-value">${dc.total_it_load_kw?.toFixed(0) || '0'}</span><span class="stat-label">IT Load kW</span></div>
                <div class="stat"><span class="stat-value">${dc.total_cooling_kw?.toFixed(0) || '0'}</span><span class="stat-label">Cooling kW</span></div>
                <div class="stat"><span class="stat-value">${dc.pue?.toFixed(2) || '--'}</span><span class="stat-label">PUE</span></div>
                <div class="stat"><span class="stat-value">${dc.average_inlet_temp?.toFixed(0) || '--'}${currentTempUnit}</span><span class="stat-label">Avg Inlet</span></div>
            </div>
        </div>
        
        <div class="section">
            <h3>SERVER RACKS</h3>
            <table class="data-table">
                <thead><tr><th>Name</th><th>IT Load</th><th>Inlet</th><th>Outlet</th><th>Utilization</th><th>PDU A</th><th>PDU B</th></tr></thead>
                <tbody>
                    ${dc.server_racks.map(r => `
                        <tr>
                            <td><strong>${r.name}</strong></td>
                            <td>${r.it_load_kw?.toFixed(1) || '0'} kW</td>
                            <td>${r.inlet_temp?.toFixed(1) || '--'}${currentTempUnit}</td>
                            <td class="${r.outlet_temp > 95 ? 'temp-hot' : ''}">${r.outlet_temp?.toFixed(1) || '--'}${currentTempUnit}</td>
                            <td><div class="bar-cell"><span>${r.utilization_pct?.toFixed(0) || '0'}%</span><div class="mini-bar"><div class="mini-fill cpu" style="width:${r.utilization_pct || 0}%"></div></div></div></td>
                            <td>${r.pdu_a_kw?.toFixed(1) || '0'} kW</td>
                            <td>${r.pdu_b_kw?.toFixed(1) || '0'} kW</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
        
        <div class="section">
            <h3>CRAC UNITS</h3>
            <table class="data-table">
                <thead><tr><th>Name</th><th>Status</th><th>Supply</th><th>Return</th><th>Cooling</th><th>Fan</th><th>kW</th></tr></thead>
                <tbody>
                    ${dc.crac_units.map(c => {
                        const path = c.point_path;
                        return `
                            <tr>
                                <td><strong>${c.name}</strong></td>
                                <td>${clickablePoint(path + '.status', c.status, '', 'Enable', isAdmin, true, '', true)}</td>
                                <td>${clickablePoint(path + '.supply_air_temp', c.supply_air_temp, currentTempUnit, 'Supply Setpoint', isAdmin, true)}</td>
                                <td>${c.return_air_temp?.toFixed(1) || '--'}${currentTempUnit}</td>
                                <td>${c.cooling_output_pct?.toFixed(0) || '0'}%</td>
                                <td><div class="bar-cell">${clickablePoint(path + '.fan_speed_pct', c.fan_speed_pct, '%', 'Fan Speed', isAdmin, true)}<div class="mini-bar"><div class="mini-fill" style="width:${c.fan_speed_pct || 0}%"></div></div></div></td>
                                <td>${c.kw?.toFixed(1) || '0'}</td>
                            </tr>
                        `;
                    }).join('')}
                </tbody>
            </table>
        </div>
    `;
    
    return html;
}

// ============== WASTEWATER VIEW ==============

async function loadWastewaterData() {
    try {
        const response = await apiRequest(`${API_BASE}/api/wastewater`);
        if (!response) return;
        const ww = await response.json();
        document.getElementById('content-view').innerHTML = renderWastewater(ww);
    } catch (error) { console.error('Failed to load wastewater data:', error); }
}

function renderWastewater(ww) {
    if (!ww.enabled) return '<div class="view-header"><h2>Wastewater not enabled</h2></div>';
    
    const isAdmin = currentUser?.role === 'admin';
    
    let html = `
        <div class="view-header">
            <h2>${ww.display_name}</h2>
            <div class="view-stats">
                <div class="stat"><span class="stat-value">${ww.influent_flow_mgd?.toFixed(2) || '0'}</span><span class="stat-label">Influent MGD</span></div>
                <div class="stat"><span class="stat-value">${ww.effluent_flow_mgd?.toFixed(2) || '0'}</span><span class="stat-label">Effluent MGD</span></div>
                <div class="stat"><span class="stat-value">${ww.dissolved_oxygen_mg_l?.toFixed(1) || '--'}</span><span class="stat-label">DO mg/L</span></div>
                <div class="stat"><span class="stat-value">${ww.ph?.toFixed(1) || '--'}</span><span class="stat-label">pH</span></div>
                <div class="stat"><span class="stat-value">${ww.total_kw?.toFixed(0) || '0'}</span><span class="stat-label">Total kW</span></div>
            </div>
        </div>
        
        <div class="section">
            <h3>LIFT STATIONS</h3>
            <table class="data-table">
                <thead><tr><th>Name</th><th>Wet Well</th><th>Flow</th><th>Pumps Running</th><th>kW</th></tr></thead>
                <tbody>
                    ${ww.lift_stations.map(ls => {
                        const path = ls.point_path;
                        return `
                            <tr>
                                <td><strong>${ls.name}</strong></td>
                                <td>${ls.wet_well_level_ft?.toFixed(2) || '--'} ${currentHeadUnit}</td>
                                <td>${ls.flow_gpm?.toFixed(0) || '0'} ${currentFlowWaterUnit}</td>
                                <td>${clickablePoint(path + '.pumps_running', ls.pumps_running, '', 'Pumps Running', isAdmin, false)}</td>
                                <td>${ls.kw?.toFixed(1) || '0'}</td>
                            </tr>
                        `;
                    }).join('')}
                </tbody>
            </table>
        </div>
        
        <div class="section">
            <h3>AERATION BLOWERS</h3>
            <table class="data-table">
                <thead><tr><th>Name</th><th>Status</th><th>Speed</th><th>Output</th><th>Discharge Temp</th><th>kW</th></tr></thead>
                <tbody>
                    ${ww.blowers.map(b => {
                        const path = b.point_path;
                        return `
                            <tr>
                                <td><strong>${b.name}</strong></td>
                                <td>${clickablePoint(path + '.status', b.status, '', 'Enable', isAdmin, true, '', true)}</td>
                                <td><div class="bar-cell">${clickablePoint(path + '.speed_pct', b.speed_pct, '%', 'Speed', isAdmin, true)}<div class="mini-bar"><div class="mini-fill" style="width:${b.speed_pct || 0}%"></div></div></div></td>
                                <td>${b.output_scfm?.toFixed(0) || '0'} ${currentFlowAirUnit}</td>
                                <td>${b.discharge_temp?.toFixed(1) || '--'}${currentTempUnit}</td>
                                <td>${b.kw?.toFixed(1) || '0'}</td>
                            </tr>
                        `;
                    }).join('')}
                </tbody>
            </table>
        </div>
        
        <div class="section">
            <h3>CLARIFIERS</h3>
            <table class="data-table">
                <thead><tr><th>Name</th><th>Type</th><th>Flow</th><th>Sludge Blanket</th><th>Torque</th><th>TSS</th></tr></thead>
                <tbody>
                    ${ww.clarifiers.map(c => `
                        <tr>
                            <td><strong>${c.name}</strong></td>
                            <td><span class="tag">${c.clarifier_type}</span></td>
                            <td>${c.flow_mgd?.toFixed(2) || '0'} MGD</td>
                            <td>${c.sludge_blanket_ft?.toFixed(2) || '--'} ${currentHeadUnit}</td>
                            <td>${c.torque_pct?.toFixed(1) || '0'}%</td>
                            <td>${c.effluent_tss_mg_l?.toFixed(1) || '--'} mg/L</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
        
        <div class="section">
            <h3>UV DISINFECTION</h3>
            <table class="data-table">
                <thead><tr><th>Name</th><th>Status</th><th>Intensity</th><th>Lamp Life</th><th>kW</th><th>E.coli MPN</th></tr></thead>
                <tbody>
                    ${ww.uv_systems.map(uv => {
                        const path = uv.point_path;
                        return `
                            <tr>
                                <td><strong>${uv.name}</strong></td>
                                <td>${clickablePoint(path + '.status', uv.status, '', 'Enable', isAdmin, true, '', true)}</td>
                                <td>${clickablePoint(path + '.uv_intensity_pct', uv.uv_intensity_pct, '%', 'Intensity', isAdmin, true)}</td>
                                <td><div class="bar-cell"><span>${uv.lamp_life_remaining_pct?.toFixed(0) || '0'}%</span><div class="mini-bar"><div class="mini-fill" style="width:${uv.lamp_life_remaining_pct || 0}%"></div></div></div></td>
                                <td>${uv.kw?.toFixed(1) || '0'}</td>
                                <td>${uv.effluent_ecoli_mpn?.toFixed(0) || '0'}</td>
                            </tr>
                        `;
                    }).join('')}
                </tbody>
            </table>
        </div>
    `;
    
    return html;
}

// ============== HELPER FUNCTIONS ==============

// Format boolean values with statusText and color
function formatBooleanValue(value) {
    // Handle various boolean representations
    if (value === true || value === 1 || value === '1' || value === 'ON' || value === 'running' || value === 'online' || value === 'enabled') {
        return { text: 'On', class: 'bool-on' };
    } else if (value === false || value === 0 || value === '0' || value === 'OFF' || value === 'stopped' || value === 'offline' || value === 'disabled') {
        return { text: 'Off', class: 'bool-off' };
    }
    return null; // Not a boolean
}

// Create a clickable point value that shows an action popup when clicked (for admin)
function clickablePoint(path, value, unit, name, isAdmin, writable, extraClass = '', isBoolean = false) {
    const overridden = isOverridden(path);
    const overrideClass = overridden ? 'point-overridden' : '';
    const clickableClass = (isAdmin && writable) ? 'point-clickable' : '';
    
    // Check if this is a boolean value
    const boolFormat = isBoolean ? formatBooleanValue(value) : null;
    let displayValue, statusClass;
    
    if (boolFormat) {
        displayValue = boolFormat.text;
        statusClass = `status-badge ${boolFormat.class}`;
    } else if (extraClass) {
        displayValue = value != null ? (typeof value === 'number' ? value.toFixed(1) : value) : '--';
        statusClass = `status-badge ${extraClass}`;
    } else {
        displayValue = value != null ? (typeof value === 'number' ? value.toFixed(1) : value) : '--';
        statusClass = '';
    }
    
    if (isAdmin && writable) {
        const clickValue = boolFormat ? (boolFormat.text === 'On' ? 1 : 0) : (value || 0);
        return `<span class="${clickableClass} ${overrideClass} ${statusClass}" onclick="showPointAction('${path}', ${clickValue}, '${name}', event)" title="Click to override">${displayValue}${unit}${overridden ? ' [!]' : ''}</span>`;
    } else if (statusClass) {
        return `<span class="${statusClass}">${displayValue}${unit}</span>`;
    } else {
        return `<span class="${overrideClass}">${displayValue}${unit}${overridden ? ' [!]' : ''}</span>`;
    }
}

// Show an inline action popup at the click location
function showPointAction(path, currentValue, name, event) {
    event.stopPropagation();
    
    // Remove any existing popup
    const existing = document.querySelector('.action-popup');
    if (existing) existing.remove();
    
    const overridden = isOverridden(path);
    
    const popup = document.createElement('div');
    popup.className = 'action-popup';
    popup.innerHTML = `
        <div class="popup-header">
            <span class="popup-name">${name}</span>
            <button class="popup-close" onclick="this.closest('.action-popup').remove()">&times;</button>
        </div>
        <div class="popup-path">${path}</div>
        <div class="popup-actions">
            ${overridden 
                ? `<button class="btn btn-release" onclick="releaseOverride('${path}'); this.closest('.action-popup').remove();">[A] Auto</button>
                   <button class="btn btn-override" onclick="this.closest('.action-popup').remove(); showQuickOverride('${path}', ${currentValue}, '${name}');">[M] Modify</button>`
                : `<button class="btn btn-override" onclick="this.closest('.action-popup').remove(); showQuickOverride('${path}', ${currentValue}, '${name}');">[!] Override</button>`
            }
        </div>
    `;
    
    // Position popup near the click
    document.body.appendChild(popup);
    const rect = event.target.getBoundingClientRect();
    popup.style.position = 'fixed';
    popup.style.top = (rect.bottom + 5) + 'px';
    popup.style.left = rect.left + 'px';
    popup.style.zIndex = '10000';
    
    // Close on click outside
    setTimeout(() => {
        document.addEventListener('click', function closePopup(e) {
            if (!popup.contains(e.target)) {
                popup.remove();
                document.removeEventListener('click', closePopup);
            }
        });
    }, 100);
}

function pointRow(path, name, value, unit, isAdmin, writablePoint = null) {
    // This function is kept for backwards compatibility but now uses clickablePoint
    const displayValue = value != null ? (typeof value === 'number' ? value.toFixed(1) : value) : '--';
    const overridden = isOverridden(path);
    const overrideClass = overridden ? 'overridden' : '';
    
    return `
        <tr class="${overrideClass}">
            <td>${name}</td>
            <td class="value-cell">${clickablePoint(path, value, unit, name, isAdmin, writablePoint)}</td>
        </tr>
    `;
}

function renderPoint(path, value, unit, isAdmin, writable = false, writablePoint = null) {
    const displayValue = value != null ? (typeof value === 'number' ? value.toFixed(1) : value) : '--';
    const overridden = isOverridden(path);
    
    if (overridden) {
        return `<span class="overridden-value" title="Overridden - Click to release" onclick="${isAdmin ? `releaseOverride('${path}')` : ''}">${displayValue}${unit} [!]</span>`;
    }
    return `${displayValue}${unit}`;
}

function getTempClass(temp) {
    if (temp < 68) return 'temp-cold';
    if (temp < 72) return 'temp-cool';
    if (temp < 76) return 'temp-warm';
    return 'temp-hot';
}

function getDamperColor(position) {
    const style = getComputedStyle(document.documentElement);
    if (position < 10) return style.getPropertyValue('--text-muted').trim() || '#94a3b8';
    if (position < 50) return style.getPropertyValue('--warning').trim() || '#f59e0b';
    return style.getPropertyValue('--success').trim() || '#22c55e';
}

// ============== OVERRIDE FUNCTIONS ==============

function showQuickOverride(pointPath, currentValue, pointName) {
    const overridden = isOverridden(pointPath);
    
    const modal = document.createElement('div');
    modal.className = 'quick-override-modal';
    modal.innerHTML = `
        <div class="qo-backdrop" onclick="closeQuickOverride()"></div>
        <div class="qo-popup">
            <div class="qo-header">
                <h4>${overridden ? 'Modify' : 'Set'} Override</h4>
                <button class="qo-close" onclick="closeQuickOverride()">&times;</button>
            </div>
            <div class="qo-body">
                <div class="qo-point-name">${pointName}</div>
                <div class="qo-point-path">${pointPath}</div>
                <div class="qo-field">
                    <label>Value:</label>
                    <input type="number" id="qo-value" value="${overridden ? getOverrideValue(pointPath) : currentValue}" step="0.1">
                </div>
                <div class="qo-field">
                    <label>Priority (1-16):</label>
                    <input type="number" id="qo-priority" value="8" min="1" max="16">
                </div>
                <div class="qo-field">
                    <label>Duration (seconds, blank=permanent):</label>
                    <input type="number" id="qo-duration" placeholder="Permanent">
                </div>
            </div>
            <div class="qo-footer">
                ${overridden ? `<button class="btn btn-release" onclick="releaseOverride('${pointPath}'); closeQuickOverride();">[R] Release</button>` : ''}
                <button class="btn btn-cancel" onclick="closeQuickOverride()">Cancel</button>
                <button class="btn btn-override" onclick="submitQuickOverride('${pointPath}')">[!] ${overridden ? 'Update' : 'Override'}</button>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
    document.getElementById('qo-value').focus();
}

function closeQuickOverride() {
    const modal = document.querySelector('.quick-override-modal');
    if (modal) modal.remove();
}

async function submitQuickOverride(pointPath) {
    const value = parseFloat(document.getElementById('qo-value').value);
    const priority = parseInt(document.getElementById('qo-priority').value) || 8;
    const durationInput = document.getElementById('qo-duration').value;
    const duration = durationInput ? parseInt(durationInput) : null;
    
    if (isNaN(value)) {
        alert('Please enter a valid numeric value.');
        return;
    }
    
    try {
        const response = await apiRequest(`${API_BASE}/api/override/set`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                point_path: pointPath,
                value: value,
                priority: priority,
                duration_seconds: duration
            })
        });
        
        if (response && response.ok) {
            const result = await response.json();
            if (result.success) {
                closeQuickOverride();
                loadOverrides();
                refreshCurrentView();
            } else {
                alert('Failed: ' + (result.error || 'Unknown error'));
            }
        }
    } catch (error) {
        console.error('Error setting override:', error);
        alert('Error: ' + error.message);
    }
}

async function releaseOverride(pointPath) {
    try {
        const response = await apiRequest(`${API_BASE}/api/override/release`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ point_path: pointPath })
        });
        
        if (response && response.ok) {
            loadOverrides();
            refreshCurrentView();
        }
    } catch (error) {
        console.error('Error releasing override:', error);
    }
}

function showAllOverrides() {
    const count = Object.keys(activeOverrides).length;
    
    if (count === 0) {
        alert('No active overrides.');
        return;
    }
    
    let rows = '';
    for (const [path, priorities] of Object.entries(activeOverrides)) {
        const lowestPriority = Math.min(...Object.keys(priorities).map(Number));
        const info = priorities[lowestPriority];
        rows += `
            <tr>
                <td title="${path}">${path.length > 50 ? '...' + path.slice(-47) : path}</td>
                <td>${info.value}</td>
                <td>${lowestPriority}</td>
                <td>${info.source}</td>
                <td><button class="btn-sm btn-release" onclick="releaseOverride('${path}'); closeAllOverridesModal();">Release</button></td>
            </tr>
        `;
    }
    
    const modal = document.createElement('div');
    modal.className = 'quick-override-modal';
    modal.id = 'all-overrides-modal';
    modal.innerHTML = `
        <div class="qo-backdrop" onclick="closeAllOverridesModal()"></div>
        <div class="qo-popup qo-wide">
            <div class="qo-header">
                <h4>Active Overrides (${count})</h4>
                <button class="qo-close" onclick="closeAllOverridesModal()">&times;</button>
            </div>
            <div class="qo-body">
                <table class="data-table">
                    <thead><tr><th>Point</th><th>Value</th><th>Priority</th><th>Source</th><th>Action</th></tr></thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>
            <div class="qo-footer">
                <button class="btn btn-cancel" onclick="closeAllOverridesModal()">Close</button>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
}

function closeAllOverridesModal() {
    const modal = document.getElementById('all-overrides-modal');
    if (modal) modal.remove();
}
