#!/usr/bin/env python3
"""
OMEGA_QUANT Production Deployment Script
Backend Engineer (Role 9) - Phase 10

Deploys OMEGA_QUANT system to production environment.
Handles configuration validation, dependency checks, and deployment verification.

Usage:
    python scripts/deploy_omega.py --env production --dry-run
    python scripts/deploy_omega.py --env production --deploy
    python scripts/deploy_omega.py --env staging --deploy
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("OmegaDeployer")


class DeploymentError(Exception):
    """Custom exception for deployment errors."""
    pass


class OmegaDeployer:
    """
    Production deployment manager for OMEGA_QUANT.
    
    Responsibilities:
    - Validate configuration files
    - Check system dependencies
    - Deploy to target environment
    - Verify deployment health
    - Rollback on failure
    """
    
    def __init__(self, environment: str, dry_run: bool = False):
        self.environment = environment
        self.dry_run = dry_run
        self.workspace_root = Path(__file__).parent.parent
        self.config_dir = self.workspace_root / "config"
        self.state_dir = self.workspace_root / ".ly_state"
        self.deployment_log: List[Dict[str, Any]] = []
        
        logger.info(f"Initializing deployment to {environment} (dry_run={dry_run})")
    
    def deploy(self) -> bool:
        """
        Execute full deployment workflow.
        
        Returns:
            True if deployment successful, False otherwise
        """
        try:
            logger.info("=" * 80)
            logger.info(f"OMEGA_QUANT DEPLOYMENT - {self.environment.upper()}")
            logger.info("=" * 80)
            
            # Step 1: Pre-deployment checks
            logger.info("\n[Step 1/6] Running pre-deployment checks...")
            self._log_step("pre_checks", "started")
            if not self._pre_deployment_checks():
                raise DeploymentError("Pre-deployment checks failed")
            self._log_step("pre_checks", "completed")
            
            # Step 2: Load and validate configuration
            logger.info("\n[Step 2/6] Loading configuration...")
            self._log_step("config_load", "started")
            config = self._load_config()
            if not self._validate_config(config):
                raise DeploymentError("Configuration validation failed")
            self._log_step("config_load", "completed")
            
            # Step 3: Check dependencies
            logger.info("\n[Step 3/6] Checking dependencies...")
            self._log_step("dependency_check", "started")
            if not self._check_dependencies():
                raise DeploymentError("Dependency check failed")
            self._log_step("dependency_check", "completed")
            
            # Step 4: Deploy application
            logger.info("\n[Step 4/6] Deploying application...")
            self._log_step("deploy", "started")
            if not self.dry_run:
                if not self._deploy_application(config):
                    raise DeploymentError("Application deployment failed")
            else:
                logger.info("DRY RUN: Skipping actual deployment")
            self._log_step("deploy", "completed")
            
            # Step 5: Post-deployment verification
            logger.info("\n[Step 5/6] Running post-deployment verification...")
            self._log_step("post_verify", "started")
            if not self.dry_run:
                if not self._post_deployment_verification():
                    raise DeploymentError("Post-deployment verification failed")
            else:
                logger.info("DRY RUN: Skipping verification")
            self._log_step("post_verify", "completed")
            
            # Step 6: Save deployment record
            logger.info("\n[Step 6/6] Saving deployment record...")
            self._save_deployment_record()
            
            logger.info("\n" + "=" * 80)
            logger.info("DEPLOYMENT SUCCESSFUL")
            logger.info("=" * 80)
            
            return True
            
        except DeploymentError as e:
            logger.error(f"\nDeployment failed: {e}")
            self._log_step("deployment", "failed", error=str(e))
            
            if not self.dry_run:
                logger.warning("Consider running rollback: python scripts/rollback.py")
            
            return False
            
        except Exception as e:
            logger.error(f"\nUnexpected error during deployment: {e}", exc_info=True)
            self._log_step("deployment", "error", error=str(e))
            return False
    
    def _pre_deployment_checks(self) -> bool:
        """Run pre-deployment checks."""
        checks_passed = True
        
        # Check 1: Workspace structure
        logger.info("  - Checking workspace structure...")
        required_dirs = ["packages", "config", "scripts", "tests"]
        for dir_name in required_dirs:
            dir_path = self.workspace_root / dir_name
            if not dir_path.exists():
                logger.error(f"    ✗ Missing required directory: {dir_name}")
                checks_passed = False
            else:
                logger.info(f"    ✓ Found directory: {dir_name}")
        
        # Check 2: Configuration file exists
        logger.info("  - Checking configuration files...")
        config_file = self.config_dir / f"{self.environment}.yaml"
        if not config_file.exists():
            logger.error(f"    ✗ Configuration file not found: {config_file}")
            checks_passed = False
        else:
            logger.info(f"    ✓ Configuration file found: {config_file}")
        
        # Check 3: Environment variables
        logger.info("  - Checking environment variables...")
        required_env_vars = ["OMEGA_ENV"]
        for var in required_env_vars:
            if var not in os.environ:
                logger.warning(f"    ⚠ Environment variable not set: {var}")
            else:
                logger.info(f"    ✓ Environment variable set: {var}")
        
        # Check 4: Git status (ensure clean state)
        logger.info("  - Checking git status...")
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                check=True
            )
            if result.stdout.strip():
                logger.warning("    ⚠ Working directory has uncommitted changes")
                logger.warning("    Consider committing changes before deployment")
            else:
                logger.info("    ✓ Working directory is clean")
        except subprocess.CalledProcessError:
            logger.warning("    ⚠ Could not check git status")
        
        return checks_passed
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration for target environment."""
        config_file = self.config_dir / f"{self.environment}.yaml"
        
        if not config_file.exists():
            raise DeploymentError(f"Configuration file not found: {config_file}")
        
        logger.info(f"  Loading configuration from: {config_file}")
        
        with open(config_file, "r") as f:
            config = yaml.safe_load(f)
        
        logger.info(f"  ✓ Configuration loaded successfully")
        return config
    
    def _validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate configuration structure and values."""
        logger.info("  Validating configuration...")
        
        validation_passed = True
        
        # Check required top-level keys
        required_keys = ["environment", "data", "risk", "execution"]
        for key in required_keys:
            if key not in config:
                logger.error(f"    ✗ Missing required config key: {key}")
                validation_passed = False
            else:
                logger.info(f"    ✓ Found config key: {key}")
        
        # Validate environment matches
        if config.get("environment") != self.environment:
            logger.error(f"    ✗ Config environment mismatch: expected {self.environment}, got {config.get('environment')}")
            validation_passed = False
        
        return validation_passed
    
    def _check_dependencies(self) -> bool:
        """Check system dependencies."""
        logger.info("  Checking Python dependencies...")
        
        dependencies_ok = True
        
        # Check Python version
        python_version = sys.version_info
        logger.info(f"    Python version: {python_version.major}.{python_version.minor}.{python_version.micro}")
        
        if python_version.major < 3 or (python_version.major == 3 and python_version.minor < 8):
            logger.error("    ✗ Python 3.8+ required")
            dependencies_ok = False
        else:
            logger.info("    ✓ Python version OK")
        
        # Check required packages
        required_packages = ["pandas", "numpy", "yaml"]
        for package in required_packages:
            try:
                __import__(package)
                logger.info(f"    ✓ Package installed: {package}")
            except ImportError:
                logger.error(f"    ✗ Package not installed: {package}")
                dependencies_ok = False
        
        return dependencies_ok
    
    def _deploy_application(self, config: Dict[str, Any]) -> bool:
        """Deploy application to target environment."""
        logger.info("  Deploying application components...")
        
        # Step 1: Create state directories
        logger.info("    - Creating state directories...")
        state_dirs = [
            self.state_dir / "session",
            self.state_dir / "memory",
            self.state_dir / "checkpoints",
            self.workspace_root / "logs",
            self.workspace_root / "artifacts"
        ]
        
        for dir_path in state_dirs:
            dir_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"      ✓ Created: {dir_path}")
        
        # Step 2: Copy configuration to deployment location
        logger.info("    - Deploying configuration...")
        deployment_config_path = self.state_dir / "session" / "active_config.yaml"
        with open(deployment_config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False)
        logger.info(f"      ✓ Configuration deployed to: {deployment_config_path}")
        
        # Step 3: Initialize deployment metadata
        logger.info("    - Initializing deployment metadata...")
        metadata = {
            "environment": self.environment,
            "deployed_at": datetime.now().isoformat(),
            "deployed_by": os.environ.get("USER", "unknown"),
            "config_version": config.get("version", "unknown"),
            "git_commit": self._get_git_commit()
        }
        
        metadata_path = self.state_dir / "session" / "deployment_metadata.json"
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)
        logger.info(f"      ✓ Metadata saved to: {metadata_path}")
        
        logger.info("  ✓ Application deployed successfully")
        return True
    
    def _post_deployment_verification(self) -> bool:
        """Verify deployment health."""
        logger.info("  Running post-deployment verification...")
        
        # Run health check script
        health_check_script = self.workspace_root / "scripts" / "health_check.py"
        
        if not health_check_script.exists():
            logger.warning("    ⚠ Health check script not found, skipping verification")
            return True
        
        try:
            logger.info("    - Running health check...")
            result = subprocess.run(
                [sys.executable, str(health_check_script), "--quick"],
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                logger.info("    ✓ Health check passed")
                return True
            else:
                logger.error("    ✗ Health check failed")
                logger.error(f"    Output: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error("    ✗ Health check timed out")
            return False
        except Exception as e:
            logger.error(f"    ✗ Health check error: {e}")
            return False
    
    def _get_git_commit(self) -> Optional[str]:
        """Get current git commit hash."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            return None
    
    def _log_step(self, step: str, status: str, error: Optional[str] = None) -> None:
        """Log deployment step."""
        log_entry = {
            "step": step,
            "status": status,
            "timestamp": datetime.now().isoformat()
        }
        if error:
            log_entry["error"] = error
        
        self.deployment_log.append(log_entry)
    
    def _save_deployment_record(self) -> None:
        """Save deployment record to state directory."""
        record_path = self.state_dir / "session" / f"deployment_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        record = {
            "environment": self.environment,
            "dry_run": self.dry_run,
            "timestamp": datetime.now().isoformat(),
            "steps": self.deployment_log
        }
        
        with open(record_path, "w") as f:
            json.dump(record, f, indent=2)
        
        logger.info(f"  Deployment record saved to: {record_path}")


def main():
    """Main entry point for deployment script."""
    parser = argparse.ArgumentParser(
        description="OMEGA_QUANT Deployment Script"
    )
    parser.add_argument(
        "--env",
        type=str,
        choices=["development", "staging", "production"],
        default="production",
        help="Target environment (default: production)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run deployment checks without actually deploying"
    )
    parser.add_argument(
        "--deploy",
        action="store_true",
        help="Execute deployment (required for non-dry-run)"
    )
    
    args = parser.parse_args()
    
    # Safety check: require explicit --deploy flag for production
    if args.env == "production" and not args.dry_run and not args.deploy:
        logger.error("Production deployment requires explicit --deploy flag")
        logger.info("Use --dry-run to test deployment without changes")
        sys.exit(1)
    
    # Create deployer
    deployer = OmegaDeployer(
        environment=args.env,
        dry_run=args.dry_run
    )
    
    # Execute deployment
    success = deployer.deploy()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
