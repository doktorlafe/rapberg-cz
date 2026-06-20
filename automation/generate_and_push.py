#!/usr/bin/env python3

import argparse
import json
import os
import subprocess
import sys
import time
from urllib import error, request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class Settings:
    api_url: str
    api_auth_token: str
    api_auth_header: str
    api_auth_scheme: str
    api_style: str
    api_version: str
    deployment: str | None
    model: str
    repo_path: Path
    output_dir: Path
    prompt_path: Path
    branch: str
    interval_seconds: int
    temperature: float
    max_tokens: int
    request_format: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Rapberg CZ lyrics with a configurable text API and push them to GitHub."
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Generate and push a single track, then exit.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate the file without committing or pushing.",
    )
    return parser.parse_args()


def env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None or value == "":
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def load_settings() -> Settings:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    repo_path = Path(os.getenv("RAPBERG_REPO_PATH", Path(__file__).resolve().parents[1])).resolve()
    output_dir = repo_path / os.getenv("RAPBERG_OUTPUT_DIR", "lyrics/generated")
    prompt_path = repo_path / "prompts" / "rap_prompt.txt"
    return Settings(
        api_url=env("RAPBERG_API_URL"),
        api_auth_token=env("RAPBERG_API_AUTH_TOKEN"),
        api_auth_header=env("RAPBERG_API_AUTH_HEADER", "Authorization"),
        api_auth_scheme=os.getenv("RAPBERG_API_AUTH_SCHEME", "Bearer"),
        api_style=os.getenv("RAPBERG_API_STYLE", "openai_compatible"),
        api_version=os.getenv("RAPBERG_API_VERSION", "2024-10-21"),
        deployment=os.getenv("RAPBERG_DEPLOYMENT") or None,
        model=env("RAPBERG_MODEL", "gpt-5.4"),
        repo_path=repo_path,
        output_dir=output_dir,
        prompt_path=prompt_path,
        branch=os.getenv("RAPBERG_GIT_BRANCH", "main"),
        interval_seconds=int(os.getenv("RAPBERG_INTERVAL_SECONDS", "3600")),
        temperature=float(os.getenv("RAPBERG_TEMPERATURE", "1.0")),
        max_tokens=int(os.getenv("RAPBERG_MAX_TOKENS", "1800")),
        request_format=os.getenv("RAPBERG_REQUEST_FORMAT", "chat_completions"),
    )


def load_prompt(prompt_path: Path) -> str:
    if not prompt_path.exists():
        raise RuntimeError(f"Prompt file not found: {prompt_path}")
    return prompt_path.read_text(encoding="utf-8")


def load_dotenv(env_path: Path) -> None:
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        cleaned = value.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), cleaned)


def build_headers(settings: Settings) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
    }
    auth_value = settings.api_auth_token
    if settings.api_auth_scheme:
        auth_value = f"{settings.api_auth_scheme} {auth_value}"
    headers[settings.api_auth_header] = auth_value
    return headers


def build_request_url(settings: Settings) -> str:
    base_url = settings.api_url.rstrip("/")

    if settings.api_style == "azure_openai":
        deployment = settings.deployment or settings.model
        resource_root = base_url
        if resource_root.endswith("/openai/v1"):
            resource_root = resource_root[: -len("/openai/v1")]
        elif "/openai/deployments/" in resource_root:
            resource_root = resource_root.split("/openai/deployments/", 1)[0]
        elif resource_root.endswith("/openai"):
            resource_root = resource_root[: -len("/openai")]
        if settings.request_format == "chat_completions":
            return (
                f"{resource_root}/openai/deployments/{deployment}/chat/completions"
                f"?api-version={settings.api_version}"
            )
        if settings.request_format == "responses":
            return (
                f"{resource_root}/openai/deployments/{deployment}/responses"
                f"?api-version={settings.api_version}"
            )

    if settings.request_format == "responses" and not base_url.endswith("/responses"):
        return f"{base_url}/responses"
    if settings.request_format == "chat_completions" and not base_url.endswith("/chat/completions"):
        return f"{base_url}/chat/completions"
    return base_url


def build_payload(settings: Settings, prompt: str) -> dict:
    if settings.request_format == "responses":
        payload = {
            "model": settings.model,
            "input": prompt,
            "temperature": settings.temperature,
            "max_output_tokens": settings.max_tokens,
        }
        if settings.api_style == "azure_openai":
            payload.pop("model", None)
        return payload

    if settings.request_format == "chat_completions":
        payload = {
            "model": settings.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            "temperature": settings.temperature,
            "max_tokens": settings.max_tokens,
        }
        if settings.api_style == "azure_openai":
            payload.pop("model", None)
        return payload

    raise RuntimeError(
        "Unsupported RAPBERG_REQUEST_FORMAT. Use 'chat_completions' or 'responses'."
    )


def extract_response_text(settings: Settings, response_data: dict) -> str:
    if settings.request_format == "responses":
        text = response_data.get("output_text", "").strip()
        if text:
            return text

        output = response_data.get("output", [])
        for item in output:
            for content in item.get("content", []):
                text = content.get("text", "").strip()
                if text:
                    return text

    if settings.request_format == "chat_completions":
        choices = response_data.get("choices", [])
        if choices:
            message = choices[0].get("message", {})
            content = message.get("content", "")
            if isinstance(content, str):
                return content.strip()
            if isinstance(content, list):
                parts = []
                for item in content:
                    text = item.get("text")
                    if text:
                        parts.append(text)
                return "\n".join(parts).strip()

    raise RuntimeError("Could not extract text from API response")


def generate_lyrics(settings: Settings, prompt: str) -> str:
    payload = build_payload(settings, prompt)
    body = json.dumps(payload).encode("utf-8")
    api_request = request.Request(
        build_request_url(settings),
        data=body,
        headers=build_headers(settings),
        method="POST",
    )

    try:
        with request.urlopen(api_request) as response:
            response_data = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"API request failed with status {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Could not reach API: {exc.reason}") from exc

    text = extract_response_text(settings, response_data)
    if not text:
        raise RuntimeError("Model returned an empty response")
    return text


def slugify(value: str) -> str:
    allowed = []
    for char in value.lower():
        if char.isalnum():
            allowed.append(char)
        elif char in {" ", "-", "_"}:
            allowed.append("-")
    slug = "".join(allowed).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "untitled-track"


def extract_title(markdown_text: str) -> str:
    for line in markdown_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return "Untitled Track"


def write_track(settings: Settings, lyrics: str) -> Path:
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    title = extract_title(lyrics)
    file_name = f"{timestamp}-{slugify(title)}.md"
    destination = settings.output_dir / file_name
    destination.write_text(lyrics + "\n", encoding="utf-8")
    return destination


def run_git(repo_path: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_path,
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout.strip()


def ensure_clean_branch(settings: Settings) -> None:
    branch = run_git(settings.repo_path, "rev-parse", "--abbrev-ref", "HEAD")
    if branch != settings.branch:
        raise RuntimeError(
            f"Repository is on branch '{branch}', expected '{settings.branch}'."
        )


def commit_and_push(settings: Settings, track_path: Path) -> None:
    relative_path = track_path.relative_to(settings.repo_path)
    run_git(settings.repo_path, "add", str(relative_path))
    status = run_git(settings.repo_path, "status", "--short")
    if not status:
        return
    title = extract_title(track_path.read_text(encoding="utf-8"))
    commit_message = f"Add generated track: {title}"
    run_git(settings.repo_path, "commit", "-m", commit_message)
    run_git(settings.repo_path, "push", "origin", settings.branch)


def generate_cycle(settings: Settings, dry_run: bool) -> Path:
    ensure_clean_branch(settings)
    prompt = load_prompt(settings.prompt_path)
    lyrics = generate_lyrics(settings, prompt)
    track_path = write_track(settings, lyrics)
    if not dry_run:
        commit_and_push(settings, track_path)
    return track_path


def main() -> int:
    args = parse_args()
    settings = load_settings()
    try:
        if args.once:
            track_path = generate_cycle(settings, args.dry_run)
            print(f"Created {track_path}")
            return 0

        while True:
            track_path = generate_cycle(settings, args.dry_run)
            print(f"Created {track_path}")
            time.sleep(settings.interval_seconds)
    except KeyboardInterrupt:
        print("Stopped by user.")
        return 130
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
