from typing import Dict, Any, List
from datetime import datetime, timedelta
from enum import Enum
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class ServiceStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"

class HealthCheck:
    def __init__(self, name: str):
        self.name = name
        self.last_check: datetime = datetime.min
        self.status: ServiceStatus = ServiceStatus.UNHEALTHY
        self.details: Dict[str, Any] = {}
    
    def update(self, status: ServiceStatus, details: Dict[str, Any]) -> None:
        self.last_check = datetime.now()
        self.status = status
        self.details = details
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "lastCheck": self.last_check.isoformat(),
            "details": self.details
        }

class HealthMonitor:
    def __init__(self, status_file: Path):
        self.status_file = status_file
        self.checks: Dict[str, HealthCheck] = {}
    
    def register_check(self, name: str) -> HealthCheck:
        """Register a new health check"""
        check = HealthCheck(name)
        self.checks[name] = check
        return check
    
    def update_check(self, name: str, status: ServiceStatus, details: Dict[str, Any]) -> None:
        """Update the status of a health check"""
        if name not in self.checks:
            self.register_check(name)
        self.checks[name].update(status, details)
        self._save_status()
    
    def get_overall_status(self) -> ServiceStatus:
        """Get the overall system status"""
        if not self.checks:
            return ServiceStatus.UNHEALTHY
        
        has_degraded = False
        for check in self.checks.values():
            if check.status == ServiceStatus.UNHEALTHY:
                return ServiceStatus.UNHEALTHY
            elif check.status == ServiceStatus.DEGRADED:
                has_degraded = True
        
        return ServiceStatus.DEGRADED if has_degraded else ServiceStatus.HEALTHY
    
    def _save_status(self) -> None:
        """Save current status to file"""
        try:
            status = {
                "timestamp": datetime.now().isoformat(),
                "overall": self.get_overall_status(),
                "checks": [check.to_dict() for check in self.checks.values()]
            }
            self.status_file.write_text(json.dumps(status, indent=2))
        except Exception as e:
            logger.error(f"Failed to save health status: {e}")
    
    def get_unhealthy_services(self) -> List[str]:
        """Get list of unhealthy services"""
        return [name for name, check in self.checks.items() 
                if check.status == ServiceStatus.UNHEALTHY]
