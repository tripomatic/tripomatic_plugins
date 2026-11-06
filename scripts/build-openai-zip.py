#!/usr/bin/env python3
"""Checks the OpenAI plugin package in plugins/tripomatic and writes dist/tripomatic-<version>.zip.

The rules are OpenAI's submission limits (https://developers.openai.com/plugins/deploy/submission).
The ZIP holds the plugin root (plugin.json, mcp.json, skills/, assets/) without the Claude-only
.claude-plugin/ folder. Standard library only; run from anywhere: python3 scripts/build-openai-zip.py
"""

import json
import re
import struct
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PLUGIN = REPO / "plugins" / "tripomatic"
DIST = REPO / "dist"

PLUGIN_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
MCP_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"
ROOT_KEYS = {"$schema", "name", "version", "description", "author", "homepage", "repository", "license", "keywords",
             "extensions"}
FORBIDDEN_KEYS = {"test_credentials", "reviewer_instructions"}
EXCLUDED_DIRS = {".claude-plugin"}
MAX_ASSET_BYTES = 5 * 1024 * 1024

errors: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


def check_text(value: object, field: str, limit: int, required: bool = True) -> None:
    if value is None:
        check(not required, f"{field} is required")
        return
    check(isinstance(value, str) and value.strip() != "", f"{field} must be a non-empty string")
    check(isinstance(value, str) and len(value) <= limit, f"{field} is longer than {limit} characters")


def check_url(value: object, field: str, limit: int = 1024) -> None:
    check_text(value, field, limit)
    check(isinstance(value, str) and value.startswith("https://") and "@" not in value,
          f"{field} must be an https URL without credentials")


def find_forbidden(node: object, path: str = "") -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            check(key not in FORBIDDEN_KEYS, f"{path}{key}: reviewer credentials never go in the package")
            find_forbidden(value, f"{path}{key}.")
    elif isinstance(node, list):
        for item in node:
            find_forbidden(item, path)


def luminance(hex_color: str) -> float:
    channels = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a: str, b: str) -> float:
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def png_size(path: Path) -> tuple[int, int] | None:
    header = path.read_bytes()[:24]
    if header[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", header[16:24])


def check_asset(value: object, field: str) -> None:
    if value is None:
        return
    check(isinstance(value, str) and value.startswith("./"), f"{field} must be a ./-relative path")
    if not isinstance(value, str):
        return
    path = PLUGIN / value
    if not path.is_file():
        errors.append(f"{field}: {value} does not exist")
        return
    check(path.stat().st_size <= MAX_ASSET_BYTES, f"{field}: {value} is larger than 5 MiB")
    size = png_size(path)
    check(size is not None, f"{field}: {value} must be a PNG (the only format this script checks)")
    if size:
        width, height = size
        check(width == height, f"{field}: {value} must be square, is {width}x{height}")
        check(48 <= width <= 4096, f"{field}: {value} must be 48-4096 px, is {width}")


def check_plugin(manifest: dict) -> None:
    check(manifest.get("$schema") == PLUGIN_SCHEMA, f"plugin.json $schema must be {PLUGIN_SCHEMA}")
    check(set(manifest) <= ROOT_KEYS, f"plugin.json has unknown root keys: {sorted(set(manifest) - ROOT_KEYS)}")
    name = manifest.get("name", "")
    check(isinstance(name, str) and len(name) <= 64 and re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name) is not None,
          "name must be lowercase letters, digits and single hyphens, at most 64 characters")
    check(re.fullmatch(r"\d+\.\d+\.\d+", str(manifest.get("version", ""))) is not None,
          "version must be an explicit semantic version")
    check_text(manifest.get("description"), "description", 4000)
    author = manifest.get("author", {})
    check_text(author.get("name"), "author.name", 120)
    check_text(author.get("email"), "author.email", 320, required=False)
    if "url" in author:
        check_url(author["url"], "author.url", 2048)
    if "homepage" in manifest:
        check_url(manifest["homepage"], "homepage", 2048)

    claude = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())
    check(claude.get("version") == manifest.get("version"),
          f"version {manifest.get('version')} differs from the Claude plugin's {claude.get('version')}")

    openai = manifest.get("extensions", {}).get("com.openai", {})
    interface = openai.get("interface", {})
    check_text(interface.get("displayName"), "interface.displayName", 30)
    check_text(interface.get("shortDescription"), "interface.shortDescription", 30)
    check("\n" not in interface.get("shortDescription", ""), "interface.shortDescription must be one line")
    check_text(interface.get("longDescription"), "interface.longDescription", 4000)
    check_text(interface.get("developerName"), "interface.developerName", 80)
    check_text(interface.get("category"), "interface.category", 80)
    for field in ("websiteURL", "supportURL", "privacyPolicyURL", "termsOfServiceURL"):
        check_url(interface.get(field), f"interface.{field}")

    capabilities = interface.get("capabilities", [])
    check(isinstance(capabilities, list) and len(capabilities) <= 20, "interface.capabilities: at most 20")
    for item in capabilities:
        check_text(item, "interface.capabilities item", 120)

    prompts = interface.get("defaultPrompt", [])
    prompts = [prompts] if isinstance(prompts, str) else prompts
    check(len(prompts) <= 3 and len(set(prompts)) == len(prompts), "interface.defaultPrompt: at most 3, unique")
    for prompt in prompts:
        check_text(prompt, "interface.defaultPrompt item", 128)
        check("@" not in prompt, "interface.defaultPrompt must not @mention apps")

    for field, background in (("brandColor", "#FFFFFF"), ("brandColorDark", "#212121")):
        color = interface.get(field)
        if color is None:
            continue
        check(re.fullmatch(r"#[0-9A-Fa-f]{6}", color) is not None, f"interface.{field} must be #RRGGBB")
        if re.fullmatch(r"#[0-9A-Fa-f]{6}", color):
            check(contrast(color, background) >= 2, f"interface.{field} needs 2:1 contrast against {background}")

    check(interface.get("logo") or interface.get("composerIcon"), "interface needs a logo or composerIcon")
    for field in ("composerIcon", "composerIconDark", "logo", "logoDark"):
        check_asset(interface.get(field), f"interface.{field}")

    cases = openai.get("review", {}).get("test_cases", {})
    positive, negative = cases.get("positive", []), cases.get("negative", [])
    check(len(positive) == 5, f"review needs 5 positive test cases, has {len(positive)}")
    check(len(negative) == 3, f"review needs 3 negative test cases, has {len(negative)}")
    for index, case in enumerate(positive, 1):
        for field in ("description", "prompt", "tools_triggered", "expected_behavior"):
            check_text(case.get(field), f"positive case {index} {field}", 4000)
    for index, case in enumerate(negative, 1):
        for field in ("description", "prompt"):
            check_text(case.get(field), f"negative case {index} {field}", 4000)

    countries = openai.get("publication", {}).get("countries")
    if countries is not None:
        check(all(re.fullmatch(r"[A-Z]{2}", c) for c in countries), "publication.countries must be ISO codes")


def check_mcp(config: dict) -> None:
    check(config.get("$schema") == MCP_SCHEMA, f"mcp.json $schema must be {MCP_SCHEMA}")
    servers = config.get("mcpServers", {})
    check(len(servers) == 1, f"mcp.json must declare exactly one server, has {len(servers)}")
    for name, server in servers.items():
        check(server.get("type") == "streamable-http", f"server {name}: type must be streamable-http")
        check_url(server.get("url"), f"server {name} url")
        check(not server.get("headers"), f"server {name}: headers are refused on submission")
        auth = server.get("extensions", {}).get("com.openai", {}).get("auth", {})
        check(auth.get("type") == "oauth", f"server {name}: the server needs sign-in, so auth.type must be oauth")
        check("clientId" not in auth.get("client", {}), f"server {name}: no client id with cimd/dcr")


def check_skills() -> None:
    skills = sorted(p for p in (PLUGIN / "skills").iterdir() if p.is_dir())
    check(len(skills) > 0, "no skills found")
    for skill in skills:
        file = skill / "SKILL.md"
        if not file.is_file():
            errors.append(f"{skill.name}: SKILL.md missing")
            continue
        match = re.match(r"---\n(.*?)\n---\n", file.read_text(), re.DOTALL)
        if not match:
            errors.append(f"{skill.name}: SKILL.md has no YAML header")
            continue
        header = match.group(1)
        name = re.search(r"^name:\s*(\S+)\s*$", header, re.MULTILINE)
        check(name is not None and name.group(1) == skill.name, f"{skill.name}: header name must equal the folder")
        check(re.search(r"^description:", header, re.MULTILINE) is not None, f"{skill.name}: description missing")


def package_files() -> list[Path]:
    files = []
    for path in sorted(PLUGIN.rglob("*")):
        relative = path.relative_to(PLUGIN)
        if path.is_file() and relative.parts[0] not in EXCLUDED_DIRS and path.name != ".DS_Store":
            files.append(relative)
    return files


def main() -> int:
    manifest = json.loads((PLUGIN / "plugin.json").read_text())
    find_forbidden(manifest)
    check_plugin(manifest)
    check_mcp(json.loads((PLUGIN / "mcp.json").read_text()))
    check_skills()
    if errors:
        print("The OpenAI package has problems:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    DIST.mkdir(exist_ok=True)
    target = DIST / f"tripomatic-{manifest['version']}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for relative in package_files():
            info = zipfile.ZipInfo(relative.as_posix(), date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, (PLUGIN / relative).read_bytes())
    print(f"Wrote {target.relative_to(REPO)}:")
    for relative in package_files():
        print(f"  {relative.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
