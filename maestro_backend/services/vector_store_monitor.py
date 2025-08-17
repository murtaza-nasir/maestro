#!/usr/bin/env python3
"""
Vector Store Health Monitor
Monitors ChromaDB vector store for corruption, size issues, and performance problems.
"""

import os
import sys
import time
import json
import asyncio
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, Tuple, Optional
import shutil

# Add parent directory to path
sys.path.insert(0, '/app')

from ai_researcher.core_rag.vector_store_safe import SafeVectorStore

logger = logging.getLogger(__name__)


class VectorStoreMonitor:
    """
    Monitors vector store health and prevents corruption.
    """
    
    def __init__(
        self,
        vector_store_path: str = "/app/ai_researcher/data/vector_store",
        check_interval_minutes: int = 30,
        max_size_gb: float = 50.0,
        auto_cleanup: bool = False
    ):
        self.vector_store_path = Path(vector_store_path)
        self.check_interval = check_interval_minutes * 60
        self.max_size_gb = max_size_gb
        self.auto_cleanup = auto_cleanup
        
        # Health metrics
        self.health_log_path = self.vector_store_path.parent / "vector_store_health.json"
        self.alert_log_path = self.vector_store_path.parent / "vector_store_alerts.log"
        
        # Thresholds
        self.size_warning_threshold = max_size_gb * 0.8  # Warn at 80% of max
        self.size_critical_threshold = max_size_gb * 0.95  # Critical at 95% of max
        self.growth_rate_threshold = 5.0  # Alert if growing > 5GB per hour
        
        # Historical data for trend analysis
        self.size_history = []
        self.max_history_entries = 48  # Keep 24 hours at 30-minute intervals
        
        logger.info(f"Vector Store Monitor initialized")
        logger.info(f"  Path: {self.vector_store_path}")
        logger.info(f"  Max size: {self.max_size_gb}GB")
        logger.info(f"  Check interval: {check_interval_minutes} minutes")
        logger.info(f"  Auto cleanup: {auto_cleanup}")
    
    def get_directory_size(self, path: Path) -> float:
        """Get total size of directory in GB."""
        total_size = 0
        if path.exists():
            for item in path.rglob("*"):
                if item.is_file():
                    try:
                        total_size += item.stat().st_size
                    except:
                        pass
        return total_size / (1024 ** 3)
    
    def get_file_statistics(self) -> Dict[str, Any]:
        """Get detailed file statistics."""
        stats = {
            "total_files": 0,
            "total_size_gb": 0,
            "largest_files": [],
            "file_types": {}
        }
        
        if not self.vector_store_path.exists():
            return stats
        
        files = []
        for item in self.vector_store_path.rglob("*"):
            if item.is_file():
                try:
                    size = item.stat().st_size
                    files.append((item, size))
                    stats["total_files"] += 1
                    
                    # Track by extension
                    ext = item.suffix or "no_extension"
                    if ext not in stats["file_types"]:
                        stats["file_types"][ext] = {"count": 0, "size": 0}
                    stats["file_types"][ext]["count"] += 1
                    stats["file_types"][ext]["size"] += size
                except:
                    pass
        
        # Sort by size and get largest files
        files.sort(key=lambda x: x[1], reverse=True)
        stats["largest_files"] = [
            {
                "path": str(f[0].relative_to(self.vector_store_path)),
                "size_gb": f[1] / (1024 ** 3),
                "size_mb": f[1] / (1024 ** 2)
            }
            for f in files[:10]  # Top 10 largest files
        ]
        
        # Convert file type sizes to GB
        for ext in stats["file_types"]:
            stats["file_types"][ext]["size_gb"] = stats["file_types"][ext]["size"] / (1024 ** 3)
        
        stats["total_size_gb"] = sum(f[1] for f in files) / (1024 ** 3)
        
        return stats
    
    def detect_corruption_signs(self) -> Tuple[bool, list]:
        """
        Detect signs of ChromaDB corruption.
        Returns (is_corrupted, issues_found)
        """
        issues = []
        
        # Check for abnormally large link_lists.bin files (ChromaDB HNSW index)
        for link_file in self.vector_store_path.rglob("link_lists.bin"):
            size_gb = link_file.stat().st_size / (1024 ** 3)
            if size_gb > 10:  # link_lists.bin should never be > 10GB for reasonable datasets
                issues.append(f"Abnormally large link_lists.bin: {size_gb:.2f}GB at {link_file}")
        
        # Check for lock files that might indicate crashed operations
        lock_files = list(self.vector_store_path.rglob("*.lock"))
        if lock_files:
            for lock_file in lock_files:
                # Check if lock file is old (> 1 hour)
                age_hours = (time.time() - lock_file.stat().st_mtime) / 3600
                if age_hours > 1:
                    issues.append(f"Stale lock file (age: {age_hours:.1f}h): {lock_file}")
        
        # Check for incomplete write operations (journal files)
        journal_files = list(self.vector_store_path.rglob("*-journal"))
        if journal_files:
            for journal in journal_files:
                age_hours = (time.time() - journal.stat().st_mtime) / 3600
                if age_hours > 0.5:  # Journal files shouldn't persist > 30 min
                    issues.append(f"Persistent journal file (age: {age_hours:.1f}h): {journal}")
        
        # Check file count vs expected patterns
        stats = self.get_file_statistics()
        if stats["total_files"] > 10000:  # Abnormal number of files
            issues.append(f"Excessive file count: {stats['total_files']} files")
        
        return len(issues) > 0, issues
    
    def calculate_growth_rate(self) -> Optional[float]:
        """Calculate growth rate in GB per hour."""
        if len(self.size_history) < 2:
            return None
        
        # Get entries from last hour
        one_hour_ago = time.time() - 3600
        recent_entries = [e for e in self.size_history if e["timestamp"] > one_hour_ago]
        
        if len(recent_entries) < 2:
            return None
        
        oldest = recent_entries[0]
        newest = recent_entries[-1]
        
        time_diff_hours = (newest["timestamp"] - oldest["timestamp"]) / 3600
        if time_diff_hours == 0:
            return None
        
        size_diff_gb = newest["size_gb"] - oldest["size_gb"]
        return size_diff_gb / time_diff_hours
    
    def check_health(self) -> Dict[str, Any]:
        """Perform comprehensive health check."""
        health_report = {
            "timestamp": datetime.now().isoformat(),
            "status": "healthy",
            "size_gb": 0,
            "issues": [],
            "warnings": [],
            "stats": {}
        }
        
        # Get current size
        health_report["size_gb"] = self.get_directory_size(self.vector_store_path)
        
        # Update history
        self.size_history.append({
            "timestamp": time.time(),
            "size_gb": health_report["size_gb"]
        })
        
        # Trim history
        if len(self.size_history) > self.max_history_entries:
            self.size_history = self.size_history[-self.max_history_entries:]
        
        # Get detailed statistics
        health_report["stats"] = self.get_file_statistics()
        
        # Check for corruption
        is_corrupted, corruption_issues = self.detect_corruption_signs()
        if is_corrupted:
            health_report["status"] = "corrupted"
            health_report["issues"].extend(corruption_issues)
        
        # Check size thresholds
        if health_report["size_gb"] > self.size_critical_threshold:
            health_report["status"] = "critical"
            health_report["issues"].append(
                f"Size {health_report['size_gb']:.2f}GB exceeds critical threshold {self.size_critical_threshold:.2f}GB"
            )
        elif health_report["size_gb"] > self.size_warning_threshold:
            if health_report["status"] == "healthy":
                health_report["status"] = "warning"
            health_report["warnings"].append(
                f"Size {health_report['size_gb']:.2f}GB exceeds warning threshold {self.size_warning_threshold:.2f}GB"
            )
        
        # Check growth rate
        growth_rate = self.calculate_growth_rate()
        if growth_rate:
            health_report["growth_rate_gb_per_hour"] = growth_rate
            if growth_rate > self.growth_rate_threshold:
                health_report["warnings"].append(
                    f"Rapid growth detected: {growth_rate:.2f}GB/hour"
                )
                if health_report["status"] == "healthy":
                    health_report["status"] = "warning"
        
        # Check for specific problem files
        for file_info in health_report["stats"]["largest_files"]:
            if file_info["size_gb"] > 5:  # Single file > 5GB is suspicious
                health_report["warnings"].append(
                    f"Large file detected: {file_info['path']} ({file_info['size_gb']:.2f}GB)"
                )
        
        return health_report
    
    def log_alert(self, level: str, message: str):
        """Log an alert to the alert file."""
        timestamp = datetime.now().isoformat()
        with open(self.alert_log_path, "a") as f:
            f.write(f"{timestamp} [{level}] {message}\n")
        
        # Also log to console
        if level == "CRITICAL":
            logger.critical(message)
        elif level == "WARNING":
            logger.warning(message)
        else:
            logger.info(message)
    
    def save_health_report(self, report: Dict[str, Any]):
        """Save health report to file."""
        try:
            # Load existing reports
            if self.health_log_path.exists():
                with open(self.health_log_path, "r") as f:
                    reports = json.load(f)
            else:
                reports = []
            
            # Add new report
            reports.append(report)
            
            # Keep only last 100 reports
            if len(reports) > 100:
                reports = reports[-100:]
            
            # Save
            with open(self.health_log_path, "w") as f:
                json.dump(reports, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save health report: {e}")
    
    def emergency_cleanup(self) -> bool:
        """
        Perform emergency cleanup if critical issues detected.
        WARNING: This is destructive and should only be used as last resort.
        """
        try:
            logger.warning("Starting emergency cleanup...")
            
            # Create backup first
            backup_dir = self.vector_store_path.parent / f"vector_store_emergency_backup_{int(time.time())}"
            shutil.copytree(self.vector_store_path, backup_dir)
            logger.info(f"Created emergency backup at {backup_dir}")
            
            # Remove stale lock files
            for lock_file in self.vector_store_path.rglob("*.lock"):
                try:
                    lock_file.unlink()
                    logger.info(f"Removed lock file: {lock_file}")
                except:
                    pass
            
            # Remove journal files
            for journal in self.vector_store_path.rglob("*-journal"):
                try:
                    journal.unlink()
                    logger.info(f"Removed journal file: {journal}")
                except:
                    pass
            
            # If link_lists.bin files are corrupted (> 10GB), we might need to rebuild
            for link_file in self.vector_store_path.rglob("link_lists.bin"):
                size_gb = link_file.stat().st_size / (1024 ** 3)
                if size_gb > 10:
                    logger.error(f"Cannot auto-fix corrupted link_lists.bin ({size_gb:.2f}GB)")
                    logger.error("Manual intervention required - consider rebuilding vector store")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Emergency cleanup failed: {e}")
            return False
    
    async def monitor_loop(self):
        """Main monitoring loop."""
        logger.info("Starting vector store monitoring loop...")
        
        while True:
            try:
                # Perform health check
                report = self.check_health()
                
                # Save report
                self.save_health_report(report)
                
                # Log status
                logger.info(f"Vector Store Health: {report['status']} | Size: {report['size_gb']:.2f}GB")
                
                # Handle different statuses
                if report["status"] == "critical":
                    self.log_alert("CRITICAL", f"Vector store in critical state: {report['issues']}")
                    
                    if self.auto_cleanup:
                        logger.warning("Attempting automatic emergency cleanup...")
                        if self.emergency_cleanup():
                            self.log_alert("INFO", "Emergency cleanup completed")
                        else:
                            self.log_alert("CRITICAL", "Emergency cleanup failed - manual intervention required")
                
                elif report["status"] == "corrupted":
                    self.log_alert("CRITICAL", f"Vector store corruption detected: {report['issues']}")
                    
                elif report["status"] == "warning":
                    for warning in report["warnings"]:
                        self.log_alert("WARNING", warning)
                
                # Log any specific issues
                for issue in report["issues"]:
                    self.log_alert("ERROR", issue)
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
            
            # Wait for next check
            await asyncio.sleep(self.check_interval)
    
    def get_summary(self) -> str:
        """Get a summary of current vector store status."""
        report = self.check_health()
        
        summary = []
        summary.append(f"Vector Store Status: {report['status'].upper()}")
        summary.append(f"Size: {report['size_gb']:.2f}GB / {self.max_size_gb}GB")
        summary.append(f"Files: {report['stats']['total_files']}")
        
        if "growth_rate_gb_per_hour" in report:
            summary.append(f"Growth: {report['growth_rate_gb_per_hour']:.2f}GB/hour")
        
        if report["issues"]:
            summary.append("Issues:")
            for issue in report["issues"]:
                summary.append(f"  - {issue}")
        
        if report["warnings"]:
            summary.append("Warnings:")
            for warning in report["warnings"]:
                summary.append(f"  - {warning}")
        
        return "\n".join(summary)


async def main():
    """Run the vector store monitor."""
    monitor = VectorStoreMonitor(
        check_interval_minutes=30,
        max_size_gb=50.0,
        auto_cleanup=False  # Set to True for automatic cleanup
    )
    
    # Print initial status
    print("\n" + "="*60)
    print("VECTOR STORE HEALTH MONITOR")
    print("="*60)
    print(monitor.get_summary())
    print("="*60)
    print("\nMonitoring started. Press Ctrl+C to stop.\n")
    
    # Start monitoring
    await monitor.monitor_loop()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nMonitoring stopped.")