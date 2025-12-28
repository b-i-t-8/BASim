import math
from abc import ABC, abstractmethod
from typing import Dict, Tuple
from dataclasses import dataclass

@dataclass
class WeatherConditions:
    oat: float  # Fahrenheit
    humidity: float  # % RH
    wet_bulb: float  # Fahrenheit
    dew_point: float  # Fahrenheit
    enthalpy: float  # BTU/lb
    pressure: float = 29.92  # inHg

def calculate_psychrometrics(t_f: float, rh: float, pressure_inhg: float = 29.92) -> WeatherConditions:
    """
    Calculate psychrometric properties based on Temp (F) and RH (%).
    """
    # Convert T to Celsius for standard formulas
    t_c = (t_f - 32) * 5/9
    
    # Saturation Vapor Pressure (hPa) - Magnus formula
    es = 6.112 * math.exp((17.67 * t_c) / (t_c + 243.5))
    
    # Actual Vapor Pressure (hPa)
    e = es * (rh / 100.0)
    
    # Dew Point (Celsius)
    try:
        alpha = math.log(e / 6.112)
        t_dp_c = (alpha * 243.5) / (17.67 - alpha)
        t_dp_f = (t_dp_c * 9/5) + 32
    except ValueError:
        t_dp_f = t_f # Low humidity edge case
        
    # Humidity Ratio (W) - lb H2O / lb dry air
    # P_atm in hPa
    p_atm_hpa = pressure_inhg * 33.8639
    
    # W = 0.622 * e / (P - e)
    w = 0.622 * e / (p_atm_hpa - e)
    
    # Enthalpy (BTU/lb)
    # h = 0.24 * T_f + W * (1061 + 0.444 * T_f)
    h = 0.24 * t_f + w * (1061 + 0.444 * t_f)
    
    # Wet Bulb (Stull's approximation)
    term1 = t_c * math.atan(0.151977 * math.sqrt(rh + 8.313659))
    term2 = math.atan(t_c + rh)
    term3 = math.atan(rh - 1.676331)
    term4 = 0.00391838 * (rh**1.5) * math.atan(0.023101 * rh)
    t_wb_c = term1 + term2 - term3 + term4 - 4.686035
    t_wb_f = (t_wb_c * 9/5) + 32
    
    return WeatherConditions(
        oat=t_f,
        humidity=rh,
        wet_bulb=t_wb_f,
        dew_point=t_dp_f,
        enthalpy=h,
        pressure=pressure_inhg
    )

# Monthly average High/Low temperatures (Fahrenheit) for Nashville, TN
# Index 0 = January, 11 = December
NASHVILLE_ALMANAC = [
    (47, 28), # Jan
    (52, 31), # Feb
    (61, 39), # Mar
    (70, 47), # Apr
    (78, 57), # May
    (85, 65), # Jun
    (89, 69), # Jul
    (88, 68), # Aug
    (82, 61), # Sep
    (71, 49), # Oct
    (59, 39), # Nov
    (49, 31)  # Dec
]

class OATCalculator(ABC):
    """
    Abstract OAT calculator (OCP - extensible for different weather models).
    """
    
    @abstractmethod
    def calculate(self, current_time: float, latitude: float, day_of_year: int = 1) -> float:
        """Calculate outside air temperature."""
        pass

    def calculate_conditions(self, current_time: float, latitude: float, day_of_year: int = 1) -> WeatherConditions:
        """Calculate full weather conditions. Default implementation uses 50% RH."""
        oat = self.calculate(current_time, latitude, day_of_year)
        return calculate_psychrometrics(oat, 50.0)

class AlmanacOATCalculator(OATCalculator):
    """
    OAT calculator based on monthly almanac data.
    Interpolates between monthly averages for daily highs/lows,
    then simulates a daily cycle.
    """
    
    def __init__(self, almanac_data: list = None):
        self._almanac = almanac_data or NASHVILLE_ALMANAC
        self._days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
        # Cumulative days at start of each month
        self._month_starts = [0] * 12
        current = 0
        for i, days in enumerate(self._days_in_month):
            self._month_starts[i] = current
            current += days
            
    def _get_monthly_stats(self, day_of_year: int) -> Tuple[float, float]:
        """Get interpolated high/low for the specific day."""
        # Handle wrap around for interpolation
        day_of_year = max(1, min(365, day_of_year))
        
        # Find current month
        month_idx = 0
        for i, start in enumerate(self._month_starts):
            if day_of_year > start:
                month_idx = i
            else:
                break
                
        # Get current month stats
        curr_high, curr_low = self._almanac[month_idx]
        
        # Get next month stats (wrap to Jan)
        next_idx = (month_idx + 1) % 12
        next_high, next_low = self._almanac[next_idx]
        
        # Interpolate based on progress through the month
        day_in_month = day_of_year - self._month_starts[month_idx]
        progress = day_in_month / self._days_in_month[month_idx]
        
        daily_high = curr_high + (next_high - curr_high) * progress
        daily_low = curr_low + (next_low - curr_low) * progress
        
        return daily_high, daily_low

    def calculate(self, current_time: float, latitude: float, day_of_year: int = 1) -> float:
        daily_high, daily_low = self._get_monthly_stats(day_of_year)
        
        # Calculate time of day (0-1)
        seconds_in_day = current_time % 86400
        hour = seconds_in_day / 3600.0
        
        # Simple diurnal cycle
        # Low at 5 AM, High at 3 PM (15:00)
        # Map 5 AM to -PI/2 (sin = -1), 3 PM to PI/2 (sin = 1)
        
        # Shift hour so 5 AM is 0, 15:00 is 10
        # Cycle is 24 hours
        
        # Using a sinusoidal approximation
        # Peak at 15:00 (3 PM), Trough at 03:00 (3 AM) roughly
        # cos((t - 15) * 2pi / 24) -> 1 at 15, -1 at 3
        
        # Normalized wave (-1 to 1)
        wave = math.cos((hour - 15) * 2 * math.pi / 24)
        
        # Map -1..1 to Low..High
        # Temp = Avg + (Range/2) * wave
        avg_temp = (daily_high + daily_low) / 2
        half_range = (daily_high - daily_low) / 2
        
        return avg_temp + (half_range * wave)

    def calculate_conditions(self, current_time: float, latitude: float, day_of_year: int = 1) -> WeatherConditions:
        oat = self.calculate(current_time, latitude, day_of_year)
        
        # Calculate time of day (0-1)
        seconds_in_day = current_time % 86400
        hour = seconds_in_day / 3600.0
        
        # Simulate RH based on diurnal cycle (inverse to temp)
        # Peak RH at 5 AM (approx 90%), Low RH at 3 PM (approx 40-60%)
        
        # Wave from -1 (at 3 AM) to 1 (at 3 PM)
        wave = math.cos((hour - 15) * 2 * math.pi / 24)
        
        # RH Wave: Peak at 5 AM, Low at 3 PM
        # Shifted wave: Peak at 5 AM -> cos((5-5)*...) = 1
        rh_wave = math.cos((hour - 5) * 2 * math.pi / 24)
        
        # Base RH varies by season (Summer humid, Winter dry?)
        # Actually Nashville is humid in summer.
        # Let's assume:
        # Summer: 90% night, 50% day
        # Winter: 80% night, 40% day
        
        # Simple model:
        max_rh = 90.0
        min_rh = 50.0
        
        avg_rh = (max_rh + min_rh) / 2
        half_range_rh = (max_rh - min_rh) / 2
        
        rh = avg_rh + (half_range_rh * rh_wave)
        rh = max(0, min(100, rh))
        
        return calculate_psychrometrics(oat, rh)


class SinusoidalOATCalculator(OATCalculator):
    """Simple sinusoidal OAT model based on time of day and season."""
    
    def __init__(self, base_temp: float = 70.0, swing: float = 15.0):
        self._base_temp = base_temp
        self._swing = swing
        self._day_length = 86400
    
    def calculate(self, current_time: float, latitude: float, day_of_year: int = 1) -> float:
        time_of_day = (current_time % self._day_length) / self._day_length
        
        # Seasonal variation (Winter ~30F, Summer ~90F base)
        # Cosine wave peaking in summer (Day ~180)
        seasonal_offset = -20.0 * math.cos(2 * math.pi * (day_of_year - 172) / 365)
        
        # Adjust base temp for latitude
        adjusted_base = self._base_temp + seasonal_offset - (abs(latitude) - 30) * 0.5
        
        # Daily Sin wave: Peak at 3 PM (0.625)
        sun_factor = math.sin((time_of_day - 0.25) * 2 * math.pi)
        
        return adjusted_base + (sun_factor * self._swing)
