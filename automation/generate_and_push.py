#!/usr/bin/env python3

import argparse
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class Settings:
    api_key: str
    model: str
    repo_path: Path
    output_dir: Path
    prompt_path: Path
    branch: str
    interval_seconds: int
    temperature: float
    max_tokens: int
    base_url: str | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Rapberg CZ lyrics with the OpenAI API and push them to GitHub."
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
        api_key=env("OPENAI_API_KEY"),
        model=env("OPENAI_MODEL", "gpt-5.4"),
        repo_path=repo_path,
        output_dir=output_dir,
        prompt_path=prompt_path,
        branch=os.getenv("RAPBERG_GIT_BRANCH", "main"),
        interval_seconds=int(os.getenv("RAPBERG_INTERVAL_SECONDS", "3600")),
        temperature=float(os.getenv("RAPBERG_TEMPERATURE", "1.0")),
        max_tokens=int(os.getenv("RAPBERG_MAX_TOKENS", "1800")),
        base_url=os.getenv("OPENAI_BASE_URL") or None,
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
        os.environ.setdefault(key.strip(), value.strip())


def build_client(settings: Settings):
    try:
        from openai import OpenAI
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Missing dependency 'openai'. Install it with 'pip install -r requirements.txt'."
        ) from exc

    kwargs = {"api_key": settings.api_key}
    if settings.base_url:
        kwargs["base_url"] = settings.base_url
    return OpenAI(**kwargs)


def generate_lyrics(settings: Settings, prompt: str) -> str:
    client = build_client(settings)
    response = client.responses.create(
        model=settings.model,
        temperature=settings.temperature,
        max_output_tokens=settings.max_tokens,
        input=prompt,
    )
    text = response.output_text.strip()
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
