"""
ingest_go_gin_example.py — Extrait, normalise (Charte Wal-e), et indexe
les patterns de eddycjy/go-gin-example dans la KB Qdrant V6.

Go A — Blog API. Gin + GORM + JWT + Redis.

Usage:
    .venv/bin/python3 ingest_go_gin_example.py
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
REPO_URL = "https://github.com/eddycjy/go-gin-example.git"
REPO_NAME = "eddycjy/go-gin-example"
REPO_LOCAL = "/tmp/go_gin_example"
LANGUAGE = "go"
FRAMEWORK = "gin"
STACK = "gin+gorm+jwt+redis"
CHARTE_VERSION = "1.0"
TAG = "eddycjy/go-gin-example"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"
SOURCE_REPO = "https://github.com/eddycjy/go-gin-example"


# ─── Patterns normalisés Charte Wal-e ───────────────────────────────────────
# U-5: Article→Xxx, article→xxx, articles→xxxs
#       Tag→XxxLabel, tag→xxxLabel, tags→xxxLabels, tag_id→xxx_label_id
#       Auth→XxxAuth, auth→xxxAuth
#       Kept: gin, gorm, jwt, redis, context, error, http
# G-1: no panic(). G-2: no fmt.Println/Printf.

PATTERNS: list[dict] = [
    # ═══════════════════════════════════════════════════════════════════════════
    # MODELS
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 1. Base model + DB setup + GORM callbacks ───────────────────────────
    {
        "normalized_code": """\
package models

import (
\t"fmt"
\t"log"
\t"time"

\t"github.com/jinzhu/gorm"
\t_ "github.com/jinzhu/gorm/dialects/mysql"
)

var db *gorm.DB

type Model struct {
\tID         int `gorm:"primary_key" json:"id"`
\tCreatedOn  int `json:"created_on"`
\tModifiedOn int `json:"modified_on"`
\tDeletedOn  int `json:"deleted_on"`
}

func Setup(dbType, dsn string) {
\tvar err error
\tdb, err = gorm.Open(dbType, dsn)
\tif err != nil {
\t\tlog.Fatalf("models.Setup err: %v", err)
\t}
\tdb.SingularTable(true)
\tdb.Callback().Create().Replace("gorm:update_time_stamp", updateTimeStampForCreateCallback)
\tdb.Callback().Update().Replace("gorm:update_time_stamp", updateTimeStampForUpdateCallback)
\tdb.Callback().Delete().Replace("gorm:delete", deleteCallback)
\tdb.DB().SetMaxIdleConns(10)
\tdb.DB().SetMaxOpenConns(100)
}

func CloseDB() {
\tdefer db.Close()
}

func updateTimeStampForCreateCallback(scope *gorm.Scope) {
\tif !scope.HasError() {
\t\tnowTime := time.Now().Unix()
\t\tif f, ok := scope.FieldByName("CreatedOn"); ok {
\t\t\tif f.IsBlank {
\t\t\t\tf.Set(nowTime)
\t\t\t}
\t\t}
\t\tif f, ok := scope.FieldByName("ModifiedOn"); ok {
\t\t\tif f.IsBlank {
\t\t\t\tf.Set(nowTime)
\t\t\t}
\t\t}
\t}
}

func updateTimeStampForUpdateCallback(scope *gorm.Scope) {
\tif _, ok := scope.Get("gorm:update_column"); !ok {
\t\tscope.SetColumn("ModifiedOn", time.Now().Unix())
\t}
}

func deleteCallback(scope *gorm.Scope) {
\tif !scope.HasError() {
\t\tvar extraOption string
\t\tif str, ok := scope.Get("gorm:delete_option"); ok {
\t\t\textraOption = fmt.Sprint(str)
\t\t}
\t\tdeletedOnField, hasDeletedOnField := scope.FieldByName("DeletedOn")
\t\tif !scope.Search.Unscoped && hasDeletedOnField {
\t\t\tscope.Raw(fmt.Sprintf(
\t\t\t\t"UPDATE %v SET %v=%v%v%v",
\t\t\t\tscope.QuotedTableName(),
\t\t\t\tscope.Quote(deletedOnField.DBName),
\t\t\t\tscope.AddToVars(time.Now().Unix()),
\t\t\t\taddExtraSpaceIfExist(scope.CombinedConditionSql()),
\t\t\t\taddExtraSpaceIfExist(extraOption),
\t\t\t)).Exec()
\t\t} else {
\t\t\tscope.Raw(fmt.Sprintf(
\t\t\t\t"DELETE FROM %v%v%v",
\t\t\t\tscope.QuotedTableName(),
\t\t\t\taddExtraSpaceIfExist(scope.CombinedConditionSql()),
\t\t\t\taddExtraSpaceIfExist(extraOption),
\t\t\t)).Exec()
\t\t}
\t}
}

func addExtraSpaceIfExist(str string) string {
\tif str != "" {
\t\treturn " " + str
\t}
\treturn ""
}
""",
        "function": "gorm_base_model_setup_callbacks",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "models/models.go",
    },

    # ── 2. Xxx GORM model + CRUD ────────────────────────────────────────────
    {
        "normalized_code": """\
package models

import "github.com/jinzhu/gorm"

type Xxx struct {
\tModel

\tXxxLabelID int      `json:"xxx_label_id" gorm:"index"`
\tXxxLabel   XxxLabel `json:"xxx_label"`

\tTitle         string `json:"title"`
\tDesc          string `json:"desc"`
\tContent       string `json:"content"`
\tCoverImageUrl string `json:"cover_image_url"`
\tCreatedBy     string `json:"created_by"`
\tModifiedBy    string `json:"modified_by"`
\tState         int    `json:"state"`
}

func ExistXxxByID(id int) (bool, error) {
\tvar xxx Xxx
\terr := db.Select("id").Where("id = ? AND deleted_on = ?", id, 0).First(&xxx).Error
\tif err != nil && err != gorm.ErrRecordNotFound {
\t\treturn false, err
\t}
\tif xxx.ID > 0 {
\t\treturn true, nil
\t}
\treturn false, nil
}

func GetXxxTotal(maps interface{}) (int, error) {
\tvar count int
\tif err := db.Model(&Xxx{}).Where(maps).Count(&count).Error; err != nil {
\t\treturn 0, err
\t}
\treturn count, nil
}

func GetXxxs(pageNum int, pageSize int, maps interface{}) ([]*Xxx, error) {
\tvar xxxs []*Xxx
\terr := db.Preload("XxxLabel").Where(maps).Offset(pageNum).Limit(pageSize).Find(&xxxs).Error
\tif err != nil && err != gorm.ErrRecordNotFound {
\t\treturn nil, err
\t}
\treturn xxxs, nil
}

func GetXxx(id int) (*Xxx, error) {
\tvar xxx Xxx
\terr := db.Where("id = ? AND deleted_on = ?", id, 0).First(&xxx).Error
\tif err != nil && err != gorm.ErrRecordNotFound {
\t\treturn nil, err
\t}
\terr = db.Model(&xxx).Related(&xxx.XxxLabel).Error
\tif err != nil && err != gorm.ErrRecordNotFound {
\t\treturn nil, err
\t}
\treturn &xxx, nil
}

func EditXxx(id int, data interface{}) error {
\treturn db.Model(&Xxx{}).Where("id = ? AND deleted_on = ?", id, 0).Updates(data).Error
}

func AddXxx(data map[string]interface{}) error {
\txxx := Xxx{
\t\tXxxLabelID:    data["xxx_label_id"].(int),
\t\tTitle:         data["title"].(string),
\t\tDesc:          data["desc"].(string),
\t\tContent:       data["content"].(string),
\t\tCreatedBy:     data["created_by"].(string),
\t\tState:         data["state"].(int),
\t\tCoverImageUrl: data["cover_image_url"].(string),
\t}
\treturn db.Create(&xxx).Error
}

func DeleteXxx(id int) error {
\treturn db.Where("id = ?", id).Delete(Xxx{}).Error
}

func CleanAllXxx() error {
\treturn db.Unscoped().Where("deleted_on != ?", 0).Delete(&Xxx{}).Error
}
""",
        "function": "gorm_model_xxx_foreign_key_crud",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "models/xxx.go",
    },

    # ── 3. XxxLabel GORM model + CRUD ───────────────────────────────────────
    {
        "normalized_code": """\
package models

import "github.com/jinzhu/gorm"

type XxxLabel struct {
\tModel

\tName       string `json:"name"`
\tCreatedBy  string `json:"created_by"`
\tModifiedBy string `json:"modified_by"`
\tState      int    `json:"state"`
}

func ExistXxxLabelByName(name string) (bool, error) {
\tvar xxxLabel XxxLabel
\terr := db.Select("id").Where("name = ? AND deleted_on = ?", name, 0).First(&xxxLabel).Error
\tif err != nil && err != gorm.ErrRecordNotFound {
\t\treturn false, err
\t}
\tif xxxLabel.ID > 0 {
\t\treturn true, nil
\t}
\treturn false, nil
}

func AddXxxLabel(name string, state int, createdBy string) error {
\treturn db.Create(&XxxLabel{Name: name, State: state, CreatedBy: createdBy}).Error
}

func GetXxxLabels(pageNum int, pageSize int, maps interface{}) ([]XxxLabel, error) {
\tvar xxxLabels []XxxLabel
\tvar err error
\tif pageSize > 0 && pageNum > 0 {
\t\terr = db.Where(maps).Find(&xxxLabels).Offset(pageNum).Limit(pageSize).Error
\t} else {
\t\terr = db.Where(maps).Find(&xxxLabels).Error
\t}
\tif err != nil && err != gorm.ErrRecordNotFound {
\t\treturn nil, err
\t}
\treturn xxxLabels, nil
}

func GetXxxLabelTotal(maps interface{}) (int, error) {
\tvar count int
\tif err := db.Model(&XxxLabel{}).Where(maps).Count(&count).Error; err != nil {
\t\treturn 0, err
\t}
\treturn count, nil
}

func ExistXxxLabelByID(id int) (bool, error) {
\tvar xxxLabel XxxLabel
\terr := db.Select("id").Where("id = ? AND deleted_on = ?", id, 0).First(&xxxLabel).Error
\tif err != nil && err != gorm.ErrRecordNotFound {
\t\treturn false, err
\t}
\tif xxxLabel.ID > 0 {
\t\treturn true, nil
\t}
\treturn false, nil
}

func DeleteXxxLabel(id int) error {
\treturn db.Where("id = ?", id).Delete(&XxxLabel{}).Error
}

func EditXxxLabel(id int, data interface{}) error {
\treturn db.Model(&XxxLabel{}).Where("id = ? AND deleted_on = ?", id, 0).Updates(data).Error
}
""",
        "function": "gorm_model_xxx_label_crud",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "models/xxx_label.go",
    },

    # ── 4. XxxAuth model + check ────────────────────────────────────────────
    {
        "normalized_code": """\
package models

import "github.com/jinzhu/gorm"

type XxxAuth struct {
\tID       int    `gorm:"primary_key" json:"id"`
\tUsername string `json:"username"`
\tPassword string `json:"password"`
}

func CheckXxxAuth(username, password string) (bool, error) {
\tvar xxxAuth XxxAuth
\terr := db.Select("id").Where(XxxAuth{Username: username, Password: password}).First(&xxxAuth).Error
\tif err != nil && err != gorm.ErrRecordNotFound {
\t\treturn false, err
\t}
\tif xxxAuth.ID > 0 {
\t\treturn true, nil
\t}
\treturn false, nil
}
""",
        "function": "gorm_model_xxx_auth_check",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "models/xxx_auth.go",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # ROUTER
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 5. Gin router setup with JWT middleware group ───────────────────────
    {
        "normalized_code": """\
package routers

import (
\t"github.com/gin-gonic/gin"

\t"project/middleware/jwt"
\t"project/routers/api"
\t"project/routers/api/v1"
)

func InitRouter() *gin.Engine {
\tr := gin.New()
\tr.Use(gin.Logger())
\tr.Use(gin.Recovery())

\tr.POST("/auth", api.GetXxxAuth)
\tr.POST("/upload", api.UploadImage)

\tapiv1 := r.Group("/api/v1")
\tapiv1.Use(jwt.JWT())
\t{
\t\tapiv1.GET("/xxxLabels", v1.GetXxxLabels)
\t\tapiv1.POST("/xxxLabels", v1.AddXxxLabel)
\t\tapiv1.PUT("/xxxLabels/:id", v1.EditXxxLabel)
\t\tapiv1.DELETE("/xxxLabels/:id", v1.DeleteXxxLabel)

\t\tapiv1.GET("/xxxs", v1.GetXxxs)
\t\tapiv1.GET("/xxxs/:id", v1.GetXxx)
\t\tapiv1.POST("/xxxs", v1.AddXxx)
\t\tapiv1.PUT("/xxxs/:id", v1.EditXxx)
\t\tapiv1.DELETE("/xxxs/:id", v1.DeleteXxx)
\t}

\treturn r
}
""",
        "function": "gin_router_setup_jwt_groups",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "routers/router.go",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # HANDLERS
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 6. Get single xxx handler ───────────────────────────────────────────
    {
        "normalized_code": """\
func GetXxx(c *gin.Context) {
\tappG := app.Gin{C: c}
\tid := com.StrTo(c.Param("id")).MustInt()
\tvalid := validation.Validation{}
\tvalid.Min(id, 1, "id")

\tif valid.HasErrors() {
\t\tapp.MarkErrors(valid.Errors)
\t\tappG.Response(http.StatusBadRequest, e.INVALID_PARAMS, nil)
\t\treturn
\t}

\txxxService := xxx_service.Xxx{ID: id}
\texists, err := xxxService.ExistByID()
\tif err != nil {
\t\tappG.Response(http.StatusInternalServerError, e.ERROR_CHECK_EXIST_XXX_FAIL, nil)
\t\treturn
\t}
\tif !exists {
\t\tappG.Response(http.StatusOK, e.ERROR_NOT_EXIST_XXX, nil)
\t\treturn
\t}

\txxx, err := xxxService.Get()
\tif err != nil {
\t\tappG.Response(http.StatusInternalServerError, e.ERROR_GET_XXX_FAIL, nil)
\t\treturn
\t}

\tappG.Response(http.StatusOK, e.SUCCESS, xxx)
}
""",
        "function": "gin_handler_xxx_get",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "routers/api/v1/xxx.go",
    },

    # ── 7. List xxxs with pagination handler ────────────────────────────────
    {
        "normalized_code": """\
func GetXxxs(c *gin.Context) {
\tappG := app.Gin{C: c}
\tvalid := validation.Validation{}

\tstate := -1
\tif arg := c.PostForm("state"); arg != "" {
\t\tstate = com.StrTo(arg).MustInt()
\t\tvalid.Range(state, 0, 1, "state")
\t}

\txxxLabelID := -1
\tif arg := c.PostForm("xxx_label_id"); arg != "" {
\t\txxxLabelID = com.StrTo(arg).MustInt()
\t\tvalid.Min(xxxLabelID, 1, "xxx_label_id")
\t}

\tif valid.HasErrors() {
\t\tapp.MarkErrors(valid.Errors)
\t\tappG.Response(http.StatusBadRequest, e.INVALID_PARAMS, nil)
\t\treturn
\t}

\txxxService := xxx_service.Xxx{
\t\tXxxLabelID: xxxLabelID,
\t\tState:      state,
\t\tPageNum:    util.GetPage(c),
\t\tPageSize:   setting.AppSetting.PageSize,
\t}

\ttotal, err := xxxService.Count()
\tif err != nil {
\t\tappG.Response(http.StatusInternalServerError, e.ERROR_COUNT_XXX_FAIL, nil)
\t\treturn
\t}

\txxxs, err := xxxService.GetAll()
\tif err != nil {
\t\tappG.Response(http.StatusInternalServerError, e.ERROR_GET_XXXS_FAIL, nil)
\t\treturn
\t}

\tdata := make(map[string]interface{})
\tdata["lists"] = xxxs
\tdata["total"] = total

\tappG.Response(http.StatusOK, e.SUCCESS, data)
}
""",
        "function": "gin_handler_xxx_list_paginate",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "routers/api/v1/xxx.go",
    },

    # ── 8. Add xxx handler with form validation ─────────────────────────────
    {
        "normalized_code": """\
type AddXxxForm struct {
\tXxxLabelID    int    `form:"xxx_label_id" valid:"Required;Min(1)"`
\tTitle         string `form:"title" valid:"Required;MaxSize(100)"`
\tDesc          string `form:"desc" valid:"Required;MaxSize(255)"`
\tContent       string `form:"content" valid:"Required;MaxSize(65535)"`
\tCreatedBy     string `form:"created_by" valid:"Required;MaxSize(100)"`
\tCoverImageUrl string `form:"cover_image_url" valid:"Required;MaxSize(255)"`
\tState         int    `form:"state" valid:"Range(0,1)"`
}

func AddXxx(c *gin.Context) {
\tvar (
\t\tappG = app.Gin{C: c}
\t\tform AddXxxForm
\t)

\thttpCode, errCode := app.BindAndValid(c, &form)
\tif errCode != e.SUCCESS {
\t\tappG.Response(httpCode, errCode, nil)
\t\treturn
\t}

\txxxLabelService := xxx_label_service.XxxLabel{ID: form.XxxLabelID}
\texists, err := xxxLabelService.ExistByID()
\tif err != nil {
\t\tappG.Response(http.StatusInternalServerError, e.ERROR_EXIST_XXX_LABEL_FAIL, nil)
\t\treturn
\t}
\tif !exists {
\t\tappG.Response(http.StatusOK, e.ERROR_NOT_EXIST_XXX_LABEL, nil)
\t\treturn
\t}

\txxxService := xxx_service.Xxx{
\t\tXxxLabelID:    form.XxxLabelID,
\t\tTitle:         form.Title,
\t\tDesc:          form.Desc,
\t\tContent:       form.Content,
\t\tCoverImageUrl: form.CoverImageUrl,
\t\tState:         form.State,
\t\tCreatedBy:     form.CreatedBy,
\t}
\tif err := xxxService.Add(); err != nil {
\t\tappG.Response(http.StatusInternalServerError, e.ERROR_ADD_XXX_FAIL, nil)
\t\treturn
\t}

\tappG.Response(http.StatusOK, e.SUCCESS, nil)
}
""",
        "function": "gin_handler_xxx_add_form",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "routers/api/v1/xxx.go",
    },

    # ── 9. Edit xxx handler with form validation ────────────────────────────
    {
        "normalized_code": """\
type EditXxxForm struct {
\tID            int    `form:"id" valid:"Required;Min(1)"`
\tXxxLabelID    int    `form:"xxx_label_id" valid:"Required;Min(1)"`
\tTitle         string `form:"title" valid:"Required;MaxSize(100)"`
\tDesc          string `form:"desc" valid:"Required;MaxSize(255)"`
\tContent       string `form:"content" valid:"Required;MaxSize(65535)"`
\tModifiedBy    string `form:"modified_by" valid:"Required;MaxSize(100)"`
\tCoverImageUrl string `form:"cover_image_url" valid:"Required;MaxSize(255)"`
\tState         int    `form:"state" valid:"Range(0,1)"`
}

func EditXxx(c *gin.Context) {
\tvar (
\t\tappG = app.Gin{C: c}
\t\tform = EditXxxForm{ID: com.StrTo(c.Param("id")).MustInt()}
\t)

\thttpCode, errCode := app.BindAndValid(c, &form)
\tif errCode != e.SUCCESS {
\t\tappG.Response(httpCode, errCode, nil)
\t\treturn
\t}

\txxxService := xxx_service.Xxx{
\t\tID:            form.ID,
\t\tXxxLabelID:    form.XxxLabelID,
\t\tTitle:         form.Title,
\t\tDesc:          form.Desc,
\t\tContent:       form.Content,
\t\tCoverImageUrl: form.CoverImageUrl,
\t\tModifiedBy:    form.ModifiedBy,
\t\tState:         form.State,
\t}
\texists, err := xxxService.ExistByID()
\tif err != nil {
\t\tappG.Response(http.StatusInternalServerError, e.ERROR_CHECK_EXIST_XXX_FAIL, nil)
\t\treturn
\t}
\tif !exists {
\t\tappG.Response(http.StatusOK, e.ERROR_NOT_EXIST_XXX, nil)
\t\treturn
\t}

\txxxLabelService := xxx_label_service.XxxLabel{ID: form.XxxLabelID}
\texists, err = xxxLabelService.ExistByID()
\tif err != nil {
\t\tappG.Response(http.StatusInternalServerError, e.ERROR_EXIST_XXX_LABEL_FAIL, nil)
\t\treturn
\t}
\tif !exists {
\t\tappG.Response(http.StatusOK, e.ERROR_NOT_EXIST_XXX_LABEL, nil)
\t\treturn
\t}

\terr = xxxService.Edit()
\tif err != nil {
\t\tappG.Response(http.StatusInternalServerError, e.ERROR_EDIT_XXX_FAIL, nil)
\t\treturn
\t}

\tappG.Response(http.StatusOK, e.SUCCESS, nil)
}
""",
        "function": "gin_handler_xxx_edit_form",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "routers/api/v1/xxx.go",
    },

    # ── 10. Delete xxx handler ──────────────────────────────────────────────
    {
        "normalized_code": """\
func DeleteXxx(c *gin.Context) {
\tappG := app.Gin{C: c}
\tvalid := validation.Validation{}
\tid := com.StrTo(c.Param("id")).MustInt()
\tvalid.Min(id, 1, "id")

\tif valid.HasErrors() {
\t\tapp.MarkErrors(valid.Errors)
\t\tappG.Response(http.StatusOK, e.INVALID_PARAMS, nil)
\t\treturn
\t}

\txxxService := xxx_service.Xxx{ID: id}
\texists, err := xxxService.ExistByID()
\tif err != nil {
\t\tappG.Response(http.StatusInternalServerError, e.ERROR_CHECK_EXIST_XXX_FAIL, nil)
\t\treturn
\t}
\tif !exists {
\t\tappG.Response(http.StatusOK, e.ERROR_NOT_EXIST_XXX, nil)
\t\treturn
\t}

\terr = xxxService.Delete()
\tif err != nil {
\t\tappG.Response(http.StatusInternalServerError, e.ERROR_DELETE_XXX_FAIL, nil)
\t\treturn
\t}

\tappG.Response(http.StatusOK, e.SUCCESS, nil)
}
""",
        "function": "gin_handler_xxx_delete",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "routers/api/v1/xxx.go",
    },

    # ── 11. XxxLabel handlers — Get + Add ───────────────────────────────────
    {
        "normalized_code": """\
func GetXxxLabels(c *gin.Context) {
\tappG := app.Gin{C: c}
\tname := c.Query("name")
\tstate := -1
\tif arg := c.Query("state"); arg != "" {
\t\tstate = com.StrTo(arg).MustInt()
\t}

\txxxLabelService := xxx_label_service.XxxLabel{
\t\tName:     name,
\t\tState:    state,
\t\tPageNum:  util.GetPage(c),
\t\tPageSize: setting.AppSetting.PageSize,
\t}
\txxxLabels, err := xxxLabelService.GetAll()
\tif err != nil {
\t\tappG.Response(http.StatusInternalServerError, e.ERROR_GET_XXX_LABELS_FAIL, nil)
\t\treturn
\t}

\tcount, err := xxxLabelService.Count()
\tif err != nil {
\t\tappG.Response(http.StatusInternalServerError, e.ERROR_COUNT_XXX_LABEL_FAIL, nil)
\t\treturn
\t}

\tappG.Response(http.StatusOK, e.SUCCESS, map[string]interface{}{
\t\t"lists": xxxLabels,
\t\t"total": count,
\t})
}

type AddXxxLabelForm struct {
\tName      string `form:"name" valid:"Required;MaxSize(100)"`
\tCreatedBy string `form:"created_by" valid:"Required;MaxSize(100)"`
\tState     int    `form:"state" valid:"Range(0,1)"`
}

func AddXxxLabel(c *gin.Context) {
\tvar (
\t\tappG = app.Gin{C: c}
\t\tform AddXxxLabelForm
\t)

\thttpCode, errCode := app.BindAndValid(c, &form)
\tif errCode != e.SUCCESS {
\t\tappG.Response(httpCode, errCode, nil)
\t\treturn
\t}

\txxxLabelService := xxx_label_service.XxxLabel{
\t\tName:      form.Name,
\t\tCreatedBy: form.CreatedBy,
\t\tState:     form.State,
\t}
\texists, err := xxxLabelService.ExistByName()
\tif err != nil {
\t\tappG.Response(http.StatusInternalServerError, e.ERROR_EXIST_XXX_LABEL_FAIL, nil)
\t\treturn
\t}
\tif exists {
\t\tappG.Response(http.StatusOK, e.ERROR_EXIST_XXX_LABEL, nil)
\t\treturn
\t}

\terr = xxxLabelService.Add()
\tif err != nil {
\t\tappG.Response(http.StatusInternalServerError, e.ERROR_ADD_XXX_LABEL_FAIL, nil)
\t\treturn
\t}

\tappG.Response(http.StatusOK, e.SUCCESS, nil)
}
""",
        "function": "gin_handler_xxx_label_get_add",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "routers/api/v1/xxx_label.go",
    },

    # ── 12. XxxLabel handlers — Edit + Delete ───────────────────────────────
    {
        "normalized_code": """\
type EditXxxLabelForm struct {
\tID         int    `form:"id" valid:"Required;Min(1)"`
\tName       string `form:"name" valid:"Required;MaxSize(100)"`
\tModifiedBy string `form:"modified_by" valid:"Required;MaxSize(100)"`
\tState      int    `form:"state" valid:"Range(0,1)"`
}

func EditXxxLabel(c *gin.Context) {
\tvar (
\t\tappG = app.Gin{C: c}
\t\tform = EditXxxLabelForm{ID: com.StrTo(c.Param("id")).MustInt()}
\t)

\thttpCode, errCode := app.BindAndValid(c, &form)
\tif errCode != e.SUCCESS {
\t\tappG.Response(httpCode, errCode, nil)
\t\treturn
\t}

\txxxLabelService := xxx_label_service.XxxLabel{
\t\tID:         form.ID,
\t\tName:       form.Name,
\t\tModifiedBy: form.ModifiedBy,
\t\tState:      form.State,
\t}

\texists, err := xxxLabelService.ExistByID()
\tif err != nil {
\t\tappG.Response(http.StatusInternalServerError, e.ERROR_EXIST_XXX_LABEL_FAIL, nil)
\t\treturn
\t}
\tif !exists {
\t\tappG.Response(http.StatusOK, e.ERROR_NOT_EXIST_XXX_LABEL, nil)
\t\treturn
\t}

\terr = xxxLabelService.Edit()
\tif err != nil {
\t\tappG.Response(http.StatusInternalServerError, e.ERROR_EDIT_XXX_LABEL_FAIL, nil)
\t\treturn
\t}

\tappG.Response(http.StatusOK, e.SUCCESS, nil)
}

func DeleteXxxLabel(c *gin.Context) {
\tappG := app.Gin{C: c}
\tvalid := validation.Validation{}
\tid := com.StrTo(c.Param("id")).MustInt()
\tvalid.Min(id, 1, "id")

\tif valid.HasErrors() {
\t\tapp.MarkErrors(valid.Errors)
\t\tappG.Response(http.StatusBadRequest, e.INVALID_PARAMS, nil)
\t}

\txxxLabelService := xxx_label_service.XxxLabel{ID: id}
\texists, err := xxxLabelService.ExistByID()
\tif err != nil {
\t\tappG.Response(http.StatusInternalServerError, e.ERROR_EXIST_XXX_LABEL_FAIL, nil)
\t\treturn
\t}
\tif !exists {
\t\tappG.Response(http.StatusOK, e.ERROR_NOT_EXIST_XXX_LABEL, nil)
\t\treturn
\t}

\tif err := xxxLabelService.Delete(); err != nil {
\t\tappG.Response(http.StatusInternalServerError, e.ERROR_DELETE_XXX_LABEL_FAIL, nil)
\t\treturn
\t}

\tappG.Response(http.StatusOK, e.SUCCESS, nil)
}
""",
        "function": "gin_handler_xxx_label_edit_delete",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "routers/api/v1/xxx_label.go",
    },

    # ── 13. Auth handler — login and get token ──────────────────────────────
    {
        "normalized_code": """\
type xxxAuthForm struct {
\tUsername string `valid:"Required; MaxSize(50)"`
\tPassword string `valid:"Required; MaxSize(50)"`
}

func GetXxxAuth(c *gin.Context) {
\tappG := app.Gin{C: c}
\tvalid := validation.Validation{}

\tusername := c.PostForm("username")
\tpassword := c.PostForm("password")

\ta := xxxAuthForm{Username: username, Password: password}
\tok, _ := valid.Valid(&a)

\tif !ok {
\t\tapp.MarkErrors(valid.Errors)
\t\tappG.Response(http.StatusBadRequest, e.INVALID_PARAMS, nil)
\t\treturn
\t}

\txxxAuthService := xxx_auth_service.XxxAuth{Username: username, Password: password}
\tisExist, err := xxxAuthService.Check()
\tif err != nil {
\t\tappG.Response(http.StatusInternalServerError, e.ERROR_AUTH_CHECK_TOKEN_FAIL, nil)
\t\treturn
\t}
\tif !isExist {
\t\tappG.Response(http.StatusUnauthorized, e.ERROR_AUTH, nil)
\t\treturn
\t}

\ttoken, err := util.GenerateToken(username, password)
\tif err != nil {
\t\tappG.Response(http.StatusInternalServerError, e.ERROR_AUTH_TOKEN, nil)
\t\treturn
\t}

\tappG.Response(http.StatusOK, e.SUCCESS, map[string]string{
\t\t"token": token,
\t})
}
""",
        "function": "gin_handler_auth_token",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "routers/api/xxx_auth.go",
    },

    # ── 14. File upload handler ─────────────────────────────────────────────
    {
        "normalized_code": """\
func UploadImage(c *gin.Context) {
\tappG := app.Gin{C: c}
\tfile, image, err := c.Request.FormFile("image")
\tif err != nil {
\t\tlogging.Warn(err)
\t\tappG.Response(http.StatusInternalServerError, e.ERROR, nil)
\t\treturn
\t}

\tif image == nil {
\t\tappG.Response(http.StatusBadRequest, e.INVALID_PARAMS, nil)
\t\treturn
\t}

\timageName := upload.GetImageName(image.Filename)
\tfullPath := upload.GetImageFullPath()
\tsavePath := upload.GetImagePath()
\tsrc := fullPath + imageName

\tif !upload.CheckImageExt(imageName) || !upload.CheckImageSize(file) {
\t\tappG.Response(http.StatusBadRequest, e.ERROR_UPLOAD_CHECK_IMAGE_FORMAT, nil)
\t\treturn
\t}

\terr = upload.CheckImage(fullPath)
\tif err != nil {
\t\tlogging.Warn(err)
\t\tappG.Response(http.StatusInternalServerError, e.ERROR_UPLOAD_CHECK_IMAGE_FAIL, nil)
\t\treturn
\t}

\tif err := c.SaveUploadedFile(image, src); err != nil {
\t\tlogging.Warn(err)
\t\tappG.Response(http.StatusInternalServerError, e.ERROR_UPLOAD_SAVE_IMAGE_FAIL, nil)
\t\treturn
\t}

\tappG.Response(http.StatusOK, e.SUCCESS, map[string]string{
\t\t"image_url":      upload.GetImageFullUrl(imageName),
\t\t"image_save_url": savePath + imageName,
\t})
}
""",
        "function": "gin_handler_file_upload",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "routers/api/upload.go",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # MIDDLEWARE
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 15. JWT middleware ──────────────────────────────────────────────────
    {
        "normalized_code": """\
package jwt

import (
\t"net/http"

\t"github.com/dgrijalva/jwt-go"
\t"github.com/gin-gonic/gin"
)

func JWT() gin.HandlerFunc {
\treturn func(c *gin.Context) {
\t\tvar code int
\t\tvar data interface{}

\t\tcode = e.SUCCESS
\t\ttoken := c.Query("token")
\t\tif token == "" {
\t\t\tcode = e.INVALID_PARAMS
\t\t} else {
\t\t\t_, err := util.ParseToken(token)
\t\t\tif err != nil {
\t\t\t\tswitch err.(*jwt.ValidationError).Errors {
\t\t\t\tcase jwt.ValidationErrorExpired:
\t\t\t\t\tcode = e.ERROR_AUTH_CHECK_TOKEN_TIMEOUT
\t\t\t\tdefault:
\t\t\t\t\tcode = e.ERROR_AUTH_CHECK_TOKEN_FAIL
\t\t\t\t}
\t\t\t}
\t\t}

\t\tif code != e.SUCCESS {
\t\t\tc.JSON(http.StatusUnauthorized, gin.H{
\t\t\t\t"code": code,
\t\t\t\t"msg":  e.GetMsg(code),
\t\t\t\t"data": data,
\t\t\t})
\t\t\tc.Abort()
\t\t\treturn
\t\t}

\t\tc.Next()
\t}
}
""",
        "function": "gin_jwt_middleware",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "middleware/jwt/jwt.go",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # SERVICES
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 16. Xxx service with Redis cache ────────────────────────────────────
    {
        "normalized_code": """\
package xxx_service

import (
\t"encoding/json"

\t"project/models"
\t"project/pkg/gredis"
\t"project/pkg/logging"
\t"project/service/cache_service"
)

type Xxx struct {
\tID            int
\tXxxLabelID    int
\tTitle         string
\tDesc          string
\tContent       string
\tCoverImageUrl string
\tState         int
\tCreatedBy     string
\tModifiedBy    string

\tPageNum  int
\tPageSize int
}

func (a *Xxx) Add() error {
\treturn models.AddXxx(map[string]interface{}{
\t\t"xxx_label_id":    a.XxxLabelID,
\t\t"title":           a.Title,
\t\t"desc":            a.Desc,
\t\t"content":         a.Content,
\t\t"created_by":      a.CreatedBy,
\t\t"cover_image_url": a.CoverImageUrl,
\t\t"state":           a.State,
\t})
}

func (a *Xxx) Edit() error {
\treturn models.EditXxx(a.ID, map[string]interface{}{
\t\t"xxx_label_id":    a.XxxLabelID,
\t\t"title":           a.Title,
\t\t"desc":            a.Desc,
\t\t"content":         a.Content,
\t\t"cover_image_url": a.CoverImageUrl,
\t\t"state":           a.State,
\t\t"modified_by":     a.ModifiedBy,
\t})
}

func (a *Xxx) Get() (*models.Xxx, error) {
\tvar cacheXxx *models.Xxx
\tcache := cache_service.Xxx{ID: a.ID}
\tkey := cache.GetXxxKey()
\tif gredis.Exists(key) {
\t\tdata, err := gredis.Get(key)
\t\tif err != nil {
\t\t\tlogging.Info(err)
\t\t} else {
\t\t\tjson.Unmarshal(data, &cacheXxx)
\t\t\treturn cacheXxx, nil
\t\t}
\t}
\txxx, err := models.GetXxx(a.ID)
\tif err != nil {
\t\treturn nil, err
\t}
\tgredis.Set(key, xxx, 3600)
\treturn xxx, nil
}

func (a *Xxx) GetAll() ([]*models.Xxx, error) {
\tvar xxxs, cacheXxxs []*models.Xxx
\tcache := cache_service.Xxx{
\t\tXxxLabelID: a.XxxLabelID,
\t\tState:      a.State,
\t\tPageNum:    a.PageNum,
\t\tPageSize:   a.PageSize,
\t}
\tkey := cache.GetXxxsKey()
\tif gredis.Exists(key) {
\t\tdata, err := gredis.Get(key)
\t\tif err != nil {
\t\t\tlogging.Info(err)
\t\t} else {
\t\t\tjson.Unmarshal(data, &cacheXxxs)
\t\t\treturn cacheXxxs, nil
\t\t}
\t}
\txxxs, err := models.GetXxxs(a.PageNum, a.PageSize, a.getMaps())
\tif err != nil {
\t\treturn nil, err
\t}
\tgredis.Set(key, xxxs, 3600)
\treturn xxxs, nil
}

func (a *Xxx) Delete() error {
\treturn models.DeleteXxx(a.ID)
}

func (a *Xxx) ExistByID() (bool, error) {
\treturn models.ExistXxxByID(a.ID)
}

func (a *Xxx) Count() (int, error) {
\treturn models.GetXxxTotal(a.getMaps())
}

func (a *Xxx) getMaps() map[string]interface{} {
\tmaps := make(map[string]interface{})
\tmaps["deleted_on"] = 0
\tif a.State != -1 {
\t\tmaps["state"] = a.State
\t}
\tif a.XxxLabelID != -1 {
\t\tmaps["xxx_label_id"] = a.XxxLabelID
\t}
\treturn maps
}
""",
        "function": "service_xxx_crud_redis_cache",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "service/xxx_service/xxx.go",
    },

    # ── 17. XxxLabel service with Redis cache ───────────────────────────────
    {
        "normalized_code": """\
package xxx_label_service

import (
\t"encoding/json"

\t"project/models"
\t"project/pkg/gredis"
\t"project/pkg/logging"
\t"project/service/cache_service"
)

type XxxLabel struct {
\tID         int
\tName       string
\tCreatedBy  string
\tModifiedBy string
\tState      int

\tPageNum  int
\tPageSize int
}

func (t *XxxLabel) ExistByName() (bool, error) {
\treturn models.ExistXxxLabelByName(t.Name)
}

func (t *XxxLabel) ExistByID() (bool, error) {
\treturn models.ExistXxxLabelByID(t.ID)
}

func (t *XxxLabel) Add() error {
\treturn models.AddXxxLabel(t.Name, t.State, t.CreatedBy)
}

func (t *XxxLabel) Edit() error {
\tdata := make(map[string]interface{})
\tdata["modified_by"] = t.ModifiedBy
\tdata["name"] = t.Name
\tif t.State >= 0 {
\t\tdata["state"] = t.State
\t}
\treturn models.EditXxxLabel(t.ID, data)
}

func (t *XxxLabel) Delete() error {
\treturn models.DeleteXxxLabel(t.ID)
}

func (t *XxxLabel) Count() (int, error) {
\treturn models.GetXxxLabelTotal(t.getMaps())
}

func (t *XxxLabel) GetAll() ([]models.XxxLabel, error) {
\tvar xxxLabels, cacheXxxLabels []models.XxxLabel
\tcache := cache_service.XxxLabel{
\t\tState:    t.State,
\t\tPageNum:  t.PageNum,
\t\tPageSize: t.PageSize,
\t}
\tkey := cache.GetXxxLabelsKey()
\tif gredis.Exists(key) {
\t\tdata, err := gredis.Get(key)
\t\tif err != nil {
\t\t\tlogging.Info(err)
\t\t} else {
\t\t\tjson.Unmarshal(data, &cacheXxxLabels)
\t\t\treturn cacheXxxLabels, nil
\t\t}
\t}
\txxxLabels, err := models.GetXxxLabels(t.PageNum, t.PageSize, t.getMaps())
\tif err != nil {
\t\treturn nil, err
\t}
\tgredis.Set(key, xxxLabels, 3600)
\treturn xxxLabels, nil
}

func (t *XxxLabel) getMaps() map[string]interface{} {
\tmaps := make(map[string]interface{})
\tmaps["deleted_on"] = 0
\tif t.Name != "" {
\t\tmaps["name"] = t.Name
\t}
\tif t.State >= 0 {
\t\tmaps["state"] = t.State
\t}
\treturn maps
}
""",
        "function": "service_xxx_label_crud_redis",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "service/xxx_label_service/xxx_label.go",
    },

    # ── 18. XxxAuth service ─────────────────────────────────────────────────
    {
        "normalized_code": """\
package xxx_auth_service

import "project/models"

type XxxAuth struct {
\tUsername string
\tPassword string
}

func (a *XxxAuth) Check() (bool, error) {
\treturn models.CheckXxxAuth(a.Username, a.Password)
}
""",
        "function": "service_xxx_auth_check",
        "feature_type": "crud",
        "file_role": "crud",
        "file_path": "service/xxx_auth_service/xxx_auth.go",
    },

    # ── 19. Cache key generation pattern ────────────────────────────────────
    {
        "normalized_code": """\
package cache_service

import (
\t"strconv"
\t"strings"
)

type Xxx struct {
\tID         int
\tXxxLabelID int
\tState      int
\tPageNum    int
\tPageSize   int
}

func (a *Xxx) GetXxxKey() string {
\treturn "CACHE_XXX_" + strconv.Itoa(a.ID)
}

func (a *Xxx) GetXxxsKey() string {
\tkeys := []string{"CACHE_XXX", "LIST"}
\tif a.ID > 0 {
\t\tkeys = append(keys, strconv.Itoa(a.ID))
\t}
\tif a.XxxLabelID > 0 {
\t\tkeys = append(keys, strconv.Itoa(a.XxxLabelID))
\t}
\tif a.State >= 0 {
\t\tkeys = append(keys, strconv.Itoa(a.State))
\t}
\tif a.PageNum > 0 {
\t\tkeys = append(keys, strconv.Itoa(a.PageNum))
\t}
\tif a.PageSize > 0 {
\t\tkeys = append(keys, strconv.Itoa(a.PageSize))
\t}
\treturn strings.Join(keys, "_")
}

type XxxLabel struct {
\tID       int
\tName     string
\tState    int
\tPageNum  int
\tPageSize int
}

func (t *XxxLabel) GetXxxLabelsKey() string {
\tkeys := []string{"CACHE_XXX_LABEL", "LIST"}
\tif t.Name != "" {
\t\tkeys = append(keys, t.Name)
\t}
\tif t.State >= 0 {
\t\tkeys = append(keys, strconv.Itoa(t.State))
\t}
\tif t.PageNum > 0 {
\t\tkeys = append(keys, strconv.Itoa(t.PageNum))
\t}
\tif t.PageSize > 0 {
\t\tkeys = append(keys, strconv.Itoa(t.PageSize))
\t}
\treturn strings.Join(keys, "_")
}
""",
        "function": "cache_key_generation_pattern",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "service/cache_service/cache.go",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # UTILITIES
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 20. Response helper + BindAndValid ──────────────────────────────────
    {
        "normalized_code": """\
package app

import (
\t"net/http"

\t"github.com/astaxie/beego/validation"
\t"github.com/gin-gonic/gin"
)

type Gin struct {
\tC *gin.Context
}

type Response struct {
\tCode int         `json:"code"`
\tMsg  string      `json:"msg"`
\tData interface{} `json:"data"`
}

func (g *Gin) Response(httpCode, errCode int, data interface{}) {
\tg.C.JSON(httpCode, Response{
\t\tCode: errCode,
\t\tMsg:  GetMsg(errCode),
\t\tData: data,
\t})
}

func BindAndValid(c *gin.Context, form interface{}) (int, int) {
\terr := c.Bind(form)
\tif err != nil {
\t\treturn http.StatusBadRequest, INVALID_PARAMS
\t}
\tvalid := validation.Validation{}
\tcheck, err := valid.Valid(form)
\tif err != nil {
\t\treturn http.StatusInternalServerError, ERROR
\t}
\tif !check {
\t\tMarkErrors(valid.Errors)
\t\treturn http.StatusBadRequest, INVALID_PARAMS
\t}
\treturn http.StatusOK, SUCCESS
}
""",
        "function": "gin_response_bind_valid",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "pkg/app/response.go",
    },

    # ── 21. Error codes + messages ──────────────────────────────────────────
    {
        "normalized_code": """\
package e

const (
\tSUCCESS        = 200
\tERROR          = 500
\tINVALID_PARAMS = 400

\tERROR_EXIST_XXX_LABEL       = 10001
\tERROR_EXIST_XXX_LABEL_FAIL  = 10002
\tERROR_NOT_EXIST_XXX_LABEL   = 10003
\tERROR_GET_XXX_LABELS_FAIL   = 10004
\tERROR_COUNT_XXX_LABEL_FAIL  = 10005
\tERROR_ADD_XXX_LABEL_FAIL    = 10006
\tERROR_EDIT_XXX_LABEL_FAIL   = 10007
\tERROR_DELETE_XXX_LABEL_FAIL = 10008

\tERROR_NOT_EXIST_XXX        = 10011
\tERROR_CHECK_EXIST_XXX_FAIL = 10012
\tERROR_ADD_XXX_FAIL         = 10013
\tERROR_DELETE_XXX_FAIL      = 10014
\tERROR_EDIT_XXX_FAIL        = 10015
\tERROR_COUNT_XXX_FAIL       = 10016
\tERROR_GET_XXXS_FAIL        = 10017
\tERROR_GET_XXX_FAIL         = 10018

\tERROR_AUTH_CHECK_TOKEN_FAIL    = 20001
\tERROR_AUTH_CHECK_TOKEN_TIMEOUT = 20002
\tERROR_AUTH_TOKEN               = 20003
\tERROR_AUTH                     = 20004

\tERROR_UPLOAD_SAVE_IMAGE_FAIL    = 30001
\tERROR_UPLOAD_CHECK_IMAGE_FAIL   = 30002
\tERROR_UPLOAD_CHECK_IMAGE_FORMAT = 30003
)

var MsgFlags = map[int]string{
\tSUCCESS:                         "ok",
\tERROR:                           "fail",
\tINVALID_PARAMS:                  "invalid params",
\tERROR_EXIST_XXX_LABEL:           "xxx label name already exists",
\tERROR_EXIST_XXX_LABEL_FAIL:      "check xxx label existence failed",
\tERROR_NOT_EXIST_XXX_LABEL:       "xxx label does not exist",
\tERROR_GET_XXX_LABELS_FAIL:       "get xxx labels failed",
\tERROR_COUNT_XXX_LABEL_FAIL:      "count xxx labels failed",
\tERROR_ADD_XXX_LABEL_FAIL:        "add xxx label failed",
\tERROR_EDIT_XXX_LABEL_FAIL:       "edit xxx label failed",
\tERROR_DELETE_XXX_LABEL_FAIL:     "delete xxx label failed",
\tERROR_NOT_EXIST_XXX:             "xxx does not exist",
\tERROR_ADD_XXX_FAIL:              "add xxx failed",
\tERROR_DELETE_XXX_FAIL:           "delete xxx failed",
\tERROR_CHECK_EXIST_XXX_FAIL:      "check xxx existence failed",
\tERROR_EDIT_XXX_FAIL:             "edit xxx failed",
\tERROR_COUNT_XXX_FAIL:            "count xxxs failed",
\tERROR_GET_XXXS_FAIL:             "get xxxs failed",
\tERROR_GET_XXX_FAIL:              "get xxx failed",
\tERROR_AUTH_CHECK_TOKEN_FAIL:      "token auth failed",
\tERROR_AUTH_CHECK_TOKEN_TIMEOUT:   "token expired",
\tERROR_AUTH_TOKEN:                 "token generation failed",
\tERROR_AUTH:                       "invalid token",
\tERROR_UPLOAD_SAVE_IMAGE_FAIL:     "save image failed",
\tERROR_UPLOAD_CHECK_IMAGE_FAIL:    "check image failed",
\tERROR_UPLOAD_CHECK_IMAGE_FORMAT:  "image format or size invalid",
}

func GetMsg(code int) string {
\tmsg, ok := MsgFlags[code]
\tif ok {
\t\treturn msg
\t}
\treturn MsgFlags[ERROR]
}
""",
        "function": "error_codes_messages_mapping",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "pkg/e/code.go",
    },

    # ── 22. JWT generate + parse ────────────────────────────────────────────
    {
        "normalized_code": """\
package util

import (
\t"time"

\t"github.com/dgrijalva/jwt-go"
)

var jwtSecret []byte

type Claims struct {
\tUsername string `json:"username"`
\tPassword string `json:"password"`
\tjwt.StandardClaims
}

func GenerateToken(username, password string) (string, error) {
\tnowTime := time.Now()
\texpireTime := nowTime.Add(3 * time.Hour)

\tclaims := Claims{
\t\tEncodeMD5(username),
\t\tEncodeMD5(password),
\t\tjwt.StandardClaims{
\t\t\tExpiresAt: expireTime.Unix(),
\t\t\tIssuer:    "gin-api",
\t\t},
\t}

\ttokenClaims := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
\treturn tokenClaims.SignedString(jwtSecret)
}

func ParseToken(token string) (*Claims, error) {
\ttokenClaims, err := jwt.ParseWithClaims(token, &Claims{}, func(token *jwt.Token) (interface{}, error) {
\t\treturn jwtSecret, nil
\t})

\tif tokenClaims != nil {
\t\tif claims, ok := tokenClaims.Claims.(*Claims); ok && tokenClaims.Valid {
\t\t\treturn claims, nil
\t\t}
\t}

\treturn nil, err
}
""",
        "function": "jwt_generate_parse_claims",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "pkg/util/jwt.go",
    },

    # ── 23. Pagination utility ──────────────────────────────────────────────
    {
        "normalized_code": """\
package util

import (
\t"github.com/unknwon/com"
\t"github.com/gin-gonic/gin"
)

func GetPage(c *gin.Context) int {
\tresult := 0
\tpage := com.StrTo(c.Query("page")).MustInt()
\tif page > 0 {
\t\tresult = (page - 1) * cfg.PageSize
\t}
\treturn result
}
""",
        "function": "pagination_get_page",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "pkg/util/pagination.go",
    },

    # ── 24. Redis connection pool + CRUD ────────────────────────────────────
    {
        "normalized_code": """\
package gredis

import (
\t"encoding/json"
\t"time"

\t"github.com/gomodule/redigo/redis"
)

var RedisConn *redis.Pool

func Setup(host, password string, maxIdle, maxActive int, idleTimeout time.Duration) error {
\tRedisConn = &redis.Pool{
\t\tMaxIdle:     maxIdle,
\t\tMaxActive:   maxActive,
\t\tIdleTimeout: idleTimeout,
\t\tDial: func() (redis.Conn, error) {
\t\t\tc, err := redis.Dial("tcp", host)
\t\t\tif err != nil {
\t\t\t\treturn nil, err
\t\t\t}
\t\t\tif password != "" {
\t\t\t\tif _, err := c.Do("AUTH", password); err != nil {
\t\t\t\t\tc.Close()
\t\t\t\t\treturn nil, err
\t\t\t\t}
\t\t\t}
\t\t\treturn c, err
\t\t},
\t\tTestOnBorrow: func(c redis.Conn, t time.Time) error {
\t\t\t_, err := c.Do("PING")
\t\t\treturn err
\t\t},
\t}
\treturn nil
}

func Set(key string, data interface{}, ttl int) error {
\tconn := RedisConn.Get()
\tdefer conn.Close()
\tvalue, err := json.Marshal(data)
\tif err != nil {
\t\treturn err
\t}
\t_, err = conn.Do("SET", key, value)
\tif err != nil {
\t\treturn err
\t}
\t_, err = conn.Do("EXPIRE", key, ttl)
\treturn err
}

func Exists(key string) bool {
\tconn := RedisConn.Get()
\tdefer conn.Close()
\texists, err := redis.Bool(conn.Do("EXISTS", key))
\tif err != nil {
\t\treturn false
\t}
\treturn exists
}

func Get(key string) ([]byte, error) {
\tconn := RedisConn.Get()
\tdefer conn.Close()
\treturn redis.Bytes(conn.Do("GET", key))
}

func Delete(key string) (bool, error) {
\tconn := RedisConn.Get()
\tdefer conn.Close()
\treturn redis.Bool(conn.Do("DEL", key))
}

func LikeDeletes(key string) error {
\tconn := RedisConn.Get()
\tdefer conn.Close()
\tkeys, err := redis.Strings(conn.Do("KEYS", "*"+key+"*"))
\tif err != nil {
\t\treturn err
\t}
\tfor _, k := range keys {
\t\t_, err = Delete(k)
\t\tif err != nil {
\t\t\treturn err
\t\t}
\t}
\treturn nil
}
""",
        "function": "redis_pool_crud",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "pkg/gredis/redis.go",
    },

    # ── 25. Config INI settings ─────────────────────────────────────────────
    {
        "normalized_code": """\
package setting

import (
\t"log"
\t"time"

\t"github.com/go-ini/ini"
)

type App struct {
\tJwtSecret      string
\tPageSize       int
\tPrefixUrl      string
\tRuntimeRootPath string
\tImageSavePath  string
\tImageMaxSize   int
\tImageAllowExts []string
\tLogSavePath    string
\tLogSaveName    string
\tLogFileExt     string
\tTimeFormat     string
}

var AppSetting = &App{}

type Server struct {
\tRunMode      string
\tHttpPort     int
\tReadTimeout  time.Duration
\tWriteTimeout time.Duration
}

var ServerSetting = &Server{}

type Database struct {
\tType        string
\tHost        string
\tName        string
\tTablePrefix string
}

var DatabaseSetting = &Database{}

type Redis struct {
\tHost        string
\tPassword    string
\tMaxIdle     int
\tMaxActive   int
\tIdleTimeout time.Duration
}

var RedisSetting = &Redis{}

var cfg *ini.File

func Setup() {
\tvar err error
\tcfg, err = ini.Load("conf/app.ini")
\tif err != nil {
\t\tlog.Fatalf("setting.Setup, fail to parse config: %v", err)
\t}
\tmapTo("app", AppSetting)
\tmapTo("server", ServerSetting)
\tmapTo("database", DatabaseSetting)
\tmapTo("redis", RedisSetting)
\tAppSetting.ImageMaxSize = AppSetting.ImageMaxSize * 1024 * 1024
\tServerSetting.ReadTimeout = ServerSetting.ReadTimeout * time.Second
\tServerSetting.WriteTimeout = ServerSetting.WriteTimeout * time.Second
\tRedisSetting.IdleTimeout = RedisSetting.IdleTimeout * time.Second
}

func mapTo(section string, v interface{}) {
\terr := cfg.Section(section).MapTo(v)
\tif err != nil {
\t\tlog.Fatalf("Cfg.MapTo %s err: %v", section, err)
\t}
}
""",
        "function": "config_ini_typed_structs",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "pkg/setting/setting.go",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "GORM base model with soft delete callbacks and timestamps",
    "GORM entity model with foreign key and CRUD operations",
    "Gin router setup with JWT middleware group",
    "Gin handler get single entity by ID with validation",
    "Gin handler list entities with pagination offset limit",
    "Gin handler add entity with form struct validation",
    "Gin auth handler login and generate JWT token",
    "Gin JWT middleware parse and validate token",
    "Go service layer with Redis cache get set pattern",
    "Redis connection pool setup with Set Get Exists Delete",
    "Go INI config parsing with typed structs and sections",
    "Error codes constants and code to message mapping",
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
