from enum import Enum

class CampusType(Enum):
    UNIVERSITY = "University"
    CORPORATE = "Corporate"
    HOSPITAL = "Hospital"
    DATA_CENTER = "Data Center"
    MIXED_USE = "Mixed Use"

class ScenarioType(Enum):
    NORMAL = "Normal"
    RAINSTORM = "Rainstorm"
    WINDSTORM = "Windstorm"
    THUNDERSTORM = "Thunderstorm"
    SNOW = "Snow"
