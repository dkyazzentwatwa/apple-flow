from __future__ import annotations

import difflib
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AgentTeam:
    slug: str
    category: str
    title: str
    summary: str
    team_md_path: Path
    preset_path: Path


class AgentTeamCatalog:
    """Read-only catalog for Codex agent teams stored under `agents/`.

    The catalog is intentionally lightweight and cacheable because it is used
    inside iMessage command handling paths.
    """

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.catalog_path = self.repo_root / "agents" / "catalog.toml"
        self.teams_root = self.repo_root / "agents" / "teams"
        self._loaded = False
        self._teams_by_slug: dict[str, AgentTeam] = {}

    def is_available(self) -> bool:
        return self.catalog_path.exists() and self.teams_root.exists()

    def list_teams(self) -> list[AgentTeam]:
        self._ensure_loaded()
        return list(self._teams_by_slug.values())

    def get_team(self, slug: str) -> AgentTeam | None:
        self._ensure_loaded()
        return self._teams_by_slug.get((slug or "").strip().lower())

    def suggest(self, slug: str, limit: int = 5) -> list[AgentTeam]:
        self._ensure_loaded()
        needle = (slug or "").strip().lower()
        if not needle:
            return list(self._teams_by_slug.values())[:limit]

        slugs = list(self._teams_by_slug.keys())
        close = difflib.get_close_matches(needle, slugs, n=limit, cutoff=0.2)
        picks: list[AgentTeam] = []
        seen: set[str] = set()

        for cand in close:
            team = self._teams_by_slug.get(cand)
            if team and team.slug not in seen:
                seen.add(team.slug)
                picks.append(team)

        if len(picks) < limit:
            for team in self._teams_by_slug.values():
                if needle in team.slug or needle in team.title.lower():
                    if team.slug in seen:
                        continue
                    seen.add(team.slug)
                    picks.append(team)
                if len(picks) >= limit:
                    break

        if len(picks) < limit:
            for team in self._teams_by_slug.values():
                if team.slug in seen:
                    continue
                picks.append(team)
                if len(picks) >= limit:
                    break

        return picks[:limit]

    def build_team_prompt_fallback(self, slug: str, max_chars: int = 1400) -> str:
        team = self.get_team(slug)
        if not team:
            return ""
        if not team.team_md_path.exists():
            return ""

        raw = team.team_md_path.read_text(encoding="utf-8")
        cleaned = re.sub(r"\n{3,}", "\n\n", raw).strip()
        if len(cleaned) > max_chars:
            cleaned = cleaned[: max_chars - 3].rstrip() + "..."

        return (
            f"Active team context ({team.slug}): {team.title}.\n"
            "Use this team contract as guidance for structure and quality.\n\n"
            f"{cleaned}"
        )

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True

        if not self.is_available():
            return

        data = tomllib.loads(self.catalog_path.read_text(encoding="utf-8"))
        teams = data.get("teams") or []

        for item in teams:
            slug = str(item.get("slug", "")).strip().lower()
            if not slug:
                continue
            category = str(item.get("category", "")).strip()
            title = str(item.get("title", slug)).strip()
            summary = str(item.get("summary", "")).strip()
            base = self.teams_root / slug
            team = AgentTeam(
                slug=slug,
                category=category,
                title=title,
                summary=summary,
                team_md_path=base / "TEAM.md",
                preset_path=base / "preset.toml",
            )
            self._teams_by_slug[slug] = team
