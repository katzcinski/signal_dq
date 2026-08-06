"""Serialisiertes Git-Schreibmodell für Contracts (WS2-3 / R2-1).

- Prozess-übergreifendes Datei-Lock — Thread-Locks reichen bei ≥2
  uvicorn-Workern nicht (S-12). POSIX nutzt fcntl, Windows msvcrt; fehlt
  beides, bleibt nur ein Best-Effort-No-Op (siehe `_process_lock`).
- Commit committet AUSSCHLIESSLICH die Contract-Datei (`git commit --only`),
  nie fremd-gestagtes Material; Author = Principal, Committer via Env —
  keine Mutation der geteilten Repo-Config.
- Push auf GIT_REMOTE, Reject → GitPushRejected (API antwortet 409 mit
  Rebase-Hinweis).
"""
from __future__ import annotations

import hashlib
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

# fcntl ist POSIX-only und existiert auf Windows nicht. Dort fällt das
# Prozess-Lock auf msvcrt (byte-range lock) zurück. Fehlt auch das, gibt es
# kein OS-Lock — die Serialisierung über Worker-Prozesse hinweg ist dann
# nur Best-Effort (Thread-Locks im selben Prozess greifen weiterhin).
try:
    import fcntl
except ModuleNotFoundError:  # Windows
    fcntl = None
    try:
        import msvcrt
    except ModuleNotFoundError:  # pragma: no cover — exotische Plattform
        msvcrt = None
else:
    msvcrt = None


class GitPushRejected(Exception):
    """Remote hat den Push abgelehnt — Rebase/Pull nötig."""


class GitRepo:
    def __init__(self, contracts_dir: str, remote: str = ""):
        self.contracts_dir = Path(contracts_dir)
        self.remote = remote
        self.contracts_dir.mkdir(parents=True, exist_ok=True)
        self._lock_path = self.contracts_dir / ".git_write.lock"

    @contextmanager
    def _process_lock(self):
        with open(self._lock_path, "w") as lf:
            if fcntl is not None:
                # POSIX: blockierendes, exklusives flock (bisheriges Verhalten).
                fcntl.flock(lf, fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lf, fcntl.LOCK_UN)
            elif msvcrt is not None:
                # Windows: blockierendes byte-range Lock auf 1 Byte. LK_LOCK
                # gibt nach ~10 s auf — daher Retry-Schleife für echtes Blocken.
                lf.write("\0")
                lf.flush()
                lf.seek(0)
                while True:
                    try:
                        msvcrt.locking(lf.fileno(), msvcrt.LK_LOCK, 1)
                        break
                    except OSError:
                        continue
                try:
                    yield
                finally:
                    lf.seek(0)
                    msvcrt.locking(lf.fileno(), msvcrt.LK_UNLCK, 1)
            else:  # pragma: no cover — kein OS-Lock verfügbar
                # Best-Effort: nur der prozess-interne Thread-Schutz greift,
                # Multi-Worker-Serialisierung ist hier nicht garantiert (S-12).
                yield

    def _path(self, product: str) -> Path:
        """Resolve a contract path, tolerating both .yaml and .yml."""
        for ext in (".yaml", ".yml"):
            candidate = self.contracts_dir / f"{product}{ext}"
            if candidate.exists():
                return candidate
        return self.contracts_dir / f"{product}.yaml"

    def read_contract(self, product: str) -> Optional[str]:
        path = self._path(product)
        if path.exists():
            return path.read_text()
        return None

    def write_contract(
        self,
        product: str,
        content: str,
        author_name: str,
        author_email: str,
        message: str,
    ) -> str:
        """Serialisierter Write + Commit (+ Push, wenn Remote). Returns commit hash."""
        with self._process_lock():
            path = self._path(product)
            path.write_text(content)
            content_hash = hashlib.sha256(content.encode()).hexdigest()[:12]

            try:
                import git
            except ImportError:
                return content_hash

            try:
                repo = git.Repo(self.contracts_dir, search_parent_directories=True)
            except git.InvalidGitRepositoryError:
                # Externer CONTRACTS_DIR ohne Repo — legal im Lokalmodus.
                return content_hash

            try:
                rel_path = str(path.resolve().relative_to(repo.working_tree_dir))
            except ValueError:
                return content_hash

            author = f"{author_name} <{author_email}>"
            env = {
                "GIT_COMMITTER_NAME": author_name,
                "GIT_COMMITTER_EMAIL": author_email,
            }
            with repo.git.custom_environment(**env):
                repo.git.add("--", rel_path)
                try:
                    # --only: genau diese Datei, unabhängig vom restlichen Index (S-12)
                    repo.git.commit(
                        "-m", message, f"--author={author}", "--only", "--", rel_path
                    )
                except git.GitCommandError as exc:
                    if "nothing to commit" in str(exc) or "nichts zu committen" in str(exc):
                        return repo.head.commit.hexsha
                    raise

                if self.remote:
                    try:
                        repo.git.push(self.remote, "HEAD")
                    except git.GitCommandError as exc:
                        if "rejected" in str(exc) or "non-fast-forward" in str(exc):
                            raise GitPushRejected(
                                f"Push auf {self.remote!r} abgelehnt — Remote hat neuere "
                                "Commits. Pull/Rebase erforderlich, dann Approve wiederholen."
                            ) from exc
                        raise

            return repo.head.commit.hexsha

    def list_products(self) -> list:
        return [
            p.stem
            for p in sorted(self.contracts_dir.glob("*.y*ml"))
            if not p.name.endswith(".active.yml")
        ]

    def get_contract_hash(self, product: str) -> str:
        content = self.read_contract(product)
        if content is None:
            return ""
        return hashlib.sha256(content.encode()).hexdigest()
