"""
ingest_drogon.py — Extrait, normalise (Charte Wal-e), et indexe
les patterns de drogonframework/drogon dans la KB Qdrant V6.

C++ B — Drogon web framework. C++17 + ORM + JSON.

Usage:
    .venv/bin/python3 ingest_drogon.py
"""

from __future__ import annotations

import os
import subprocess

from qdrant_client import QdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointStruct,
)

from embedder import embed_documents_batch, embed_query
from kb_utils import (
    audit_report,
    build_payload,
    check_charte_violations,
    make_uuid,
    query_kb,
)

# ─── Constantes ──────────────────────────────────────────────────────────────
REPO_URL = "https://github.com/drogonframework/drogon.git"
REPO_NAME = "drogonframework/drogon"
REPO_LOCAL = "/tmp/drogon"
LANGUAGE = "cpp"
FRAMEWORK = "drogon"
STACK = "drogon+orm+cpp17"
CHARTE_VERSION = "1.0"
TAG = "drogonframework/drogon"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"
SOURCE_REPO = "https://github.com/drogonframework/drogon"


# ─── Patterns normalisés Charte Wal-e ───────────────────────────────────────
# U-5: Entity→Xxx, entity→xxx, entities→xxxs
#       Kept: drogon, HttpController, HttpSimpleController, WebSocketController,
#             Mapper, Json::Value, HttpRequest, HttpResponse, HttpAppFramework,
#             trantor, EventLoop, HttpFilter, MultiPartParser, DrObject
# U-7: no printf/cout/std::cerr for debug — use LOG_INFO/LOG_DEBUG

PATTERNS: list[dict] = [
    # ═══════════════════════════════════════════════════════════════════════════
    # ROUTES — HttpController, HttpSimpleController, WebSocket
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 1. http_controller_basic ────────────────────────────────────────────
    {
        "normalized_code": """\
#pragma once

#include <drogon/HttpController.h>

using namespace drogon;

class XxxController : public HttpController<XxxController>
{
  public:
    METHOD_LIST_BEGIN
    ADD_METHOD_TO(XxxController::getXxx, "/xxxs/{1}", Get);
    ADD_METHOD_TO(XxxController::getXxxs, "/xxxs", Get);
    ADD_METHOD_TO(XxxController::createXxx, "/xxxs", Post);
    ADD_METHOD_TO(XxxController::updateXxx, "/xxxs/{1}", Put);
    ADD_METHOD_TO(XxxController::deleteXxx, "/xxxs/{1}", Delete);
    METHOD_LIST_END

    void getXxx(const HttpRequestPtr &req,
                std::function<void(const HttpResponsePtr &)> &&callback,
                int xxxId) const;
    void getXxxs(const HttpRequestPtr &req,
                 std::function<void(const HttpResponsePtr &)> &&callback) const;
    void createXxx(const HttpRequestPtr &req,
                   std::function<void(const HttpResponsePtr &)> &&callback) const;
    void updateXxx(const HttpRequestPtr &req,
                   std::function<void(const HttpResponsePtr &)> &&callback,
                   int xxxId) const;
    void deleteXxx(const HttpRequestPtr &req,
                   std::function<void(const HttpResponsePtr &)> &&callback,
                   int xxxId) const;
};
""",
        "function": "http_controller_basic",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "controllers/XxxController.h",
    },

    # ── 2. http_simple_controller ───────────────────────────────────────────
    {
        "normalized_code": """\
#pragma once

#include <drogon/HttpSimpleController.h>

using namespace drogon;

class XxxSimpleController : public HttpSimpleController<XxxSimpleController>
{
  public:
    PATH_LIST_BEGIN
    PATH_ADD("/xxx", Get, Post);
    PATH_LIST_END

    void asyncHandleHttpRequest(
        const HttpRequestPtr &req,
        std::function<void(const HttpResponsePtr &)> &&callback) override;
};
""",
        "function": "http_simple_controller",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "controllers/XxxSimpleController.h",
    },

    # ── 3. websocket_controller ─────────────────────────────────────────────
    {
        "normalized_code": """\
#pragma once

#include <drogon/WebSocketController.h>

using namespace drogon;

class XxxWebSocketController : public WebSocketController<XxxWebSocketController>
{
  public:
    WS_PATH_LIST_BEGIN
    WS_PATH_ADD("/ws/xxx");
    WS_PATH_LIST_END

    void handleNewMessage(const WebSocketConnectionPtr &wsConnPtr,
                          std::string &&payload,
                          const WebSocketMessageType &type) override;
    void handleNewConnection(const HttpRequestPtr &req,
                             const WebSocketConnectionPtr &wsConnPtr) override;
    void handleConnectionClosed(const WebSocketConnectionPtr &wsConnPtr) override;
};

// ── Implementation ──

void XxxWebSocketController::handleNewMessage(
    const WebSocketConnectionPtr &wsConnPtr,
    std::string &&payload,
    const WebSocketMessageType &type)
{
    LOG_INFO << "New data from WebSocket: " << payload;
    if (type == WebSocketMessageType::Text)
    {
        Json::Value json;
        json["payload"] = payload;
        json["status"] = "received";
        wsConnPtr->send(Json::FastWriter().write(json));
    }
}

void XxxWebSocketController::handleNewConnection(
    const HttpRequestPtr &req,
    const WebSocketConnectionPtr &wsConnPtr)
{
    LOG_INFO << "New WebSocket connection established";
}

void XxxWebSocketController::handleConnectionClosed(
    const WebSocketConnectionPtr &wsConnPtr)
{
    LOG_INFO << "WebSocket connection closed";
}
""",
        "function": "websocket_controller",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "controllers/XxxWebSocketController.cc",
    },

    # ── 4. json_request_handling ────────────────────────────────────────────
    {
        "normalized_code": """\
#include "XxxController.h"

using namespace drogon;

void XxxController::createXxx(
    const HttpRequestPtr &req,
    std::function<void(const HttpResponsePtr &)> &&callback) const
{
    auto jsonPtr = req->getJsonObject();
    if (!jsonPtr)
    {
        auto resp = HttpResponse::newHttpResponse();
        resp->setStatusCode(k400BadRequest);
        resp->setContentTypeCode(CT_APPLICATION_JSON);
        Json::Value error;
        error["error"] = "Invalid JSON body";
        resp->setBody(Json::FastWriter().write(error));
        callback(resp);
        return;
    }

    const auto &json = *jsonPtr;
    std::string name = json.get("name", "").asString();
    std::string description = json.get("description", "").asString();

    if (name.empty())
    {
        Json::Value error;
        error["error"] = "Field 'name' is required";
        auto resp = HttpResponse::newHttpJsonResponse(error);
        resp->setStatusCode(k422UnprocessableEntity);
        callback(resp);
        return;
    }

    LOG_DEBUG << "Creating xxx with name: " << name;

    Json::Value result;
    result["name"] = name;
    result["description"] = description;
    result["status"] = "created";
    auto resp = HttpResponse::newHttpJsonResponse(result);
    resp->setStatusCode(k201Created);
    callback(resp);
}
""",
        "function": "json_request_handling",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "controllers/XxxController.cc",
    },

    # ── 5. json_response_creation ───────────────────────────────────────────
    {
        "normalized_code": """\
#include <drogon/HttpResponse.h>
#include <json/json.h>

using namespace drogon;

void sendJsonResponse(
    std::function<void(const HttpResponsePtr &)> &&callback,
    const Json::Value &data,
    HttpStatusCode statusCode)
{
    Json::Value envelope;
    envelope["success"] = true;
    envelope["data"] = data;
    auto resp = HttpResponse::newHttpJsonResponse(envelope);
    resp->setStatusCode(statusCode);
    callback(resp);
}

void sendErrorResponse(
    std::function<void(const HttpResponsePtr &)> &&callback,
    const std::string &detail,
    HttpStatusCode statusCode)
{
    Json::Value envelope;
    envelope["success"] = false;
    envelope["error"] = detail;
    auto resp = HttpResponse::newHttpJsonResponse(envelope);
    resp->setStatusCode(statusCode);
    callback(resp);
}
""",
        "function": "json_response_creation",
        "feature_type": "route",
        "file_role": "utility",
        "file_path": "utils/JsonResponse.cc",
    },

    # ── 6. async_callback_pattern ───────────────────────────────────────────
    {
        "normalized_code": """\
#include "XxxController.h"

using namespace drogon;

void XxxController::getXxx(
    const HttpRequestPtr &req,
    std::function<void(const HttpResponsePtr &)> &&callback,
    int xxxId) const
{
    auto dbClientPtr = drogon::app().getDbClient();
    dbClientPtr->execSqlAsync(
        "SELECT * FROM xxxs WHERE id = $1",
        [callback](const drogon::orm::Result &result) {
            if (result.empty())
            {
                Json::Value error;
                error["error"] = "Xxx not found";
                auto resp = HttpResponse::newHttpJsonResponse(error);
                resp->setStatusCode(k404NotFound);
                callback(resp);
                return;
            }
            Json::Value json;
            json["id"] = result[0]["id"].as<int>();
            json["name"] = result[0]["name"].as<std::string>();
            auto resp = HttpResponse::newHttpJsonResponse(json);
            callback(resp);
        },
        [callback](const drogon::orm::DrogonDbException &e) {
            LOG_ERROR << "DB error: " << e.base().what();
            Json::Value error;
            error["error"] = "Internal server error";
            auto resp = HttpResponse::newHttpJsonResponse(error);
            resp->setStatusCode(k500InternalServerError);
            callback(resp);
        },
        xxxId);
}
""",
        "function": "async_callback_pattern",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "controllers/XxxController.cc",
    },

    # ── 7. coroutine_handler ────────────────────────────────────────────────
    {
        "normalized_code": """\
#include <drogon/HttpController.h>
#include <drogon/utils/coroutine.h>

using namespace drogon;

class XxxCoroController : public HttpController<XxxCoroController>
{
  public:
    METHOD_LIST_BEGIN
    ADD_METHOD_TO(XxxCoroController::getXxx, "/api/xxxs/{1}", Get);
    ADD_METHOD_TO(XxxCoroController::getXxxs, "/api/xxxs", Get);
    METHOD_LIST_END

    Task<HttpResponsePtr> getXxx(HttpRequestPtr req, int xxxId);
    Task<HttpResponsePtr> getXxxs(HttpRequestPtr req);
};

Task<HttpResponsePtr> XxxCoroController::getXxx(HttpRequestPtr req, int xxxId)
{
    auto dbClientPtr = drogon::app().getDbClient();
    try
    {
        auto result = co_await dbClientPtr->execSqlCoro(
            "SELECT * FROM xxxs WHERE id = $1", xxxId);
        if (result.empty())
        {
            Json::Value error;
            error["error"] = "Xxx not found";
            auto resp = HttpResponse::newHttpJsonResponse(error);
            resp->setStatusCode(k404NotFound);
            co_return resp;
        }
        Json::Value json;
        json["id"] = result[0]["id"].as<int>();
        json["name"] = result[0]["name"].as<std::string>();
        co_return HttpResponse::newHttpJsonResponse(json);
    }
    catch (const drogon::orm::DrogonDbException &e)
    {
        LOG_ERROR << "DB error: " << e.base().what();
        Json::Value error;
        error["error"] = "Internal server error";
        auto resp = HttpResponse::newHttpJsonResponse(error);
        resp->setStatusCode(k500InternalServerError);
        co_return resp;
    }
}

Task<HttpResponsePtr> XxxCoroController::getXxxs(HttpRequestPtr req)
{
    auto dbClientPtr = drogon::app().getDbClient();
    auto result = co_await dbClientPtr->execSqlCoro("SELECT * FROM xxxs");
    Json::Value arr(Json::arrayValue);
    for (const auto &row : result)
    {
        Json::Value element;
        element["id"] = row["id"].as<int>();
        element["name"] = row["name"].as<std::string>();
        arr.append(element);
    }
    Json::Value envelope;
    envelope["data"] = arr;
    envelope["total"] = static_cast<int>(result.size());
    co_return HttpResponse::newHttpJsonResponse(envelope);
}
""",
        "function": "coroutine_handler",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "controllers/XxxCoroController.cc",
    },

    # ── 8. file_upload_multipart ────────────────────────────────────────────
    {
        "normalized_code": """\
#include <drogon/HttpController.h>
#include <drogon/MultiPart.h>

using namespace drogon;

class XxxUploadController : public HttpController<XxxUploadController>
{
  public:
    METHOD_LIST_BEGIN
    ADD_METHOD_TO(XxxUploadController::upload, "/xxxs/upload", Post);
    METHOD_LIST_END

    void upload(const HttpRequestPtr &req,
                std::function<void(const HttpResponsePtr &)> &&callback) const;
};

void XxxUploadController::upload(
    const HttpRequestPtr &req,
    std::function<void(const HttpResponsePtr &)> &&callback) const
{
    MultiPartParser fileUpload;
    if (fileUpload.parse(req) != 0)
    {
        Json::Value error;
        error["error"] = "Invalid multipart request";
        auto resp = HttpResponse::newHttpJsonResponse(error);
        resp->setStatusCode(k400BadRequest);
        callback(resp);
        return;
    }

    auto &files = fileUpload.getFiles();
    if (files.empty())
    {
        Json::Value error;
        error["error"] = "No file uploaded";
        auto resp = HttpResponse::newHttpJsonResponse(error);
        resp->setStatusCode(k400BadRequest);
        callback(resp);
        return;
    }

    Json::Value result(Json::arrayValue);
    for (const auto &file : files)
    {
        LOG_INFO << "Uploaded file: " << file.getFileName()
                 << " (" << file.fileLength() << " bytes)";
        file.save();
        Json::Value entry;
        entry["filename"] = file.getFileName();
        entry["size"] = static_cast<Json::UInt64>(file.fileLength());
        entry["md5"] = file.getMd5();
        result.append(entry);
    }

    Json::Value envelope;
    envelope["uploaded"] = result;
    auto resp = HttpResponse::newHttpJsonResponse(envelope);
    resp->setStatusCode(k201Created);
    callback(resp);
}
""",
        "function": "file_upload_multipart",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "controllers/XxxUploadController.cc",
    },

    # ── 9. session_handling ─────────────────────────────────────────────────
    {
        "normalized_code": """\
#include <drogon/HttpController.h>

using namespace drogon;

class XxxSessionController : public HttpController<XxxSessionController>
{
  public:
    METHOD_LIST_BEGIN
    ADD_METHOD_TO(XxxSessionController::login, "/xxx/login", Post);
    ADD_METHOD_TO(XxxSessionController::profile, "/xxx/profile", Get);
    ADD_METHOD_TO(XxxSessionController::logout, "/xxx/logout", Post);
    METHOD_LIST_END

    void login(const HttpRequestPtr &req,
               std::function<void(const HttpResponsePtr &)> &&callback) const;
    void profile(const HttpRequestPtr &req,
                 std::function<void(const HttpResponsePtr &)> &&callback) const;
    void logout(const HttpRequestPtr &req,
                std::function<void(const HttpResponsePtr &)> &&callback) const;
};

void XxxSessionController::login(
    const HttpRequestPtr &req,
    std::function<void(const HttpResponsePtr &)> &&callback) const
{
    auto jsonPtr = req->getJsonObject();
    if (!jsonPtr)
    {
        Json::Value error;
        error["error"] = "Invalid JSON body";
        auto resp = HttpResponse::newHttpJsonResponse(error);
        resp->setStatusCode(k400BadRequest);
        callback(resp);
        return;
    }

    std::string username = (*jsonPtr)["username"].asString();
    auto session = req->session();
    session->insert("username", username);
    session->insert("logged_in", true);

    LOG_INFO << "Xxx logged in: " << username;

    Json::Value result;
    result["status"] = "logged_in";
    result["username"] = username;
    auto resp = HttpResponse::newHttpJsonResponse(result);
    callback(resp);
}

void XxxSessionController::profile(
    const HttpRequestPtr &req,
    std::function<void(const HttpResponsePtr &)> &&callback) const
{
    auto session = req->session();
    bool loggedIn = session->get<bool>("logged_in");
    if (!loggedIn)
    {
        Json::Value error;
        error["error"] = "Not authenticated";
        auto resp = HttpResponse::newHttpJsonResponse(error);
        resp->setStatusCode(k401Unauthorized);
        callback(resp);
        return;
    }

    std::string username = session->get<std::string>("username");
    Json::Value result;
    result["username"] = username;
    auto resp = HttpResponse::newHttpJsonResponse(result);
    callback(resp);
}

void XxxSessionController::logout(
    const HttpRequestPtr &req,
    std::function<void(const HttpResponsePtr &)> &&callback) const
{
    auto session = req->session();
    session->erase("username");
    session->erase("logged_in");

    Json::Value result;
    result["status"] = "logged_out";
    auto resp = HttpResponse::newHttpJsonResponse(result);
    callback(resp);
}
""",
        "function": "session_handling",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "controllers/XxxSessionController.cc",
    },

    # ── 10. view_rendering ──────────────────────────────────────────────────
    {
        "normalized_code": """\
#include <drogon/HttpController.h>

using namespace drogon;

class XxxViewController : public HttpController<XxxViewController>
{
  public:
    METHOD_LIST_BEGIN
    ADD_METHOD_TO(XxxViewController::index, "/xxxs/view", Get);
    ADD_METHOD_TO(XxxViewController::detail, "/xxxs/view/{1}", Get);
    METHOD_LIST_END

    void index(const HttpRequestPtr &req,
               std::function<void(const HttpResponsePtr &)> &&callback) const;
    void detail(const HttpRequestPtr &req,
                std::function<void(const HttpResponsePtr &)> &&callback,
                int xxxId) const;
};

void XxxViewController::index(
    const HttpRequestPtr &req,
    std::function<void(const HttpResponsePtr &)> &&callback) const
{
    HttpViewData data;
    data.insert("title", std::string("Xxx List"));
    auto resp = HttpResponse::newHttpViewResponse("XxxListView", data);
    callback(resp);
}

void XxxViewController::detail(
    const HttpRequestPtr &req,
    std::function<void(const HttpResponsePtr &)> &&callback,
    int xxxId) const
{
    HttpViewData data;
    data.insert("title", std::string("Xxx Detail"));
    data.insert("xxxId", xxxId);
    auto resp = HttpResponse::newHttpViewResponse("XxxDetailView", data);
    callback(resp);
}
""",
        "function": "view_rendering",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "controllers/XxxViewController.cc",
    },

    # ── 11. http_response_types ─────────────────────────────────────────────
    {
        "normalized_code": """\
#include <drogon/HttpResponse.h>

using namespace drogon;

// JSON response
HttpResponsePtr makeJsonResponse(const Json::Value &json)
{
    return HttpResponse::newHttpJsonResponse(json);
}

// Plain text response
HttpResponsePtr makeTextResponse(const std::string &text)
{
    auto resp = HttpResponse::newHttpResponse();
    resp->setContentTypeCode(CT_TEXT_PLAIN);
    resp->setBody(text);
    return resp;
}

// File download response
HttpResponsePtr makeFileResponse(const std::string &filePath)
{
    return HttpResponse::newFileResponse(filePath);
}

// Redirect response
HttpResponsePtr makeRedirectResponse(const std::string &url)
{
    return HttpResponse::newRedirectionResponse(url);
}

// Custom status response
HttpResponsePtr makeCustomResponse(
    const std::string &body,
    ContentType contentType,
    HttpStatusCode statusCode)
{
    auto resp = HttpResponse::newHttpResponse();
    resp->setContentTypeCode(contentType);
    resp->setStatusCode(statusCode);
    resp->setBody(body);
    return resp;
}
""",
        "function": "http_response_types",
        "feature_type": "route",
        "file_role": "utility",
        "file_path": "utils/ResponseHelper.cc",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # CONFIG — App setup, filters, plugins
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 12. app_setup_listener ──────────────────────────────────────────────
    {
        "normalized_code": """\
#include <drogon/drogon.h>

int main()
{
    drogon::app()
        .setLogPath("./logs")
        .setLogLevel(trantor::Logger::kInfo)
        .addListener("0.0.0.0", 8080)
        .setThreadNum(16)
        .enableSession(3600)
        .setDocumentRoot("./public")
        .setUploadPath("./uploads")
        .run();
    return 0;
}
""",
        "function": "app_setup_listener",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "main.cc",
    },

    # ── 13. http_filter_chain ───────────────────────────────────────────────
    {
        "normalized_code": """\
#pragma once

#include <drogon/HttpFilter.h>

using namespace drogon;

class XxxFilter : public HttpFilter<XxxFilter>
{
  public:
    void doFilter(const HttpRequestPtr &req,
                  FilterCallback &&fcb,
                  FilterChainCallback &&fccb) override;
};

// ── Implementation ──

void XxxFilter::doFilter(
    const HttpRequestPtr &req,
    FilterCallback &&fcb,
    FilterChainCallback &&fccb)
{
    auto session = req->session();
    bool isAuthenticated = session->get<bool>("logged_in");

    if (!isAuthenticated)
    {
        Json::Value error;
        error["error"] = "Unauthorized";
        auto resp = HttpResponse::newHttpJsonResponse(error);
        resp->setStatusCode(k401Unauthorized);
        fcb(resp);
        return;
    }

    LOG_DEBUG << "XxxFilter: request authorized";
    fccb();
}
""",
        "function": "http_filter_chain",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "filters/XxxFilter.cc",
    },

    # ── 14. config_json_loading ─────────────────────────────────────────────
    {
        "normalized_code": """\
#include <drogon/drogon.h>

int main()
{
    drogon::app().loadConfigFile("./config.json");
    drogon::app().run();
    return 0;
}

/*
 * config.json example:
 * {
 *   "listeners": [
 *     { "address": "0.0.0.0", "port": 8080, "https": false }
 *   ],
 *   "app": {
 *     "threads_num": 16,
 *     "session": { "timeout": 3600 },
 *     "document_root": "./public",
 *     "upload_path": "./uploads",
 *     "log": { "log_path": "./logs", "log_level": "INFO" }
 *   },
 *   "db_clients": [
 *     {
 *       "name": "default",
 *       "rdbms": "postgresql",
 *       "host": "127.0.0.1",
 *       "port": 5432,
 *       "dbname": "xxx_db",
 *       "user": "xxx_user",
 *       "passwd": "",
 *       "connection_number": 4
 *     }
 *   ]
 * }
 */
""",
        "function": "config_json_loading",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "main.cc",
    },

    # ── 15. global_filter_registration ──────────────────────────────────────
    {
        "normalized_code": """\
#include <drogon/drogon.h>
#include "filters/XxxFilter.h"

int main()
{
    drogon::app()
        .addListener("0.0.0.0", 8080)
        .setThreadNum(16)
        .registerPreRoutingAdvice(
            [](const HttpRequestPtr &req,
               AdviceCallback &&acb,
               AdviceChainCallback &&accb) {
                LOG_DEBUG << "Pre-routing: " << req->getPath();
                accb();
            })
        .registerPostRoutingAdvice(
            [](const HttpRequestPtr &req,
               AdviceCallback &&acb,
               AdviceChainCallback &&accb) {
                LOG_DEBUG << "After-routing: " << req->getPath();
                accb();
            })
        .registerPreHandlingAdvice(
            [](const HttpRequestPtr &req,
               AdviceCallback &&acb,
               AdviceChainCallback &&accb) {
                req->addHeader("X-Request-Id", drogon::utils::getUuid());
                accb();
            })
        .run();
    return 0;
}
""",
        "function": "global_filter_registration",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "main.cc",
    },

    # ── 16. database_client_get ─────────────────────────────────────────────
    {
        "normalized_code": """\
#include <drogon/drogon.h>

using namespace drogon;
using namespace drogon::orm;

void queryXxxById(
    int xxxId,
    std::function<void(const HttpResponsePtr &)> &&callback)
{
    auto dbClientPtr = drogon::app().getDbClient();

    dbClientPtr->execSqlAsync(
        "SELECT id, name, status, created_at FROM xxxs WHERE id = $1",
        [callback](const Result &result) {
            if (result.empty())
            {
                Json::Value error;
                error["error"] = "Xxx not found";
                auto resp = HttpResponse::newHttpJsonResponse(error);
                resp->setStatusCode(k404NotFound);
                callback(resp);
                return;
            }
            Json::Value json;
            json["id"] = result[0]["id"].as<int>();
            json["name"] = result[0]["name"].as<std::string>();
            json["status"] = result[0]["status"].as<std::string>();
            json["created_at"] = result[0]["created_at"].as<std::string>();
            auto resp = HttpResponse::newHttpJsonResponse(json);
            callback(resp);
        },
        [callback](const DrogonDbException &e) {
            LOG_ERROR << "DB query failed: " << e.base().what();
            Json::Value error;
            error["error"] = "Database error";
            auto resp = HttpResponse::newHttpJsonResponse(error);
            resp->setStatusCode(k500InternalServerError);
            callback(resp);
        },
        xxxId);
}

void queryXxxList(
    int limit,
    int offset,
    std::function<void(const HttpResponsePtr &)> &&callback)
{
    auto dbClientPtr = drogon::app().getDbClient();

    dbClientPtr->execSqlAsync(
        "SELECT id, name, status FROM xxxs ORDER BY id LIMIT $1 OFFSET $2",
        [callback](const Result &result) {
            Json::Value arr(Json::arrayValue);
            for (const auto &row : result)
            {
                Json::Value element;
                element["id"] = row["id"].as<int>();
                element["name"] = row["name"].as<std::string>();
                element["status"] = row["status"].as<std::string>();
                arr.append(element);
            }
            Json::Value envelope;
            envelope["data"] = arr;
            auto resp = HttpResponse::newHttpJsonResponse(envelope);
            callback(resp);
        },
        [callback](const DrogonDbException &e) {
            LOG_ERROR << "DB query failed: " << e.base().what();
            Json::Value error;
            error["error"] = "Database error";
            auto resp = HttpResponse::newHttpJsonResponse(error);
            resp->setStatusCode(k500InternalServerError);
            callback(resp);
        },
        limit, offset);
}
""",
        "function": "database_client_get",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "services/XxxDbService.cc",
    },

    # ── 17. timer_scheduling ────────────────────────────────────────────────
    {
        "normalized_code": """\
#include <drogon/drogon.h>

using namespace drogon;

int main()
{
    drogon::app()
        .addListener("0.0.0.0", 8080)
        .setThreadNum(4);

    // Periodic timer — runs every 60 seconds
    drogon::app().getLoop()->runEvery(60.0, []() {
        LOG_INFO << "Periodic job: cleaning expired xxxs";
        auto dbClientPtr = drogon::app().getDbClient();
        dbClientPtr->execSqlAsync(
            "DELETE FROM xxxs WHERE expired_at < NOW()",
            [](const drogon::orm::Result &result) {
                LOG_INFO << "Cleaned " << result.affectedRows() << " expired xxxs";
            },
            [](const drogon::orm::DrogonDbException &e) {
                LOG_ERROR << "Cleanup failed: " << e.base().what();
            });
    });

    // One-shot delayed timer — runs after 5 seconds
    drogon::app().getLoop()->runAfter(5.0, []() {
        LOG_INFO << "Startup job: initializing xxx cache";
    });

    drogon::app().run();
    return 0;
}
""",
        "function": "timer_scheduling",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "main.cc",
    },

    # ── 18. plugin_system ───────────────────────────────────────────────────
    {
        "normalized_code": """\
#pragma once

#include <drogon/plugins/Plugin.h>

using namespace drogon;

class XxxPlugin : public Plugin<XxxPlugin>
{
  public:
    XxxPlugin() = default;

    void initAndStart(const Json::Value &config) override;
    void shutdown() override;

  private:
    std::string configValue_;
    bool enabled_{false};
};

// ── Implementation ──

void XxxPlugin::initAndStart(const Json::Value &config)
{
    configValue_ = config.get("xxx_key", "default_value").asString();
    enabled_ = config.get("enabled", false).asBool();

    if (enabled_)
    {
        LOG_INFO << "XxxPlugin initialized with key: " << configValue_;
    }
    else
    {
        LOG_INFO << "XxxPlugin is disabled";
    }
}

void XxxPlugin::shutdown()
{
    LOG_INFO << "XxxPlugin shutting down";
    enabled_ = false;
}
""",
        "function": "plugin_system",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "plugins/XxxPlugin.cc",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # CRUD — ORM Mapper patterns
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 19. orm_mapper_find ─────────────────────────────────────────────────
    {
        "normalized_code": """\
#include <drogon/orm/Mapper.h>
#include <drogon/HttpController.h>
#include "models/Xxx.h"

using namespace drogon;
using namespace drogon::orm;

void findXxxByPrimaryKey(
    int xxxId,
    std::function<void(const HttpResponsePtr &)> &&callback)
{
    auto dbClientPtr = drogon::app().getDbClient();
    Mapper<drogon_model::xxx_db::Xxx> mapper(dbClientPtr);

    mapper.findByPrimaryKey(
        xxxId,
        [callback](const drogon_model::xxx_db::Xxx &xxx) {
            Json::Value json = xxx.toJson();
            auto resp = HttpResponse::newHttpJsonResponse(json);
            callback(resp);
        },
        [callback](const DrogonDbException &e) {
            LOG_ERROR << "Find xxx failed: " << e.base().what();
            Json::Value error;
            error["error"] = "Xxx not found";
            auto resp = HttpResponse::newHttpJsonResponse(error);
            resp->setStatusCode(k404NotFound);
            callback(resp);
        });
}

void findXxxsByCriteria(
    const Criteria &criteria,
    int limit,
    int offset,
    std::function<void(const HttpResponsePtr &)> &&callback)
{
    auto dbClientPtr = drogon::app().getDbClient();
    Mapper<drogon_model::xxx_db::Xxx> mapper(dbClientPtr);

    mapper.orderBy(drogon_model::xxx_db::Xxx::Cols::_id)
        .limit(limit)
        .offset(offset)
        .findBy(
            criteria,
            [callback](const std::vector<drogon_model::xxx_db::Xxx> &xxxs) {
                Json::Value arr(Json::arrayValue);
                for (const auto &xxx : xxxs)
                {
                    arr.append(xxx.toJson());
                }
                Json::Value envelope;
                envelope["data"] = arr;
                envelope["total"] = static_cast<int>(xxxs.size());
                auto resp = HttpResponse::newHttpJsonResponse(envelope);
                callback(resp);
            },
            [callback](const DrogonDbException &e) {
                LOG_ERROR << "Find xxxs failed: " << e.base().what();
                Json::Value error;
                error["error"] = "Query failed";
                auto resp = HttpResponse::newHttpJsonResponse(error);
                resp->setStatusCode(k500InternalServerError);
                callback(resp);
            });
}
""",
        "function": "orm_mapper_find",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "services/XxxService.cc",
    },

    # ── 20. orm_mapper_insert ───────────────────────────────────────────────
    {
        "normalized_code": """\
#include <drogon/orm/Mapper.h>
#include <drogon/HttpController.h>
#include "models/Xxx.h"

using namespace drogon;
using namespace drogon::orm;

void insertXxx(
    const Json::Value &jsonBody,
    std::function<void(const HttpResponsePtr &)> &&callback)
{
    auto dbClientPtr = drogon::app().getDbClient();
    Mapper<drogon_model::xxx_db::Xxx> mapper(dbClientPtr);

    drogon_model::xxx_db::Xxx xxx;
    xxx.setName(jsonBody["name"].asString());
    xxx.setStatus(jsonBody.get("status", "active").asString());

    mapper.insert(
        xxx,
        [callback](const drogon_model::xxx_db::Xxx &inserted) {
            Json::Value json = inserted.toJson();
            auto resp = HttpResponse::newHttpJsonResponse(json);
            resp->setStatusCode(k201Created);
            callback(resp);
        },
        [callback](const DrogonDbException &e) {
            LOG_ERROR << "Insert xxx failed: " << e.base().what();
            Json::Value error;
            error["error"] = "Failed to create xxx";
            auto resp = HttpResponse::newHttpJsonResponse(error);
            resp->setStatusCode(k500InternalServerError);
            callback(resp);
        });
}

void updateXxx(
    int xxxId,
    const Json::Value &jsonBody,
    std::function<void(const HttpResponsePtr &)> &&callback)
{
    auto dbClientPtr = drogon::app().getDbClient();
    Mapper<drogon_model::xxx_db::Xxx> mapper(dbClientPtr);

    mapper.findByPrimaryKey(
        xxxId,
        [callback, jsonBody, &mapper](drogon_model::xxx_db::Xxx xxx) {
            if (jsonBody.isMember("name"))
            {
                xxx.setName(jsonBody["name"].asString());
            }
            if (jsonBody.isMember("status"))
            {
                xxx.setStatus(jsonBody["status"].asString());
            }
            mapper.update(
                xxx,
                [callback](const size_t count) {
                    Json::Value result;
                    result["updated"] = static_cast<int>(count);
                    auto resp = HttpResponse::newHttpJsonResponse(result);
                    callback(resp);
                },
                [callback](const DrogonDbException &e) {
                    LOG_ERROR << "Update xxx failed: " << e.base().what();
                    Json::Value error;
                    error["error"] = "Failed to update xxx";
                    auto resp = HttpResponse::newHttpJsonResponse(error);
                    resp->setStatusCode(k500InternalServerError);
                    callback(resp);
                });
        },
        [callback](const DrogonDbException &e) {
            Json::Value error;
            error["error"] = "Xxx not found";
            auto resp = HttpResponse::newHttpJsonResponse(error);
            resp->setStatusCode(k404NotFound);
            callback(resp);
        });
}

void deleteXxx(
    int xxxId,
    std::function<void(const HttpResponsePtr &)> &&callback)
{
    auto dbClientPtr = drogon::app().getDbClient();
    Mapper<drogon_model::xxx_db::Xxx> mapper(dbClientPtr);

    mapper.deleteByPrimaryKey(
        xxxId,
        [callback](const size_t count) {
            Json::Value result;
            result["deleted"] = static_cast<int>(count);
            auto resp = HttpResponse::newHttpJsonResponse(result);
            callback(resp);
        },
        [callback](const DrogonDbException &e) {
            LOG_ERROR << "Delete xxx failed: " << e.base().what();
            Json::Value error;
            error["error"] = "Failed to delete xxx";
            auto resp = HttpResponse::newHttpJsonResponse(error);
            resp->setStatusCode(k500InternalServerError);
            callback(resp);
        });
}
""",
        "function": "orm_mapper_insert",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "services/XxxService.cc",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "drogon HttpController route handler",
    "drogon JSON request response",
    "drogon ORM mapper find insert",
    "drogon websocket controller",
    "drogon filter chain middleware",
    "drogon file upload multipart",
    "drogon session handling",
    "drogon app configuration setup",
]


def clone_repo() -> None:
    if os.path.isdir(REPO_LOCAL):
        print(f"  Repo already cloned: {REPO_LOCAL}")
        return
    print(f"  Cloning {REPO_URL} → {REPO_LOCAL} ...")
    subprocess.run(
        ["git", "clone", REPO_URL, REPO_LOCAL, "--depth=1"],
        check=True,
        capture_output=True,
    )
    print("  Cloned.")


def build_payloads() -> list[dict]:
    payloads = []
    all_violations = []
    for p in PATTERNS:
        v = check_charte_violations(
            p["normalized_code"], p["function"], language=LANGUAGE
        )
        all_violations.extend(v)
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
    if all_violations:
        print("  PRE-INDEX violations:")
        for v in all_violations:
            print(f"    WARN: {v}")
    return payloads


def index_patterns(client: QdrantClient, payloads: list[dict]) -> int:
    codes = [p["normalized_code"] for p in payloads]
    print(f"  Embedding {len(codes)} patterns (batch) ...")
    vectors = embed_documents_batch(codes)
    print(f"  {len(vectors)} vectors generated.")

    points = []
    for i, (vec, payload) in enumerate(zip(vectors, payloads)):
        points.append(PointStruct(id=make_uuid(), vector=vec, payload=payload))
        if (i + 1) % 5 == 0:
            print(f"    ... {i + 1}/{len(payloads)} points prepared")

    print(f"  Upserting {len(points)} points into '{COLLECTION}' ...")
    client.upsert(collection_name=COLLECTION, points=points)
    print("  Upsert done.")
    return len(points)


def run_audit_queries(client: QdrantClient) -> list[dict]:
    results = []
    for q in AUDIT_QUERIES:
        vec = embed_query(q)
        hits = query_kb(
            client=client,
            collection=COLLECTION,
            query_vector=vec,
            language=LANGUAGE,
            limit=1,
        )
        if hits:
            h = hits[0]
            results.append({
                "query": q,
                "function": h.payload.get("function", "?"),
                "file_role": h.payload.get("file_role", "?"),
                "score": h.score,
                "code_preview": h.payload.get("normalized_code", "")[:50],
                "norm_ok": True,
            })
        else:
            results.append({
                "query": q,
                "function": "NO_RESULT",
                "file_role": "?",
                "score": 0.0,
                "code_preview": "",
                "norm_ok": False,
            })
    return results


def audit_normalization(client: QdrantClient) -> list[str]:
    scroll_result = client.scroll(
        collection_name=COLLECTION,
        scroll_filter=Filter(
            must=[FieldCondition(key="_tag", match=MatchValue(value=TAG))]
        ),
        limit=100,
    )
    points = scroll_result[0]
    violations = []
    for point in points:
        code = point.payload.get("normalized_code", "")
        fn = point.payload.get("function", "?")
        violations.extend(check_charte_violations(code, fn, language=LANGUAGE))
    return violations


def cleanup(client: QdrantClient) -> None:
    client.delete(
        collection_name=COLLECTION,
        points_selector=FilterSelector(
            filter=Filter(
                must=[FieldCondition(key="_tag", match=MatchValue(value=TAG))]
            )
        ),
    )


def main() -> None:
    print(f"\n{'='*60}")
    print(f"  INGESTION {REPO_NAME}")
    print(f"  Mode: {'DRY_RUN (test)' if DRY_RUN else 'PRODUCTION'}")
    print(f"  Language: {LANGUAGE} | Stack: {STACK}")
    print(f"{'='*60}\n")

    client = QdrantClient(path=KB_PATH)

    print("── Step 1: Prerequisites")
    collections = [c.name for c in client.get_collections().collections]
    if COLLECTION not in collections:
        print(f"  ERROR: collection '{COLLECTION}' not found.")
        return
    count_initial = client.count(collection_name=COLLECTION).count
    print(f"  Collection '{COLLECTION}': {count_initial} points (initial)")

    print("\n── Step 2: Clone")
    clone_repo()

    print(f"\n── Step 3-4: {len(PATTERNS)} patterns extracted and normalized")
    payloads = build_payloads()
    print(f"  {len(payloads)} payloads built.")

    print("\n── Step 5: Indexation")
    n_indexed = 0
    query_results: list[dict] = []
    violations: list[str] = []

    try:
        n_indexed = index_patterns(client, payloads)
        count_after = client.count(collection_name=COLLECTION).count
        print(f"  Count after indexation: {count_after}")

        print("\n── Step 6: Audit")
        print(f"\n  6a. Semantic queries (filtered by language={LANGUAGE}):")
        query_results = run_audit_queries(client)
        for r in query_results:
            score_ok = 0.0 <= r["score"] <= 1.0
            print(
                f"    Q: {r['query'][:50]:50s} | fn={r['function']:40s} | "
                f"score={r['score']:.4f} {'✓' if score_ok else '✗'}"
            )

        print("\n  6b. Normalization audit:")
        violations = audit_normalization(client)
        if violations:
            for v in violations:
                print(f"    WARN: {v}")
        else:
            print("    No violations detected ✓")

    finally:
        print(f"\n── Step 7: {'Cleanup (DRY_RUN)' if DRY_RUN else 'Conservation'}")
        if DRY_RUN:
            cleanup(client)
            count_final = client.count(collection_name=COLLECTION).count
            print(f"  Points deleted. Count final: {count_final}")
        else:
            count_final = client.count(collection_name=COLLECTION).count
            print(f"  PRODUCTION — {n_indexed} patterns kept in KB")
            print(f"  Total count: {count_final}")

    count_now = client.count(collection_name=COLLECTION).count
    report = audit_report(
        repo_name=REPO_NAME,
        dry_run=DRY_RUN,
        count_before=count_initial,
        count_after=count_now,
        patterns_extracted=len(PATTERNS),
        patterns_indexed=n_indexed,
        query_results=query_results,
        violations=violations,
    )
    print(report)


if __name__ == "__main__":
    main()
