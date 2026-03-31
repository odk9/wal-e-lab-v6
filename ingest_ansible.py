"""
ingest_ansible.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de ansible/ansible dans la KB Qdrant V6.

Focus : CORE patterns Ansible automation/IaC :
  - Module interface (AnsibleModule init, argument_spec, result dict)
  - Action plugin base class
  - Callback plugin base class
  - Inventory plugin
  - Connection plugin
  - Lookup plugin
  - Filter plugin
  - Fact gathering
  - Variable precedence
  - Play/task execution flow
  - Error handling (fail_json/exit_json)
  - Vault encryption/decryption

Usage:
    .venv/bin/python3 ingest_ansible.py
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
REPO_URL = "https://github.com/ansible/ansible.git"
REPO_NAME = "ansible/ansible"
REPO_LOCAL = "/tmp/ansible"
LANGUAGE = "python"
FRAMEWORK = "generic"
STACK = "python+ansible+automation+iac"
CHARTE_VERSION = "1.0"
TAG = "ansible/ansible"
SOURCE_REPO = "https://github.com/ansible/ansible"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# Ansible = framework automation/IaC multiplateforme Python.
# Patterns CORE : interfaces plugin, modules, execution flow, vault.
# U-5 : remplacer task→play_step, user→xxx, item→element, message→result_data, etc.

PATTERNS: list[dict] = [
    # ── 1. AnsibleModule initialization (module interface) ──────────────────
    {
        "normalized_code": """\
from ansible.module_utils.basic import AnsibleModule


def main() -> None:
    \"\"\"Initialize Ansible module with argument spec and execute logic.\"\"\"
    module = AnsibleModule(
        argument_spec=dict(
            src=dict(type='path', required=True, aliases=['source']),
            dest=dict(type='path', required=True, aliases=['destination']),
            mode=dict(type='str', default='0644'),
            force=dict(type='bool', default=False),
        ),
        supports_check_mode=True,
    )

    src_path = module.params['src']
    dest_path = module.params['dest']
    force = module.params['force']

    try:
        if not os.path.exists(src_path):
            module.fail_json(msg=f"Source not found: {src_path}")

        if os.path.exists(dest_path) and not force:
            module.exit_json(changed=False, msg="File already exists")

        copy_file(src_path, dest_path)
        module.exit_json(changed=True, src=src_path, dest=dest_path)

    except Exception as exc:
        module.fail_json(msg=f"Error: {exc}", exception=str(exc))


if __name__ == '__main__':
    main()
""",
        "function": "ansiblemodule_init_argument_spec",
        "feature_type": "module",
        "file_role": "utility",
        "file_path": "lib/ansible/module_utils/basic.py",
    },
    # ── 2. fail_json / exit_json result dict pattern ──────────────────────
    {
        "normalized_code": """\
def fail_json(module: AnsibleModule, msg: str, **kwargs) -> None:
    \"\"\"Fail module execution with error payload.\"\"\"
    result_data = {
        'failed': True,
        'msg': msg,
        'changed': False,
    }
    result_data.update(kwargs)
    module.fail_json(**result_data)


def exit_json(module: AnsibleModule, changed: bool = False, **kwargs) -> None:
    \"\"\"Exit module execution successfully with result payload.\"\"\"
    result_data = {
        'changed': changed,
        'failed': False,
    }
    result_data.update(kwargs)
    module.exit_json(**result_data)
""",
        "function": "result_dict_fail_exit_json",
        "feature_type": "route",
        "file_role": "utility",
        "file_path": "lib/ansible/module_utils/basic.py",
    },
    # ── 3. ActionBase plugin initialization ────────────────────────────────
    {
        "normalized_code": """\
from abc import ABC, abstractmethod
from ansible.plugins import _AnsiblePluginInfoMixin


class ActionBase(ABC, _AnsiblePluginInfoMixin):
    \"\"\"Base class for action plugins.\"\"\"

    _VALID_ARGS = frozenset([])
    BYPASS_HOST_LOOP = False
    TRANSFERS_FILES = False
    _requires_connection = True
    _supports_check_mode = True
    _supports_async = False

    def __init__(self, play_step, connection, play_context, loader, templar, shared_loader_obj=None):
        self._play_step = play_step
        self._connection = connection
        self._play_context = play_context
        self._loader = loader
        self._templar = templar
        self._shared_loader_obj = shared_loader_obj
        self._cleanup_remote_tmp = False

    @abstractmethod
    def run(self, xyz_xxx=None, xyz_context=None):
        \"\"\"Execute the action. Must be overridden by subclasses.\"\"\"
        return {
            'failed': False,
            'changed': False,
        }
""",
        "function": "action_plugin_base_class",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "lib/ansible/plugins/action/__init__.py",
    },
    # ── 4. CallbackBase plugin (event handler) ────────────────────────────
    {
        "normalized_code": """\
from ansible.plugins import AnsiblePlugin
import typing as t


class CallbackBase(AnsiblePlugin):
    \"\"\"Base class for callback plugins (signal handlers).\"\"\"

    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = 'stdout'
    CALLBACK_NAME = 'xxx_callback'

    def __init__(self):
        super().__init__()

    def v2_playbook_on_start(self, playbook) -> None:
        \"\"\"Handler: playbook execution started.\"\"\"
        pass

    def v2_playbook_on_play_start(self, play) -> None:
        \"\"\"Handler: play execution started.\"\"\"
        pass

    def v2_playbook_on_ansible_step_complete(self, result) -> None:
        \"\"\"Handler: ansible_step completed.\"\"\"
        if result._result.get('failed'):
            self._handle_failure(result)

    def v2_playbook_on_stats(self, stats) -> None:
        \"\"\"Handler: playbook execution finished.\"\"\"
        pass

    def _handle_failure(self, result) -> None:
        \"\"\"Process failed play_step.\"\"\"
        pass
""",
        "function": "callback_plugin_base_class",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "lib/ansible/plugins/callback/__init__.py",
    },
    # ── 5. ConnectionBase plugin ──────────────────────────────────────────
    {
        "normalized_code": """\
from abc import abstractmethod
from ansible.plugins import AnsiblePlugin


class ConnectionBase(AnsiblePlugin):
    \"\"\"Base class for connection plugins.\"\"\"

    has_pipelining = False
    has_native_async = False
    has_tty = True
    module_implementation_preferences = ('',)
    allow_executable = True
    supports_persistence = False

    def __init__(self, play_context, new_stdin, xyz_obj=None, **kwargs):
        super().__init__()
        self._play_context = play_context
        self._connected = False
        self._new_stdin = new_stdin

    @abstractmethod
    def _connect(self) -> None:
        \"\"\"Establish connection to remote host.\"\"\"
        self._connected = True

    @abstractmethod
    def exec_command(
        self,
        cmd: str,
        in_data=None,
        sudoable: bool = True,
    ) -> tuple[int, bytes, bytes]:
        \"\"\"Execute a command on the remote host.\"\"\"
        pass

    def close(self) -> None:
        \"\"\"Close the connection.\"\"\"
        self._connected = False
""",
        "function": "connection_plugin_base_class",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "lib/ansible/plugins/connection/__init__.py",
    },
    # ── 6. LookupBase plugin (data retrieval) ────────────────────────────
    {
        "normalized_code": """\
from abc import abstractmethod
from ansible.plugins import AnsiblePlugin


class LookupBase(AnsiblePlugin):
    \"\"\"Base class for lookup plugins (data retrieval from external sources).\"\"\"

    accept_args_markers = False
    accept_lazy_markers = False

    def __init__(self, loader=None, templar=None, **kwargs):
        super().__init__()
        self._loader = loader
        self._templar = templar

    def get_basedir(self, variables):
        if 'role_path' in variables:
            return variables['role_path']
        return self._loader.get_basedir()

    @abstractmethod
    def run(self, xyz_list, variables=None, **kwargs):
        \"\"\"Retrieve data from external source.\"\"\"
        pass

    @staticmethod
    def _flatten(elements):
        \"\"\"Flatten nested lists.\"\"\"
        result = []
        for element in elements:
            if isinstance(element, (list, tuple)):
                result.extend(element)
            else:
                result.append(element)
        return result
""",
        "function": "lookup_plugin_base_class",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "lib/ansible/plugins/lookup/__init__.py",
    },
    # ── 7. FilterModule plugin registration ──────────────────────────────
    {
        "normalized_code": """\
class FilterModule:
    \"\"\"Register custom Jinja2 filters for playbook templating.\"\"\"

    def filters(self) -> dict:
        \"\"\"Return dict of filter_name -> filter_function.\"\"\"
        return {
            'format_string': self.format_string,
            'xxx_split': self.xxx_split,
            'xxx_join': self.xxx_join,
            'xxx_upper': self.xxx_upper,
        }

    @staticmethod
    def format_string(value: str, separator: str = ' ') -> str:
        \"\"\"Format string with custom separator.\"\"\"
        return separator.join(value.split())

    @staticmethod
    def xxx_split(value: str, delimiter: str = ',') -> list:
        \"\"\"Split string by delimiter and strip whitespace.\"\"\"
        return [x.strip() for x in value.split(delimiter)]

    @staticmethod
    def xxx_join(elements: list, separator: str = ',') -> str:
        \"\"\"Join list elements with separator.\"\"\"
        return separator.join(str(x) for x in elements)

    @staticmethod
    def xxx_upper(value: str) -> str:
        \"\"\"Convert to uppercase.\"\"\"
        return value.upper()
""",
        "function": "filter_module_custom_jinja2_filters",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "lib/ansible/plugins/filter/__init__.py",
    },
    # ── 8. InventoryPlugin (host/group discovery) ───────────────────────
    {
        "normalized_code": """\
from ansible.plugins.inventory import BaseInventoryPlugin, Cacheable
from ansible.parsing.dataloader import DataLoader


class InventoryModule(BaseInventoryPlugin, Cacheable):
    \"\"\"Dynamic inventory plugin to discover hosts from external source.\"\"\"

    NAME = 'xxx_inventory'
    PLUGIN_TYPE = 'inventory'
    PLUGIN_NAME = 'xxx'

    def __init__(self):
        super().__init__()
        self.inventory = None

    def verify_file(self, path: str) -> bool:
        \"\"\"Check if inventory file is valid for this plugin.\"\"\"
        return path.endswith(('.yml', '.yaml', '.ini'))

    def parse(self, inventory, loader: DataLoader, path: str, cache: bool = True):
        \"\"\"Parse inventory and populate host/group structure.\"\"\"
        super().parse(inventory, loader, path, cache)
        self.inventory = inventory

        config = self._read_config_data(path)

        for group_name, group_data in config.items():
            self.inventory.add_group(group_name)

            for hostname in group_data.get('hosts', []):
                self.inventory.add_host(hostname, group=group_name)
                host = self.inventory.get_host(hostname)
                for var_name, var_value in group_data.get('vars', {}).items():
                    host.set_variable(var_name, var_value)

    def _read_config_data(self, path: str) -> dict:
        \"\"\"Load and parse configuration data from file.\"\"\"
        with open(path) as file_handle:
            return self.loader.load_from_file(file_handle)
""",
        "function": "inventory_plugin_host_discovery",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "lib/ansible/plugins/inventory/__init__.py",
    },
    # ── 9. Variable precedence resolution (fact gathering) ──────────────
    {
        "normalized_code": """\
def resolve_xxx_precedence(xxx_values: dict) -> dict:
    \"\"\"Resolve variable precedence hierarchy.

    Priority (highest → lowest):
      1. play_step vars
      2. host vars
      3. group vars
      4. ansible_facts (gathered)
      5. defaults
    \"\"\"
    result = {}

    if 'defaults' in xxx_values:
        result.update(xxx_values['defaults'])

    if 'facts' in xxx_values:
        result.update(xxx_values['facts'])

    if 'group_vars' in xxx_values:
        result.update(xxx_values['group_vars'])

    if 'host_vars' in xxx_values:
        result.update(xxx_values['host_vars'])

    if 'play_step_vars' in xxx_values:
        result.update(xxx_values['play_step_vars'])

    return result


def gather_facts(hostname: str, connection) -> dict:
    \"\"\"Gather system facts from remote host via connection plugin.\"\"\"
    facts = {
        'ansible_hostname': hostname,
        'ansible_fqdn': '',
        'ansible_os_family': '',
        'ansible_distribution': '',
        'ansible_distribution_version': '',
    }

    try:
        rc, stdout, stderr = connection.exec_command('uname -a')
        if rc == 0:
            facts['ansible_system_info'] = stdout.decode().strip()
    except Exception:
        pass

    return facts
""",
        "function": "xxx_precedence_fact_gathering",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "lib/ansible/vars/manager.py",
    },
    # ── 10. Play/Task execution flow ──────────────────────────────────────
    {
        "normalized_code": """\
import logging

logger = logging.getLogger(__name__)


def execute_play_sequence(play, context, xxx_manager):
    \"\"\"Execute play: parse → validate → run play_steps → collect results.\"\"\"
    logger.info(f"Starting play: {play.name}")

    try:
        for play_step in play.play_steps:
            logger.debug(f"Executing play_step: {play_step.name}")

            if play_step.when and not evaluate_condition(play_step.when, xxx_manager):
                logger.info(f"Skipping play_step {play_step.name} (when condition false)")
                continue

            result_data = execute_play_step(play_step, context)

            if result_data.get('failed'):
                if play_step.ignore_errors:
                    logger.warning(f"play_step {play_step.name} failed but ignored")
                else:
                    logger.error(f"play_step {play_step.name} failed")
                    break

    except Exception as exc:
        logger.error(f"Play execution failed: {exc}")
        return {'failed': True, 'error': str(exc)}

    logger.info(f"Play completed: {play.name}")
    return {'changed': True, 'stats': collect_play_stats(play)}


def evaluate_condition(condition_expr: str, xxx_manager) -> bool:
    \"\"\"Evaluate conditional expression in play_step.\"\"\"
    return xxx_manager.templar.do_template(condition_expr)


def execute_play_step(play_step, context) -> dict:
    \"\"\"Execute single play_step (module invocation).\"\"\"
    action_plugin = load_action_plugin(play_step.action)
    return action_plugin.run(play_step.args, context=context)
""",
        "function": "play_sequence_execution_flow",
        "feature_type": "pipeline",
        "file_role": "utility",
        "file_path": "lib/ansible/executor/play_iterator.py",
    },
    # ── 11. Vault encryption/decryption ──────────────────────────────────
    {
        "normalized_code": """\
import os
from ansible.parsing.vault import VaultLib, VaultPassword


class VaultManager:
    \"\"\"Manage Ansible vault encryption/decryption.\"\"\"

    def __init__(self, vault_password: str | None = None):
        self.vault_password = vault_password or os.getenv('ANSIBLE_VAULT_PASSWORD', '')
        self.vault_lib = VaultLib([(self._get_vault_id(), self._get_vault_pass)])

    def _get_vault_id(self) -> str:
        return 'default'

    def _get_vault_pass(self) -> VaultPassword:
        return VaultPassword(self.vault_password.encode())

    def encrypt_xxx(self, plaintext: str) -> str:
        \"\"\"Encrypt plaintext with vault.\"\"\"
        ciphertext = self.vault_lib.encrypt(plaintext)
        return ciphertext.decode()

    def decrypt_xxx(self, ciphertext: str) -> str:
        \"\"\"Decrypt ciphertext from vault.\"\"\"
        plaintext = self.vault_lib.decrypt(ciphertext)
        return plaintext.decode()

    def encrypt_xxx_file(self, file_path: str) -> None:
        \"\"\"Encrypt file in-place.\"\"\"
        with open(file_path, 'rb') as fh:
            plaintext = fh.read().decode()

        ciphertext = self.encrypt_xxx(plaintext)

        with open(file_path, 'wb') as fh:
            fh.write(ciphertext.encode())
""",
        "function": "vault_encryption_decryption_manager",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "lib/ansible/parsing/vault.py",
    },
    # ── 12. Error handling with context (exception wrapper) ──────────────
    {
        "normalized_code": """\
import traceback
from typing import Optional


class AnsibleError(Exception):
    \"\"\"Base exception for Ansible errors.\"\"\"

    def __init__(self, result_data: str, exception: Optional[Exception] = None):
        self.result_data = result_data
        self.exception = exception
        super().__init__(result_data)


class AnsiblePlayStepError(AnsibleError):
    \"\"\"Error during play_step execution.\"\"\"
    pass


def safe_execute(fn, *args, context_label: str = '', **kwargs) -> dict:
    \"\"\"Execute function with error handling and context.\"\"\"
    try:
        result = fn(*args, **kwargs)
        return {'success': True, 'result': result}

    except AnsiblePlayStepError as exc:
        return {
            'success': False,
            'failed': True,
            'payload': str(exc.result_data),
            'exception': str(exc.exception),
            'context': context_label,
        }

    except Exception as exc:
        return {
            'success': False,
            'failed': True,
            'payload': f"Unexpected error in {context_label}",
            'exception': str(exc),
            'traceback': traceback.format_exc(),
        }
""",
        "function": "error_handling_exception_wrapper",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "lib/ansible/errors/__init__.py",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "AnsibleModule initialization argument specification",
    "module fail_json exit_json result dictionary",
    "action plugin base class",
    "callback plugin signal handler",
    "connection plugin remote host execution",
    "lookup plugin external data retrieval",
    "custom filter module Jinja2",
    "inventory plugin host discovery",
    "variable precedence fact gathering",
    "play step execution flow control",
    "vault encryption decryption manager",
    "error handling exception context",
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
