import time
import random
import math
import logging
from typing import Any
from .types import ScenarioType

logger = logging.getLogger("ScenarioManager")

class ScenarioManager:
    """
    Manages active scenarios (weather events, disasters) that override normal physics.
    """
    def __init__(self, engine: Any):
        self._engine = engine
        self._active_scenario = ScenarioType.NORMAL
        self._scenario_start_time = 0
        self._scenario_duration = 0
        self._auto_change_frequency = 0 # Seconds, 0 = disabled
        self._last_auto_change = time.time()
    
    def start_scenario(self, scenario_type: ScenarioType, duration: int = 300):
        """Start a specific scenario for a duration in seconds."""
        self._active_scenario = scenario_type
        self._scenario_start_time = time.time()
        self._scenario_duration = duration
        logger.info(f"Started scenario: {scenario_type.value} for {duration} seconds")
        
        # Reset any previous effects immediately
        if self._engine.electrical_system:
            self._engine.electrical_system.utility_available = True

    def update(self):
        """Update scenario state and apply effects."""
        # Auto scenario change logic
        if self._auto_change_frequency > 0:
            if time.time() - self._last_auto_change > self._auto_change_frequency:
                self._last_auto_change = time.time()
                # Pick a random scenario
                # 70% chance of NORMAL, 30% chance of something else
                if random.random() < 0.7:
                    new_scenario = ScenarioType.NORMAL
                else:
                    options = [s for s in ScenarioType if s != ScenarioType.NORMAL]
                    new_scenario = random.choice(options)
                
                # Start new scenario (or switch to normal)
                if new_scenario == ScenarioType.NORMAL:
                    self.stop_scenario()
                else:
                    self.start_scenario(new_scenario, duration=self._auto_change_frequency)

        if self._active_scenario == ScenarioType.NORMAL:
            return

        elapsed = time.time() - self._scenario_start_time
        if elapsed > self._scenario_duration:
            self.stop_scenario()
            return

        # Apply scenario effects
        if self._active_scenario == ScenarioType.SNOW:
            # Override OAT to freezing (20-30F)
            # Accessing private member _oat - should ideally use a setter
            self._engine._oat = 25.0 + math.sin(elapsed / 20) * 2.0
        
        elif self._active_scenario == ScenarioType.RAINSTORM:
            # Heavy rain - moderate cooling, no power issues
            # Drop temp to ~60-65F
            target_temp = 62.0
            if self._engine._oat > target_temp:
                self._engine._oat -= 0.5  # Gradual cooling
            
            # Increase humidity (implied by cooling load increase in future)
            
        elif self._active_scenario == ScenarioType.WINDSTORM:
            # High winds - erratic temperature readings (wind chill)
            noise = random.uniform(-3.0, 3.0)
            self._engine._oat += noise
            
            # Power flickers (brief outages) due to lines swaying
            if random.random() < 0.08: # 8% chance per tick
                if self._engine.electrical_system:
                    self._engine.electrical_system.utility_available = False
            else:
                if self._engine.electrical_system:
                    self._engine.electrical_system.utility_available = True

        elif self._active_scenario == ScenarioType.THUNDERSTORM:
            # Severe storm - Power outage
            # Grid failure after 15 seconds
            if elapsed > 15:
                if self._engine.electrical_system:
                    self._engine.electrical_system.utility_available = False
            
            # Rapid temp drop
            self._engine._oat -= 0.2  # Fast drop per tick

    def stop_scenario(self):
        """Stop the current scenario."""
        self._active_scenario = ScenarioType.NORMAL
        if self._engine.electrical_system:
            self._engine.electrical_system.utility_available = True
        logger.info("Scenario ended, returning to normal operation")
        
    @property
    def active_scenario(self) -> str:
        return self._active_scenario.value
