"""
ingest_compose.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de docker/compose dans la KB Qdrant V6.

Focus : CORE patterns container orchestration (Service model, dependency graph,
container lifecycle, network/volume management, port binding, healthcheck,
restart policy, environment interpolation, build context, project loading).

PAS de patterns API HTTP — patterns du domaine Docker Compose.

Usage:
    .venv/bin/python3 ingest_compose.py
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
REPO_URL = "https://github.com/docker/compose.git"
REPO_NAME = "docker/compose"
REPO_LOCAL = "/tmp/compose"
LANGUAGE = "go"
FRAMEWORK = "generic"
STACK = "go+docker+compose+containers"
CHARTE_VERSION = "1.0"
TAG = "docker/compose"
SOURCE_REPO = "https://github.com/docker/compose"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# Docker Compose = container orchestration via YAML spec parsing + Docker daemon API.
# Patterns CORE : Service model parsing, dependency resolution, container lifecycle,
# network/volume creation, port binding, healthcheck, restart policy, env interpolation,
# build context, project loading.
# U-5 : service→xxx, network→yyy, volume→zzz, container→element, project→proj,
#       build→construction, port→gateway, restart→reactivate, healthcheck→liveliness.
# KEEP : Service, Container, Network, Volume, Port, Build, Project, Compose, Docker,
#        healthcheck, restart, replicas, depends_on, context, image.

PATTERNS: list[dict] = [
    # ── 1. Service model definition + metadata parsing ────────────────────────────
    {
        "normalized_code": """\
package types

import "github.com/compose-spec/compose-go/v2/types"

// Xxx represents a Compose service definition
type Xxx struct {
    Name            string
    Image           string
    Build           *Construction
    Container       *element
    Environment     map[string]string
    Ports           []gateway
    Volumes         []*Volume
    Networks        map[string]*network
    DependsOn       map[string]DependencyConfig
    Restart         RestartPolicy
    Healthcheck     *HealthcheckConfig
    Labels          map[string]string
    Scale           int
    Replicas        int
}

// Load unmarshals Service from parsed YAML types.Service
func (s *Xxx) Load(spec *types.Service) error {
    s.Name = spec.Name
    s.Image = spec.Image
    s.Labels = spec.Labels
    s.Environment = spec.Environment
    s.DependsOn = spec.DependsOn
    if spec.Build != nil {
        s.Build = &Construction{}
        s.Build.Load(spec.Build)
    }
    if spec.HealthCheck != nil {
        s.Healthcheck = &HealthcheckConfig{}
        s.Healthcheck.Load(spec.HealthCheck)
    }
    return nil
}
""",
        "function": "service_model_definition_parse",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "pkg/compose/model.go",
    },
    # ── 2. Dependency graph construction (DAG) ────────────────────────────────────
    {
        "normalized_code": """\
package compose

import (
    "fmt"
    "sync"

    "github.com/compose-spec/compose-go/v2/types"
)

// Graph is a directed acyclic graph of Service dependencies
type Graph struct {
    Vertices map[string]*Vertex
    mu       sync.RWMutex
}

// Vertex represents a Service node in the graph
type Vertex struct {
    Service string
    Parents []*Vertex
    Children []*Vertex
    Status  ServiceStatus
}

// NewGraph builds a DAG from Service depends_on directives
func NewGraph(proj *types.Project, initialStatus ServiceStatus) (*Graph, error) {
    g := &Graph{
        Vertices: make(map[string]*Vertex),
    }

    // Create vertices for all services
    for _, svc := range proj.Services {
        g.Vertices[svc.Name] = &Vertex{
            Service: svc.Name,
            Status:  initialStatus,
        }
    }

    // Wire dependencies: if svc A depends_on B, B is parent of A
    for _, svc := range proj.Services {
        vertex := g.Vertices[svc.Name]
        for depName := range svc.DependsOn {
            if parent, ok := g.Vertices[depName]; ok {
                vertex.Parents = append(vertex.Parents, parent)
                parent.Children = append(parent.Children, vertex)
            }
        }
    }

    return g, nil
}

// GetAncestors returns all transitive parents of a Vertex
func GetAncestors(v *Vertex) []*Vertex {
    var ancestors []*Vertex
    var visit func(*Vertex)
    visited := make(map[string]bool)
    visit = func(node *Vertex) {
        if visited[node.Service] {
            return
        }
        visited[node.Service] = true
        ancestors = append(ancestors, node)
        for _, parent := range node.Parents {
            visit(parent)
        }
    }
    for _, parent := range v.Parents {
        visit(parent)
    }
    return ancestors
}
""",
        "function": "dependency_graph_dag_construction",
        "feature_type": "model",
        "file_role": "utility",
        "file_path": "pkg/compose/dependencies.go",
    },
    # ── 3. Container lifecycle: create, start, stop, remove ─────────────────────
    {
        "normalized_code": """\
package compose

import (
    "context"

    "github.com/moby/moby/api/types/container"
)

// ContainerOp represents a container lifecycle operation
type ContainerOp struct {
    Name      string
    Operation string // "create", "start", "stop", "rm"
    Config    *container.Config
    HostConfig *container.HostConfig
}

// Create instantiates a container from Service config (does not start)
func (c *Container) Create(ctx context.Context) error {
    resp, err := c.daemon.ContainerCreate(
        ctx,
        c.Config,
        c.HostConfig,
        c.NetworkConfig,
        nil,
        c.Name,
    )
    if err != nil {
        return err
    }
    c.ID = resp.ID
    return nil
}

// Start runs a created container (idempotent)
func (c *Container) Start(ctx context.Context) error {
    return c.daemon.ContainerStart(ctx, c.ID, container.StartOptions{})
}

// Stop terminates a running container gracefully
func (c *Container) Stop(ctx context.Context, timeoutSeconds int) error {
    timeout := int(timeoutSeconds)
    return c.daemon.ContainerStop(ctx, c.ID, container.StopOptions{Timeout: &timeout})
}

// Remove deletes a container (force if running)
func (c *Container) Remove(ctx context.Context, force bool) error {
    return c.daemon.ContainerRemove(ctx, c.ID, container.RemoveOptions{Force: force})
}
""",
        "function": "container_lifecycle_create_start_stop_rm",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "pkg/compose/containers.go",
    },
    # ── 4. Network creation + service discovery via aliases ─────────────────────
    {
        "normalized_code": """\
package compose

import (
    "context"

    "github.com/moby/moby/api/types/network"
)

// NetworkConfig wraps Docker network creation options
type NetworkConfig struct {
    Name    string
    Driver  string
    Labels  map[string]string
    Options map[string]string
}

// CreateNetwork creates a custom bridge network for service discovery
func (s *composeService) CreateNetwork(ctx context.Context, cfg *NetworkConfig) (string, error) {
    resp, err := s.daemon.NetworkCreate(ctx, cfg.Name, network.CreateOptions{
        Driver: cfg.Driver,
        Labels: cfg.Labels,
        Options: cfg.Options,
    })
    if err != nil {
        return "", err
    }
    return resp.ID, nil
}

// AttachToNetwork connects a Container to a network with DNS alias
func (s *composeService) AttachToNetwork(
    ctx context.Context,
    containerID string,
    networkID string,
    serviceAlias string,
) error {
    return s.daemon.NetworkConnect(ctx, networkID, containerID, &network.EndpointSettings{
        Aliases: []string{serviceAlias},
    })
}

// RemoveNetwork deletes a network and all attached containers
func (s *composeService) RemoveNetwork(ctx context.Context, networkID string) error {
    return s.daemon.NetworkRemove(ctx, networkID)
}
""",
        "function": "network_creation_service_discovery_aliases",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "pkg/compose/convergence.go",
    },
    # ── 5. Volume management: creation, mounting, cleanup ───────────────────────
    {
        "normalized_code": """\
package compose

import (
    "context"

    "github.com/moby/moby/api/types/volume"
)

// VolumeConfig specifies volume creation parameters
type VolumeConfig struct {
    Name    string
    Driver  string
    Labels  map[string]string
    Options map[string]string
}

// EnsureVolume creates a volume if it does not exist
func (s *composeService) EnsureVolume(ctx context.Context, cfg *VolumeConfig) (string, error) {
    resp, err := s.daemon.VolumeCreate(ctx, volume.CreateOptions{
        Name:   cfg.Name,
        Driver: cfg.Driver,
        Labels: cfg.Labels,
        Options: cfg.Options,
    })
    if err != nil {
        return "", err
    }
    return resp.Name, nil
}

// MountVolume attaches a volume to a Container at a mount point
func (c *Container) MountVolume(volumeName string, containerPath string, readOnly bool) {
    // Add to HostConfig.Mounts slice
    mode := "rw"
    if readOnly {
        mode = "ro"
    }
    mount := &mount.Mount{
        Type:     mount.TypeVolume,
        Source:   volumeName,
        Target:   containerPath,
        ReadOnly: readOnly,
    }
    c.HostConfig.Mounts = append(c.HostConfig.Mounts, mount)
}

// RemoveVolume deletes a volume (no-op if not found)
func (s *composeService) RemoveVolume(ctx context.Context, volumeName string) error {
    return s.daemon.VolumeRemove(ctx, volumeName, false)
}
""",
        "function": "volume_creation_mounting_cleanup",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "pkg/compose/convergence.go",
    },
    # ── 6. Port binding (host:container, protocol) ────────────────────────────────
    {
        "normalized_code": """\
package compose

import (
    "fmt"
    "strconv"
    "strings"

    "github.com/moby/moby/api/types/nat"
)

// PortBinding maps container port to host address:port
type PortBinding struct {
    ContainerPort uint16
    HostPort      uint16
    HostIP        string
    Protocol      string // "tcp" or "udp"
}

// ToNATPort converts to Docker API PortBinding format
func (pb *PortBinding) ToNATPort() (nat.Port, nat.PortBinding) {
    port := nat.Port(fmt.Sprintf("%d/%s", pb.ContainerPort, pb.Protocol))
    binding := nat.PortBinding{
        HostIP:   pb.HostIP,
        HostPort: strconv.Itoa(int(pb.HostPort)),
    }
    return port, binding
}

// ParsePortString parses "8080:80/tcp" → PortBinding
func ParsePortString(spec string) (*PortBinding, error) {
    parts := strings.Split(spec, "/")
    proto := "tcp"
    if len(parts) == 2 {
        proto = parts[1]
    }
    portParts := strings.Split(parts[0], ":")
    if len(portParts) == 2 {
        hostPort, _ := strconv.Atoi(portParts[0])
        containerPort, _ := strconv.Atoi(portParts[1])
        return &PortBinding{
            HostPort:      uint16(hostPort),
            ContainerPort: uint16(containerPort),
            Protocol:      proto,
        }, nil
    }
    return nil, fmt.Errorf("invalid port spec: %s", spec)
}

// ApplyPortBindings configures HostConfig.PortBindings
func (c *Container) ApplyPortBindings(bindings []*PortBinding) {
    c.HostConfig.PortBindings = nat.PortMap{}
    for _, pb := range bindings {
        port, binding := pb.ToNATPort()
        c.HostConfig.PortBindings[port] = []nat.PortBinding{binding}
    }
}
""",
        "function": "port_binding_host_container_protocol",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "pkg/compose/create.go",
    },
    # ── 7. Healthcheck: start_period, interval, timeout, retries ────────────────
    {
        "normalized_code": """\
package compose

import (
    "time"

    "github.com/moby/moby/api/types/container"
)

// HealthcheckConfig specifies container liveliness probe
type HealthcheckConfig struct {
    Test        []string
    Interval    time.Duration
    Timeout     time.Duration
    StartPeriod time.Duration
    Retries     int
    Disable     bool
}

// ToDockerHealthcheck converts to Docker API format
func (hc *HealthcheckConfig) ToDockerHealthcheck() *container.HealthConfig {
    if hc.Disable {
        return &container.HealthConfig{Test: []string{"NONE"}}
    }
    return &container.HealthConfig{
        Test:        hc.Test,
        Interval:    hc.Interval,
        Timeout:     hc.Timeout,
        StartPeriod: hc.StartPeriod,
        Retries:     hc.Retries,
    }
}

// FromComposeHealthcheck converts Compose spec to internal format
func (hc *HealthcheckConfig) FromComposeHealthcheck(spec *types.HealthCheckConfig) {
    if spec == nil {
        return
    }
    hc.Test = spec.Test
    hc.Interval = time.Duration(spec.Interval)
    hc.Timeout = time.Duration(spec.Timeout)
    hc.StartPeriod = time.Duration(spec.StartPeriod)
    hc.Retries = spec.Retries
    hc.Disable = spec.Disable
}
""",
        "function": "healthcheck_liveliness_probe_config",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "pkg/compose/create.go",
    },
    # ── 8. Restart policy: no/always/on-failure/unless-stopped ──────────────────
    {
        "normalized_code": """\
package compose

import "github.com/moby/moby/api/types/container"

// RestartPolicy defines container reactivation behavior
type RestartPolicy struct {
    Name              string // "no", "always", "on-failure", "unless-stopped"
    MaximumRetryCount int    // for "on-failure" policy
}

// ToDockerRestartPolicy converts to Docker API format
func (rp *RestartPolicy) ToDockerRestartPolicy() container.RestartPolicy {
    return container.RestartPolicy{
        Name:              rp.Name,
        MaximumRetryCount: rp.MaximumRetryCount,
    }
}

// ApplyRestartPolicy sets the Container restart behavior
func (c *Container) ApplyRestartPolicy(rp *RestartPolicy) {
    c.HostConfig.RestartPolicy = rp.ToDockerRestartPolicy()
}

// DefaultRestartPolicy returns "no" policy (disabled)
func DefaultRestartPolicy() *RestartPolicy {
    return &RestartPolicy{Name: "no", MaximumRetryCount: 0}
}

// AlwaysRestartPolicy returns "always" policy (reactivate on exit)
func AlwaysRestartPolicy() *RestartPolicy {
    return &RestartPolicy{Name: "always", MaximumRetryCount: 0}
}

// OnFailureRestartPolicy returns "on-failure" with max retries
func OnFailureRestartPolicy(maxRetries int) *RestartPolicy {
    return &RestartPolicy{Name: "on-failure", MaximumRetryCount: maxRetries}
}
""",
        "function": "restart_policy_reactivation_behavior",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "pkg/compose/create.go",
    },
    # ── 9. Environment variable interpolation from .env files ───────────────────
    {
        "normalized_code": """\
package compose

import (
    "os"
    "regexp"
    "strings"
)

// EnvResolver handles ${VAR} and $VAR substitution in Compose files
type EnvResolver struct {
    vars map[string]string
}

// NewEnvResolver loads variables from .env files and os.Environ()
func NewEnvResolver(envFilePaths []string) (*EnvResolver, error) {
    vars := make(map[string]string)

    // Load from files first (lowest priority)
    for _, path := range envFilePaths {
        content, _ := os.ReadFile(path)
        parseEnvFile(string(content), vars)
    }

    // Override with os.Environ() (highest priority)
    for _, pair := range os.Environ() {
        parts := strings.SplitN(pair, "=", 2)
        if len(parts) == 2 {
            vars[parts[0]] = parts[1]
        }
    }

    return &EnvResolver{vars: vars}, nil
}

// Resolve substitutes ${VAR} and $VAR patterns in a string
func (er *EnvResolver) Resolve(text string) string {
    // ${VAR} or ${VAR:-default}
    bracedRx := regexp.MustCompile(`\$\{([A-Z_][A-Z0-9_]*)(:-([^}]*))?\}`)
    text = bracedRx.ReplaceAllStringFunc(text, func(match string) string {
        m := bracedRx.FindStringSubmatch(match)
        varName := m[1]
        defaultVal := m[3]
        if val, ok := er.vars[varName]; ok {
            return val
        }
        if defaultVal != "" {
            return defaultVal
        }
        return ""
    })

    // $VAR
    simpleRx := regexp.MustCompile(`\$([A-Z_][A-Z0-9_]*)`)
    text = simpleRx.ReplaceAllStringFunc(text, func(match string) string {
        varName := strings.TrimPrefix(match, "$")
        if val, ok := er.vars[varName]; ok {
            return val
        }
        return ""
    })

    return text
}

func parseEnvFile(content string, vars map[string]string) {
    for _, line := range strings.Split(content, "\n") {
        line = strings.TrimSpace(line)
        if line == "" || strings.HasPrefix(line, "#") {
            continue
        }
        parts := strings.SplitN(line, "=", 2)
        if len(parts) == 2 {
            vars[parts[0]] = parts[1]
        }
    }
}
""",
        "function": "env_interpolation_variable_substitution",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "pkg/compose/envresolver.go",
    },
    # ── 10. Build context: context path, dockerfile, args, target ──────────────
    {
        "normalized_code": """\
package compose

import (
    "context"

    "github.com/compose-spec/compose-go/v2/types"
    "github.com/moby/moby/api/types/image"
)

// Construction represents a service build definition
type Construction struct {
    Context    string            // build context directory
    Dockerfile string            // path to Dockerfile relative to context
    Args       map[string]string // build args: ARG key=value
    Target     string            // multi-stage target
    CacheFrom  []string          // base images to use as cache
    Labels     map[string]string // labels for built image
}

// FromComposeConstruction converts Compose spec to internal format
func (b *Construction) FromComposeConstruction(spec *types.BuildConfig) {
    if spec == nil {
        return
    }
    b.Context = spec.Context
    b.Dockerfile = spec.Dockerfile
    b.Args = spec.Args
    b.Target = spec.Target
    b.CacheFrom = spec.CacheFrom
    b.Labels = spec.Labels
}

// BuildImage creates a Docker image from Dockerfile in context directory
func (s *composeService) BuildImage(
    ctx context.Context,
    imageName string,
    construction *Construction,
) error {
    buildOpts := image.BuildOptions{
        Dockerfile: construction.Dockerfile,
        BuildArgs:  toStringMap(construction.Args),
        CacheFrom:  construction.CacheFrom,
        Target:     construction.Target,
        Labels:     construction.Labels,
    }

    resp, err := s.daemon.ImageBuild(ctx, fileInfo(construction.Context), buildOpts)
    if err != nil {
        return err
    }
    defer resp.Body.Close()
    return nil
}
""",
        "function": "build_context_dockerfile_args_target",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "pkg/compose/create.go",
    },
    # ── 11. Project loading from YAML + validation ────────────────────────────────
    {
        "normalized_code": """\
package compose

import (
    "context"

    "github.com/compose-spec/compose-go/v2/cli"
    "github.com/compose-spec/compose-go/v2/types"
)

// ProjectLoadConfig specifies how to load a Compose project
type ProjectLoadConfig struct {
    Name            string   // project name
    ConfigPaths     []string // compose file paths
    WorkingDir      string   // project root directory
    EnvFiles        []string // .env file paths
    Profiles        []string // active profiles
    Services        []string // selected services (empty = all)
    Offline         bool     // disable remote resource fetching
    Compatibility   bool     // v1 compatibility mode
    ProjectOptionsFns []cli.ProjectOptionsFn
}

// LoadProject parses and validates a Compose project from YAML files
func (s *composeService) LoadProject(
    ctx context.Context,
    cfg *ProjectLoadConfig,
) (*types.Project, error) {
    opts := []cli.ProjectOptionsFn{
        cli.WithName(cfg.Name),
        cli.WithWorkingDirectory(cfg.WorkingDir),
        cli.WithProfiles(cfg.Profiles),
        cli.WithOsEnv(),
    }

    for _, envFile := range cfg.EnvFiles {
        opts = append(opts, cli.WithEnvFile(envFile))
    }

    if cfg.Compatibility {
        opts = append(opts, cli.WithCompatibility())
    }

    if cfg.Offline {
        opts = append(opts, cli.WithSkipNormalization())
    }

    opts = append(opts, cfg.ProjectOptionsFns...)

    proj, err := cli.ProjectFromOptions(ctx, &cli.ProjectOptions{
        ConfigPaths: cfg.ConfigPaths,
        ProjectName: cfg.Name,
        WorkDir:     cfg.WorkingDir,
    }, opts...)

    if err != nil {
        return nil, err
    }

    // Validate: check for name unicity, required fields, etc.
    if err := proj.CheckContainerNameUnicity(); err != nil {
        return nil, err
    }

    return proj, nil
}
""",
        "function": "project_loading_yaml_validation",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "pkg/compose/loader.go",
    },
    # ── 12. Scale/replicas: update running instance count ───────────────────────
    {
        "normalized_code": """\
package compose

import (
    "context"
    "fmt"

    "github.com/compose-spec/compose-go/v2/types"
)

// ScaleConfig specifies desired replicas per service
type ScaleConfig struct {
    Services map[string]int // service name → desired replica count
}

// Scale adjusts the number of running Container instances per service
func (s *composeService) Scale(
    ctx context.Context,
    proj *types.Project,
    scaleConfig *ScaleConfig,
) error {
    // Get current containers for each service
    observedContainers, err := s.GetObservedContainers(ctx, proj.Name)
    if err != nil {
        return err
    }

    for serviceName, desiredCount := range scaleConfig.Services {
        currentCount := len(observedContainers[serviceName])

        if currentCount < desiredCount {
            // Scale up: create additional Container instances
            for i := 0; i < desiredCount-currentCount; i++ {
                element := &Container{
                    Name:     fmt.Sprintf("%s_%s_%d", proj.Name, serviceName, currentCount+i+1),
                    // ... copy config from existing or service definition ...
                }
                if err := element.Create(ctx); err != nil {
                    return err
                }
                if err := element.Start(ctx); err != nil {
                    return err
                }
            }
        } else if currentCount > desiredCount {
            // Scale down: stop and remove excess Container instances
            for i := desiredCount; i < currentCount; i++ {
                container := observedContainers[serviceName][i]
                if err := container.Stop(ctx, 10); err != nil {
                    return err
                }
                if err := container.Remove(ctx, true); err != nil {
                    return err
                }
            }
        }
    }

    return nil
}
""",
        "function": "scale_replicas_instance_count",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "pkg/compose/scale.go",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "service model definition container orchestration compose",
    "dependency graph DAG topological traversal services",
    "container lifecycle create start stop remove",
    "network creation service discovery DNS aliases",
    "volume management creation mounting cleanup",
    "port binding host container TCP UDP protocol",
    "healthcheck liveness probe interval timeout retries",
    "restart policy always on-failure unless-stopped",
    "environment variable interpolation dollar sign braces",
    "build context dockerfile args target multi-stage",
    "project loading YAML compose files validation",
    "scale replicas running instances per service",
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
            })
        else:
            results.append({"query": q, "function": "NO_RESULT", "file_role": "?", "score": 0.0, "code_preview": ""})
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
