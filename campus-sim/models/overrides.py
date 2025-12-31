import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional, Tuple

# Configure logging
logger = logging.getLogger("CampusEngine")

@dataclass
class PointOverride:
    """Represents an override on a point."""
    value: float
    priority: int = 8  # BACnet-style priority (1-16, lower = higher priority)
    timestamp: datetime = field(default_factory=datetime.now)
    expires: Optional[datetime] = None  # None = no expiration
    source: str = "manual"  # Who/what set the override
    
    def is_expired(self) -> bool:
        """Check if the override has expired."""
        if self.expires is None:
            return False
        return datetime.now() > self.expires


class OverrideManager:
    """
    Centralized override management for all points in the system.
    Supports priority-based overrides similar to BACnet priority arrays.
    """
    
    def __init__(self):
        self._overrides: Dict[str, Dict[int, PointOverride]] = {}  # point_path -> {priority -> override}
        self._lock = threading.Lock()
    
    def set_override(self, point_path: str, value: float, priority: int = 8,
                     duration_seconds: Optional[int] = None, source: str = "manual") -> bool:
        """
        Set an override on a point.
        
        Args:
            point_path: Full path to the point (e.g., "Building_1.AHU_1.VAV_1.setpoint")
            value: Override value
            priority: Priority level (1-16, lower = higher priority)
            duration_seconds: Optional duration in seconds (None = permanent)
            source: Source of the override
            
        Returns:
            True if override was set successfully
        """
        if priority < 1 or priority > 16:
            return False
            
        expires = None
        if duration_seconds:
            expires = datetime.now()
            from datetime import timedelta
            expires = expires + timedelta(seconds=duration_seconds)
        
        override = PointOverride(
            value=value,
            priority=priority,
            timestamp=datetime.now(),
            expires=expires,
            source=source
        )
        
        with self._lock:
            if point_path not in self._overrides:
                self._overrides[point_path] = {}
            self._overrides[point_path][priority] = override
            
        logger.info(f"Override set: {point_path} = {value} (priority {priority}, source: {source})")
        return True
    
    def release_override(self, point_path: str, priority: Optional[int] = None) -> bool:
        """
        Release an override on a point.
        
        Args:
            point_path: Full path to the point
            priority: Specific priority to release (None = release all)
            
        Returns:
            True if any override was released
        """
        with self._lock:
            if point_path not in self._overrides:
                return False
            
            if priority is None:
                # Release all overrides for this point
                del self._overrides[point_path]
                logger.info(f"All overrides released: {point_path}")
                return True
            elif priority in self._overrides[point_path]:
                del self._overrides[point_path][priority]
                if not self._overrides[point_path]:
                    del self._overrides[point_path]
                logger.info(f"Override released: {point_path} (priority {priority})")
                return True
        return False
    
    def get_override(self, point_path: str) -> Optional[Tuple[float, int]]:
        """
        Get the active override value for a point (highest priority non-expired).
        
        Returns:
            Tuple of (value, priority) or None if no active override
        """
        with self._lock:
            if point_path not in self._overrides:
                return None
            
            # Clean expired overrides and find highest priority
            active_overrides = {}
            for priority, override in list(self._overrides[point_path].items()):
                if override.is_expired():
                    del self._overrides[point_path][priority]
                else:
                    active_overrides[priority] = override
            
            if not active_overrides:
                del self._overrides[point_path]
                return None
            
            # Return highest priority (lowest number)
            highest_priority = min(active_overrides.keys())
            return (active_overrides[highest_priority].value, highest_priority)
    
    def get_all_overrides(self) -> Dict[str, Dict]:
        """Get all active overrides with their details."""
        result = {}
        with self._lock:
            for point_path, priorities in list(self._overrides.items()):
                active = {}
                for priority, override in list(priorities.items()):
                    if not override.is_expired():
                        active[priority] = {
                            'value': override.value,
                            'priority': override.priority,
                            'timestamp': override.timestamp.isoformat(),
                            'expires': override.expires.isoformat() if override.expires else None,
                            'source': override.source
                        }
                if active:
                    result[point_path] = active
        return result
    
    def get_point_override_info(self, point_path: str) -> Optional[Dict]:
        """Get detailed override info for a specific point."""
        with self._lock:
            if point_path not in self._overrides:
                return None
            
            result = {}
            for priority, override in self._overrides[point_path].items():
                if not override.is_expired():
                    result[priority] = {
                        'value': override.value,
                        'priority': override.priority,
                        'timestamp': override.timestamp.isoformat(),
                        'expires': override.expires.isoformat() if override.expires else None,
                        'source': override.source
                    }
            return result if result else None


# Global override manager instance
_override_manager: Optional[OverrideManager] = None

def get_override_manager() -> OverrideManager:
    """Get the global override manager instance."""
    global _override_manager
    if _override_manager is None:
        _override_manager = OverrideManager()
    return _override_manager
