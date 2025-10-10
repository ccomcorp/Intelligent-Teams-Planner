"""
Comprehensive Testing Suite for NLP Functionality
Story 1.3 Task 7: Test all NLP components and integration
"""

import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, AsyncMock, patch
import json

# Import NLP components
from src.nlp.intent_classifier import IntentClassifier
from src.nlp.entity_extractor import EntityExtractor
from src.nlp.date_parser import NaturalLanguageDateParser
from src.nlp.context_manager import ConversationContextManager, ConversationContext, ConversationMessage
from src.nlp.batch_processor import BatchProcessor, BatchJob, BatchOperation
from src.nlp.disambiguator import NLDisambiguator, AmbiguityContext, ClarificationRequest
from src.nlp.error_handler import NLErrorHandler, ErrorContext
from src.services.nlp_service import NLPService


class TestIntentClassifier:
    """Test intent classification functionality"""

    @pytest.fixture
    async def classifier(self):
        """Create intent classifier for testing"""
        classifier = IntentClassifier()
        await classifier.initialize()
        return classifier

    @pytest.mark.asyncio
    async def test_create_task_intent(self, classifier):
        """Test detection of create task intent"""
        test_cases = [
            "Create a task to review the quarterly report",
            "Add a new task for project planning",
            "Make a task called 'Update documentation'",
            "I need to create a task to call the client"
        ]

        for user_input in test_cases:
            result = await classifier.classify_intent(user_input)
            assert result.intent == "create_task"
            assert result.confidence > 0.7

    @pytest.mark.asyncio
    async def test_update_task_intent(self, classifier):
        """Test detection of update task intent"""
        test_cases = [
            "Update the task 'Review budget' to be due tomorrow",
            "Change the priority of 'Client meeting' to high",
            "Modify the task description for project planning"
        ]

        for user_input in test_cases:
            result = await classifier.classify_intent(user_input)
            assert result.intent == "update_task"
            assert result.confidence > 0.3

    @pytest.mark.asyncio
    async def test_list_tasks_intent(self, classifier):
        """Test detection of read tasks intent"""
        test_cases = [
            "Show me my tasks",
            "List all tasks in the Marketing project",
            "What tasks do I have due today?",
            "Display tasks assigned to John"
        ]

        for user_input in test_cases:
            result = await classifier.classify_intent(user_input)
            assert result.intent == "read_tasks"
            assert result.confidence > 0.4

    @pytest.mark.asyncio
    async def test_ambiguous_input(self, classifier):
        """Test handling of ambiguous input"""
        ambiguous_inputs = [
            "task",
            "do something",
            "help me with stuff",
            "what about that thing"
        ]

        for user_input in ambiguous_inputs:
            result = await classifier.classify_intent(user_input)
            # Should have low confidence or require clarification
            assert result.confidence < 0.5 or result.intent == "get_help"


class TestEntityExtractor:
    """Test entity extraction functionality"""

    @pytest.fixture
    async def extractor(self):
        """Create entity extractor for testing"""
        extractor = EntityExtractor()
        await extractor.initialize()
        return extractor

    @pytest.mark.asyncio
    async def test_task_title_extraction(self, extractor):
        """Test extraction of task titles"""
        test_cases = [
            ("Create a task called 'Review quarterly report'", "Review quarterly report"),
            ("Add task to update the website", "update the website"),
            ("Make a task for client meeting", "client meeting")
        ]

        for user_input, expected_title in test_cases:
            result = await extractor.extract_entities(user_input)
            task_titles = [e.value for e in result.entities if e.type == "TASK_TITLE"]
            assert len(task_titles) > 0
            assert any(expected_title.lower() in title.lower() for title in task_titles)

    @pytest.mark.asyncio
    async def test_due_date_extraction(self, extractor):
        """Test extraction of due dates"""
        test_cases = [
            "Create task due tomorrow",
            "Add task with deadline next Friday",
            "Task due by end of week",
            "Due on December 25th"
        ]

        for user_input in test_cases:
            result = await extractor.extract_entities(user_input)
            due_dates = [e.value for e in result.entities if e.type == "DUE_DATE"]
            assert len(due_dates) > 0

    @pytest.mark.asyncio
    async def test_assignee_extraction(self, extractor):
        """Test extraction of assignees"""
        test_cases = [
            ("Assign task to John Smith", "John Smith"),
            ("Give this to sarah.jones@company.com", "sarah.jones@company.com"),
            ("Delegate to @mike", "mike"),
            ("For Maria Rodriguez", "Maria Rodriguez")
        ]

        for user_input, expected_assignee in test_cases:
            result = await extractor.extract_entities(user_input)
            assignees = [e.value for e in result.entities if e.type == "ASSIGNEE"]
            assert len(assignees) > 0
            assert any(expected_assignee.lower() in assignee.lower() for assignee in assignees)

    @pytest.mark.asyncio
    async def test_plan_name_extraction(self, extractor):
        """Test extraction of plan names"""
        test_cases = [
            ("Add task to Marketing Campaign project", "Marketing Campaign"),
            ("Create task in Q4 Planning board", "Q4 Planning"),
            ("For the Website Redesign plan", "Website Redesign")
        ]

        for user_input, expected_plan in test_cases:
            result = await extractor.extract_entities(user_input)
            plans = [e.value for e in result.entities if e.type == "PLAN_NAME"]
            assert len(plans) > 0
            assert any(expected_plan.lower() in plan.lower() for plan in plans)

    @pytest.mark.asyncio
    async def test_priority_extraction(self, extractor):
        """Test extraction of priorities"""
        test_cases = [
            ("Create high priority task", "high"),
            ("Mark as urgent", "urgent"),
            ("Low priority task", "low"),
            ("Set to normal priority", "normal")
        ]

        for user_input, expected_priority in test_cases:
            result = await extractor.extract_entities(user_input)
            priorities = [e.value for e in result.entities if e.type == "PRIORITY"]
            assert len(priorities) > 0
            # Check normalized priority values
            normalized_priorities = [extractor.priority_mappings.get(p.lower(), p.lower()) for p in priorities]
            assert expected_priority.lower() in normalized_priorities or any(p in expected_priority.lower() for p in normalized_priorities)


class TestDateParser:
    """Test natural language date parsing"""

    @pytest.fixture
    async def date_parser(self):
        """Create date parser for testing"""
        parser = NaturalLanguageDateParser()
        await parser.initialize()
        return parser

    @pytest.mark.asyncio
    async def test_relative_dates(self, date_parser):
        """Test parsing of relative date expressions"""
        reference_date = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)  # Monday

        test_cases = [
            ("tomorrow", 1),  # 1 day later
            ("next week", 7),  # 1 week later
            ("in 3 days", 3),  # 3 days later
            ("next Friday", 4),  # 4 days later (Friday)
        ]

        for date_str, expected_days_diff in test_cases:
            result = await date_parser.parse_date(date_str, reference_date)
            assert result.success
            assert result.parsed_date is not None

            actual_diff = (result.parsed_date - reference_date).days
            assert abs(actual_diff - expected_days_diff) <= 1  # Allow 1 day tolerance

    @pytest.mark.asyncio
    async def test_absolute_dates(self, date_parser):
        """Test parsing of absolute date formats"""
        test_cases = [
            "12/25/2024",
            "December 25, 2024",
            "2024-12-25",
            "Dec 25"
        ]

        for date_str in test_cases:
            result = await date_parser.parse_date(date_str)
            assert result.success
            assert result.parsed_date is not None
            # Should be in December
            assert result.parsed_date.month == 12

    @pytest.mark.asyncio
    async def test_business_hours_adjustment(self, date_parser):
        """Test that dates are adjusted to business hours"""
        result = await date_parser.parse_date("tomorrow")
        assert result.success
        assert result.parsed_date is not None
        # Should be set to business hours start (9 AM by default)
        assert result.parsed_date.hour == 9

    @pytest.mark.asyncio
    async def test_invalid_dates(self, date_parser):
        """Test handling of invalid date expressions"""
        invalid_dates = [
            "xyz",
            "some random text",
            "13/45/2024",  # Invalid date
            ""
        ]

        for date_str in invalid_dates:
            result = await date_parser.parse_date(date_str)
            assert not result.success


class TestContextManager:
    """Test conversation context management"""

    @pytest.fixture
    async def context_manager(self):
        """Create context manager with mock database"""
        mock_db = AsyncMock()
        context_manager = ConversationContextManager(mock_db)
        await context_manager.initialize()
        return context_manager

    @pytest.mark.asyncio
    async def test_add_message(self, context_manager):
        """Test adding messages to context"""
        user_id = "test_user"
        session_id = "test_session"

        # Mock database operations
        context_manager.database.fetch_one.return_value = None  # No existing context
        context_manager.database.execute.return_value = Mock()

        success = await context_manager.add_message(
            user_id, session_id, "user", "Create a task",
            entities={"TASK_TITLE": "Test Task"},
            intent="create_task"
        )

        assert success
        context_manager.database.execute.assert_called()

    @pytest.mark.asyncio
    async def test_resolve_reference(self, context_manager):
        """Test resolving contextual references"""
        user_id = "test_user"
        session_id = "test_session"

        # Mock context with existing entities
        mock_context = {
            'user_id': user_id,
            'session_id': session_id,
            'message_history': [
                {
                    'role': 'user',
                    'content': 'Create task in Marketing project',
                    'timestamp': datetime.now().isoformat(),
                    'entities': {'PLAN_NAME': 'Marketing'},
                    'intent': 'create_task',
                    'metadata': None
                }
            ],
            'extracted_entities': {'PLAN_NAME': 'Marketing'},
            'user_preferences': {},
            'created_at': datetime.now(),
            'updated_at': datetime.now(),
            'expires_at': datetime.now() + timedelta(hours=1)
        }

        context_manager.database.fetch_one.return_value = mock_context

        # Test resolving "same project"
        result = await context_manager.resolve_reference(user_id, session_id, "same project")
        assert result is not None
        assert result.get("PLAN_NAME") == "Marketing"


class TestBatchProcessor:
    """Test batch operation processing"""

    @pytest.fixture
    def batch_processor(self):
        """Create batch processor for testing"""
        return BatchProcessor()

    @pytest.mark.asyncio
    async def test_detect_batch_operation(self, batch_processor):
        """Test detection of batch operations"""
        test_cases = [
            ("Create 5 tasks for project Alpha", True),
            ("Add multiple tasks to the board", True),
            ("Delete all completed tasks", True),
            ("Create a single task", False)
        ]

        for user_input, should_be_batch in test_cases:
            result = await batch_processor.detect_batch_operation(user_input, {})

            if should_be_batch:
                assert result is not None
                assert result["is_batch"] is True
            else:
                assert result is None or result["is_batch"] is False

    @pytest.mark.asyncio
    async def test_create_batch_job(self, batch_processor):
        """Test creation of batch jobs"""
        user_id = "test_user"
        session_id = "test_session"
        operation_type = "create_multiple_tasks"
        parameters = {
            "quantity": 3,
            "task_template": {"title": "Task", "plan_name": "Test Project"}
        }

        batch_job = await batch_processor.create_batch_job(user_id, session_id, operation_type, parameters)

        assert batch_job.user_id == user_id
        assert batch_job.session_id == session_id
        assert batch_job.total_operations == 3
        assert len(batch_job.operations) == 3
        assert batch_job.status == "pending"

    @pytest.mark.asyncio
    async def test_batch_job_execution(self, batch_processor):
        """Test execution of batch jobs"""
        # Create a simple batch job
        user_id = "test_user"
        session_id = "test_session"
        batch_job = await batch_processor.create_batch_job(
            user_id, session_id, "create_multiple_tasks",
            {"quantity": 2, "task_template": {"title": "Task"}}
        )

        # Mock operation executor
        async def mock_executor(operation_type, parameters):
            return {"success": True, "task_id": f"task_{parameters.get('batch_index', 1)}"}

        # Execute batch job and collect progress updates
        progress_updates = []
        async for update in batch_processor.execute_batch_job(batch_job.job_id, mock_executor):
            progress_updates.append(update)

        # Should have initial, progress, and final updates
        assert len(progress_updates) >= 3
        assert progress_updates[0]["status"] == "started"
        assert progress_updates[-1]["status"] == "completed"
        assert progress_updates[-1]["progress"] == 100


class TestDisambiguator:
    """Test disambiguation and clarification logic"""

    @pytest.fixture
    async def disambiguator(self):
        """Create disambiguator with mock dependencies"""
        mock_db = AsyncMock()
        mock_context_manager = AsyncMock()
        disambiguator = NLDisambiguator(mock_db, mock_context_manager)
        return disambiguator

    @pytest.mark.asyncio
    async def test_missing_parameters(self, disambiguator):
        """Test detection of missing required parameters"""
        intent = "create_task"
        entities = {}  # Missing required title
        user_input = "Create a task"
        user_id = "test_user"
        session_id = "test_session"

        result = await disambiguator.disambiguate_command(intent, entities, user_input, user_id, session_id)

        assert result.needs_clarification
        assert len(result.clarification_requests) > 0
        assert any(req.parameter_name == "title" for req in result.clarification_requests)

    @pytest.mark.asyncio
    async def test_high_confidence_no_clarification(self, disambiguator):
        """Test that high confidence commands don't need clarification"""
        intent = "create_task"
        entities = {"TASK_TITLE": "Review budget", "PLAN_NAME": "Q4 Planning"}
        user_input = "Create task 'Review budget' in Q4 Planning"
        user_id = "test_user"
        session_id = "test_session"

        result = await disambiguator.disambiguate_command(intent, entities, user_input, user_id, session_id)

        assert not result.needs_clarification
        assert result.confidence_score > 0.7
        assert result.suggested_action is not None

    @pytest.mark.asyncio
    async def test_process_clarification_response(self, disambiguator):
        """Test processing of clarification responses"""
        clarification_request = ClarificationRequest(
            question="What would you like to name this task?",
            question_type="input_request",
            parameter_name="title"
        )

        original_entities = {}
        response = "Update documentation"

        updated_entities = await disambiguator.process_clarification_response(
            response, clarification_request, original_entities
        )

        assert "TASK_TITLE" in updated_entities
        assert updated_entities["TASK_TITLE"] == "Update documentation"


class TestErrorHandler:
    """Test natural language error handling"""

    @pytest.fixture
    def error_handler(self):
        """Create error handler for testing"""
        return NLErrorHandler()

    @pytest.mark.asyncio
    async def test_authentication_error_handling(self, error_handler):
        """Test handling of authentication errors"""
        error = Exception("Authentication failed")
        context = ErrorContext(
            error_type="authentication",
            error_code="401",
            original_message="Authentication failed",
            user_input="Create a task",
            intent="create_task",
            entities={},
            user_id="test_user",
            session_id="test_session"
        )

        response = await error_handler.handle_error(error, context)

        assert ("authentication" in response.message.lower() or
                "sign in" in response.message.lower() or
                "permission" in response.message.lower())
        assert response.tone in ["helpful", "apologetic"]
        assert len(response.suggestions) > 0
        assert not response.retry_possible  # Auth errors typically need user action

    @pytest.mark.asyncio
    async def test_network_error_handling(self, error_handler):
        """Test handling of network errors"""
        error = Exception("Connection timeout")
        context = ErrorContext(
            error_type="network",
            error_code="503",
            original_message="Connection timeout",
            user_input="List my tasks",
            intent="list_tasks",
            entities={},
            user_id="test_user",
            session_id="test_session"
        )

        response = await error_handler.handle_error(error, context)

        assert "network" in response.message.lower() or "connection" in response.message.lower()
        assert response.retry_possible  # Network errors can be retried

    @pytest.mark.asyncio
    async def test_success_response_generation(self, error_handler):
        """Test generation of success responses"""
        intent = "create_task"
        parameters = {"TASK_TITLE": "Review budget", "PLAN_NAME": "Q4 Planning"}
        result = {"task_id": "123", "status": "created"}

        message = await error_handler.generate_success_response(intent, parameters, result)

        assert "Review budget" in message
        assert "created" in message.lower() or "added" in message.lower()

    @pytest.mark.asyncio
    async def test_clarification_request_generation(self, error_handler):
        """Test generation of clarification requests"""
        ambiguous_input = "task"
        possible_intents = ["create_task", "list_tasks"]

        response = await error_handler.generate_clarification_request(ambiguous_input, possible_intents)

        assert response.tone == "encouraging"
        assert len(response.suggestions) > 0
        assert "create" in response.message.lower() or "list" in response.message.lower()


class TestNLPServiceIntegration:
    """Test integration of all NLP components"""

    @pytest.fixture
    async def nlp_service(self):
        """Create NLP service with mock dependencies"""
        mock_db = AsyncMock()

        # Create service
        nlp_service = NLPService(mock_db)

        # Mock the initialize methods of components
        with patch.object(nlp_service.intent_classifier, 'initialize'), \
             patch.object(nlp_service.entity_extractor, 'initialize'), \
             patch.object(nlp_service.date_parser, 'initialize'), \
             patch.object(nlp_service.context_manager, 'initialize'):
            await nlp_service.initialize()

        return nlp_service

    @pytest.mark.asyncio
    async def test_complete_processing_pipeline(self, nlp_service):
        """Test complete NLP processing pipeline"""
        user_input = "Create a task called 'Review quarterly report' due tomorrow"
        user_id = "test_user"
        session_id = "test_session"

        # Mock component responses
        nlp_service.intent_classifier.classify_intent = AsyncMock(return_value=Mock(
            intent="create_task", confidence=0.9, metadata={}
        ))

        nlp_service.entity_extractor.extract_entities = AsyncMock(return_value=Mock(
            entities=[
                Mock(type="TASK_TITLE", value="Review quarterly report", confidence=0.9),
                Mock(type="DUE_DATE", value="tomorrow", confidence=0.8)
            ],
            cleaned_text="Create a task due",
            metadata={}
        ))

        nlp_service.date_parser.parse_date = AsyncMock(return_value=Mock(
            success=True,
            parsed_date=datetime.now() + timedelta(days=1),
            confidence=0.9,
            original_text="tomorrow"
        ))

        nlp_service.context_manager.add_message = AsyncMock(return_value=True)
        nlp_service.context_manager.resolve_reference = AsyncMock(return_value=None)

        nlp_service.batch_processor.detect_batch_operation = AsyncMock(return_value=None)

        nlp_service.disambiguator.disambiguate_command = AsyncMock(return_value=Mock(
            needs_clarification=False,
            clarification_requests=[],
            confidence_score=0.9,
            suggested_action={"intent": "create_task", "parameters": {}},
            resolved_parameters={}
        ))

        # Process the input
        result = await nlp_service.process_natural_language(user_input, user_id, session_id)

        # Verify the pipeline executed correctly
        assert result.intent == "create_task"
        assert result.confidence > 0.8
        assert not result.needs_clarification
        assert "Review quarterly report" in str(result.entities)

    @pytest.mark.asyncio
    async def test_batch_operation_detection(self, nlp_service):
        """Test detection and handling of batch operations"""
        user_input = "Create 3 tasks for the Marketing project"
        user_id = "test_user"
        session_id = "test_session"

        # Mock batch operation detection
        nlp_service.batch_processor.detect_batch_operation = AsyncMock(return_value={
            "is_batch": True,
            "operation_type": "create_multiple_tasks",
            "quantity": 3,
            "entities": {"PLAN_NAME": "Marketing"}
        })

        nlp_service.intent_classifier.classify_intent = AsyncMock(return_value=Mock(
            intent="create_task", confidence=0.8, metadata={}
        ))

        nlp_service.entity_extractor.extract_entities = AsyncMock(return_value=Mock(
            entities=[Mock(type="QUANTITY", value="3"), Mock(type="PLAN_NAME", value="Marketing")],
            cleaned_text="Create tasks for the project",
            metadata={}
        ))

        result = await nlp_service.process_natural_language(user_input, user_id, session_id)

        assert result.is_batch_operation
        assert result.batch_info is not None
        assert result.batch_info["operation_type"] == "create_multiple_tasks"

    @pytest.mark.asyncio
    async def test_clarification_needed(self, nlp_service):
        """Test when clarification is needed"""
        user_input = "Create a task"  # Missing required information
        user_id = "test_user"
        session_id = "test_session"

        # Mock responses requiring clarification
        nlp_service.intent_classifier.classify_intent = AsyncMock(return_value=Mock(
            intent="create_task", confidence=0.8, metadata={}
        ))

        nlp_service.entity_extractor.extract_entities = AsyncMock(return_value=Mock(
            entities=[],  # No entities extracted
            cleaned_text="Create a task",
            metadata={}
        ))

        nlp_service.disambiguator.disambiguate_command = AsyncMock(return_value=Mock(
            needs_clarification=True,
            clarification_requests=[Mock(
                question="What would you like to name this task?",
                question_type="input_request",
                parameter_name="title"
            )],
            confidence_score=0.4,
            suggested_action=None,
            resolved_parameters={}
        ))

        result = await nlp_service.process_natural_language(user_input, user_id, session_id)

        assert result.needs_clarification
        assert len(result.clarification_requests) > 0
        assert result.confidence < 0.7

    @pytest.mark.asyncio
    async def test_error_handling_integration(self, nlp_service):
        """Test error handling throughout the pipeline"""
        user_input = "Create a task"
        user_id = "test_user"
        session_id = "test_session"

        # Mock an error in intent classification
        nlp_service.intent_classifier.classify_intent = AsyncMock(side_effect=Exception("Test error"))

        result = await nlp_service.process_natural_language(user_input, user_id, session_id)

        # Should handle error gracefully
        assert result.intent == "unknown"
        assert result.confidence == 0.0
        assert result.natural_language_response is not None
        assert "error" in result.natural_language_response.lower() or "issue" in result.natural_language_response.lower()


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])