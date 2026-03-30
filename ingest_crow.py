"""
ingest_crow.py — Extrait, normalise (Charte Wal-e), et indexe
les patterns de CrowCpp/Crow dans la KB Qdrant V6.

C++ A — HTTP micro-framework. Crow + C++17.

Usage:
    .venv/bin/python3 ingest_crow.py
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
REPO_URL = "https://github.com/CrowCpp/Crow.git"
REPO_NAME = "crowcpp/Crow"
REPO_LOCAL = "/tmp/crowcpp_crow"
LANGUAGE = "cpp"
FRAMEWORK = "crow"
STACK = "crow+cpp17"
CHARTE_VERSION = "1.0"
TAG = "crowcpp/Crow"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"
SOURCE_REPO = "https://github.com/CrowCpp/Crow"


# ─── Patterns normalisés Charte Wal-e ───────────────────────────────────────
# U-5: Entity names → Xxx/xxx/xxxs (C++ examples rarely have named entities)
# U-7: No std::cout / printf — use CROW_LOG_INFO / CROW_LOG_DEBUG
# Kept: crow, CROW_ROUTE, CROW_WEBSOCKET_ROUTE, std::, boost, etc.
# No language-specific rules for C++ (only U-* universal rules apply)

PATTERNS: list[dict] = [
    # ═══════════════════════════════════════════════════════════════════════════
    # CONFIG — App setup & infrastructure
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 1. app_setup_simple ─────────────────────────────────────────────────
    {
        "normalized_code": """\
#include "crow.h"

int main()
{
    crow::SimpleApp app;

    CROW_ROUTE(app, "/")([]() {
        return "Hello, Crow!";
    });

    CROW_ROUTE(app, "/about")([]() {
        return "About page";
    });

    app.port(8080)
        .multithreaded()
        .run();

    return 0;
}
""",
        "function": "app_setup_simple",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "examples/simple_app.cpp",
    },

    # ── 2. app_setup_middleware ──────────────────────────────────────────────
    {
        "normalized_code": """\
#include "crow.h"

struct XxxMiddleware
{
    struct context
    {
        std::string xxx_data;
    };

    void before_handle(crow::request& req, crow::response& res, context& ctx)
    {
        ctx.xxx_data = req.get_header_value("X-Xxx-Header");
        CROW_LOG_INFO << "XxxMiddleware before_handle: " << ctx.xxx_data;
    }

    void after_handle(crow::request& req, crow::response& res, context& ctx)
    {
        res.add_header("X-Xxx-Processed", "true");
        CROW_LOG_INFO << "XxxMiddleware after_handle";
    }
};

int main()
{
    crow::App<XxxMiddleware> app;

    CROW_ROUTE(app, "/")([]() {
        return "App with middleware";
    });

    app.port(8080).run();

    return 0;
}
""",
        "function": "app_setup_middleware",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "examples/middleware_app.cpp",
    },

    # ── 3. route_get_handler ────────────────────────────────────────────────
    {
        "normalized_code": """\
#include "crow.h"

int main()
{
    crow::SimpleApp app;

    CROW_ROUTE(app, "/xxxs")
    ([]() {
        crow::json::wvalue result;
        result["status"] = "ok";
        result["status_text"] = "List of xxxs";
        return result;
    });

    CROW_ROUTE(app, "/health")
    ([]() {
        return crow::response(200, "OK");
    });

    app.port(8080).run();

    return 0;
}
""",
        "function": "route_get_handler",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/route_get.cpp",
    },

    # ── 4. route_post_json ──────────────────────────────────────────────────
    {
        "normalized_code": """\
#include "crow.h"

int main()
{
    crow::SimpleApp app;

    CROW_ROUTE(app, "/xxxs")
        .methods("POST"_method)
    ([](const crow::request& req) {
        auto body = crow::json::load(req.body);
        if (!body) {
            return crow::response(400, "Invalid JSON");
        }

        std::string name = body["name"].s();
        int status = body["status"].i();

        CROW_LOG_INFO << "Creating xxx: " << name;

        crow::json::wvalue result;
        result["id"] = 1;
        result["name"] = name;
        result["status"] = status;
        return crow::response(201, result);
    });

    app.port(8080).run();

    return 0;
}
""",
        "function": "route_post_json",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/route_post_json.cpp",
    },

    # ── 5. route_multiple_methods ───────────────────────────────────────────
    {
        "normalized_code": """\
#include "crow.h"

int main()
{
    crow::SimpleApp app;

    CROW_ROUTE(app, "/xxxs")
        .methods("GET"_method, "POST"_method)
    ([](const crow::request& req) {
        if (req.method == crow::HTTPMethod::GET) {
            crow::json::wvalue result;
            result["action"] = "list";
            return crow::response(200, result);
        }

        auto body = crow::json::load(req.body);
        if (!body) {
            return crow::response(400, "Invalid JSON");
        }

        crow::json::wvalue result;
        result["action"] = "create";
        result["name"] = body["name"].s();
        return crow::response(201, result);
    });

    app.port(8080).run();

    return 0;
}
""",
        "function": "route_multiple_methods",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/route_multiple_methods.cpp",
    },

    # ── 6. url_params_int_string ────────────────────────────────────────────
    {
        "normalized_code": """\
#include "crow.h"

int main()
{
    crow::SimpleApp app;

    CROW_ROUTE(app, "/xxxs/<int>")
    ([](int xxx_id) {
        crow::json::wvalue result;
        result["id"] = xxx_id;
        result["type"] = "int_param";
        return result;
    });

    CROW_ROUTE(app, "/xxxs/<string>")
    ([](const std::string& xxx_name) {
        crow::json::wvalue result;
        result["name"] = xxx_name;
        result["type"] = "string_param";
        return result;
    });

    CROW_ROUTE(app, "/files/<path>")
    ([](const std::string& file_path) {
        crow::json::wvalue result;
        result["path"] = file_path;
        result["type"] = "path_param";
        return result;
    });

    app.port(8080).run();

    return 0;
}
""",
        "function": "url_params_int_string",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/url_params.cpp",
    },

    # ── 7. query_params_parsing ─────────────────────────────────────────────
    {
        "normalized_code": """\
#include "crow.h"

int main()
{
    crow::SimpleApp app;

    CROW_ROUTE(app, "/xxxs")
    ([](const crow::request& req) {
        auto page = req.url_params.get("page");
        auto limit = req.url_params.get("limit");
        auto labels = req.url_params.get_list("label", false);
        auto filters = req.url_params.get_dict("filter");

        crow::json::wvalue result;
        result["page"] = page ? std::stoi(page) : 1;
        result["limit"] = limit ? std::stoi(limit) : 10;

        int idx = 0;
        for (const auto& label : labels) {
            result["labels"][idx++] = label;
        }

        for (const auto& [key, val] : filters) {
            result["filters"][key] = val;
        }

        return result;
    });

    app.port(8080).run();

    return 0;
}
""",
        "function": "query_params_parsing",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/query_params.cpp",
    },

    # ── 8. json_write_wvalue ────────────────────────────────────────────────
    {
        "normalized_code": """\
#include "crow.h"

int main()
{
    crow::SimpleApp app;

    CROW_ROUTE(app, "/xxxs")
    ([]() {
        crow::json::wvalue result;
        result["id"] = 1;
        result["name"] = "xxx_name";
        result["active"] = true;
        result["score"] = 9.5;

        crow::json::wvalue::list elements;
        for (int i = 0; i < 3; i++) {
            crow::json::wvalue element;
            element["index"] = i;
            element["label"] = "entry_" + std::to_string(i);
            elements.push_back(std::move(element));
        }
        result["elements"] = std::move(elements);

        crow::json::wvalue nested;
        nested["key"] = "value";
        result["metadata"] = std::move(nested);

        return result;
    });

    app.port(8080).run();

    return 0;
}
""",
        "function": "json_write_wvalue",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/json_write.cpp",
    },

    # ── 9. json_read_rvalue ─────────────────────────────────────────────────
    {
        "normalized_code": """\
#include "crow.h"

int main()
{
    crow::SimpleApp app;

    CROW_ROUTE(app, "/xxxs")
        .methods("POST"_method)
    ([](const crow::request& req) {
        auto body = crow::json::load(req.body);
        if (!body) {
            return crow::response(400, "Invalid JSON body");
        }

        std::string name = body["name"].s();
        int count = body["count"].i();
        double score = body["score"].d();
        bool active = body["active"].b();

        if (body.has("optional_field")) {
            std::string opt = body["optional_field"].s();
            CROW_LOG_DEBUG << "Optional field: " << opt;
        }

        auto& elements = body["elements"];
        for (unsigned i = 0; i < elements.size(); i++) {
            CROW_LOG_INFO << "Entry: " << elements[i].s();
        }

        crow::json::wvalue result;
        result["parsed_name"] = name;
        result["parsed_count"] = count;
        result["parsed_score"] = score;
        result["parsed_active"] = active;
        return crow::response(200, result);
    });

    app.port(8080).run();

    return 0;
}
""",
        "function": "json_read_rvalue",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/json_read.cpp",
    },

    # ── 10. mustache_template ───────────────────────────────────────────────
    {
        "normalized_code": """\
#include "crow.h"
#include "crow/mustache.h"

int main()
{
    crow::SimpleApp app;

    CROW_ROUTE(app, "/xxxs")
    ([]() {
        crow::mustache::context ctx;
        ctx["title"] = "Xxx List";

        crow::json::wvalue::list elements;
        for (int i = 0; i < 3; i++) {
            crow::json::wvalue element;
            element["name"] = "xxx_" + std::to_string(i);
            element["id"] = i;
            elements.push_back(std::move(element));
        }
        ctx["xxxs"] = std::move(elements);

        auto page = crow::mustache::load("xxx_list.html");
        return page.render(ctx);
    });

    CROW_ROUTE(app, "/xxxs/<int>")
    ([](int xxx_id) {
        crow::mustache::context ctx;
        ctx["id"] = xxx_id;
        ctx["name"] = "xxx_detail";

        auto page = crow::mustache::load("xxx_detail.html");
        return page.render(ctx);
    });

    app.port(8080).run();

    return 0;
}
""",
        "function": "mustache_template",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/mustache_template.cpp",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # CONFIG — Middleware patterns
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 11. middleware_before_after ──────────────────────────────────────────
    {
        "normalized_code": """\
#include "crow.h"

struct XxxAuthMiddleware
{
    struct context
    {
        std::string xxx_token;
        bool authenticated{false};
    };

    void before_handle(crow::request& req, crow::response& res, context& ctx)
    {
        ctx.xxx_token = req.get_header_value("Authorization");
        if (ctx.xxx_token.empty()) {
            CROW_LOG_INFO << "No auth token provided";
            res.code = 401;
            res.write("Unauthorized");
            res.end();
            return;
        }
        ctx.authenticated = true;
        CROW_LOG_INFO << "Authenticated request";
    }

    void after_handle(crow::request& req, crow::response& res, context& ctx)
    {
        res.add_header("X-Xxx-Auth", ctx.authenticated ? "true" : "false");
    }
};

int main()
{
    crow::App<XxxAuthMiddleware> app;

    CROW_ROUTE(app, "/xxxs")
    ([&](const crow::request& req) {
        auto& ctx = app.get_context<XxxAuthMiddleware>(req);
        if (!ctx.authenticated) {
            return crow::response(401);
        }
        crow::json::wvalue result;
        result["token"] = ctx.xxx_token;
        return crow::response(200, result);
    });

    app.port(8080).run();

    return 0;
}
""",
        "function": "middleware_before_after",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "examples/middleware_auth.cpp",
    },

    # ── 12. local_middleware ─────────────────────────────────────────────────
    {
        "normalized_code": """\
#include "crow.h"

struct XxxLocalGuard : crow::ILocalMiddleware
{
    struct context
    {
        bool allowed{false};
    };

    void before_handle(crow::request& req, crow::response& res, context& ctx)
    {
        auto key = req.get_header_value("X-Api-Key");
        if (key == "xxx-secret-key") {
            ctx.allowed = true;
        } else {
            CROW_LOG_INFO << "Local middleware: access denied";
            res.code = 403;
            res.write("Forbidden");
            res.end();
        }
    }

    void after_handle(crow::request& req, crow::response& res, context& ctx)
    {
    }
};

int main()
{
    crow::App<XxxLocalGuard> app;

    CROW_ROUTE(app, "/public")
    ([]() {
        return "Public endpoint";
    });

    CROW_ROUTE(app, "/xxxs/protected")
        .CROW_MIDDLEWARES(app, XxxLocalGuard)
    ([](const crow::request& req) {
        return "Protected xxx endpoint";
    });

    app.port(8080).run();

    return 0;
}
""",
        "function": "local_middleware",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "examples/local_middleware.cpp",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # ROUTE — Advanced patterns
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 13. websocket_broadcast ─────────────────────────────────────────────
    {
        "normalized_code": """\
#include "crow.h"

#include <mutex>
#include <unordered_set>

int main()
{
    crow::SimpleApp app;

    std::mutex mtx;
    std::unordered_set<crow::websocket::connection*> xxx_clients;

    CROW_WEBSOCKET_ROUTE(app, "/ws/xxxs")
        .onopen([&](crow::websocket::connection& conn) {
            std::lock_guard<std::mutex> lock(mtx);
            xxx_clients.insert(&conn);
            CROW_LOG_INFO << "WebSocket client connected, total: "
                          << xxx_clients.size();
        })
        .onclose([&](crow::websocket::connection& conn,
                      const std::string& reason) {
            std::lock_guard<std::mutex> lock(mtx);
            xxx_clients.erase(&conn);
            CROW_LOG_INFO << "WebSocket client disconnected: " << reason;
        })
        .onmessage([&](crow::websocket::connection& conn,
                        const std::string& data,
                        bool is_binary) {
            std::lock_guard<std::mutex> lock(mtx);
            CROW_LOG_INFO << "Broadcasting message: " << data;
            for (auto* client : xxx_clients) {
                if (client != &conn) {
                    client->send_text(data);
                }
            }
        });

    app.port(8080).run();

    return 0;
}
""",
        "function": "websocket_broadcast",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/websocket_broadcast.cpp",
    },

    # ── 14. multipart_file_upload ───────────────────────────────────────────
    {
        "normalized_code": """\
#include "crow.h"
#include "crow/multipart.h"

#include <fstream>

int main()
{
    crow::SimpleApp app;

    CROW_ROUTE(app, "/xxxs/upload")
        .methods("POST"_method)
    ([](const crow::request& req) {
        crow::multipart::message_view file_message(req);

        crow::json::wvalue result;
        int idx = 0;

        for (const auto& [part_name, part] : file_message.part_map) {
            auto content_disposition = part.get_header_object("Content-Disposition");
            std::string filename = content_disposition.params.at("filename");

            CROW_LOG_INFO << "Received file: " << filename
                          << " (part: " << part_name << ")";

            std::ofstream out("./uploads/" + filename, std::ios::binary);
            out.write(part.body.data(), static_cast<std::streamsize>(part.body.size()));
            out.close();

            crow::json::wvalue file_info;
            file_info["name"] = filename;
            file_info["size"] = part.body.size();
            file_info["part"] = part_name;
            result["files"][idx++] = std::move(file_info);
        }

        result["uploaded"] = idx;
        return crow::response(200, result);
    });

    app.port(8080).run();

    return 0;
}
""",
        "function": "multipart_file_upload",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/multipart_upload.cpp",
    },

    # ── 15. static_file_serving ─────────────────────────────────────────────
    {
        "normalized_code": """\
#include "crow.h"

int main()
{
    crow::SimpleApp app;

    CROW_ROUTE(app, "/static/<path>")
    ([](const crow::request& req, crow::response& res, std::string file_path) {
        res.set_static_file_info("static/" + file_path);
        CROW_LOG_DEBUG << "Serving static file: " << file_path;
        res.end();
    });

    CROW_ROUTE(app, "/download/<string>")
    ([](const crow::request& req, crow::response& res, const std::string& filename) {
        res.set_static_file_info("downloads/" + filename);
        res.add_header("Content-Disposition",
                        "attachment; filename=\"" + filename + "\"");
        res.end();
    });

    app.port(8080).run();

    return 0;
}
""",
        "function": "static_file_serving",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "examples/static_files.cpp",
    },

    # ── 16. blueprint_modular ───────────────────────────────────────────────
    {
        "normalized_code": """\
#include "crow.h"

int main()
{
    crow::SimpleApp app;

    crow::Blueprint xxx_bp("xxxs", "xxxs", "xxxs");
    crow::Blueprint admin_bp("admin", "admin", "admin");

    CROW_BP_ROUTE(xxx_bp, "/")
    ([]() {
        crow::json::wvalue result;
        result["action"] = "list_xxxs";
        return result;
    });

    CROW_BP_ROUTE(xxx_bp, "/<int>")
    ([](int xxx_id) {
        crow::json::wvalue result;
        result["id"] = xxx_id;
        result["action"] = "get_xxx";
        return result;
    });

    CROW_BP_ROUTE(admin_bp, "/dashboard")
    ([]() {
        return "Admin dashboard";
    });

    app.register_blueprint(xxx_bp);
    app.register_blueprint(admin_bp);

    CROW_LOG_INFO << "Blueprints registered: /xxxs, /admin";

    app.port(8080).run();

    return 0;
}
""",
        "function": "blueprint_modular",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "examples/blueprint_modular.cpp",
    },

    # ── 17. ssl_https_setup ─────────────────────────────────────────────────
    {
        "normalized_code": """\
#include "crow.h"

int main()
{
    crow::SimpleApp app;

    CROW_ROUTE(app, "/")
    ([]() {
        return "Secure endpoint";
    });

    CROW_ROUTE(app, "/xxxs")
    ([]() {
        crow::json::wvalue result;
        result["secure"] = true;
        result["status_text"] = "TLS-protected xxxs endpoint";
        return result;
    });

    app.port(443)
        .ssl_file("cert.pem", "key.pem")
        .multithreaded()
        .run();

    return 0;
}
""",
        "function": "ssl_https_setup",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "examples/ssl_setup.cpp",
    },

    # ── 18. cors_middleware ──────────────────────────────────────────────────
    {
        "normalized_code": """\
#include "crow.h"
#include "crow/middlewares/cors.h"

int main()
{
    crow::App<crow::CORSHandler> app;

    auto& cors = app.get_middleware<crow::CORSHandler>();

    cors
        .global()
        .headers("Content-Type", "Authorization", "X-Requested-With")
        .methods("GET"_method, "POST"_method, "PUT"_method, "DELETE"_method, "OPTIONS"_method)
        .origin("*")
        .max_age(3600);

    cors
        .prefix("/xxxs")
        .origin("https://xxx-frontend.example.com")
        .headers("Content-Type", "Authorization")
        .methods("GET"_method, "POST"_method);

    CROW_ROUTE(app, "/xxxs")
    ([]() {
        crow::json::wvalue result;
        result["status_text"] = "CORS-enabled endpoint";
        return result;
    });

    app.port(8080).run();

    return 0;
}
""",
        "function": "cors_middleware",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "examples/cors_middleware.cpp",
    },

    # ── 19. cookie_middleware ────────────────────────────────────────────────
    {
        "normalized_code": """\
#include "crow.h"
#include "crow/middlewares/cookie_parser.h"

int main()
{
    crow::App<crow::CookieParser> app;

    CROW_ROUTE(app, "/xxxs/login")
        .methods("POST"_method)
    ([&](const crow::request& req) {
        auto& ctx = app.get_context<crow::CookieParser>(req);

        ctx.set_cookie("xxx_session", "session_token_value")
            .path("/")
            .max_age(3600)
            .httponly();

        CROW_LOG_INFO << "Cookie set for xxx session";

        crow::json::wvalue result;
        result["status_text"] = "Login successful, cookie set";
        return crow::response(200, result);
    });

    CROW_ROUTE(app, "/xxxs/profile")
    ([&](const crow::request& req) {
        auto& ctx = app.get_context<crow::CookieParser>(req);

        std::string session = ctx.get_cookie("xxx_session");
        if (session.empty()) {
            return crow::response(401, "No session cookie");
        }

        CROW_LOG_INFO << "Session cookie found: " << session;

        crow::json::wvalue result;
        result["session"] = session;
        result["status_text"] = "Profile data";
        return crow::response(200, result);
    });

    app.port(8080).run();

    return 0;
}
""",
        "function": "cookie_middleware",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "examples/cookie_middleware.cpp",
    },

    # ── 20. session_middleware ───────────────────────────────────────────────
    {
        "normalized_code": """\
#include "crow.h"
#include "crow/middlewares/cookie_parser.h"
#include "crow/middlewares/session.h"

using Session = crow::SessionMiddleware<crow::InMemoryStore>;

int main()
{
    crow::App<crow::CookieParser, Session> app{
        Session{
            crow::CookieParser::Cookie("xxx_sid").max_age(3600).path("/"),
            64,
            crow::InMemoryStore{}
        }
    };

    CROW_ROUTE(app, "/xxxs/login")
        .methods("POST"_method)
    ([&](const crow::request& req) {
        auto& session = app.get_context<Session>(req);
        session.set("xxx_account", "xxx_name");
        session.set("xxx_role", "admin");

        CROW_LOG_INFO << "Session created for xxx account";

        crow::json::wvalue result;
        result["status_text"] = "Session started";
        return crow::response(200, result);
    });

    CROW_ROUTE(app, "/xxxs/profile")
    ([&](const crow::request& req) {
        auto& session = app.get_context<Session>(req);
        auto account = session.get("xxx_account", "");

        if (account.empty()) {
            return crow::response(401, "No active session");
        }

        auto role = session.get("xxx_role", "guest");

        crow::json::wvalue result;
        result["account"] = account;
        result["role"] = role;
        return crow::response(200, result);
    });

    CROW_ROUTE(app, "/xxxs/logout")
        .methods("POST"_method)
    ([&](const crow::request& req) {
        auto& session = app.get_context<Session>(req);
        session.remove("xxx_account");
        session.remove("xxx_role");

        CROW_LOG_INFO << "Session destroyed";

        return crow::response(200, "Logged out");
    });

    app.port(8080).run();

    return 0;
}
""",
        "function": "session_middleware",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "examples/session_middleware.cpp",
    },

    # ── 21. compression_setup ───────────────────────────────────────────────
    {
        "normalized_code": """\
#include "crow.h"

int main()
{
    crow::SimpleApp app;

    app.use_compression(crow::compression::algorithm::DEFLATE);

    CROW_ROUTE(app, "/xxxs")
    ([]() {
        crow::json::wvalue result;
        result["status_text"] = "Compressed response";
        result["compression"] = "deflate";

        crow::json::wvalue::list elements;
        for (int i = 0; i < 100; i++) {
            crow::json::wvalue element;
            element["id"] = i;
            element["name"] = "xxx_" + std::to_string(i);
            elements.push_back(std::move(element));
        }
        result["xxxs"] = std::move(elements);

        return result;
    });

    CROW_LOG_INFO << "Compression enabled (DEFLATE)";

    app.port(8080)
        .multithreaded()
        .run();

    return 0;
}
""",
        "function": "compression_setup",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "examples/compression.cpp",
    },

    # ── 22. catchall_route ──────────────────────────────────────────────────
    {
        "normalized_code": """\
#include "crow.h"

int main()
{
    crow::SimpleApp app;

    CROW_ROUTE(app, "/xxxs")
    ([]() {
        crow::json::wvalue result;
        result["status_text"] = "Xxx list";
        return result;
    });

    CROW_CATCHALL_ROUTE(app)
    ([](const crow::request& req, crow::response& res) {
        if (req.url.rfind("/api/", 0) == 0) {
            res.code = 404;
            crow::json::wvalue error;
            error["error"] = "Not Found";
            error["path"] = req.url;
            error["method"] = crow::method_name(req.method);
            res.set_header("Content-Type", "application/json");
            res.write(error.dump());
        } else {
            res.code = 404;
            res.write("Page not found: " + req.url);
        }

        CROW_LOG_INFO << "Catchall: " << crow::method_name(req.method)
                      << " " << req.url << " -> 404";
        res.end();
    });

    app.port(8080).run();

    return 0;
}
""",
        "function": "catchall_route",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/catchall_route.cpp",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "crow app setup route handler",
    "crow JSON read write",
    "crow websocket broadcast",
    "crow middleware before after handle",
    "crow blueprint modular routing",
    "crow multipart file upload",
    "crow session cookie middleware",
    "crow CORS configuration",
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
