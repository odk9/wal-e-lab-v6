"""
Wirings ingestion script for Wal-e Lab V6 Qdrant KB.
Repo: eddycjy/go-gin-example (Go Simple)

Manual wiring extraction (no AST for Go).
8 wirings extracted and normalized.

Author: Wal-e Lab V6
Date: 2026-03-31
"""

from __future__ import annotations

import os
import subprocess
import time
import uuid
from datetime import datetime

from qdrant_client import QdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointStruct,
)

from embedder import embed_documents_batch, embed_query

# ============================================================================
# CONSTANTS
# ============================================================================

REPO_URL = "https://github.com/eddycjy/go-gin-example.git"
REPO_NAME = "eddycjy/go-gin-example"
REPO_LOCAL = "/tmp/go-gin-example"
LANGUAGE = "go"
FRAMEWORK = "gin"
STACK = "gin+gorm+jwt+redis"
CHARTE_VERSION = "1.0"
TAG = "wirings/eddycjy/go-gin-example"
DRY_RUN = False
KB_PATH = "./kb_qdrant"
COLLECTION = "wirings"

# ============================================================================
# WIRINGS DATA (8 manual wirings)
# ============================================================================

WIRINGS = [
    {
        "wiring_type": "import_graph",
        "description": "Go package dependency tree for Gin API: main.go imports routers which imports pkg/api/v1 handlers, models for GORM, pkg/setting for config, pkg/util for JWT and pagination utilities, middleware for authentication and CORS",
        "modules": [
            "main.go",
            "routers/router.go",
            "routers/api/v1/",
            "models/models.go",
            "pkg/setting/setting.go",
            "pkg/util/jwt.go",
            "pkg/util/pagination.go",
            "middleware/jwt.go",
        ],
        "connections": [
            "main.go → routers.Setup (router initialization)",
            "routers/router.go → routers/api/v1 (handler imports)",
            "routers/api/v1 → models (entity references)",
            "routers/api/v1 → pkg/util (JWT, pagination helpers)",
            "models/models.go → pkg/setting (database URL)",
            "middleware → pkg/util/jwt (token parsing)",
        ],
        "code_example": """// main.go
package main

import (
    "Xxxpkg/setting"
    "Xxxrouters"
    _ "github.com/jinzhu/gorm/dialects/mysql"
)

func main() {
    setting.Setup()
    routers.Setup()
}

// routers/router.go
package routers

import (
    "Xxxmiddleware"
    v1 "Xxxrouters/api/v1"
    "github.com/gin-gonic/gin"
)

func Setup() *gin.Engine {
    r := gin.New()
    r.Use(middleware.CORS())

    apiv1 := r.Group("/api/v1")
    apiv1.Use(middleware.JWT())
    {
        apiv1.GET("/xxxs", v1.GetXxxs)
        apiv1.POST("/xxxs", v1.AddXxx)
    }
    return r
}
""",
        "pattern_scope": "crud_simple",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": int(time.time()),
        "_tag": TAG,
    },
    {
        "wiring_type": "flow_pattern",
        "description": "Complete Go file creation order for Gin CRUD API: 1) conf/app.ini (config), 2) pkg/setting (ini parser), 3) models/models.go (GORM DB init + base model + callbacks), 4) models/xxx.go (entity + CRUD functions), 5) pkg/util/jwt.go (token gen/parse), 6) pkg/util/pagination.go (offset calculator), 7) middleware/jwt.go (JWT auth), 8) routers/api/v1/xxx.go (handlers), 9) routers/router.go (route groups), 10) main.go (startup)",
        "modules": [
            "conf/app.ini",
            "pkg/setting/setting.go",
            "models/models.go",
            "models/xxx.go",
            "pkg/util/jwt.go",
            "pkg/util/pagination.go",
            "middleware/jwt.go",
            "routers/api/v1/xxx.go",
            "routers/router.go",
            "main.go",
        ],
        "connections": [
            "conf/app.ini → pkg/setting (config parsing)",
            "pkg/setting → models.Setup (database DSN)",
            "models.Setup → models.xxx (CRUD functions access db)",
            "pkg/util/jwt → middleware (token validation)",
            "pkg/util/pagination → routers/api/v1 (offset calculation)",
            "middleware → routers/router (applied to groups)",
            "routers/api/v1 → main (registered routes)",
        ],
        "code_example": """// conf/app.ini
[database]
Type = mysql
User = root
Password = password
Host = 127.0.0.1:3306
Name = xxx_db

// pkg/setting/setting.go
package setting

import "Xxxutil"

var (
    Cfg *ini.File
    DatabaseSetting *DatabaseSettingS
)

func Setup() {
    Cfg, _ = ini.Load("conf/app.ini")
    DatabaseSetting = new(DatabaseSettingS)
    DatabaseSetting.ReadSection(Cfg)
}

// models/models.go
package models

import (
    "Xxxsetting"
    "github.com/jinzhu/gorm"
)

var db *gorm.DB

type Model struct {
    ID        int   `gorm:"primary_key"`
    CreatedOn int64
    ModifiedOn int64
    DeletedOn int64
}

func Setup() error {
    db, _ = gorm.Open("mysql", setting.DatabaseSetting.DSN())
    db.Callback().Create().Register("updateTimeStampForCreateCallback", updateTimeStampForCreateCallback)
    db.Callback().Update().Register("updateTimeStampForUpdateCallback", updateTimeStampForUpdateCallback)
    db.Callback().Delete().Register("deleteCallback", deleteCallback)
    return nil
}

// models/xxx.go
package models

func GetXxxs(pageNum, pageSize int, maps interface{}) ([]*Xxx, error) {
    var xxxs []*Xxx
    db.Where(maps).Offset(pageNum).Limit(pageSize).Find(&xxxs)
    return xxxs, db.Error
}

func AddXxx(data map[string]interface{}) error {
    db.Create(&Xxx{XxxName: data["xxx_name"].(string)})
    return db.Error
}

// pkg/util/jwt.go
package util

import "github.com/dgrijalho/jwt-go"

func GenerateToken(username, password string) (string, error) {
    claims := jwt.StandardClaims{
        Subject: username,
        ExpiresAt: time.Now().Add(time.Hour * 24).Unix(),
    }
    token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
    return token.SignedString([]byte("secret"))
}

// middleware/jwt.go
package middleware

import (
    "Xxxutil"
    "github.com/gin-gonic/gin"
)

func JWT() gin.HandlerFunc {
    return func(c *gin.Context) {
        token := c.Query("token")
        if token == "" {
            c.AbortWithStatusJSON(401, gin.H{"error": "no token"})
            return
        }
        claims, err := util.ParseToken(token)
        if err != nil {
            c.AbortWithStatusJSON(401, gin.H{"error": "invalid token"})
            return
        }
        c.Set("username", claims.Subject)
        c.Next()
    }
}

// routers/api/v1/xxx.go
package v1

import (
    "Xxxmiddleware"
    "Xxxmodels"
    "Xxxutil"
    "github.com/gin-gonic/gin"
)

func GetXxxs(c *gin.Context) {
    pageNum := util.GetPage(c)
    pageSize := util.GetPageSize(c)
    xxxs, err := models.GetXxxs(pageNum, pageSize, nil)
    c.JSON(200, gin.H{"data": xxxs})
}

func AddXxx(c *gin.Context) {
    var input struct{XxxName string}
    c.BindJSON(&input)
    models.AddXxx(map[string]interface{}{"xxx_name": input.XxxName})
    c.JSON(201, gin.H{"message": "created"})
}

// routers/router.go
package routers

import (
    "Xxxmiddleware"
    v1 "Xxxrouters/api/v1"
    "github.com/gin-gonic/gin"
)

func Setup() *gin.Engine {
    r := gin.New()
    r.Use(middleware.CORS())

    apiv1 := r.Group("/api/v1")
    apiv1.Use(middleware.JWT())
    {
        apiv1.GET("/xxxs", v1.GetXxxs)
        apiv1.POST("/xxxs", v1.AddXxx)
    }
    return r
}

// main.go
package main

import (
    "Xxxmodels"
    "Xxxrouters"
    "Xxxsetting"
)

func main() {
    setting.Setup()
    models.Setup()
    router := routers.Setup()
    router.Run(":8000")
}
""",
        "pattern_scope": "crud_simple",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": int(time.time()),
        "_tag": TAG,
    },
    {
        "wiring_type": "dependency_chain",
        "description": "GORM singleton pattern with callback registration: models.Setup() at startup calls gorm.Open() → configures connection pooling (MaxIdleConns, MaxOpenConns) → registers GORM callbacks for timestamps (create, update, delete) → exposes global db var used by all CRUD functions",
        "modules": ["models/models.go", "models/callbacks.go"],
        "connections": [
            "main.Setup → models.Setup (initialization)",
            "models.Setup → gorm.Open (database connection)",
            "gorm.Open → db.Callback() chains (register handlers)",
            "CRUD functions → global db variable",
        ],
        "code_example": """// models/models.go
package models

import (
    "fmt"
    "time"
    "Xxxsetting"
    "github.com/jinzhu/gorm"
    _ "github.com/jinzhu/gorm/dialects/mysql"
)

type Model struct {
    ID        int   `gorm:"primary_key"`
    CreatedOn int64
    ModifiedOn int64
    DeletedOn int64
}

var db *gorm.DB

func Setup() error {
    var err error
    dsn := setting.DatabaseSetting.DSN()
    db, err = gorm.Open("mysql", dsn)
    if err != nil {
        return err
    }

    db.SingularTable(true)
    db.DB().SetMaxIdleConns(10)
    db.DB().SetMaxOpenConns(100)

    // Register callbacks
    db.Callback().Create().Register("updateTimeStampForCreateCallback", updateTimeStampForCreateCallback)
    db.Callback().Update().Register("updateTimeStampForUpdateCallback", updateTimeStampForUpdateCallback)
    db.Callback().Delete().Register("deleteCallback", deleteCallback)

    return nil
}

// models/callbacks.go
package models

import (
    "time"
    "github.com/jinzhu/gorm"
)

func updateTimeStampForCreateCallback(scope *gorm.Scope) {
    if !scope.HasError() {
        now := time.Now().Unix()
        scope.SetColumn("CreatedOn", now)
        scope.SetColumn("ModifiedOn", now)
    }
}

func updateTimeStampForUpdateCallback(scope *gorm.Scope) {
    if !scope.HasError() {
        scope.SetColumn("ModifiedOn", time.Now().Unix())
    }
}

func deleteCallback(scope *gorm.Scope) {
    if !scope.HasError() {
        if scope.HasColumn("DeletedOn") {
            scope.SetColumn("DeletedOn", time.Now().Unix())
        } else {
            scope.Delete()
        }
    }
}

// CRUD function using db singleton
func GetXxx(id int) (*Xxx, error) {
    var xxx Xxx
    err := db.Where("id = ?", id).Where("deleted_on = 0").First(&xxx).Error
    return &xxx, err
}

func AddXxx(data map[string]interface{}) error {
    xxx := Xxx{
        XxxName: data["xxx_name"].(string),
    }
    return db.Create(&xxx).Error
}

func DeleteXxx(id int) error {
    return db.Where("id = ?", id).Delete(&Xxx{}).Error
}
""",
        "pattern_scope": "crud_simple",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": int(time.time()),
        "_tag": TAG,
    },
    {
        "wiring_type": "dependency_chain",
        "description": "Gin router group versioning with middleware: r := gin.New() → r.Use(middleware) for global → apiv1 := r.Group(\"/api/v1\") → apiv1.Use(middleware.JWT()) → register routes (GET, POST, PUT, DELETE) on versioned group. Auth routes registered outside JWT group",
        "modules": ["routers/router.go", "middleware/jwt.go", "routers/api/v1/xxx.go"],
        "connections": [
            "router.Setup → gin.New()",
            "r.Use(middleware.CORS()) (global)",
            "r.Group(\"/api/v1\") (versioning)",
            "apiv1.Use(middleware.JWT()) (group-level auth)",
            "apiv1.GET/POST/PUT/DELETE (route registration)",
        ],
        "code_example": """// routers/router.go
package routers

import (
    "Xxxmiddleware"
    v1 "Xxxrouters/api/v1"
    "github.com/gin-gonic/gin"
)

func Setup() *gin.Engine {
    r := gin.New()

    // Global middleware
    r.Use(middleware.CORS())
    r.Use(middleware.RequestLogger())

    // Public routes (no JWT)
    r.POST("/login", v1.Login)
    r.POST("/register", v1.Register)

    // API v1 group with JWT auth
    apiv1 := r.Group("/api/v1")
    apiv1.Use(middleware.JWT())
    {
        // Xxx routes
        apiv1.GET("/xxxs", v1.GetXxxs)
        apiv1.GET("/xxxs/:id", v1.GetXxx)
        apiv1.POST("/xxxs", v1.AddXxx)
        apiv1.PUT("/xxxs/:id", v1.EditXxx)
        apiv1.DELETE("/xxxs/:id", v1.DeleteXxx)

        // Yyy routes
        apiv1.GET("/yyys", v1.GetYyys)
        apiv1.POST("/yyys", v1.AddYyy)
    }

    return r
}

// middleware/jwt.go
package middleware

import (
    "Xxxutil"
    "github.com/gin-gonic/gin"
)

func JWT() gin.HandlerFunc {
    return func(c *gin.Context) {
        token := c.GetHeader("Authorization")
        if token == "" {
            token = c.Query("token")
        }

        if token == "" {
            c.AbortWithStatusJSON(401, gin.H{"error": "missing token"})
            return
        }

        claims, err := util.ParseToken(token)
        if err != nil {
            c.AbortWithStatusJSON(401, gin.H{"error": "invalid token"})
            return
        }

        c.Set("username", claims.Subject)
        c.Next()
    }
}

// routers/api/v1/xxx.go
package v1

import (
    "Xxxmodels"
    "Xxxutil"
    "github.com/gin-gonic/gin"
)

func GetXxxs(c *gin.Context) {
    pageNum := util.GetPage(c)
    pageSize := util.GetPageSize(c)

    total, _ := models.GetXxxTotal(nil)
    xxxs, _ := models.GetXxxs(pageNum, pageSize, nil)

    c.JSON(200, gin.H{
        "total": total,
        "data": xxxs,
    })
}

func AddXxx(c *gin.Context) {
    var input struct{XxxName string}
    if err := c.BindJSON(&input); err != nil {
        c.JSON(400, gin.H{"error": err.Error()})
        return
    }

    err := models.AddXxx(map[string]interface{}{
        "xxx_name": input.XxxName,
    })

    if err != nil {
        c.JSON(500, gin.H{"error": err.Error()})
        return
    }

    c.JSON(201, gin.H{"message": "created"})
}
""",
        "pattern_scope": "crud_simple",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": int(time.time()),
        "_tag": TAG,
    },
    {
        "wiring_type": "flow_pattern",
        "description": "CRUD function pattern in Go: package-level functions (not methods) with signature func GetXxxs(pageNum, pageSize int, maps interface{}) ([]*Xxx, error) → uses GORM query builder db.Where(maps).Offset(pageNum).Limit(pageSize).Find(&xxxs) → optional Preload for relations → returns slice and error",
        "modules": ["models/xxx.go"],
        "connections": [
            "handler (routers/api/v1) → CRUD function",
            "CRUD function → db singleton variable",
            "db.Where() → db.Offset() → db.Limit() → db.Find()",
        ],
        "code_example": """// models/xxx.go
package models

type Xxx struct {
    Model
    XxxName string `json:"xxx_name"`
    XxxDescription string `json:"xxx_description"`
    XxxLabelID int `json:"xxx_label_id"`
    XxxLabel *XxxLabel `json:"xxx_label" gorm:"foreignKey:XxxLabelID"`
}

type XxxLabel struct {
    ID int `gorm:"primary_key"`
    LabelName string
}

// Get total count with optional filtering
func GetXxxTotal(maps interface{}) (int, error) {
    var count int
    if maps != nil {
        db.Where(maps).Model(&Xxx{}).Count(&count)
    } else {
        db.Model(&Xxx{}).Count(&count)
    }
    return count, db.Error
}

// Get paginated list with optional filtering
func GetXxxs(pageNum, pageSize int, maps interface{}) ([]*Xxx, error) {
    var xxxs []*Xxx

    query := db.Where("deleted_on = 0")

    if maps != nil {
        query = query.Where(maps)
    }

    err := query.
        Offset((pageNum - 1) * pageSize).
        Limit(pageSize).
        Preload("XxxLabel").
        Find(&xxxs).Error

    return xxxs, err
}

// Get single entity by ID
func GetXxx(id int) (*Xxx, error) {
    var xxx Xxx
    err := db.Where("id = ? AND deleted_on = 0", id).
        Preload("XxxLabel").
        First(&xxx).Error
    return &xxx, err
}

// Check existence by ID
func ExistXxxByID(id int) (bool, error) {
    var xxx Xxx
    err := db.Select("id").Where("id = ? AND deleted_on = 0", id).First(&xxx).Error
    if err != nil && err.RecordNotFound() {
        return false, nil
    }
    return err == nil, err
}

// Create new entity
func AddXxx(data map[string]interface{}) error {
    xxx := Xxx{
        XxxName: data["xxx_name"].(string),
        XxxDescription: data["xxx_description"].(string),
        XxxLabelID: data["xxx_label_id"].(int),
    }
    return db.Create(&xxx).Error
}

// Update entity
func EditXxx(id int, data map[string]interface{}) error {
    return db.Model(&Xxx{}).Where("id = ?", id).Updates(data).Error
}

// Delete entity (soft delete via callback)
func DeleteXxx(id int) error {
    return db.Where("id = ?", id).Delete(&Xxx{}).Error
}
""",
        "pattern_scope": "crud_simple",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": int(time.time()),
        "_tag": TAG,
    },
    {
        "wiring_type": "dependency_chain",
        "description": "JWT token flow: GenerateToken(username, password) creates JWT claims → jwt.NewWithClaims(HS256, claims) → SignedString() → returns token string. Middleware: ParseToken() extracts token from header or query → jwt.ParseWithClaims() → validates signature → returns claims or error. Token stored in Authorization header or query parameter",
        "modules": ["pkg/util/jwt.go", "middleware/jwt.go", "routers/api/v1/xxx.go"],
        "connections": [
            "handler Login → util.GenerateToken",
            "middleware JWT → util.ParseToken",
            "ParseToken validates signature with secret",
            "claims stored in gin.Context.Set()",
        ],
        "code_example": """// pkg/util/jwt.go
package util

import (
    "errors"
    "time"
    "github.com/dgrijalho/jwt-go"
)

const (
    SigningSecret = "your-secret-key"
    JWTExpirationHours = 24
)

type Claims struct {
    Username string `json:"username"`
    jwt.StandardClaims
}

// Generate JWT token for user
func GenerateToken(username string) (string, error) {
    claims := Claims{
        Username: username,
        StandardClaims: jwt.StandardClaims{
            ExpiresAt: time.Now().Add(time.Hour * JWTExpirationHours).Unix(),
            IssuedAt: time.Now().Unix(),
        },
    }

    token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
    signed, err := token.SignedString([]byte(SigningSecret))

    return signed, err
}

// Parse and validate JWT token
func ParseToken(tokenString string) (*Claims, error) {
    claims := &Claims{}

    token, err := jwt.ParseWithClaims(tokenString, claims, func(token *jwt.Token) (interface{}, error) {
        if _, ok := token.Method.(*jwt.SigningMethodHMAC); !ok {
            return nil, errors.New("unexpected signing method")
        }
        return []byte(SigningSecret), nil
    })

    if err != nil {
        return nil, err
    }

    if !token.Valid {
        return nil, errors.New("invalid token")
    }

    if claims.ExpiresAt < time.Now().Unix() {
        return nil, errors.New("token expired")
    }

    return claims, nil
}

// middleware/jwt.go
package middleware

import (
    "strings"
    "Xxxutil"
    "github.com/gin-gonic/gin"
)

func JWT() gin.HandlerFunc {
    return func(c *gin.Context) {
        var token string

        // Try Authorization header first
        authHeader := c.GetHeader("Authorization")
        if authHeader != "" {
            parts := strings.SplitN(authHeader, " ", 2)
            if len(parts) == 2 && parts[0] == "Bearer" {
                token = parts[1]
            }
        }

        // Fallback to query parameter
        if token == "" {
            token = c.Query("token")
        }

        if token == "" {
            c.AbortWithStatusJSON(401, gin.H{"error": "missing token"})
            return
        }

        claims, err := util.ParseToken(token)
        if err != nil {
            c.AbortWithStatusJSON(401, gin.H{"error": "invalid token: " + err.Error()})
            return
        }

        c.Set("username", claims.Username)
        c.Next()
    }
}

// routers/api/v1/xxx.go - Login handler
package v1

import (
    "Xxxutil"
    "github.com/gin-gonic/gin"
)

func Login(c *gin.Context) {
    var input struct {
        Username string `json:"username" binding:"required"`
        Password string `json:"password" binding:"required"`
    }

    if err := c.BindJSON(&input); err != nil {
        c.JSON(400, gin.H{"error": err.Error()})
        return
    }

    // Validate credentials (implement your logic)
    if input.Username != "admin" || input.Password != "password" {
        c.JSON(401, gin.H{"error": "invalid credentials"})
        return
    }

    token, err := util.GenerateToken(input.Username)
    if err != nil {
        c.JSON(500, gin.H{"error": err.Error()})
        return
    }

    c.JSON(200, gin.H{"token": token})
}

func GetXxxs(c *gin.Context) {
    username := c.MustGet("username").(string)
    // Use username in query logic...
    c.JSON(200, gin.H{"data": []interface{}{}, "user": username})
}
""",
        "pattern_scope": "crud_auth",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": int(time.time()),
        "_tag": TAG,
    },
    {
        "wiring_type": "flow_pattern",
        "description": "Soft delete pattern using GORM callbacks: DeleteXxx(id) calls db.Where(\"id = ?\", id).Delete(&Xxx{}) → deleteCallback is triggered → checks if Xxx struct has DeletedOn field → if yes: executes UPDATE SET deleted_on = time.Now().Unix() (soft delete) → if no: executes hard DELETE. Records not soft-deleted are filtered in queries with WHERE deleted_on = 0",
        "modules": ["models/models.go", "models/callbacks.go", "models/xxx.go"],
        "connections": [
            "DeleteXxx → db.Delete() → deleteCallback",
            "deleteCallback → scope.HasColumn(\"DeletedOn\")",
            "if true: scope.SetColumn(\"DeletedOn\", timestamp)",
            "if false: scope.Delete() (hard delete)",
            "GetXxxs filters: WHERE deleted_on = 0",
        ],
        "code_example": """// models/models.go
package models

import (
    "time"
    "github.com/jinzhu/gorm"
)

type Model struct {
    ID        int   `gorm:"primary_key"`
    CreatedOn int64
    ModifiedOn int64
    DeletedOn int64 `gorm:"index"`
}

// models/callbacks.go
package models

import (
    "time"
    "github.com/jinzhu/gorm"
)

// Delete callback: soft or hard delete based on field existence
func deleteCallback(scope *gorm.Scope) {
    if !scope.HasError() {
        if scope.HasColumn("DeletedOn") {
            // Soft delete: mark with timestamp
            scope.SetColumn("DeletedOn", time.Now().Unix())
        } else {
            // Hard delete: remove from database
            scope.Delete()
        }
    }
}

// models/xxx.go
package models

type Xxx struct {
    Model
    XxxName string `json:"xxx_name"`
}

// Get only non-deleted records
func GetXxxs(pageNum, pageSize int, maps interface{}) ([]*Xxx, error) {
    var xxxs []*Xxx

    query := db.Where("deleted_on = 0")

    if maps != nil {
        query = query.Where(maps)
    }

    err := query.
        Offset((pageNum - 1) * pageSize).
        Limit(pageSize).
        Find(&xxxs).Error

    return xxxs, err
}

// Get single non-deleted record
func GetXxx(id int) (*Xxx, error) {
    var xxx Xxx
    err := db.Where("id = ? AND deleted_on = 0", id).First(&xxx).Error
    return &xxx, err
}

// Soft delete: called by callback
func DeleteXxx(id int) error {
    return db.Where("id = ?", id).Delete(&Xxx{}).Error
}

// Recovery: unsoft-delete if needed
func RecoverXxx(id int) error {
    return db.Model(&Xxx{}).Where("id = ?", id).Update("deleted_on", 0).Error
}

// Hard delete from trash (admin only)
func PermanentlyDeleteXxx(id int) error {
    return db.Unscoped().Where("id = ?", id).Delete(&Xxx{}).Error
}

// Get soft-deleted records only
func GetDeletedXxxs() ([]*Xxx, error) {
    var xxxs []*Xxx
    err := db.Where("deleted_on > 0").Find(&xxxs).Error
    return xxxs, err
}
""",
        "pattern_scope": "crud_simple",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": int(time.time()),
        "_tag": TAG,
    },
    {
        "wiring_type": "flow_pattern",
        "description": "Testing wiring for Gin handlers: Go testing package with httptest.NewRecorder + gin.CreateTestContext for isolated handler tests, models.Setup() with test database (separate schema), JWT token generation in test helpers, table-driven test pattern, TestClient-style GET/POST setup",
        "modules": ["main_test.go", "routers/api/v1/xxx_test.go"],
        "connections": [
            "test main → init test db → register routes",
            "handler test → jwt token helper",
            "httptest → gin handler",
            "assert response status + JSON",
        ],
        "code_example": """// main_test.go
package main

import (
    "os"
    "testing"
    "Xxxmodels"
    "Xxxrouters"
)

var testRouter *gin.Engine

func TestMain(m *testing.M) {
    // Setup test database
    os.Setenv("DATABASE_NAME", "xxx_test_db")

    err := models.Setup()
    if err != nil {
        panic(err)
    }

    testRouter = routers.Setup()

    code := m.Run()
    os.Exit(code)
}

// routers/api/v1/xxx_test.go
package v1

import (
    "bytes"
    "encoding/json"
    "net/http"
    "net/http/httptest"
    "testing"
    "Xxxmodels"
    "Xxxutil"
    "github.com/gin-gonic/gin"
    "github.com/stretchr/testify/assert"
)

// Helper: generate valid JWT for test
func generateTestToken(username string) string {
    token, _ := util.GenerateToken(username)
    return token
}

// Test: Get all Xxxs
func TestGetXxxs(t *testing.T) {
    // Create test data
    models.AddXxx(map[string]interface{}{
        "xxx_name": "test_xxx_1",
    })
    models.AddXxx(map[string]interface{}{
        "xxx_name": "test_xxx_2",
    })

    // Setup handler test
    w := httptest.NewRecorder()
    req, _ := http.NewRequest("GET", "/api/v1/xxxs?page=1&page_size=10", nil)
    token := generateTestToken("testuser")
    req.Header.Set("Authorization", "Bearer "+token)

    gin.SetMode(gin.TestMode)
    router := gin.New()
    router.GET("/api/v1/xxxs", GetXxxs)
    router.ServeHTTP(w, req)

    // Assert
    assert.Equal(t, 200, w.Code)
    var response map[string]interface{}
    json.Unmarshal(w.Body.Bytes(), &response)
    assert.NotNil(t, response["data"])
}

// Test: Create Xxx
func TestAddXxx(t *testing.T) {
    input := map[string]interface{}{
        "xxx_name": "new_xxx",
    }

    body, _ := json.Marshal(input)
    w := httptest.NewRecorder()
    req, _ := http.NewRequest("POST", "/api/v1/xxxs", bytes.NewBuffer(body))
    req.Header.Set("Content-Type", "application/json")
    token := generateTestToken("testuser")
    req.Header.Set("Authorization", "Bearer "+token)

    gin.SetMode(gin.TestMode)
    router := gin.New()
    router.POST("/api/v1/xxxs", AddXxx)
    router.ServeHTTP(w, req)

    assert.Equal(t, 201, w.Code)
}

// Test: Authentication required
func TestGetXxxsNoAuth(t *testing.T) {
    w := httptest.NewRecorder()
    req, _ := http.NewRequest("GET", "/api/v1/xxxs", nil)
    // No token

    gin.SetMode(gin.TestMode)
    router := gin.New()
    router.GET("/api/v1/xxxs", GetXxxs)
    router.ServeHTTP(w, req)

    assert.Equal(t, 401, w.Code)
}

// Table-driven test pattern
func TestXxxHandlers(t *testing.T) {
    tests := []struct {
        name           string
        method         string
        path           string
        token          string
        expectedStatus int
    }{
        {
            name:           "get_xxxs_with_auth",
            method:         "GET",
            path:           "/api/v1/xxxs",
            token:          generateTestToken("user1"),
            expectedStatus: 200,
        },
        {
            name:           "get_xxxs_no_auth",
            method:         "GET",
            path:           "/api/v1/xxxs",
            token:          "",
            expectedStatus: 401,
        },
        {
            name:           "get_xxxs_invalid_token",
            method:         "GET",
            path:           "/api/v1/xxxs",
            token:          "invalid_token",
            expectedStatus: 401,
        },
    }

    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            w := httptest.NewRecorder()
            req, _ := http.NewRequest(tt.method, tt.path, nil)
            if tt.token != "" {
                req.Header.Set("Authorization", "Bearer "+tt.token)
            }

            router := testRouter
            router.ServeHTTP(w, req)

            assert.Equal(t, tt.expectedStatus, w.Code)
        })
    }
}
""",
        "pattern_scope": "crud_simple",
        "language": LANGUAGE,
        "framework": FRAMEWORK,
        "stack": STACK,
        "source_repo": REPO_URL,
        "charte_version": CHARTE_VERSION,
        "created_at": int(time.time()),
        "_tag": TAG,
    },
]


# ============================================================================
# MAIN INGESTION LOGIC
# ============================================================================


def main():
    """Main entry point for wiring ingestion."""
    print("\n" + "=" * 80)
    print("Wirings Ingestion: eddycjy/go-gin-example (Go Simple)")
    print("=" * 80)

    # Initialize Qdrant client
    client = QdrantClient(path=KB_PATH)
    print(f"✓ Qdrant client initialized: {KB_PATH}")

    # Cleanup previous versions
    print(f"\nCleaning up previous wirings (tag: {TAG})...")
    try:
        client.delete(
            collection_name=COLLECTION,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[
                        FieldCondition(
                            key="_tag",
                            match=MatchValue(value=TAG),
                        )
                    ]
                )
            ),
        )
        print(f"✓ Cleanup complete")
    except Exception as e:
        print(f"  (no previous wirings to clean: {e})")

    # Build wiring payloads
    print("\nBuilding wiring payloads...")
    points_to_upsert = []

    for idx, wiring in enumerate(WIRINGS, 1):
        # Embed description
        description = wiring["description"]
        embedded = embed_documents_batch([description])[0]

        # Create point
        point = PointStruct(
            id=int(str(int(time.time() * 1e6)) + f"{idx:02d}"),  # Unique ID
            vector=embedded,
            payload={
                "wiring_type": wiring["wiring_type"],
                "description": wiring["description"],
                "modules": wiring["modules"],
                "connections": wiring["connections"],
                "code_example": wiring["code_example"],
                "pattern_scope": wiring["pattern_scope"],
                "language": wiring["language"],
                "framework": wiring["framework"],
                "stack": wiring["stack"],
                "source_repo": wiring["source_repo"],
                "charte_version": wiring["charte_version"],
                "created_at": wiring["created_at"],
                "_tag": wiring["_tag"],
            },
        )
        points_to_upsert.append(point)

    print(f"✓ Built {len(points_to_upsert)} wiring points")

    # Upsert to Qdrant
    if not DRY_RUN:
        print("\nUpserting to Qdrant...")
        client.upsert(
            collection_name=COLLECTION,
            points=points_to_upsert,
        )
        print(f"✓ Upserted {len(points_to_upsert)} points")
    else:
        print("[DRY RUN] Would upsert", len(points_to_upsert), "points")

    # Verify ingestion
    print("\nVerifying ingestion...")
    results = client.query_points(
        collection_name=COLLECTION,
        query=embed_query("Gin GORM CRUD"),
        query_filter=Filter(
            must=[
                FieldCondition(key="language", match=MatchValue(value="go")),
                FieldCondition(
                    key="framework",
                    match=MatchValue(value="gin"),
                ),
            ]
        ),
        limit=5,
    )

    print(f"✓ Query returned {len(results.points)} results")
    for pt in results.points[:3]:
        wiring_type = pt.payload.get("wiring_type", "unknown")
        pattern_scope = pt.payload.get("pattern_scope", "unknown")
        print(f"  - {wiring_type} ({pattern_scope})")

    # Summary
    print("\n" + "=" * 80)
    print(f"Summary: {len(WIRINGS)} wirings ingested for {REPO_NAME}")
    print(f"Language: {LANGUAGE}, Framework: {FRAMEWORK}, Stack: {STACK}")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
