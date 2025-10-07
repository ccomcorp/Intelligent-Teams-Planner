"""
MVP tests for Microsoft Teams and Planner connectivity
Focus on basic authentication and task creation
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from src.teams_planner_client import SimpleTeamsPlannerClient, TeamsPlannierError
from src.auth import AuthService


class TestMVPTeamsPlanner:
    """Test basic Teams and Planner functionality for MVP"""

    @pytest.fixture
    def mock_auth_service(self):
        """Mock auth service for testing"""
        auth_service = AsyncMock(spec=AuthService)
        auth_service.get_access_token.return_value = "mock_access_token_12345"
        return auth_service

    @pytest.fixture
    def teams_client(self, mock_auth_service):
        """Teams and Planner client for testing"""
        return SimpleTeamsPlannerClient(mock_auth_service)

    @pytest.mark.asyncio
    async def test_get_user_teams_success(self, teams_client, mock_auth_service):
        """Test successful retrieval of user teams"""
        mock_teams_response = {
            "value": [
                {
                    "id": "team-001",
                    "displayName": "Test Team 1",
                    "description": "A test team for MVP"
                },
                {
                    "id": "team-002",
                    "displayName": "Test Team 2",
                    "description": "Another test team"
                }
            ]
        }

        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_teams_response

            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response

            result = await teams_client.get_user_teams("test_user")

            assert len(result) == 2
            assert result[0]["id"] == "team-001"
            assert result[0]["displayName"] == "Test Team 1"
            mock_auth_service.get_access_token.assert_called_once_with("test_user")

    @pytest.mark.asyncio
    async def test_get_user_teams_no_token(self, teams_client, mock_auth_service):
        """Test teams retrieval with no access token"""
        mock_auth_service.get_access_token.return_value = None

        with pytest.raises(TeamsPlannierError, match="No valid access token available"):
            await teams_client.get_user_teams("test_user")

    @pytest.mark.asyncio
    async def test_create_planner_task_success(self, teams_client, mock_auth_service):
        """Test successful task creation in Planner with description update"""
        mock_task_response = {
            "id": "task-12345",
            "planId": "plan-001",
            "title": "Test Task",
            "createdDateTime": datetime.now(timezone.utc).isoformat(),
            "assignments": {}
        }

        mock_details_response = {
            "id": "task-12345",
            "description": "This is a test task"
        }

        with patch('httpx.AsyncClient') as mock_client:
            mock_client_instance = mock_client.return_value.__aenter__.return_value

            # Mock task creation response
            mock_post_response = MagicMock()
            mock_post_response.status_code = 201
            mock_post_response.json.return_value = mock_task_response

            # Mock task details get response (for description update)
            mock_get_response = MagicMock()
            mock_get_response.status_code = 200
            mock_get_response.json.return_value = mock_details_response
            mock_get_response.headers = {"ETag": "test-etag"}

            # Mock task details patch response
            mock_patch_response = MagicMock()
            mock_patch_response.status_code = 200

            mock_client_instance.post.return_value = mock_post_response
            mock_client_instance.get.return_value = mock_get_response
            mock_client_instance.patch.return_value = mock_patch_response

            result = await teams_client.create_planner_task(
                "test_user",
                "plan-001",
                "Test Task",
                "This is a test task"
            )

            assert result["id"] == "task-12345"
            assert result["title"] == "Test Task"
            assert result["planId"] == "plan-001"
            # Enhanced method calls get_access_token twice (task creation + description update)
            assert mock_auth_service.get_access_token.call_count == 2

    @pytest.mark.asyncio
    async def test_create_planner_task_failure(self, teams_client, mock_auth_service):
        """Test task creation failure handling"""
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 403
            mock_response.text = "Forbidden: Insufficient privileges"

            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response

            with pytest.raises(TeamsPlannierError, match="Failed to create task: 403"):
                await teams_client.create_planner_task(
                    "test_user",
                    "plan-001",
                    "Test Task"
                )

    @pytest.mark.asyncio
    async def test_connectivity_test_success(self, teams_client, mock_auth_service):
        """Test successful connectivity check"""
        mock_user_response = {
            "id": "user-123",
            "displayName": "Test User",
            "mail": "test@example.com"
        }

        mock_teams_response = {
            "value": [
                {"id": "team-001", "displayName": "Test Team"}
            ]
        }

        with patch('httpx.AsyncClient') as mock_client:
            mock_client_instance = mock_client.return_value.__aenter__.return_value

            # Mock user info response
            mock_user_resp = MagicMock()
            mock_user_resp.status_code = 200
            mock_user_resp.json.return_value = mock_user_response

            # Mock teams response
            mock_teams_resp = MagicMock()
            mock_teams_resp.status_code = 200
            mock_teams_resp.json.return_value = mock_teams_response

            mock_client_instance.get.side_effect = [mock_user_resp, mock_teams_resp]

            result = await teams_client.test_connectivity("test_user")

            assert result["connectivity_test"] is True
            assert result["user_info"]["id"] == "user-123"
            assert len(result["teams"]) == 1
            assert len(result["errors"]) == 0

    @pytest.mark.asyncio
    async def test_connectivity_test_partial_failure(self, teams_client, mock_auth_service):
        """Test connectivity with partial failures"""
        mock_user_response = {
            "id": "user-123",
            "displayName": "Test User",
            "mail": "test@example.com"
        }

        with patch('httpx.AsyncClient') as mock_client:
            mock_client_instance = mock_client.return_value.__aenter__.return_value

            # Mock successful user info response
            mock_user_resp = MagicMock()
            mock_user_resp.status_code = 200
            mock_user_resp.json.return_value = mock_user_response

            # Mock failed teams response
            mock_teams_resp = MagicMock()
            mock_teams_resp.status_code = 403

            mock_client_instance.get.side_effect = [mock_user_resp, mock_teams_resp]

            result = await teams_client.test_connectivity("test_user")

            assert result["connectivity_test"] is False
            assert result["user_info"]["id"] == "user-123"
            assert result["teams"] is None
            assert len(result["errors"]) == 1
            assert "Failed to get teams: 403" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_get_team_planner_plans_success(self, teams_client, mock_auth_service):
        """Test successful retrieval of team planner plans"""
        mock_plans_response = {
            "value": [
                {
                    "id": "plan-001",
                    "title": "Sprint Planning",
                    "owner": "team-001"
                },
                {
                    "id": "plan-002",
                    "title": "Feature Development",
                    "owner": "team-001"
                }
            ]
        }

        with patch('httpx.AsyncClient') as mock_client:
            mock_client_instance = mock_client.return_value.__aenter__.return_value

            # Mock plans response (direct API call to /groups/{team_id}/planner/plans)
            mock_plans_resp = MagicMock()
            mock_plans_resp.status_code = 200
            mock_plans_resp.json.return_value = mock_plans_response

            mock_client_instance.get.return_value = mock_plans_resp

            result = await teams_client.get_team_planner_plans("test_user", "team-001")

            assert len(result) == 2
            assert result[0]["id"] == "plan-001"
            assert result[0]["title"] == "Sprint Planning"
            mock_auth_service.get_access_token.assert_called_once_with("test_user")


class TestMVPIntegration:
    """Integration tests for MVP functionality"""

    @pytest.mark.asyncio
    async def test_end_to_end_task_creation_workflow(self):
        """Test the complete workflow from auth to task creation"""
        # This test would require actual Azure AD credentials in a real scenario
        # For MVP, we'll test the workflow with mocks

        with patch('src.teams_planner_client.AuthService') as mock_auth_class:
            mock_auth_service = AsyncMock()
            mock_auth_service.get_access_token.return_value = "valid_token"
            mock_auth_class.return_value = mock_auth_service

            client = SimpleTeamsPlannerClient(mock_auth_service)

            # Test the full workflow with mocked responses
            with patch('httpx.AsyncClient') as mock_http_client:
                mock_client_instance = mock_http_client.return_value.__aenter__.return_value

                # Mock responses for the workflow
                user_info_response = MagicMock(status_code=200, json=lambda: {"id": "user-123", "displayName": "Test User"})
                teams_response = MagicMock(status_code=200, json=lambda: {"value": [{"id": "team-001", "displayName": "Test Team"}]})
                plans_response = MagicMock(status_code=200, json=lambda: {"value": [{"id": "plan-001", "title": "Test Plan"}]})
                task_creation_response = MagicMock(status_code=201, json=lambda: {"id": "task-123", "title": "MVP Test Task", "planId": "plan-001"})
                task_details_response = MagicMock(status_code=200, json=lambda: {"id": "task-123", "description": "End-to-end test task"})
                task_details_response.headers = {"ETag": "test-etag"}
                task_patch_response = MagicMock(status_code=200)

                # Set up mock responses for different calls
                get_responses = [user_info_response, teams_response, plans_response, task_details_response]
                mock_client_instance.get.side_effect = get_responses
                mock_client_instance.post.return_value = task_creation_response
                mock_client_instance.patch.return_value = task_patch_response

                # Execute the workflow
                connectivity = await client.test_connectivity("test_user")
                assert connectivity["connectivity_test"] is True

                if connectivity["teams"]:
                    team_id = connectivity["teams"][0]["id"]
                    plans = await client.get_team_planner_plans("test_user", team_id)
                    assert len(plans) == 1

                    if plans:
                        plan_id = plans[0]["id"]
                        task = await client.create_planner_task(
                            "test_user",
                            plan_id,
                            "MVP Test Task",
                            "End-to-end test task"
                        )
                        assert task["id"] == "task-123"
                        assert task["title"] == "MVP Test Task"