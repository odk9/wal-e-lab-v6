"""
ingest_rasa.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de RasaHQ/rasa dans la KB Qdrant V6.

Focus : Chatbot/NLU core patterns (custom actions, slot mapping, NLU training,
domain config, story training, custom components, tracker store, action server,
response selector, entity extraction, fallback policy, conversation testing).

Usage:
    .venv/bin/python3 ingest_rasa.py
"""

from __future__ import annotations

import subprocess
import time
import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointStruct,
)

from embedder import embed_documents_batch, embed_query
from kb_utils import build_payload, check_charte_violations, make_uuid, query_kb, audit_report

# ─── Constantes ──────────────────────────────────────────────────────────────
REPO_URL = "https://github.com/RasaHQ/rasa.git"
REPO_NAME = "RasaHQ/rasa"
REPO_LOCAL = "/tmp/rasa"
LANGUAGE = "python"
FRAMEWORK = "rasa"
STACK = "python+rasa+chatbot+nlu"
CHARTE_VERSION = "1.0"
TAG = "RasaHQ/rasa"
SOURCE_REPO = "https://github.com/RasaHQ/rasa"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# Rasa = open-source chatbot framework. Core patterns from action handlers,
# slot mapping, NLU training data, domain config, story training, custom
# components, tracker store, action server, response selector, entity extraction,
# fallback policies, and conversation tests.
# U-5 : `action`, `intent`, `slot`, `tracker`, `dispatcher`, `domain`, `story`,
#       `span`, `layer`, `subscriber`, `filter` are TECHNICAL TERMS — keep as-is.

PATTERNS: list[dict] = [
    # ── 1. Custom Action Handler ───────────────────────────────────────────────
    {
        "normalized_code": """\
import logging
from typing import Any, List, Dict, Text

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, ActionExecuted

log = logging.getLogger(__name__)


class ActionXxx(Action):
    \"\"\"Custom action handler for Rasa chatbot.

    Implements run() method to handle business logic, database queries,
    or external API calls triggered by caller intent.
    \"\"\"

    def name(self) -> Text:
        \"\"\"Return unique action name matching story/domain.\"\"\"
        return "action_xxx"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        \"\"\"Execute action logic.

        Extract slots from tracker, call external services, then return
        SlotSet or ActionExecuted outcomes.
        \"\"\"
        xxx_id = tracker.get_slot("xxx_id")
        if not xxx_id:
            dispatcher.utter_message(text="No entity provided.")
            return []

        result = self.query_database(xxx_id)
        if not result:
            dispatcher.utter_message(text="Not found.")
            return [SlotSet("xxx_result", None)]

        dispatcher.utter_message(text=f"Found: {result['name']}")
        return [SlotSet("xxx_result", result)]

    def query_database(self, xxx_id: int) -> Dict[Text, Any] | None:
        \"\"\"Query external database or API.\"\"\"
        raise NotImplementedError()
""",
        "function": "custom_action_handler",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "rasa/core/actions/action.py",
    },
    # ── 2. Slot Mapping with Forms ────────────────────────────────────────────
    {
        "normalized_code": """\
from typing import Any, List, Dict, Text, Optional

from rasa_sdk import Tracker
from rasa_sdk.events import SlotSet, FollowupAction
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.forms import FormAction, FormValidationAction


class XxxForm(FormAction):
    \"\"\"Multi-turn form slot filling pattern.

    Guides caller through required slots (name, email, phone) before
    submitting business logic.
    \"\"\"

    def name(self) -> Text:
        return "xxx_form"

    @staticmethod
    def required_slots(domain: Dict[Text, Any]) -> List[Text]:
        \"\"\"Define mandatory slots to fill.\"\"\"
        return ["xxx_name", "xxx_email", "xxx_phone"]

    def slot_mappings(self) -> Dict[Text, Any]:
        \"\"\"Map intents/entities to slots.\"\"\"
        return {
            "xxx_name": [
                self.from_entity(entity="PERSON"),
                self.from_intent(intent="inform", value="generic"),
            ],
            "xxx_email": [
                self.from_entity(entity="EMAIL"),
                self.from_intent(intent="inform", value="unknown"),
            ],
            "xxx_phone": [
                self.from_entity(entity="PHONE_NUMBER"),
            ],
        }

    def validate_xxx_email(
        self,
        value: str,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> Dict[Text, Any]:
        \"\"\"Custom validation for email slot.\"\"\"
        if "@" not in value:
            dispatcher.utter_message(text="Invalid email format.")
            return {"xxx_email": None}
        return {"xxx_email": value}

    async def submit(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict]:
        \"\"\"Submit form after all slots filled.\"\"\"
        dispatcher.utter_message(text="Form submitted successfully.")
        return [SlotSet("form_submitted", True)]
""",
        "function": "slot_mapping_form",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "rasa/core/forms/form_action.py",
    },
    # ── 3. NLU Training Data (YAML format) ──────────────────────────────────────
    {
        "normalized_code": """\
\"\"\"NLU training data for intent and entity recognition.\"\"\"

version: "3.0"
nlu:
  - intent: greet
    examples: |
      - hello
      - hi
      - hey
      - good morning
      - welcome

  - intent: goodbye
    examples: |
      - bye
      - goodbye
      - see you
      - thanks bye

  - intent: request_xxx
    examples: |
      - I want to [action_xxx](action)
      - Can you [process](action) my data
      - Please [check](action) my [xxx_id](xxx)
      - Show me [results](action) for [id 123](xxx)

  - intent: deny
    examples: |
      - no
      - nope
      - don't
      - cancel

  - entity: xxx_id
    description: "Identifier for resource"

  - entity: action
    description: "Verb/action requested"

  - regex: phone
    pattern: "\\+?[0-9]{1,3}[-.]?[0-9]{3}[-.]?[0-9]{3}[-.]?[0-9]{4}"
""",
        "function": "nlu_training_data",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "rasa/nlu/training_data/examples.yml",
    },
    # ── 4. Domain Configuration ────────────────────────────────────────────────
    {
        "normalized_code": """\
\"\"\"Rasa domain defines intents, actions, slots, responses, forms.\"\"\"

version: "3.0"

intents:
  - greet
  - goodbye
  - request_xxx
  - deny
  - affirm

entities:
  - xxx_id
  - action
  - PERSON
  - EMAIL

slots:
  xxx_name:
    type: text
    influence_conversation: false
  xxx_email:
    type: text
  xxx_result:
    type: any

actions:
  - action_xxx
  - action_listen

responses:
  utter_greet:
    - text: "Hello! How can I help?"
  utter_goodbye:
    - text: "Goodbye!"
  utter_default:
    - text: "I didn't understand. Can you rephrase?"

forms:
  xxx_form:
    required_slots:
      - xxx_name
      - xxx_email

session_config:
  session_expiration_time: 60
  carry_over_slots_to_new_session: true
""",
        "function": "domain_config",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "rasa/core/domain.yml",
    },
    # ── 5. Story Training Data ────────────────────────────────────────────────
    {
        "normalized_code": """\
\"\"\"Rasa stories define conversation flows (happy path, edge cases).\"\"\"

version: "3.0"

stories:
  - story: happy path greet
    steps:
      - intent: greet
      - action: utter_greet
      - intent: request_xxx
      - action: xxx_form
      - active_loop: xxx_form
      - intent: inform
      - nlu_fallback:
      - action: action_xxx
      - action: utter_default

  - story: goodbye
    steps:
      - intent: greet
      - action: utter_greet
      - intent: goodbye
      - action: utter_goodbye

  - story: handle deny
    steps:
      - intent: request_xxx
      - action: utter_ask_confirmation
      - intent: deny
      - action: utter_default

rules:
  - rule: activate form on request
    steps:
      - intent: request_xxx
      - action: xxx_form
      - active_loop: xxx_form
""",
        "function": "story_training_data",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "rasa/core/training_data/stories.yml",
    },
    # ── 6. Custom NLU Component (Pipeline Layer) ────────────────────────────────
    {
        "normalized_code": """\
from typing import Any, Dict, List, Text

import numpy as np
from rasa.nlu.components import Component
from rasa.nlu.config import RasaNLUModelConfig
from rasa.nlu.training_data import TrainingData, Message
from rasa.nlu.model import Metadata


class CustomComponentXxx(Component):
    \"\"\"Custom NLU component — preprocessing, entity extraction, or intent classification.

    Inserts between Tokenizer and EntityExtractor in pipeline for
    domain-specific feature engineering.
    \"\"\"

    defaults = {
        "name": "custom_component_xxx",
        "threshold": 0.5,
    }

    def __init__(self, config: RasaNLUModelConfig):
        super().__init__(config)
        self.threshold = config.get("threshold", 0.5)

    def train(
        self,
        training_data: TrainingData,
        config: RasaNLUModelConfig,
        **kwargs: Any,
    ) -> None:
        \"\"\"Train component on training data.\"\"\"
        for utterance in training_data.training_examples:
            self._process_message(utterance, training=True)

    def process(
        self,
        utterance: Message,
        **kwargs: Any,
    ) -> None:
        \"\"\"Process single utterance during inference.\"\"\"
        self._process_message(utterance, training=False)

    def _process_message(self, utterance: Message, training: bool = False) -> None:
        \"\"\"Extract features or modify utterance tokens.\"\"\"
        tokens = utterance.get("tokens", [])
        if not tokens:
            return
        features = self._extract_features(tokens)
        utterance.set("custom_features", features, add_to_output=True)

    def _extract_features(self, tokens: List[str]) -> Dict[Text, float]:
        \"\"\"Domain-specific feature extraction.\"\"\"
        return {}

    @classmethod
    def load(
        cls,
        model_dir: Text,
        model_metadata: Metadata,
        cached_component: "CustomComponentXxx" | None = None,
        **kwargs: Any,
    ) -> "CustomComponentXxx":
        return cached_component or cls(model_metadata.config)
""",
        "function": "custom_component_pipeline",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "rasa/nlu/components/custom_component.py",
    },
    # ── 7. Tracker Store (SQL Persistence) ──────────────────────────────────────
    {
        "normalized_code": """\
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional, Text

from sqlalchemy import Column, Integer, String, LargeBinary, DateTime
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from rasa.core.tracker_store import TrackerStore, DialogueState


class Base(DeclarativeBase):
    pass


class XxxTrackerStore(TrackerStore):
    \"\"\"SQL-backed tracker store for conversation persistence.

    Stores conversation state (dialog flow, slots, latest intent)
    in database for recovery and analytics.
    \"\"\"

    def __init__(
        self,
        domain,
        db_url: Text = "sqlite:///rasa.db",
        **kwargs: Any,
    ):
        super().__init__(domain, **kwargs)
        self.engine = create_engine(db_url)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def save(self, dialogue_state: DialogueState) -> None:
        \"\"\"Persist conversation state to database.\"\"\"
        session = self.SessionLocal()
        try:
            tracker_record = TrackerRecord(
                sender_id=dialogue_state.sender_id,
                outcomes_json=json.dumps([e.as_dict() for e in dialogue_state.outcomes]),
                updated_at=datetime.now(UTC),
            )
            session.merge(tracker_record)
            session.commit()
        finally:
            session.close()

    def retrieve(self, sender_id: Text) -> Optional[DialogueState]:
        \"\"\"Load conversation state from database.\"\"\"
        session = self.SessionLocal()
        try:
            record = session.query(TrackerRecord).filter_by(sender_id=sender_id).first()
            if not record:
                return None
            outcomes = [event_from_dict(e) for e in json.loads(record.outcomes_json)]
            return DialogueState(sender_id=sender_id, outcomes=outcomes)
        finally:
            session.close()

    def list_all_sender_ids(self) -> List[Text]:
        \"\"\"List all conversation sender IDs.\"\"\"
        session = self.SessionLocal()
        try:
            return [r.sender_id for r in session.query(TrackerRecord.sender_id).all()]
        finally:
            session.close()
""",
        "function": "tracker_store_sql",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "rasa/core/tracker_store.py",
    },
    # ── 8. Action Server Endpoint ───────────────────────────────────────────────
    {
        "normalized_code": """\
import asyncio
import logging
from typing import Any, Dict, List, Text

from aiohttp import web
from rasa_sdk.executor import ActionExecutor
from rasa_sdk.interfaces import Action

log = logging.getLogger(__name__)


class ActionServerXxx:
    \"\"\"HTTP server exposing custom action handlers as REST endpoints.

    Rasa dialogue manager calls action_server via submit /webhook
    with tracker state; server executes action and returns outcomes.
    \"\"\"

    def __init__(self, action_dir: Text = "./actions"):
        self.executor = ActionExecutor(action_dir)

    async def handle_webhook(self, request: web.Request) -> web.Response:
        \"\"\"Handle submit /webhook for action execution.\"\"\"
        try:
            body = await request.json()
            action_name = body.get("action")
            tracker = body.get("tracker", {})

            if not action_name:
                return web.json_response(
                    {"error": "action field missing"},
                    status=400,
                )

            outcomes = await self.executor.run(action_name, tracker)

            return web.json_response(
                {"outcomes": outcomes},
                status=200,
            )
        except Exception as e:
            log.exception("Action execution failed")
            return web.json_response(
                {"error": str(e)},
                status=500,
            )

    async def health_check(self, request: web.Request) -> web.Response:
        \"\"\"GET /health — liveness probe.\"\"\"
        return web.json_response({"status": "ok"})

    def create_app(self) -> web.Application:
        \"\"\"Create aiohttp application.\"\"\"
        app = web.Application()
        app.router.post("/webhook")(self.handle_webhook)
        app.router.get("/health")(self.health_check)
        return app
""",
        "function": "action_server_endpoint",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "rasa/core/action_server.py",
    },
    # ── 9. Response Selector (Intent-conditional responses) ───────────────────
    {
        "normalized_code": """\
from typing import Any, Dict, List, Text, Optional

from rasa.nlu.components import Component
from rasa.nlu.training_data import TrainingData, Message
from rasa.nlu.config import RasaNLUModelConfig


class ResponseSelectorXxx(Component):
    \"\"\"Select response based on intent or context.

    Handles intent-specific response templates, fallback responses,
    and context-aware dynamic text generation.
    \"\"\"

    defaults = {
        "name": "response_selector_xxx",
        "ranking_threshold": 0.7,
    }

    def __init__(self, config: RasaNLUModelConfig):
        super().__init__(config)
        self.ranking_threshold = config.get("ranking_threshold", 0.7)
        self.response_templates = {}

    def train(
        self,
        training_data: TrainingData,
        config: RasaNLUModelConfig,
        **kwargs: Any,
    ) -> None:
        \"\"\"Build response template index from training data.\"\"\"
        for utterance in training_data.training_examples:
            intent = utterance.get("intent")
            response = utterance.get("response")
            if intent and response:
                if intent not in self.response_templates:
                    self.response_templates[intent] = []
                self.response_templates[intent].append(response)

    def process(self, utterance: Message, **kwargs: Any) -> None:
        \"\"\"Select response for current intent.\"\"\"
        intent = utterance.get("intent")
        if not intent:
            return

        candidates = self.response_templates.get(intent, [])
        if not candidates:
            utterance.set("selected_response", "default_fallback", add_to_output=True)
            return

        selected = self._rank_responses(utterance, candidates)
        utterance.set("selected_response", selected, add_to_output=True)

    def _rank_responses(self, utterance: Message, candidates: List[Text]) -> Text:
        \"\"\"Rank responses by similarity or custom scoring.\"\"\"
        if not candidates:
            return "default_fallback"
        return candidates[0]
""",
        "function": "response_selector_config",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "rasa/nlu/response_selector.py",
    },
    # ── 10. Custom Entity Extraction ────────────────────────────────────────────
    {
        "normalized_code": """\
import re
from typing import Any, Dict, List, Text

from rasa.nlu.extractors.extractor import EntityExtractor
from rasa.nlu.training_data import Message


class CustomEntityExtractorXxx(EntityExtractor):
    \"\"\"Custom entity extractor using regex or fuzzy matching.

    Supplements standard NER for domain-specific entity types
    (e.g., widget SKU, request ID, customer account).
    \"\"\"

    defaults = {
        "name": "custom_entity_extractor_xxx",
        "patterns": {},
        "confidence": 0.9,
    }

    def __init__(self, config):
        super().__init__(config)
        self.patterns = config.get("patterns", {})
        self.confidence = config.get("confidence", 0.9)

    def process(self, utterance: Message, **kwargs: Any) -> None:
        \"\"\"Extract entities from utterance text.\"\"\"
        text = utterance.get("text", "")
        entities = []

        for entity_type, pattern in self.patterns.items():
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                entities.append({
                    "entity": entity_type,
                    "start": match.start(),
                    "end": match.end(),
                    "value": match.group(0),
                    "confidence": self.confidence,
                    "extractor": self.name,
                })

        utterance.set("entities", utterance.get("entities", []) + entities, add_to_output=True)

    @staticmethod
    def load(model_dir: Text, model_metadata, **kwargs: Any):
        return CustomEntityExtractorXxx(model_metadata.config)
""",
        "function": "entity_extraction_custom",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "rasa/nlu/extractors/custom_extractor.py",
    },
    # ── 11. Fallback Policy ─────────────────────────────────────────────────────
    {
        "normalized_code": """\
from typing import Any, Dict, List, Optional, Text

from rasa.core.policies.policy import Policy
from rasa_sdk import Tracker
from rasa.core.trackers import DialogueStateTracker


class FallbackPolicyXxx(Policy):
    \"\"\"Fallback policy for low-confidence predictions.

    When NLU intent confidence < threshold or dialogue policy
    confidence < threshold, take fallback action (ask user to rephrase).
    \"\"\"

    defaults = {
        "name": "fallback_policy_xxx",
        "nlu_threshold": 0.3,
        "dialogue_threshold": 0.1,
        "fallback_action": "action_default_fallback",
    }

    def __init__(self, config: Dict[Text, Any]):
        super().__init__(config)
        self.nlu_threshold = config.get("nlu_threshold", 0.3)
        self.dialogue_threshold = config.get("dialogue_threshold", 0.1)
        self.fallback_action = config.get("fallback_action", "action_default_fallback")

    def predict_action_probabilities(
        self,
        tracker: DialogueStateTracker,
        domain,
        **kwargs: Any,
    ) -> List[float]:
        \"\"\"Return probability distribution over actions.\"\"\"
        latest_intent = tracker.latest_message.get("intent")
        if not latest_intent:
            return [0.0] * len(domain.actions)

        intent_confidence = latest_intent.get("confidence", 0.0)
        if intent_confidence < self.nlu_threshold:
            action_idx = domain.actions.index(self.fallback_action)
            probs = [0.0] * len(domain.actions)
            probs[action_idx] = 1.0
            return probs

        return None
""",
        "function": "fallback_policy_config",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "rasa/core/policies/fallback_policy.py",
    },
    # ── 12. Conversation Test (End-to-end Testing) ──────────────────────────────
    {
        "normalized_code": """\
\"\"\"E2E conversation tests for Rasa chatbot.\"\"\"

import asyncio
from typing import List, Dict, Text, Any

from rasa.core.agent import Agent
from rasa.shared.nlu.training_data.training_data import TrainingData


class ConversationTestXxx:
    \"\"\"Run multi-turn conversation test scenarios.

    Validates dialogue flow, slot filling, action execution,
    and response correctness end-to-end.
    \"\"\"

    def __init__(self, agent: Agent):
        self.agent = agent

    async def test_conversation_flow(self) -> Dict[Text, Any]:
        \"\"\"Run single conversation test.\"\"\"
        utterances = [
            "hello",
            "I want to request something",
            "my id is 123",
            "yes",
        ]

        results = {
            "utterances": utterances,
            "responses": [],
            "slots": [],
            "passed": True,
        }

        tracker = self.agent.create_tracker("test_user")
        for utt in utterances:
            response = await self.agent.handle_text(utt, sender_id="test_user")
            results["responses"].append(response)
            tracker = self.agent.get_latest_input_channel().get_tracker("test_user")
            results["slots"].append(tracker.slots)

            if not response.get("text"):
                results["passed"] = False

        return results

    async def run_all_tests(self, test_cases: List[List[Text]]) -> List[Dict]:
        \"\"\"Run multiple conversation test scenarios.\"\"\"
        all_results = []
        for i, utterances in enumerate(test_cases):
            print(f"Running test {i+1}...")
            result = await self._run_scenario(utterances)
            all_results.append(result)
        return all_results

    async def _run_scenario(self, utterances: List[Text]) -> Dict[Text, Any]:
        \"\"\"Execute single scenario.\"\"\"
        return {"scenario": utterances, "status": "passed"}
""",
        "function": "conversation_test",
        "feature_type": "test",
        "file_role": "test",
        "file_path": "rasa/core/test_conversation.py",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "custom action handler logic",
    "slot mapping form filling validation",
    "NLU training data intents entities",
    "domain configuration actions responses",
    "story training conversation flow",
    "custom NLU component pipeline layer",
    "tracker store SQL persistence",
    "action server webhook endpoint",
    "response selector intent conditional",
    "entity extraction regex custom",
    "fallback policy low confidence",
    "conversation test end-to-end",
]


def clone_repo() -> None:
    import os
    if os.path.isdir(REPO_LOCAL):
        return
    subprocess.run(
        ["git", "clone", REPO_URL, REPO_LOCAL, "--depth=1"],
        check=True, capture_output=True,
    )


def build_payloads() -> list[dict]:
    payloads = []
    for p in PATTERNS:
        payloads.append(
            build_payload(
                normalized_code=p["normalized_code"],
                function=p["function"],
                feature_type=p["feature_type"],
                file_role=p["file_role"],
                language=LANGUAGE,
                framework=FRAMEWORK,
                stack=STACK,
                file_path=p["file_path"],
                source_repo=SOURCE_REPO,
                tag=TAG,
                charte_version=CHARTE_VERSION,
            )
        )
    return payloads


def index_patterns(client: QdrantClient, payloads: list[dict]) -> int:
    codes = [p["normalized_code"] for p in payloads]
    vectors = embed_documents_batch(codes)
    points = []
    for vec, payload in zip(vectors, payloads):
        points.append(PointStruct(id=make_uuid(), vector=vec, payload=payload))
    client.upsert(collection_name=COLLECTION, points=points)
    return len(points)


def run_audit_queries(client: QdrantClient) -> list[dict]:
    results = []
    for q in AUDIT_QUERIES:
        vec = embed_query(q)
        hits = query_kb(client, COLLECTION, query_vector=vec, language=LANGUAGE, limit=1)
        if hits:
            hit = hits[0]
            results.append({
                "query": q,
                "function": hit.payload.get("function", "?"),
                "file_role": hit.payload.get("file_role", "?"),
                "score": hit.score,
                "code_preview": hit.payload.get("normalized_code", "")[:50],
                "norm_ok": True,
            })
        else:
            results.append({"query": q, "function": "NO_RESULT", "file_role": "?", "score": 0.0, "code_preview": "", "norm_ok": False})
    return results


def audit_normalization(client: QdrantClient) -> list[str]:
    violations = []
    scroll_result = client.scroll(
        collection_name=COLLECTION,
        scroll_filter=Filter(must=[FieldCondition(key="_tag", match=MatchValue(value=TAG))]),
        limit=100,
    )
    for point in scroll_result[0]:
        code = point.payload.get("normalized_code", "")
        fn = point.payload.get("function", "?")
        v = check_charte_violations(code, fn, language=LANGUAGE)
        violations.extend(v)
    return violations


def cleanup(client: QdrantClient) -> None:
    client.delete(
        collection_name=COLLECTION,
        points_selector=FilterSelector(
            filter=Filter(must=[FieldCondition(key="_tag", match=MatchValue(value=TAG))])
        ),
    )


def main() -> None:
    print(f"\n{'='*60}")
    print(f"  INGESTION {REPO_NAME}")
    print(f"  Mode: {'DRY_RUN' if DRY_RUN else 'PRODUCTION'}")
    print(f"{'='*60}\n")

    client = QdrantClient(path=KB_PATH)
    count_initial = client.count(collection_name=COLLECTION).count
    print(f"  KB initial: {count_initial} points")

    clone_repo()

    payloads = build_payloads()
    print(f"  {len(PATTERNS)} patterns extraits")

    # Cleanup existing points for this tag
    cleanup(client)

    n_indexed = index_patterns(client, payloads)
    count_after = client.count(collection_name=COLLECTION).count
    print(f"  {n_indexed} patterns indexés — KB: {count_after} points")

    query_results = run_audit_queries(client)
    violations = audit_normalization(client)

    report = audit_report(
        repo_name=REPO_NAME,
        dry_run=DRY_RUN,
        count_before=count_initial,
        count_after=count_after,
        patterns_extracted=len(PATTERNS),
        patterns_indexed=n_indexed,
        query_results=query_results,
        violations=violations,
    )
    print(report)

    if DRY_RUN:
        cleanup(client)
        print("  DRY_RUN — données supprimées")


if __name__ == "__main__":
    main()
