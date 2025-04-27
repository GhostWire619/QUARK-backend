import os
import subprocess
import tempfile
import threading
import logging
import time
import shutil
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple, Callable
import uuid
import json

from sqlalchemy.orm import Session, sessionmaker
from app.database.database import DeploymentStatus, DeploymentEnvironment, get_db, SessionLocal
from app.database.deployment_crud import (
    get_deployment,
    update_deployment_status,
    add_deployment_log,
    get_deployment_config
)
from app.schemas.deployment_models import DeploymentRequest, DeploymentResult

logger = logging.getLogger(__name__)

# Deployment cache to track running deployments
active_deployments = {}

def get_thread_db():
    """Get a new database session for the current thread"""
    db = SessionLocal()
    try:
        return db
    finally:
        db.close()


def run_command(command: str, cwd: str, env: Dict[str, str], deployment_id: Optional[str] = None, db: Optional[Session] = None) -> Tuple[int, str, str]:
    """Run a shell command and return exit code, stdout, and stderr"""
    logger.info(f"Running command: {command}")
    
    process = subprocess.Popen(
        command,
        shell=True,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        universal_newlines=True
    )
    
    stdout_lines = []
    stderr_lines = []
    
    def read_stream(stream, lines, is_error=False):
        for line in iter(stream.readline, ''):
            lines.append(line)
            if deployment_id and db:
                # Add log with appropriate color coding
                if is_error:
                    log_line = f"\033[0;31m{line.strip()}\033[0m"  # Red for errors
                else:
                    log_line = line.strip()
                add_deployment_log(db, deployment_id, log_line)
    
    # Create threads to read stdout and stderr
    stdout_thread = threading.Thread(target=read_stream, args=(process.stdout, stdout_lines))
    stderr_thread = threading.Thread(target=read_stream, args=(process.stderr, stderr_lines, True))
    
    # Start threads
    stdout_thread.start()
    stderr_thread.start()
    
    # Wait for process to complete
    process.wait()
    
    # Wait for output threads to complete
    stdout_thread.join()
    stderr_thread.join()
    
    return process.returncode, ''.join(stdout_lines), ''.join(stderr_lines)


def prepare_deployment_directory(repo_url: str, branch: str, commit_sha: str) -> str:
    """Clone the repository and checkout the specific commit"""
    deploy_dir = os.path.join(tempfile.gettempdir(), f"deploy_{uuid.uuid4().hex}")
    os.makedirs(deploy_dir, exist_ok=True)
    
    # Clone the repository
    clone_cmd = f"git clone {repo_url} {deploy_dir}"
    code, stdout, stderr = run_command(clone_cmd, "/tmp", os.environ.copy())
    if code != 0:
        raise Exception(f"Failed to clone repository: {stderr}")
    
    # Checkout the specific commit
    checkout_cmd = f"git checkout {commit_sha}"
    code, stdout, stderr = run_command(checkout_cmd, deploy_dir, os.environ.copy())
    if code != 0:
        raise Exception(f"Failed to checkout commit {commit_sha}: {stderr}")
    
    return deploy_dir


def cleanup_deployment_directory(deploy_dir: str):
    """Clean up the deployment directory"""
    try:
        if os.path.exists(deploy_dir):
            shutil.rmtree(deploy_dir)
    except Exception as e:
        logger.error(f"Failed to clean up deployment directory {deploy_dir}: {str(e)}")


def execute_deployment(deployment_id: str, callback: Optional[Callable] = None):
    """Execute a deployment asynchronously"""
    # Create a new database session for this thread
    db = get_thread_db()
    try:
        # Mark deployment as in progress
        deployment = update_deployment_status(db, deployment_id, DeploymentStatus.IN_PROGRESS)
        if not deployment:
            logger.error(f"Deployment {deployment_id} not found")
            return
        
        # Track active deployment
        active_deployments[deployment_id] = {
            "id": deployment_id,
            "status": DeploymentStatus.IN_PROGRESS.value,
            "start_time": datetime.now().isoformat()
        }
        
        # Get deployment config
        config = get_deployment_config(db, deployment.repo_full_name, deployment.user_id)
        if not config:
            error_msg = f"Deployment configuration for {deployment.repo_full_name} not found"
            logger.error(error_msg)
            update_deployment_status(db, deployment_id, DeploymentStatus.FAILED, 
                                    error_message=error_msg)
            active_deployments[deployment_id]["status"] = DeploymentStatus.FAILED.value
            return
        
        add_deployment_log(db, deployment_id, f"Starting deployment of {deployment.repo_full_name} at commit {deployment.commit_sha}")
        
        # GitHub repository URL
        repo_url = f"https://github.com/{deployment.repo_full_name}.git"
        
        try:
            # Prepare environment
            env = os.environ.copy()
            
            # Add deployment-specific variables
            env["DEPLOYMENT_ID"] = deployment_id
            env["REPO_NAME"] = deployment.repo_full_name
            env["COMMIT_SHA"] = deployment.commit_sha
            env["BRANCH"] = deployment.branch
            
            # Add custom environment variables from config
            if config.environment_variables:
                add_deployment_log(db, deployment_id, "Setting environment variables from config")
                env.update(config.environment_variables)
            
            # Prepare deployment directory
            add_deployment_log(db, deployment_id, "Preparing deployment directory")
            deploy_dir = prepare_deployment_directory(repo_url, deployment.branch, deployment.commit_sha)
            
            try:
                # Check if deploy script exists
                deploy_script_path = os.path.join(deploy_dir, "deploy.sh")
                if not os.path.exists(deploy_script_path):
                    error_msg = "deploy.sh script not found in repository"
                    add_deployment_log(db, deployment_id, f"Error: {error_msg}")
                    raise Exception(error_msg)
                
                # Make deploy script executable
                add_deployment_log(db, deployment_id, "Setting execute permissions on deploy script")
                os.chmod(deploy_script_path, 0o755)
                
                # Create .env file if environment variables are provided
                if config.environment_variables:
                    env_file_path = os.path.join(deploy_dir, ".env")
                    add_deployment_log(db, deployment_id, "Creating .env file")
                    with open(env_file_path, "w") as f:
                        for key, value in config.environment_variables.items():
                            f.write(f"{key}={value}\n")
                
                # Execute deploy command
                add_deployment_log(db, deployment_id, f"Running: {config.deploy_command}")
                code, stdout, stderr = run_command(config.deploy_command, deploy_dir, env, deployment_id, db)
                
                if code != 0:
                    error_msg = f"Deploy command failed with exit code {code}"
                    raise Exception(error_msg)
                
                # Mark deployment as completed
                add_deployment_log(db, deployment_id, "Deployment completed successfully")
                update_deployment_status(db, deployment_id, DeploymentStatus.COMPLETED)
                active_deployments[deployment_id]["status"] = DeploymentStatus.COMPLETED.value
                
            except Exception as e:
                # This block handles errors *during* the deployment command execution (e.g., script not found, command fails)
                error_message = str(e)
                logger.error(f"Deployment {deployment_id} failed during execution: {error_message}")
                # Ensure the final error log is added before updating status
                add_deployment_log(db, deployment_id, f"\033[0;31mDeployment failed: {error_message}\033[0m")
                db.commit() # Commit the log immediately
                
                update_deployment_status(db, deployment_id, DeploymentStatus.FAILED, 
                                       error_message=error_message)
                active_deployments[deployment_id]["status"] = DeploymentStatus.FAILED.value
            
            finally:
                # Clean up deployment directory regardless of success or failure inside the inner try
                add_deployment_log(db, deployment_id, "Cleaning up deployment directory")
                cleanup_deployment_directory(deploy_dir)

        except Exception as e:
            # This outer block handles errors *before* the deploy command runs (e.g., cloning fails, config not found)
            error_message = str(e)
            logger.error(f"Deployment {deployment_id} failed during setup: {error_message}")
            # Ensure the final error log is added before updating status
            add_deployment_log(db, deployment_id, f"\033[0;31mDeployment setup failed: {error_message}\033[0m")
            db.commit() # Commit the log immediately
            
            update_deployment_status(db, deployment_id, DeploymentStatus.FAILED, 
                                   error_message=error_message)
            active_deployments[deployment_id]["status"] = DeploymentStatus.FAILED.value
        
        # Execute callback if provided
        if callback:
            callback(deployment_id)
        
    except Exception as e:
        # This handles errors even before the main try block (e.g., initial status update fails)
        logger.error(f"Critical error in deployment execution {deployment_id}: {str(e)}")
        # We might not have a valid deployment record here, so log cautiously
        try:
             if deployment_id and db:
                 update_deployment_status(db, deployment_id, DeploymentStatus.FAILED, 
                               error_message=f"Internal error: {str(e)}")
                 if deployment_id in active_deployments:
                     active_deployments[deployment_id]["status"] = DeploymentStatus.FAILED.value
        except Exception as final_err:
             logger.error(f"Failed to even update status for deployment {deployment_id} after critical error: {final_err}")

    finally:
        # Close the database session
        if db:
            db.close()
        
        # Remove from active deployments after some time
        def cleanup_active_deployment():
            time.sleep(3600)  # Keep in active list for 1 hour
            if deployment_id in active_deployments:
                del active_deployments[deployment_id]
        
        threading.Thread(target=cleanup_active_deployment, daemon=True).start()


def start_deployment(db: Session, user_id: str, request: DeploymentRequest) -> Tuple[bool, str, Optional[str]]:
    """Start a new deployment process"""
    from app.database.deployment_crud import create_deployment
    
    # Create deployment record
    deployment = create_deployment(db, user_id, request)
    if not deployment:
        return False, "Failed to create deployment record", None
    
    # Start deployment in a separate thread
    thread = threading.Thread(
        target=execute_deployment,
        args=(deployment.id,),
        daemon=True
    )
    thread.start()
    
    return True, "Deployment started", deployment.id


def cancel_deployment(db: Session, deployment_id: str) -> bool:
    """Cancel a running deployment"""
    deployment = get_deployment(db, deployment_id)
    if not deployment:
        return False
    
    # Can only cancel pending or in-progress deployments
    if deployment.status not in [DeploymentStatus.PENDING.value, DeploymentStatus.IN_PROGRESS.value]:
        return False
    
    update_deployment_status(db, deployment_id, DeploymentStatus.CANCELLED, 
                          logs=["Deployment cancelled by user"])
    
    if deployment_id in active_deployments:
        active_deployments[deployment_id]["status"] = DeploymentStatus.CANCELLED.value
    
    return True


def get_deployment_status(deployment_id: str) -> Dict[str, Any]:
    """Get current status of a deployment"""
    if deployment_id in active_deployments:
        return active_deployments[deployment_id]
    return {"id": deployment_id, "status": "unknown", "message": "Deployment not found in active deployments"}


def process_webhook_event(db: Session, event_type: str, payload: Dict[str, Any]) -> Optional[str]:
    """Process webhook event and trigger deployment if configured"""
    try:
        # Only process push events for now
        if event_type != "push":
            return None
        
        # Extract repository and branch information
        repo_name = payload.get("repository", {}).get("full_name")
        ref = payload.get("ref", "")
        
        # Skip if not a branch push
        if not ref.startswith("refs/heads/"):
            return None
        
        branch = ref.replace("refs/heads/", "")
        
        # Get the latest commit
        head_commit = payload.get("head_commit", {})
        if not head_commit:
            return None
        
        commit_sha = head_commit.get("id")
        if not commit_sha:
            return None
        
        # Find user who owns this repository config
        # This is simplified - in reality, you would need to look up which user has this repo configured
        from app.database.user_crud import get_users
        users = get_users(db)
        
        for user in users:
            # Check if user has a deployment config for this repo
            config = get_deployment_config(db, repo_name, user.id)
            if not config:
                continue
            
            # Check if auto-deploy is enabled and branch matches
            if config.auto_deploy and config.branch == branch:
                # Create deployment request
                request = DeploymentRequest(
                    repo_full_name=repo_name,
                    commit_sha=commit_sha,
                    branch=branch,
                    manual_trigger=False,
                    triggered_by="webhook"
                )
                
                # Start deployment
                success, message, deployment_id = start_deployment(db, user.id, request)
                if success:
                    logger.info(f"Auto-deployment triggered for {repo_name} at commit {commit_sha}")
                    return deployment_id
                else:
                    logger.error(f"Failed to trigger auto-deployment: {message}")
        
        return None
    
    except Exception as e:
        logger.error(f"Error processing webhook event: {str(e)}")
        return None 