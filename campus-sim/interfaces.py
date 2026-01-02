"""
Abstract interfaces following Interface Segregation Principle (ISP) and 
Dependency Inversion Principle (DIP).
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Protocol
from dataclasses import dataclass


class Updatable(ABC):
    """Interface for components that can be updated in the physics loop."""
    
    @abstractmethod
    def update(self, oat: float, dt: float) -> None:
        """Update the component state."""
        pass


class PointProvider(ABC):
    """Interface for components that expose readable points."""
    
    @abstractmethod
    def get_points(self) -> Dict[str, float]:
        """Return a dictionary of point names to values."""
        pass


@dataclass
class PointDefinition:
    """Metadata for a simulation point."""
    name: str
    units: str
    writable: bool = False
    description: str = ""
    bacnet_object_type: str = "AI"  # AI, AO, BI, BO, AV, BV
    internal_key: str = ""  # Key in get_points() dict
    bacnet_address: str = "" # e.g. "AV:3020" or just "3020" if type is inferred


class PointMetadataProvider(ABC):
    """Interface for components that provide metadata about their points."""
    
    @abstractmethod
    def get_point_definitions(self) -> List[PointDefinition]:
        """Return a list of point definitions."""
        pass


class ProtocolServer(ABC):
    """
    Abstract base class for protocol servers (SRP + OCP).
    New protocols can be added by extending this class without modifying existing code.
    """
    
    @abstractmethod
    def start(self) -> None:
        """Start the protocol server."""
        pass
    
    @abstractmethod
    def stop(self) -> None:
        """Stop the protocol server."""
        pass
    
    @abstractmethod
    def register_point(self, name: str, initial_value: float, writable: bool = False) -> None:
        """Register a new point with the server."""
        pass
    
    @abstractmethod
    def update_point(self, name: str, value: float) -> None:
        """Update a point's value."""
        pass
    
    @abstractmethod
    def get_point(self, name: str) -> float:
        """Get a point's current value."""
        pass


class PhysicsEngine(ABC):
    """Interface for physics simulation engines."""
    
    @abstractmethod
    def start(self) -> None:
        """Start the physics simulation."""
        pass
    
    @abstractmethod
    def stop(self) -> None:
        """Stop the physics simulation."""
        pass
    
    @property
    @abstractmethod
    def oat(self) -> float:
        """Get the current outside air temperature."""
        pass


@dataclass
class CampusSizeConfig:
    """
    Configuration for campus size (OCP - extensible without modification).
    New sizes can be added by creating new instances.
    """
    name: str
    num_buildings: int
    num_ahus_per_building: int
    num_vavs_per_ahu: int

    @classmethod
    def small(cls) -> 'CampusSizeConfig':
        return cls("Small", 1, 2, 5)
    
    @classmethod
    def medium(cls) -> 'CampusSizeConfig':
        return cls("Medium", 2, 5, 10)
    
    @classmethod
    def large(cls) -> 'CampusSizeConfig':
        return cls("Large", 5, 10, 20)

    @classmethod
    def huge(cls) -> 'CampusSizeConfig':
        return cls("Huge", 10, 15, 25)

    @classmethod
    def massive(cls) -> 'CampusSizeConfig':
        return cls("Massive", 20, 20, 30)
    
    @classmethod
    def from_string(cls, size: str) -> 'CampusSizeConfig':
        """Factory method to create config from string."""
        configs = {
            "Small": cls.small,
            "Medium": cls.medium,
            "Large": cls.large,
            "Huge": cls.huge,
            "Massive": cls.massive,
        }
        factory = configs.get(size, cls.small)
        return factory()


class PointRegistry:
    """
    Registry for tracking all points across the system (SRP).
    Centralizes point management separate from protocol handling.
    """
    
    def __init__(self):
        self._points: Dict[str, Dict[str, Any]] = {}
    
    def register(self, name: str, initial_value: float, writable: bool = False,
                 source_obj: Any = None, source_attr: str = None) -> None:
        """Register a point with metadata."""
        self._points[name] = {
            'value': initial_value,
            'writable': writable,
            'source_obj': source_obj,
            'source_attr': source_attr,
        }
    
    def update(self, name: str, value: float) -> None:
        """Update a point's value."""
        if name in self._points:
            self._points[name]['value'] = value
    
    def get(self, name: str) -> float:
        """Get a point's value."""
        return self._points.get(name, {}).get('value', 0.0)
    
    def get_all(self) -> Dict[str, float]:
        """Get all points as name -> value dict."""
        return {name: data['value'] for name, data in self._points.items()}
    
    def items(self):
        """Iterate over all points."""
        return self._points.items()
