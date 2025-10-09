"""
Planner Monitoring Service for RAG Integration
Phase 5: Planner Integration - Automatic Task Attachment Monitoring
"""

import os
import asyncio
import signal
from typing import Dict, Any, List, Optional, Set
from datetime import datetime, timezone, timedelta
import sys
import json

import structlog

# Import from planner MCP server
sys.path.append("/Users/Jason/CCOMGROUPINC Dropbox/Jason Greenawalt/CODING/GITHUB/Intelligent-Teams-Planner/planner-mcp-server/src")

try:
    from auth import AuthService
    from cache import CacheService
    from graph_client import GraphAPIClient
except ImportError as e:
    print(f"Failed to import planner MCP components: {e}")
    print("Please ensure the planner-mcp-server is accessible")
    sys.exit(1)

# Import local planner handler
try:
    from planner_handler import PlannerAttachmentHandler
except ImportError as e:
    print(f"Failed to import local planner handler: {e}")
    print("Please ensure planner_handler.py is accessible")
    sys.exit(1)

logger = structlog.get_logger(__name__)


class PlannerMonitoringService:
    """
    Monitors Microsoft Planner tasks for new attachments
    Automatically processes attachments and forwards them to RAG service
    """

    def __init__(
        self,
        poll_interval: int = 300,  # 5 minutes as per implementation plan
        rag_service_url: str = "http://localhost:7120",
        user_id: str = "default"
    ):
        self.poll_interval = poll_interval
        self.rag_service_url = rag_service_url
        self.user_id = user_id
        self.running = False
        self.shutdown_event = asyncio.Event()

        # Track processed tasks to detect changes
        self.processed_task_attachments: Dict[str, Set[str]] = {}
        self.last_scan_time = None

        # Initialize services
        self.auth_service = None
        self.cache_service = None
        self.graph_client = None
        self.attachment_handler = None

    async def initialize(self) -> None:
        """Initialize monitoring service components"""
        try:
            # Initialize auth and cache services
            self.auth_service = AuthService()
            self.cache_service = CacheService()

            # Initialize Graph API client
            self.graph_client = GraphAPIClient(self.auth_service, self.cache_service)

            # Test connectivity
            is_connected = await self.graph_client.test_connection(self.user_id)
            if not is_connected:
                raise Exception("Failed to connect to Microsoft Graph API")

            # Initialize attachment handler with graph client factory
            async def graph_client_factory(user_id: str = "default"):
                return self.graph_client

            self.attachment_handler = PlannerAttachmentHandler(
                graph_client_factory=graph_client_factory,
                rag_service_url=self.rag_service_url
            )

            logger.info(
                "Planner monitoring service initialized successfully",
                poll_interval=self.poll_interval,
                rag_service_url=self.rag_service_url
            )

        except Exception as e:
            logger.error("Failed to initialize planner monitoring service", error=str(e))
            raise

    async def get_all_tasks(self) -> List[Dict[str, Any]]:
        """
        Get all Planner tasks accessible to the user

        Returns:
            List of task information dictionaries
        """
        try:
            # Get user's plans first
            plans_response = await self.graph_client._make_request(
                "GET", "/me/planner/plans", self.user_id
            )

            if not plans_response or "value" not in plans_response:
                logger.warning("No planner plans found for user")
                return []

            all_tasks = []

            # Get tasks from each plan
            for plan in plans_response["value"]:
                plan_id = plan.get("id")
                if not plan_id:
                    continue

                try:
                    # Get tasks for this plan
                    tasks_response = await self.graph_client._make_request(
                        "GET", f"/planner/plans/{plan_id}/tasks", self.user_id
                    )

                    if tasks_response and "value" in tasks_response:
                        for task in tasks_response["value"]:
                            task["planId"] = plan_id
                            task["planTitle"] = plan.get("title", "Unknown Plan")
                            all_tasks.append(task)

                except Exception as e:
                    logger.warning(
                        "Failed to get tasks for plan",
                        plan_id=plan_id,
                        error=str(e)
                    )
                    continue

            logger.info(
                "Retrieved planner tasks",
                total_tasks=len(all_tasks),
                plans_scanned=len(plans_response["value"])
            )

            return all_tasks

        except Exception as e:
            logger.error("Error retrieving planner tasks", error=str(e))
            return []

    async def scan_task_attachments(self, task: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Scan a single task for new attachments

        Args:
            task: Task information dictionary

        Returns:
            List of processing results for new attachments
        """
        task_id = task.get("id", "")
        task_title = task.get("title", "")

        if not task_id:
            return []

        try:
            # Get current task attachments
            attachments = await self.attachment_handler.get_task_attachments(task_id, self.user_id)

            if not attachments:
                return []

            # Track current attachment IDs
            current_attachment_ids = {att.get("id", "") for att in attachments}

            # Get previously processed attachment IDs for this task
            previously_processed = self.processed_task_attachments.get(task_id, set())

            # Find new attachments (not previously processed)
            new_attachment_ids = current_attachment_ids - previously_processed

            if not new_attachment_ids:
                logger.debug(
                    "No new attachments found for task",
                    task_id=task_id,
                    task_title=task_title
                )
                return []

            # Filter to only process new attachments
            new_attachments = [
                att for att in attachments
                if att.get("id", "") in new_attachment_ids
            ]

            logger.info(
                "Found new attachments for task",
                task_id=task_id,
                task_title=task_title,
                new_attachments=len(new_attachments),
                total_attachments=len(attachments)
            )

            # Process new attachments
            results = []
            for attachment in new_attachments:
                try:
                    # Process single task attachments
                    task_results = await self.attachment_handler.process_task_attachments(
                        task_id, task_title, self.user_id
                    )
                    results.extend(task_results)

                except Exception as e:
                    logger.error(
                        "Error processing attachment",
                        error=str(e),
                        task_id=task_id,
                        attachment_id=attachment.get("id", "")
                    )

            # Update processed attachments tracking
            self.processed_task_attachments[task_id] = current_attachment_ids

            return results

        except Exception as e:
            logger.error(
                "Error scanning task attachments",
                error=str(e),
                task_id=task_id
            )
            return []

    async def scan_all_tasks(self) -> Dict[str, Any]:
        """
        Scan all tasks for new attachments

        Returns:
            Summary of scan results
        """
        scan_start = datetime.now(timezone.utc)

        try:
            logger.info("Starting planner attachment scan")

            # Get all tasks
            tasks = await self.get_all_tasks()

            if not tasks:
                logger.info("No tasks found to scan")
                return {
                    "scan_time": scan_start.isoformat(),
                    "tasks_scanned": 0,
                    "attachments_processed": 0,
                    "successful_uploads": 0,
                    "failed_uploads": 0
                }

            # Process tasks concurrently (but with rate limiting)
            total_results = []
            batch_size = 5  # Process 5 tasks at a time to avoid rate limits

            for i in range(0, len(tasks), batch_size):
                batch = tasks[i:i + batch_size]

                # Process batch concurrently
                batch_results = await asyncio.gather(*[
                    self.scan_task_attachments(task) for task in batch
                ], return_exceptions=True)

                # Collect results
                for results in batch_results:
                    if isinstance(results, list):
                        total_results.extend(results)
                    elif isinstance(results, Exception):
                        logger.error("Task scan failed", error=str(results))

                # Rate limiting pause between batches
                if i + batch_size < len(tasks):
                    await asyncio.sleep(2)

            # Calculate summary statistics
            successful_uploads = len([r for r in total_results if r.get("success")])
            failed_uploads = len([r for r in total_results if not r.get("success")])

            scan_summary = {
                "scan_time": scan_start.isoformat(),
                "scan_duration_seconds": (datetime.now(timezone.utc) - scan_start).total_seconds(),
                "tasks_scanned": len(tasks),
                "attachments_processed": len(total_results),
                "successful_uploads": successful_uploads,
                "failed_uploads": failed_uploads,
                "results": total_results
            }

            # Update last scan time
            self.last_scan_time = scan_start

            logger.info(
                "Planner attachment scan completed",
                **{k: v for k, v in scan_summary.items() if k != "results"}
            )

            return scan_summary

        except Exception as e:
            logger.error("Error during planner scan", error=str(e))
            return {
                "scan_time": scan_start.isoformat(),
                "error": str(e),
                "tasks_scanned": 0,
                "attachments_processed": 0,
                "successful_uploads": 0,
                "failed_uploads": 0
            }

    async def run_monitoring_loop(self) -> None:
        """
        Main monitoring loop
        Runs continuously until shutdown signal received
        """
        logger.info("Starting planner monitoring loop", poll_interval=self.poll_interval)
        self.running = True

        try:
            while self.running and not self.shutdown_event.is_set():
                try:
                    # Perform scan
                    scan_results = await self.scan_all_tasks()

                    # Log summary
                    if scan_results.get("attachments_processed", 0) > 0:
                        logger.info(
                            "Planner scan found new attachments",
                            processed=scan_results.get("attachments_processed"),
                            successful=scan_results.get("successful_uploads"),
                            failed=scan_results.get("failed_uploads")
                        )

                    # Wait for next scan or shutdown signal
                    try:
                        await asyncio.wait_for(
                            self.shutdown_event.wait(),
                            timeout=self.poll_interval
                        )
                        # If we reach here, shutdown was requested
                        break
                    except asyncio.TimeoutError:
                        # Timeout means continue with next scan
                        continue

                except Exception as e:
                    logger.error("Error in monitoring loop", error=str(e))
                    # Wait before retrying on error
                    await asyncio.sleep(min(60, self.poll_interval))

        except Exception as e:
            logger.error("Fatal error in monitoring loop", error=str(e))
        finally:
            self.running = False
            if self.attachment_handler:
                await self.attachment_handler.close()
            logger.info("Planner monitoring loop stopped")

    async def start(self) -> None:
        """Start the monitoring service"""
        try:
            await self.initialize()
            await self.run_monitoring_loop()
        except Exception as e:
            logger.error("Failed to start planner monitoring service", error=str(e))
            raise

    async def stop(self) -> None:
        """Stop the monitoring service"""
        logger.info("Stopping planner monitoring service")
        self.running = False
        self.shutdown_event.set()

    def setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown"""
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating graceful shutdown")
            asyncio.create_task(self.stop())

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)


async def main():
    """Main entry point for planner monitoring service"""
    # Configure logging
    structlog.configure(
        processors=[structlog.dev.ConsoleRenderer()],
        wrapper_class=structlog.make_filtering_bound_logger(10),  # DEBUG level
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True
    )

    # Get configuration from environment
    poll_interval = int(os.getenv("PLANNER_POLL_INTERVAL", "300"))  # 5 minutes default
    rag_service_url = os.getenv("RAG_SERVICE_URL", "http://localhost:7120")
    user_id = os.getenv("PLANNER_USER_ID", "default")

    # Create and start monitoring service
    monitor = PlannerMonitoringService(
        poll_interval=poll_interval,
        rag_service_url=rag_service_url,
        user_id=user_id
    )

    # Setup signal handlers
    monitor.setup_signal_handlers()

    try:
        logger.info(
            "Starting Planner monitoring service",
            poll_interval=poll_interval,
            rag_service_url=rag_service_url
        )
        await monitor.start()
    except KeyboardInterrupt:
        logger.info("Shutdown requested via keyboard interrupt")
    except Exception as e:
        logger.error("Monitoring service failed", error=str(e))
        sys.exit(1)
    finally:
        await monitor.stop()


if __name__ == "__main__":
    asyncio.run(main())