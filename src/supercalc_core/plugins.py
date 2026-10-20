from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .api import Engine
from .models import RunResult

ALLOWED_PERMISSIONS = {
    "workspace.variables.read",
    "clipboard.write",
}


class PluginError(ValueError):
    pass


@dataclass
class PluginManifest:
    id: str
    name: str
    version: str
    api_version: int
    entry: str
    permissions: list[str] = field(default_factory=list)
    description: str = ""
    modules: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PluginManifest:
        required = {"id", "name", "version", "apiVersion", "entry"}
        missing = required - data.keys()
        if missing:
            raise PluginError(f"插件清单缺少字段：{', '.join(sorted(missing))}")
        permissions = [str(item) for item in data.get("permissions", [])]
        unknown = set(permissions) - ALLOWED_PERMISSIONS
        if unknown:
            raise PluginError(f"插件请求了未知权限：{', '.join(sorted(unknown))}")
        api_version = int(data["apiVersion"])
        if api_version != 1:
            raise PluginError(f"不支持的插件 API 版本：{api_version}")
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            version=str(data["version"]),
            api_version=api_version,
            entry=str(data["entry"]),
            permissions=permissions,
            description=str(data.get("description", "")),
            modules=[str(item) for item in data.get("modules", [])],
        )


@dataclass
class PluginPackage:
    root: Path
    manifest: PluginManifest
    sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": str(self.root),
            "id": self.manifest.id,
            "name": self.manifest.name,
            "version": self.manifest.version,
            "permissions": self.manifest.permissions,
            "sha256": self.sha256,
            "description": self.manifest.description,
        }


def _safe_relative(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    if root not in candidate.parents:
        raise PluginError("插件文件路径越界")
    return candidate


def load_plugin_package(directory: str | Path) -> PluginPackage:
    root = Path(directory).resolve()
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise PluginError("目录中没有 manifest.json")
    try:
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PluginError(f"无法读取插件清单：{exc}") from exc
    manifest = PluginManifest.from_dict(manifest_data)
    entry = _safe_relative(root, manifest.entry)
    if entry.suffix.lower() != ".scscript":
        raise PluginError("插件入口必须是 .scscript 文件")
    if not entry.is_file():
        raise PluginError("插件入口文件不存在")
    for module in manifest.modules:
        module_path = _safe_relative(root, module)
        if module_path.suffix.lower() != ".scscript" or not module_path.is_file():
            raise PluginError(f"插件模块无效：{module}")
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".scscript", ".json", ".md", ".txt"}:
            raise PluginError(f"不允许的文件类型：{path.relative_to(root)}")
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return PluginPackage(root=root, manifest=manifest, sha256=digest.hexdigest())


def execute_plugin(package: PluginPackage, engine: Engine | None = None) -> RunResult:
    engine = engine or Engine()
    engine.module_root = package.root
    entry = _safe_relative(package.root, package.manifest.entry)
    source = entry.read_text(encoding="utf-8")
    return engine.run_script(source)
