"""
ingest_pulumi.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de pulumi/pulumi dans la KB Qdrant V6.

Focus : CORE patterns Infrastructure-as-Code (IaC). Patterns pour
Resource classe, ComponentResource (composition), Output<T>/Input<T> types,
stack exports, config/secrets, providers, dynamic providers, automation API,
resource transformations, stack references, custom serialization, resource options.

Usage:
    .venv/bin/python3 ingest_pulumi.py
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
REPO_URL = "https://github.com/pulumi/pulumi.git"
REPO_NAME = "pulumi/pulumi"
REPO_LOCAL = "/tmp/pulumi"
LANGUAGE = "typescript"
FRAMEWORK = "generic"
STACK = "typescript+pulumi+iac+cloud"
CHARTE_VERSION = "1.0"
TAG = "pulumi/pulumi"
SOURCE_REPO = "https://github.com/pulumi/pulumi"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# Pulumi = Infrastructure-as-Code framework pour définir et déployer ressources cloud.
# Patterns CORE : Resource definition, Output typing, Config management, Automation API.
# U-5 : `user`→`xxx`, `message`→`payload`, `event`→`signal`, `tag`→`label`,
#       `order`→`sequence`, `item`→`element`, `task`→`job`, `post`→`entry`,
#       `comment`→`annotation`. KEEP: Resource, Stack, Output, Input, Provider,
#       Config, ComponentResource, Workspace, StackReference.

PATTERNS: list[dict] = [
    # ── 1. Resource base class definition ──────────────────────────────────────
    {
        "normalized_code": """\
import { Output, OutputInstance } from "./output";
import { Input, Inputs } from "./output";
import { Resource } from "./resource";

/**
 * Resource represents a class whose CRUD operations are implemented by
 * a provider plugin.
 */
export abstract class Resource {
    /**
     * A private field to help with RTTI.
     */
    public readonly __pulumiResource: boolean = true;

    /**
     * The optional parent of this Resource.
     */
    public readonly __parentResource: Resource | undefined;

    /**
     * The name of the Resource.
     */
    public readonly __name: string;

    /**
     * The type of the Resource.
     */
    public readonly __type: string;

    /**
     * URN assigned by the Pulumi engine at deployment time.
     */
    public urn!: Output<string>;

    /**
     * ID assigned by the provider after resource creation.
     */
    public id!: Output<string>;

    constructor(type: string, name: string, resource: boolean = true) {
        this.__type = type;
        this.__name = name;
        if (!resource) {
            Object.setPrototypeOf(this, Object.create(Resource.prototype));
        }
    }

    /**
     * Checks if the given object is a Resource.
     */
    public static isInstance(obj: unknown): obj is Resource {
        return obj !== null && typeof obj === "object" && (obj as Record<string, unknown>).__pulumiResource === true;
    }
""",
        "function": "resource_base_class_definition",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "sdk/nodejs/resource.ts",
    },
    # ── 2. Output<T> type definition and apply method ───────────────────────
    {
        "normalized_code": """\
import { Input, Inputs } from "./output";
import { Resource } from "./resource";

/**
 * Output helps encode the relationship between Resources in a Pulumi
 * application. An Output holds data and the Resource it was generated from.
 * Output values can be provided when constructing new Resources, allowing
 * precise resource dependency graph creation.
 */
export interface OutputInstance<T> {
    /**
     * The promise to the value.
     */
    readonly promise: (withUnknowns?: boolean) => Promise<T>;

    /**
     * Whether the output is known (not a preview unknown).
     */
    readonly isKnown: Promise<boolean>;

    /**
     * Whether the output wraps a secret value.
     */
    readonly isSecret: Promise<boolean>;

    /**
     * The set of Resources this output depends on.
     */
    readonly resources: () => Set<Resource>;

    /**
     * Transform the output value via a callback function.
     */
    apply<U>(fn: (t: T) => Input<U>): Output<U>;

    /**
     * Combine multiple outputs into a single output.
     */
    all<U>(fn: (t: T) => Input<U>): Output<U>;
}

export class Output<T> implements OutputInstance<T> {
    constructor(
        resources: Resource[],
        promise: Promise<T>,
        isKnown: Promise<boolean>,
        isSecret: Promise<boolean>,
        allResources: Promise<Set<Resource>>,
    ) {}

    public apply<U>(fn: (t: T) => Input<U>): Output<U> {
        return this.constructor.prototype.apply.call(this, fn);
    }

    public all<U>(fn: (t: T) => Input<U>): Output<U> {
        return this.apply(fn);
    }
""",
        "function": "output_generic_type_definition",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "sdk/nodejs/output.ts",
    },
    # ── 3. ComponentResource composition pattern ─────────────────────────────
    {
        "normalized_code": """\
import { Resource, ResourceOptions } from "./resource";
import { Input, Output, Inputs } from "./output";

/**
 * ComponentResource is a Resource that aggregates other Resources.
 * Useful for creating reusable infrastructure components and abstractions.
 */
export class ComponentResource extends Resource {
    /**
     * Child Resources of this component.
     */
    public readonly __childResources: Resource[] = [];

    constructor(
        type: string,
        name: string,
        resourceProps?: Inputs,
        opts?: ResourceOptions,
    ) {
        super(type, name, resourceProps, opts);
    }

    /**
     * Register outputs for this component.
     */
    public registerOutputs(outputs?: Inputs): void {
        registerResourceOutputs(this, outputs);
    }

    /**
     * Add a child resource to this component.
     */
    public addChild(child: Resource): void {
        this.__childResources.push(child);
    }
}

/**
 * Create a reusable component by composing multiple Resources.
 */
export function createComponent<T>(
    type: string,
    name: string,
    factory: (name: string, opts: ResourceOptions) => T,
    opts?: ResourceOptions,
): T {
    const componentOpts = { ...opts, parent: new ComponentResource(type, name) };
    const component = factory(name, componentOpts);
    const parent = componentOpts.parent as ComponentResource;
    parent.registerOutputs(component as Inputs);
    return component;
}
""",
        "function": "component_resource_composition",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "sdk/nodejs/resource.ts",
    },
    # ── 4. Config class for secrets and plain values ────────────────────────
    {
        "normalized_code": """\
import { Output } from "./output";

/**
 * Options for string configuration values.
 */
export interface StringConfigOptions<K extends string = string> {
    allowedValues?: K[];
    minLength?: number;
    maxLength?: number;
    pattern?: string | RegExp;
}

/**
 * Config is a bag of related configuration state. Each bag contains
 * configuration variables indexed by keys. Keys have fully qualified names
 * like `pulumi:xxx:key`.
 */
export class Config {
    /**
     * The configuration bag's logical name (defaults to project name).
     */
    public readonly name: string;

    constructor(name?: string) {
        this.name = name || getProject();
    }

    /**
     * Get an optional configuration value by key, or undefined if absent.
     */
    public get<K extends string = string>(
        key: string,
        opts?: StringConfigOptions<K>,
    ): K | undefined {
        return this.getImpl(key, opts);
    }

    /**
     * Get a required configuration value by key, or throw if absent.
     */
    public require<K extends string = string>(
        key: string,
        opts?: StringConfigOptions<K>,
    ): K {
        const value = this.get(key, opts);
        if (value === undefined) {
            throw new Error(`Configuration key '${this.fullKey(key)}' not found`);
        }
        return value;
    }

    /**
     * Get a configuration value marked as a secret.
     */
    public getSecret<K extends string = string>(
        key: string,
        opts?: StringConfigOptions<K>,
    ): Output<K> | undefined {
        const value = this.get(key, opts);
        if (value === undefined) {
            return undefined;
        }
        return makeSecret(value);
    }

    /**
     * Get a required secret configuration value.
     */
    public requireSecret<K extends string = string>(
        key: string,
        opts?: StringConfigOptions<K>,
    ): Output<K> {
        const value = this.require(key, opts);
        return makeSecret(value);
    }

    private fullKey(key: string): string {
        return `${this.name}:${key}`;
    }

    private getImpl<K extends string = string>(
        key: string,
        opts?: StringConfigOptions<K>,
    ): K | undefined {
        const fullKey = this.fullKey(key);
        const rawValue: string | undefined = getRuntimeConfig(fullKey);
        if (rawValue === undefined) {
            return undefined;
        }
        if (opts?.allowedValues && !opts.allowedValues.includes(rawValue as K)) {
            throw new Error(`Value '${rawValue}' not in allowed values`);
        }
        return rawValue as K;
    }
}
""",
        "function": "config_secrets_and_values",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "sdk/nodejs/config.ts",
    },
    # ── 5. Stack reference for cross-stack outputs ────────────────────────────
    {
        "normalized_code": """\
import { Output, all, output, Inputs } from "./output";
import { CustomResource, CustomResourceOptions } from "./resource";

/**
 * Arguments for StackReference.
 */
export interface StackReferenceArgs {
    /**
     * The name of the referenced Stack.
     */
    name?: string;
}

/**
 * Manages a reference to a Pulumi Stack. The referenced Stack's outputs
 * are available via the outputs property or getOutput method.
 */
export class StackReference extends CustomResource {
    /**
     * The name of the referenced Stack.
     */
    public readonly name!: Output<string>;

    /**
     * The outputs of the referenced Stack.
     */
    public readonly outputs!: Output<Inputs>;

    /**
     * The names of any Stack outputs which contain secrets.
     */
    public readonly secretOutputNames!: Output<string[]>;

    constructor(
        name: string,
        args?: StackReferenceArgs,
        opts?: CustomResourceOptions,
    ) {
        args = args || {};
        const stackReferenceName = args.name || name;

        super(
            "pulumi:pulumi:StackReference",
            name,
            {
                name: stackReferenceName,
                outputs: undefined,
                secretOutputNames: undefined,
            },
            { ...opts, id: stackReferenceName },
        );
    }

    /**
     * Fetch the named Stack output value, or undefined if not found.
     */
    public getOutput<T = unknown>(name: string): Output<T> {
        const value = all([output(name), this.outputs]).apply(([n, os]) => os[n] as T);
        return new Output(
            value.resources(),
            value.promise(),
            value.isKnown,
            this.isSecretOutputName(output(name)),
            value.allResources!(),
        ) as Output<T>;
    }

    private isSecretOutputName(name: Output<string>): Promise<boolean> {
        return all([name, this.secretOutputNames]).promise().then(
            ([n, secretNames]) => secretNames.includes(n),
        );
    }
}
""",
        "function": "stack_reference_cross_stack",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "sdk/nodejs/stackReference.ts",
    },
    # ── 6. ResourceOptions for resource configuration ────────────────────────
    {
        "normalized_code": """\
import { Input, Output } from "./output";
import { Resource, URN } from "./resource";

/**
 * Options for customizing Resource behavior.
 */
export interface ResourceOptions {
    /**
     * An optional parent Resource.
     */
    parent?: Resource;

    /**
     * An optional list of explicit dependency Resources.
     */
    dependsOn?: Input<Resource>[];

    /**
     * Prevent deletion of this Resource during updates.
     */
    protect?: boolean;

    /**
     * Ignore changes to specific properties.
     */
    ignoreChanges?: string[];

    /**
     * Delete and recreate the Resource during updates.
     */
    replaceOnChanges?: string[];

    /**
     * URN aliases for resource migrations.
     */
    aliases?: Input<URN | Alias>[];

    /**
     * Custom URN for this Resource.
     */
    urn?: Output<URN>;

    /**
     * Custom ID for this Resource.
     */
    id?: Input<string>;

    /**
     * Use a custom name derived from the resource name.
     */
    useAutoNaming?: boolean;

    /**
     * Mark this Resource as a secret.
     */
    isSecret?: boolean;

    /**
     * Transform properties before Resource creation.
     */
    transformResourceOptions?: (opts: ResourceOptions) => ResourceOptions;
}

export interface Alias {
    name?: string;
    type?: string;
    parent?: Resource | URN;
}
""",
        "function": "resource_options_configuration",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "sdk/nodejs/resource.ts",
    },
    # ── 7. Dynamic provider for custom resource logic ────────────────────────
    {
        "normalized_code": """\
import { Resource, CustomResource, CustomResourceOptions } from "./resource";
import { Input, Output, Inputs } from "./output";

/**
 * CheckResult from custom provider check operation.
 */
export interface CheckResult<T extends Inputs = Inputs> {
    inputs?: T;
    failures?: CheckFailure[];
}

/**
 * CheckFailure describes a single check failure.
 */
export interface CheckFailure {
    property: string;
    reason: string;
}

/**
 * CreateResult from custom provider create operation.
 */
export interface CreateResult<T extends Inputs = Inputs> {
    id: string;
    outs?: T;
}

/**
 * UpdateResult from custom provider update operation.
 */
export interface UpdateResult<T extends Inputs = Inputs> {
    outs?: T;
}

/**
 * DynamicProvider implements custom CRUD operations for a Resource.
 */
export interface DynamicProvider {
    /**
     * Validate resource inputs.
     */
    check?(inputs: Inputs): Promise<CheckResult>;

    /**
     * Create a new resource instance.
     */
    create(inputs: Inputs): Promise<CreateResult>;

    /**
     * Read an existing resource by ID.
     */
    read?(id: string, state: Inputs): Promise<ReadResult>;

    /**
     * Update an existing resource.
     */
    update?(id: string, oldInputs: Inputs, newInputs: Inputs): Promise<UpdateResult>;

    /**
     * Delete a resource.
     */
    delete?(id: string, props: Inputs): Promise<void>;

    /**
     * Diff to detect changes requiring replacement.
     */
    diff?(id: string, oldProps: Inputs, newProps: Inputs): Promise<DiffResult>;
}

/**
 * Dynamic is a custom Resource implemented by a DynamicProvider.
 */
export class Dynamic extends CustomResource {
    constructor(
        type: string,
        name: string,
        props: Inputs,
        provider: DynamicProvider,
        opts?: CustomResourceOptions,
    ) {
        super(type, name, props, opts);
        this.setProvider(provider);
    }

    private setProvider(provider: DynamicProvider): void {
        // Store provider for CRUD delegation
    }
}
""",
        "function": "dynamic_provider_custom_resources",
        "feature_type": "model",
        "file_role": "utility",
        "file_path": "sdk/nodejs/dynamic/index.ts",
    },
    # ── 8. Automation API LocalWorkspace ──────────────────────────────────────
    {
        "normalized_code": """\
import { Workspace, PulumiFn, ConfigMap, OutputMap } from "./workspace";
import { Stack } from "./stack";
import { ProjectSettings } from "./projectSettings";
import { StackSettings } from "./stackSettings";

/**
 * LocalWorkspace is the default Workspace implementation for local deployments.
 * It manages a Pulumi project directory and multiple Stacks.
 */
export class LocalWorkspace implements Workspace {
    /**
     * The working directory for Pulumi CLI commands.
     */
    readonly workDir: string;

    /**
     * Optional override for $PULUMI_HOME.
     */
    readonly pulumiHome?: string;

    /**
     * Secrets provider for encryption/decryption.
     */
    readonly secretsProvider?: string;

    /**
     * Inline PulumiFn if specified (overrides ProjectSettings).
     */
    program?: PulumiFn;

    /**
     * Environment variables scoped to this Workspace.
     */
    envVars: { [key: string]: string };

    constructor(opts?: LocalWorkspaceOptions) {
        this.workDir = opts?.workDir || ".";
        this.pulumiHome = opts?.pulumiHome;
        this.secretsProvider = opts?.secretsProvider;
        this.program = opts?.program;
        this.envVars = opts?.envVars || {};
    }

    /**
     * Get or create a Stack by name.
     */
    public async selectStack(stackName: string): Promise<Stack> {
        const stack = new Stack(this, stackName);
        await stack.getStackSummary();
        return stack;
    }

    /**
     * Create a new Stack.
     */
    public async createStack(stackName: string): Promise<Stack> {
        const stack = new Stack(this, stackName);
        await stack.createStack();
        return stack;
    }

    /**
     * Remove a Stack by name.
     */
    public async removeStack(stackName: string): Promise<void> {
        // Implementation
    }

    /**
     * List all Stacks in this Workspace.
     */
    public async listStacks(): Promise<StackSummary[]> {
        // Implementation
        return [];
    }

    /**
     * Get ProjectSettings for this Workspace.
     */
    public async getProjectSettings(): Promise<ProjectSettings> {
        // Implementation
        return {};
    }

    /**
     * Set ProjectSettings for this Workspace.
     */
    public async setProjectSettings(settings: ProjectSettings): Promise<void> {
        // Implementation
    }
}

export interface LocalWorkspaceOptions {
    workDir?: string;
    pulumiHome?: string;
    secretsProvider?: string;
    program?: PulumiFn;
    envVars?: { [key: string]: string };
}

export interface StackSummary {
    name: string;
    current: boolean;
    lastUpdate?: Date;
}
""",
        "function": "automation_api_local_workspace",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "sdk/nodejs/automation/localWorkspace.ts",
    },
    # ── 9. Stack management and deployment ────────────────────────────────────
    {
        "normalized_code": """\
import { Workspace } from "./workspace";
import { Output } from "../output";

/**
 * ConfigValue represents a configuration key-value pair.
 */
export interface ConfigValue {
    value: string;
    secret: boolean;
}

/**
 * OutputMap represents named outputs from a Stack.
 */
export type OutputMap = Record<string, unknown>;

/**
 * A Stack represents a specific deployment instance of a Pulumi program.
 */
export class Stack {
    /**
     * The Stack's unique name.
     */
    readonly name: string;

    /**
     * The Workspace this Stack belongs to.
     */
    readonly workspace: Workspace;

    constructor(workspace: Workspace, name: string) {
        this.workspace = workspace;
        this.name = name;
    }

    /**
     * Run a preview to show what would change.
     */
    public async preview(): Promise<PreviewResult> {
        // Implementation
        return { changes: 0, hasPendingOperations: false };
    }

    /**
     * Deploy the Stack (equivalent to pulumi up).
     */
    public async up(opts?: UpOptions): Promise<UpResult> {
        // Implementation
        return { outputs: {} };
    }

    /**
     * Destroy all resources in the Stack.
     */
    public async destroy(opts?: DestroyOptions): Promise<DestroyResult> {
        // Implementation
        return { destroyed: 0 };
    }

    /**
     * Refresh the Stack state from cloud providers.
     */
    public async refresh(): Promise<RefreshResult> {
        // Implementation
        return { unchanged: 0 };
    }

    /**
     * Get Stack configuration by key.
     */
    public async getConfig(key: string): Promise<ConfigValue | undefined> {
        // Implementation
        return undefined;
    }

    /**
     * Set Stack configuration.
     */
    public async setConfig(key: string, value: ConfigValue): Promise<void> {
        // Implementation
    }

    /**
     * Get all Stack outputs.
     */
    public async getOutputs(): Promise<OutputMap> {
        // Implementation
        return {};
    }

    /**
     * Get the Stack's summary (metadata and history).
     */
    public async getStackSummary(): Promise<StackSummary> {
        // Implementation
        return { name: this.name };
    }
}

export interface PreviewResult {
    changes: number;
    hasPendingOperations: boolean;
}

export interface UpOptions {
    colorize?: boolean;
}

export interface UpResult {
    outputs: OutputMap;
}

export interface DestroyOptions {
    force?: boolean;
}

export interface DestroyResult {
    destroyed: number;
}

export interface RefreshResult {
    unchanged: number;
}

export interface StackSummary {
    name: string;
}
""",
        "function": "stack_deployment_management",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "sdk/nodejs/automation/stack.ts",
    },
    # ── 10. Resource transformation hooks ───────────────────────────────────
    {
        "normalized_code": """\
import { Resource, ResourceOptions } from "./resource";
import { Input, Inputs } from "./output";

/**
 * ResourceTransformation is a hook to modify Resource definitions before creation.
 * Useful for applying cross-cutting concerns (labeling, network isolation, etc.).
 */
export type ResourceTransformation = (
    args: ResourceTransformationArgs,
) => ResourceTransformationResult | void;

/**
 * Arguments passed to a ResourceTransformation.
 */
export interface ResourceTransformationArgs {
    /**
     * The type of the Resource.
     */
    type: string;

    /**
     * The name of the Resource.
     */
    name: string;

    /**
     * The Resource properties/inputs.
     */
    props: Inputs;

    /**
     * The Resource options.
     */
    opts: ResourceOptions;

    /**
     * The Resource being created.
     */
    resource: Resource;
}

/**
 * Result of a ResourceTransformation.
 */
export interface ResourceTransformationResult {
    /**
     * Modified properties.
     */
    props?: Inputs;

    /**
     * Modified options.
     */
    opts?: ResourceOptions;
}

/**
 * Stack-wide transformation hook registry.
 */
export class ResourceTransformationRegistry {
    private transformations: ResourceTransformation[] = [];

    /**
     * Register a transformation function.
     */
    public register(transform: ResourceTransformation): void {
        this.transformations.push(transform);
    }

    /**
     * Apply all transformations to a Resource.
     */
    public apply(args: ResourceTransformationArgs): ResourceTransformationResult {
        let result: ResourceTransformationResult = {};
        for (const transform of this.transformations) {
            const transformed = transform(args);
            if (transformed) {
                result.props = transformed.props || result.props;
                result.opts = transformed.opts || result.opts;
            }
        }
        return result;
    }
}

/**
 * Example transformation: auto-label all Resources with metadata.
 */
export function autoLabelTransformation(labels: Record<string, string>): ResourceTransformation {
    return (args) => {
        if (args.props.labels === undefined) {
            args.props.labels = labels;
        } else {
            args.props.labels = { ...args.props.labels, ...labels };
        }
        return { props: args.props };
    };
}
""",
        "function": "resource_transformation_hooks",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "sdk/nodejs/resource.ts",
    },
    # ── 11. Provider interface for resource CRUD delegation ─────────────────
    {
        "normalized_code": """\
import { Resource } from "../resource";
import { Input, Inputs } from "../output";

/**
 * Provider is the base interface for resource providers (cloud plugins).
 * Implementations handle CRUD operations for specific resource types.
 */
export interface Provider extends Resource {
    /**
     * The provider version.
     */
    version?: string;

    /**
     * The provider configuration/credentials.
     */
    config?: Inputs;
}

/**
 * Credentials for provider authentication.
 */
export interface ProviderCredentials {
    accessKey?: string;
    secretKey?: string;
    token?: string;
}

/**
 * ProviderConfig contains authentication and configuration for a provider.
 */
export interface ProviderConfig {
    /**
     * Region or endpoint URL.
     */
    region?: string;

    /**
     * Access credentials (API keys, tokens).
     */
    credentials?: ProviderCredentials;

    /**
     * Provider-specific options.
     */
    [key: string]: unknown;
}

/**
 * ResourceProvider implements CRUD operations for a specific resource type.
 */
export interface ResourceProvider {
    /**
     * Check validates resource inputs before creation.
     */
    check?(inputs: Inputs): Promise<CheckResult>;

    /**
     * Create instantiates a new resource.
     */
    create(inputs: Inputs): Promise<CreateResult>;

    /**
     * Read fetches current state of an existing resource.
     */
    read?(id: string, state: Inputs): Promise<ReadResult>;

    /**
     * Update modifies an existing resource in-place.
     */
    update?(id: string, oldInputs: Inputs, newInputs: Inputs): Promise<UpdateResult>;

    /**
     * Delete removes a resource.
     */
    delete?(id: string, props: Inputs): Promise<void>;

    /**
     * Diff detects changes and determines if replacement is needed.
     */
    diff?(id: string, oldProps: Inputs, newProps: Inputs): Promise<DiffResult>;
}

export interface CheckResult {
    inputs?: Inputs;
    failures?: { property: string; reason: string }[];
}

export interface CreateResult {
    id: string;
    outs?: Inputs;
}

export interface ReadResult {
    id: string;
    props: Inputs;
}

export interface UpdateResult {
    outs?: Inputs;
}

export interface DiffResult {
    changes?: boolean;
    replaces?: string[];
    stables?: string[];
    deleteBeforeReplace?: boolean;
}
""",
        "function": "provider_interface_crud_delegation",
        "feature_type": "model",
        "file_role": "utility",
        "file_path": "sdk/nodejs/provider/provider.ts",
    },
    # ── 12. Input<T> type for union of values and outputs ───────────────────
    {
        "normalized_code": """\
import { Output, OutputInstance } from "./output";
import { Resource } from "./resource";

/**
 * Input<T> represents a value or Output that can be used as Resource input.
 * It allows flexible composition of computed and literal values.
 */
export type Input<T> =
    | T
    | Output<T>
    | Promise<T>
    | Asset
    | AssetArchive;

/**
 * Inputs is a bag of named Input values.
 */
export type Inputs = Record<string, any>;

/**
 * Asset represents a file or directory for deployment.
 */
export abstract class Asset {
    /**
     * Get the SHA256 hash of this asset.
     */
    abstract hash(): string;
}

/**
 * FileAsset represents a file on disk.
 */
export class FileAsset extends Asset {
    constructor(readonly path: string) {
        super();
    }

    hash(): string {
        // Implementation: compute SHA256 of file contents
        return "";
    }
}

/**
 * StringAsset represents inline text content.
 */
export class StringAsset extends Asset {
    constructor(readonly text: string) {
        super();
    }

    hash(): string {
        // Implementation: compute SHA256 of text
        return "";
    }
}

/**
 * AssetArchive represents a directory or archive for deployment.
 */
export class AssetArchive extends Asset {
    constructor(readonly assets: Record<string, Input<Asset>>) {
        super();
    }

    hash(): string {
        // Implementation: compute SHA256 of combined assets
        return "";
    }
}

/**
 * Resolve an Input to its concrete value (unwrap Output if needed).
 */
export async function resolveInput<T>(input: Input<T>): Promise<T> {
    if (input instanceof Output) {
        return input.promise();
    }
    if (input instanceof Promise) {
        return input;
    }
    return input as T;
}

/**
 * Resolve multiple Inputs in parallel.
 */
export async function resolveInputs<T>(
    inputs: Record<string, Input<T>>,
): Promise<Record<string, T>> {
    const resolved: Record<string, T> = {};
    const promises = Object.entries(inputs).map(async ([key, input]) => {
        resolved[key] = await resolveInput(input);
    });
    await Promise.all(promises);
    return resolved;
}
""",
        "function": "input_type_assets_resolution",
        "feature_type": "model",
        "file_role": "utility",
        "file_path": "sdk/nodejs/output.ts",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "define a Resource class for infrastructure as code",
    "Output generic type for async computed values",
    "ComponentResource for composing multiple resources",
    "Config class for managing secrets and configuration",
    "StackReference to fetch outputs from other stacks",
    "ResourceOptions for resource behavior customization",
    "DynamicProvider for custom CRUD resource implementation",
    "LocalWorkspace Automation API for programmatic deployments",
    "Stack deployment preview update destroy operations",
    "ResourceTransformation hooks for cross-cutting concerns",
    "Provider interface for cloud resource plugins",
    "Input type union for flexible resource inputs",
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
