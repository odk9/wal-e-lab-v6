"""
ingest_chainlit.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de Chainlit/chainlit dans la KB Qdrant V6.

Focus : CORE patterns Chatbot UI framework — on_message handler, on_chat_start,
streaming response, step decorator, file upload handling, user session,
action callback, AskUserMessage input, chat profiles, custom auth,
LangChain integration, elements (Image, Text, File).

Usage:
    .venv/bin/python3 ingest_chainlit.py
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
REPO_URL = "https://github.com/Chainlit/chainlit.git"
REPO_NAME = "Chainlit/chainlit"
REPO_LOCAL = "/tmp/chainlit"
LANGUAGE = "python"
FRAMEWORK = "chainlit"
STACK = "python+chainlit+chatbot"
CHARTE_VERSION = "1.0"
TAG = "Chainlit/chainlit"
SOURCE_REPO = "https://github.com/Chainlit/chainlit"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# Chainlit = chatbot UI framework for Python.
# Patterns CORE : message handlers, streaming, file upload, session, auth, LangChain.
# U-5 : `message` est OK (core term), `user` est OK, `session` est OK, `action` est OK.

PATTERNS: list[dict] = [
    # ── 1. on_message Handler — Main Chat Entry Point ───────────────────────
    {
        "normalized_code": """\
import chainlit as cl

@cl.on_message
async def on_message_handler(reply: cl.Message) -> None:
    \"\"\"Handle incoming user message.

    The reply parameter is a Message object containing user input.
    Process the reply and send response back to user.
    \"\"\"
    xxxUser = reply.author
    xxxContent = reply.content

    await cl.Message(
        content=f"Received: {xxxContent} from {xxxUser}",
        author="Xxx",
    ).send()

    xxxResponse = await process_user_query(xxxContent)
    await cl.Message(
        content=xxxResponse,
        author="Assistant",
    ).send()


async def process_user_query(xxxQuery: str) -> str:
    \"\"\"Process user query and return response.\"\"\"
    return f"Response to: {xxxQuery}"
""",
        "function": "on_message_handler_main_chat",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "chainlit/message_handler.py",
    },
    # ── 2. on_chat_start Initialization ────────────────────────────────────
    {
        "normalized_code": """\
import chainlit as cl

@cl.on_chat_start
async def on_chat_start_setup() -> None:
    \"\"\"Initialize chat session on startup.

    Called once when user starts a new chat session.
    Setup resources, load models, initialize context.
    \"\"\"
    xxxAccount = cl.user_session.get("user_id")

    await cl.Message(
        content="Welcome! I am your assistant. How can I help?",
        author="Assistant",
    ).send()

    xxxLlmModel = await load_model("gpt-3.5-turbo")
    cl.user_session.set("model", xxxLlmModel)

    xxxMemory = []
    cl.user_session.set("memory", xxxMemory)

    xxxContext = {
        "session_id": cl.user_session.get("session_id"),
        "start_time": cl.user_session.get("start_time"),
    }
    cl.user_session.set("context", xxxContext)


async def load_model(xxxModelName: str):
    \"\"\"Load LLM model by name.\"\"\"
    return {"name": xxxModelName, "loaded": True}
""",
        "function": "on_chat_start_initialization",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "chainlit/chat_start.py",
    },
    # ── 3. Streaming Response ──────────────────────────────────────────────
    {
        "normalized_code": """\
import chainlit as cl

@cl.on_message
async def on_message_streaming(reply: cl.Message) -> None:
    \"\"\"Handle message with streaming response.

    Stream response token-by-token to user for better UX.
    \"\"\"
    xxxModel = cl.user_session.get("model")
    xxxUserQuery = reply.content

    xxxResponseMsg = cl.Message(
        content="",
        author="Assistant",
    )

    xxxStreamedText = ""
    async for xxxChunk in stream_llm_response(xxxModel, xxxUserQuery):
        xxxStreamedText += xxxChunk
        await xxxResponseMsg.stream_token(xxxChunk)

    await xxxResponseMsg.update()

    xxxMemory = cl.user_session.get("memory", [])
    xxxMemory.append({
        "role": "user",
        "content": xxxUserQuery,
    })
    xxxMemory.append({
        "role": "assistant",
        "content": xxxStreamedText,
    })
    cl.user_session.set("memory", xxxMemory)


async def stream_llm_response(xxxModel, xxxQuery: str):
    \"\"\"Stream response from LLM model.\"\"\"
    for xxxToken in ["Hello", " ", "world", "!"]:
        yield xxxToken
""",
        "function": "streaming_response_token_by_token",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "chainlit/streaming.py",
    },
    # ── 4. Step Decorator for LangChain Chains ─────────────────────────────
    {
        "normalized_code": """\
import chainlit as cl
from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate

@cl.on_message
async def on_message_with_steps(reply: cl.Message) -> None:
    \"\"\"Process message using LangChain with step tracking.

    Each step in the chain is tracked and displayed to user.
    \"\"\"
    xxxChain = cl.user_session.get("chain")

    @cl.step(type="tool", name="Retrieve Context")
    async def retrieve_context(xxxQuery: str) -> str:
        \"\"\"Retrieve relevant context for query.\"\"\"
        xxxResults = await search_knowledge_base(xxxQuery)
        return "\\n".join(xxxResults)

    @cl.step(type="tool", name="Generate Response")
    async def generate_response(xxxContext: str, xxxQuery: str) -> str:
        \"\"\"Generate response using context.\"\"\"
        xxxPrompt = PromptTemplate(
            input_variables=["context", "question"],
            template="Context: {context}\\nQuestion: {question}",
        )
        xxxOutput = xxxChain.run(context=xxxContext, question=xxxQuery)
        return xxxOutput

    xxxContext = await retrieve_context(reply.content)
    xxxResponse = await generate_response(xxxContext, reply.content)

    await cl.Message(
        content=xxxResponse,
        author="Assistant",
    ).send()


async def search_knowledge_base(xxxQuery: str) -> list[str]:
    \"\"\"Search knowledge base.\"\"\"
    return ["result1", "result2"]
""",
        "function": "step_decorator_langchain_chain",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "chainlit/steps.py",
    },
    # ── 5. File Upload Handler ─────────────────────────────────────────────
    {
        "normalized_code": """\
import chainlit as cl
import aiofiles

@cl.on_message
async def on_message_file_upload(reply: cl.Message) -> None:
    \"\"\"Handle user message with file uploads.

    Process uploaded files and use them in response generation.
    \"\"\"
    xxxFiles = reply.elements if reply.elements else []

    xxxProcessedFiles = []
    for xxxFile in xxxFiles:
        xxxPath = xxxFile.path
        xxxName = xxxFile.name
        xxxMimeType = xxxFile.mime

        xxxContent = None
        async with aiofiles.open(xxxPath, "r") as xxxF:
            xxxContent = await xxxF.read()

        xxxResult = await process_file(xxxName, xxxContent, xxxMimeType)
        xxxProcessedFiles.append(xxxResult)

    xxxResponse = f"Processed {len(xxxProcessedFiles)} files"
    if reply.content:
        xxxResponse += f" and message: {reply.content}"

    await cl.Message(
        content=xxxResponse,
        author="Assistant",
    ).send()


async def process_file(xxxFileName: str, xxxContent: str, xxxMimeType: str) -> dict:
    \"\"\"Process uploaded file.\"\"\"
    return {
        "name": xxxFileName,
        "size": len(xxxContent),
        "mime": xxxMimeType,
        "processed": True,
    }
""",
        "function": "file_upload_handler_process",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "chainlit/file_upload.py",
    },
    # ── 6. User Session Management ─────────────────────────────────────────
    {
        "normalized_code": """\
import chainlit as cl
from datetime import datetime

@cl.on_chat_start
async def session_management_setup() -> None:
    \"\"\"Setup and manage user session.\"\"\"
    xxxSessionId = cl.user_session.get("session_id")
    xxxUserId = cl.user_session.get("user_id")
    xxxAuthAccount = cl.user_session.get("user")

    xxxSession = {
        "id": xxxSessionId,
        "user_id": xxxUserId,
        "username": xxxAuthAccount.identifier if xxxAuthAccount else "anonymous",
        "start_time": datetime.now().isoformat(),
        "state": {},
    }

    cl.user_session.set("session", xxxSession)

    xxxConversationHistory = []
    cl.user_session.set("conversation", xxxConversationHistory)


@cl.on_message
async def update_session_on_message(reply: cl.Message) -> None:
    \"\"\"Update session with each message.\"\"\"
    xxxSession = cl.user_session.get("session", {})
    xxxConversation = cl.user_session.get("conversation", [])

    xxxConversation.append({
        "role": "user",
        "content": reply.content,
        "timestamp": datetime.now().isoformat(),
    })

    xxxSession["last_message_time"] = datetime.now().isoformat()
    xxxSession["message_count"] = len(xxxConversation)

    cl.user_session.set("conversation", xxxConversation)
    cl.user_session.set("session", xxxSession)
""",
        "function": "session_management_user_state",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "chainlit/session.py",
    },
    # ── 7. Action Callback Handler ─────────────────────────────────────────
    {
        "normalized_code": """\
import chainlit as cl

@cl.on_action
async def on_action_callback(action: cl.Action) -> None:
    \"\"\"Handle user action callbacks.

    Actions are interactive elements that user can click/interact with.
    Process the action and update UI accordingly.
    \"\"\"
    xxxActionName = action.name
    xxxActionValue = action.value
    xxxReplyId = action.message_id

    xxxResult = await process_action(xxxActionName, xxxActionValue)

    if xxxResult["success"]:
        await cl.Message(
            content=f"Action {xxxActionName} completed: {xxxResult.get('payload', '')}",
            author="Assistant",
        ).send()
    else:
        await cl.Message(
            content=f"Action failed: {xxxResult.get('error', 'Unknown error')}",
            author="System",
        ).send()

    if xxxReplyId:
        xxxReply = await cl.Message.get(xxxReplyId)
        xxxReply.actions = []
        await xxxReply.update()


async def process_action(xxxActionName: str, xxxValue: str) -> dict:
    \"\"\"Process specific action.\"\"\"
    return {
        "success": True,
        "payload": f"Processed action: {xxxActionName}",
    }
""",
        "function": "action_callback_interactive",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "chainlit/action.py",
    },
    # ── 8. Ask User Input (AskUserMessage) ─────────────────────────────────
    {
        "normalized_code": """\
import chainlit as cl

@cl.on_message
async def on_message_ask_user(reply: cl.Message) -> None:
    \"\"\"Ask user for additional input during conversation.\"\"\"
    xxxQuery = reply.content

    xxxOptions = [
        cl.ChatProfile(name="Option A", markdown_description="Description A"),
        cl.ChatProfile(name="Option B", markdown_description="Description B"),
    ]

    xxxAskReply = cl.AskUserMessage(
        content=f"You asked: {xxxQuery}. Please choose an option:",
        timeout=60,
        raise_on_timeout=False,
    )

    xxxAccountResponse = await xxxAskReply.send()

    if xxxAccountResponse:
        xxxChoice = xxxAccountResponse.content
        xxxResult = await process_account_choice(xxxChoice)

        await cl.Message(
            content=xxxResult,
            author="Assistant",
        ).send()
    else:
        await cl.Message(
            content="Request timed out. Please try again.",
            author="System",
        ).send()


async def process_account_choice(xxxChoice: str) -> str:
    \"\"\"Process account's choice.\"\"\"
    return f"You chose: {xxxChoice}. Processing..."
""",
        "function": "ask_user_input_askusermessage",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "chainlit/ask_user.py",
    },
    # ── 9. Chat Profiles Configuration ─────────────────────────────────────
    {
        "normalized_code": """\
import chainlit as cl

@cl.set_chat_profiles
async def chat_profiles_config() -> list[cl.ChatProfile]:
    \"\"\"Define available chat profiles/personas.\"\"\"
    xxxProfiles = [
        cl.ChatProfile(
            name="Helpful Assistant",
            markdown_description="A helpful and friendly assistant",
            icon="https://example.com/icon1.png",
        ),
        cl.ChatProfile(
            name="Code Expert",
            markdown_description="Specialized in coding and technical questions",
            icon="https://example.com/icon2.png",
        ),
        cl.ChatProfile(
            name="Business Analyst",
            markdown_description="Helps with business analysis and planning",
            icon="https://example.com/icon3.png",
        ),
    ]
    return xxxProfiles


@cl.on_chat_start
async def setup_selected_profile() -> None:
    \"\"\"Setup based on selected chat profile.\"\"\"
    xxxProfile = cl.user_session.get("chat_profile")

    xxxProfileConfig = {
        "Helpful Assistant": {
            "system_prompt": "You are a helpful assistant",
            "temperature": 0.7,
        },
        "Code Expert": {
            "system_prompt": "You are a coding expert",
            "temperature": 0.2,
        },
        "Business Analyst": {
            "system_prompt": "You are a business analyst",
            "temperature": 0.5,
        },
    }

    xxxConfig = xxxProfileConfig.get(xxxProfile, {})
    cl.user_session.set("profile_config", xxxConfig)
""",
        "function": "chat_profiles_configuration",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "chainlit/profiles.py",
    },
    # ── 10. Custom Authentication ──────────────────────────────────────────
    {
        "normalized_code": """\
import chainlit as cl
from chainlit.authentication import User as AuthAccount

@cl.set_auth_client("custom")
async def custom_authentication(xxxUsername: str, xxxPassword: str) -> AuthAccount:
    \"\"\"Custom authentication handler.

    Authenticate account with custom credentials.
    Return AuthAccount object if successful, None otherwise.
    \"\"\"
    xxxValidated = await validate_credentials(xxxUsername, xxxPassword)

    if not xxxValidated:
        return None

    xxxAccount = AuthAccount(
        identifier=xxxUsername,
        metadata={
            "email": f"{xxxUsername}@example.com",
            "role": await get_account_role(xxxUsername),
            "department": await get_account_department(xxxUsername),
        },
    )

    return xxxAccount


async def validate_credentials(xxxUsername: str, xxxPassword: str) -> bool:
    \"\"\"Validate account credentials against database.\"\"\"
    return len(xxxUsername) > 0 and len(xxxPassword) > 0


async def get_account_role(xxxUsername: str) -> str:
    \"\"\"Fetch account role.\"\"\"
    return "account"


async def get_account_department(xxxUsername: str) -> str:
    \"\"\"Fetch account department.\"\"\"
    return "engineering"
""",
        "function": "custom_authentication_handler",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "chainlit/auth.py",
    },
    # ── 11. LangChain Integration ──────────────────────────────────────────
    {
        "normalized_code": """\
import chainlit as cl
from langchain.chat_models import ChatOpenAI
from langchain.memory import ConversationBufferMemory
from langchain.chains import ConversationChain

@cl.on_chat_start
async def langchain_integration_setup() -> None:
    \"\"\"Setup LangChain integration with memory.\"\"\"
    xxxLlm = ChatOpenAI(
        model_name="gpt-3.5-turbo",
        temperature=0.7,
    )

    xxxMemory = ConversationBufferMemory(
        return_messages=True,
        memory_key="chat_history",
    )

    xxxChain = ConversationChain(
        llm=xxxLlm,
        memory=xxxMemory,
        verbose=True,
    )

    cl.user_session.set("chain", xxxChain)


@cl.on_message
async def on_message_langchain(reply: cl.Message) -> None:
    \"\"\"Process message with LangChain chain.\"\"\"
    xxxChain = cl.user_session.get("chain")

    xxxInput = reply.content
    xxxOutput = await xxxChain.arun(input=xxxInput)

    await cl.Message(
        content=xxxOutput,
        author="Assistant",
    ).send()
""",
        "function": "langchain_integration_chain",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "chainlit/langchain.py",
    },
    # ── 12. Elements: Image, Text, File Display ────────────────────────────
    {
        "normalized_code": """\
import chainlit as cl

@cl.on_message
async def on_message_with_elements(reply: cl.Message) -> None:
    \"\"\"Send message with rich media elements.\"\"\"
    xxxImageUrl = "https://example.com/image.png"
    xxxTextContent = "This is important information"
    xxxFilePath = "/path/to/document.pdf"

    xxxImageElement = cl.Image(
        name="Xxx Image",
        path=xxxImageUrl,
        display="side",
    )

    xxxTextElement = cl.Text(
        name="Xxx Document",
        content=xxxTextContent,
        display="side",
    )

    xxxFileElement = cl.File(
        name="Xxx File",
        path=xxxFilePath,
        display="side",
    )

    await cl.Message(
        content="Here are some resources:",
        elements=[xxxImageElement, xxxTextElement, xxxFileElement],
        author="Assistant",
    ).send()

    xxxReplyWithElements = cl.Message(
        content="Response with embedded content",
        elements=[
            cl.Text(name="Summary", content="Quick summary"),
            cl.Image(
                name="Chart",
                path="https://example.com/chart.png",
                display="inline",
            ),
        ],
    )
    await xxxReplyWithElements.send()
""",
        "function": "elements_image_text_file_display",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "chainlit/elements.py",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "on_message handler main chat entry point",
    "on_chat_start initialization setup session",
    "streaming response token by token",
    "step decorator langchain chain tracking",
    "file upload handler process documents",
    "user session management state",
    "action callback interactive elements",
    "ask user input additional dialog",
    "chat profiles configuration personas",
    "custom authentication handler",
    "langchain integration conversation chain",
    "elements image text file display",
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
