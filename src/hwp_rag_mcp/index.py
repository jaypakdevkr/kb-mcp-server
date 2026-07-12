"""HWP/HWPX parsing, chunking, safe persistence, and FAISS retrieval."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
import uuid
from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from langchain_community.docstore.in_memory import InMemoryDocstore
from langchain_community.vectorstores import FAISS
from langchain_community.vectorstores.utils import DistanceStrategy
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .config import IndexConfig, resolve_dataset_dir, resolve_storage_root
from .embeddings import create_local_embeddings
from .models import (
    DocumentSummary,
    IndexState,
    IndexStatus,
    SearchResponse,
    SearchResult,
    SyncFailure,
    SyncReport,
)

SCHEMA_VERSION = 1
SUPPORTED_EXTENSIONS = {".hwp", ".hwpx"}

DocumentLoader = Callable[[Path], list[Document]]
EmbeddingsFactory = Callable[[], Embeddings]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return str(value)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


class IndexDataError(RuntimeError):
    """Persisted index data is missing, inconsistent, or corrupt."""


class IndexManager:
    """Manage one explicitly synchronized local HWP/HWPX dataset."""

    def __init__(
        self,
        dataset_dir: str | Path | None = None,
        *,
        storage_root: str | Path | None = None,
        model_name: str = "intfloat/multilingual-e5-small",
        chunk_size: int = 1_000,
        chunk_overlap: int = 150,
        embeddings_factory: EmbeddingsFactory | None = None,
        document_loader: DocumentLoader | None = None,
    ) -> None:
        self.config = IndexConfig(
            dataset_dir=resolve_dataset_dir(dataset_dir),
            storage_root=resolve_storage_root(storage_root),
            model_name=model_name,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        self._embeddings_factory = embeddings_factory or (
            lambda: create_local_embeddings(self.config.model_name)
        )
        self._document_loader = document_loader or self._load_hwp_documents
        self._embeddings: Embeddings | None = None
        self._lock = threading.RLock()

    @property
    def dataset_dir(self) -> Path:
        return self.config.dataset_dir

    @property
    def index_dir(self) -> Path:
        return self.config.index_dir

    def status(self) -> IndexStatus:
        """Compare a content-hashed dataset snapshot with its persisted manifest."""

        if not self.dataset_dir.exists():
            return self._status(
                "missing", f"Dataset directory does not exist: {self.dataset_dir}"
            )
        if not self.dataset_dir.is_dir():
            return self._status("missing", f"Dataset path is not a directory: {self.dataset_dir}")

        files = self._discover_files()
        if not files:
            return self._status("missing", "No .hwp or .hwpx files were found in the dataset.")

        try:
            manifest = self._read_manifest()
            self._validate_persisted_files(manifest)
        except (IndexDataError, OSError, ValueError, json.JSONDecodeError) as exc:
            state: IndexState = "missing" if not self.index_dir.exists() else "stale"
            return self._status(state, f"Index is not ready: {exc}")

        current_snapshot = self._snapshot(files)
        changed = self._changed_files(manifest.get("files", []), current_snapshot)
        config_changed = any(
            (
                manifest.get("dataset_dir") != str(self.dataset_dir),
                manifest.get("model_name") != self.config.model_name,
                manifest.get("chunk_size") != self.config.chunk_size,
                manifest.get("chunk_overlap") != self.config.chunk_overlap,
            )
        )
        if changed or config_changed:
            if config_changed:
                changed = sorted(set(changed + ["<index-configuration>"]))
            return self._status(
                "stale",
                "Dataset or index settings changed. Run sync before searching.",
                manifest=manifest,
                changed_files=changed,
            )
        return self._status(
            "current",
            "Index is current and ready for search.",
            manifest=manifest,
        )

    def sync(self, force: bool = False) -> SyncReport:
        """Rebuild the complete index and atomically replace the previous version."""

        with self._lock:
            if not self.dataset_dir.exists():
                return self._sync_report(
                    "missing", message=f"Dataset directory does not exist: {self.dataset_dir}"
                )
            if not self.dataset_dir.is_dir():
                return self._sync_report(
                    "missing", message=f"Dataset path is not a directory: {self.dataset_dir}"
                )

            files = self._discover_files()
            if not files:
                return self._sync_report(
                    "missing", message="No .hwp or .hwpx files were found in the dataset."
                )

            existing = self.status()
            if existing.state == "current" and not force:
                return self._sync_report(
                    "current",
                    chunk_count=existing.chunk_count,
                    message="Index is already current. Use --force to rebuild it.",
                )

            snapshot = self._snapshot(files)
            snapshot_by_relative = {item["relative_path"]: item for item in snapshot}
            chunks: list[Document] = []
            indexed_files: list[str] = []
            skipped_files: list[str] = []
            failed_files: list[SyncFailure] = []

            for path in files:
                relative_path = path.relative_to(self.dataset_dir).as_posix()
                try:
                    documents = self._document_loader(path)
                    if not documents:
                        skipped_files.append(relative_path)
                        continue
                    file_chunks = self._chunk_documents(
                        path,
                        relative_path,
                        snapshot_by_relative[relative_path]["sha256"],
                        documents,
                    )
                    if not file_chunks:
                        skipped_files.append(relative_path)
                        continue
                    chunks.extend(file_chunks)
                    indexed_files.append(relative_path)
                except Exception as exc:  # one bad source must not abort a dataset sync
                    failed_files.append(
                        SyncFailure(file_name=relative_path, error=self._safe_error(exc))
                    )

            if not chunks:
                return self._sync_report(
                    "stale" if self.index_dir.exists() else "missing",
                    indexed_files=indexed_files,
                    skipped_files=skipped_files,
                    failed_files=failed_files,
                    message="No searchable chunks were produced; the previous index was preserved.",
                )

            try:
                store = self._build_store(chunks)
                self._persist_store(
                    store,
                    snapshot,
                    indexed_files=indexed_files,
                    skipped_files=skipped_files,
                    failed_files=failed_files,
                )
            except Exception as exc:
                failed_files.append(SyncFailure(file_name="<index>", error=self._safe_error(exc)))
                return self._sync_report(
                    "stale" if self.index_dir.exists() else "missing",
                    indexed_files=indexed_files,
                    skipped_files=skipped_files,
                    failed_files=failed_files,
                    message="Index construction failed; the previous index was preserved.",
                )

            return self._sync_report(
                "current",
                indexed_files=indexed_files,
                skipped_files=skipped_files,
                failed_files=failed_files,
                chunk_count=len(chunks),
                message="Index synchronization completed.",
            )

    def list_documents(self) -> list[DocumentSummary]:
        """List files represented by the last valid persisted index."""

        try:
            manifest = self._read_manifest()
            self._validate_persisted_files(manifest)
            payload = self._read_documents_payload()
        except (IndexDataError, OSError, ValueError, json.JSONDecodeError):
            return []

        summaries: dict[tuple[str, str, str], int] = defaultdict(int)
        for item in payload["documents"]:
            metadata = item["metadata"]
            key = (
                str(metadata.get("file_name", "")),
                str(metadata.get("source", "")),
                str(metadata.get("file_type", "")),
            )
            summaries[key] += 1
        return [
            DocumentSummary(
                file_name=file_name,
                source=source,
                file_type=file_type,
                chunk_count=chunk_count,
            )
            for (file_name, source, file_type), chunk_count in sorted(summaries.items())
        ]

    def search(
        self,
        query: str,
        top_k: int = 5,
        file_names: list[str] | None = None,
    ) -> SearchResponse:
        """Return ranked local evidence only when the index exactly matches the dataset."""

        query = query.strip()
        if not query:
            raise ValueError("query must not be empty")
        if not 1 <= top_k <= 20:
            raise ValueError("top_k must be between 1 and 20")

        index_status = self.status()
        if index_status.state != "current":
            reason = "index_missing" if index_status.state == "missing" else "index_stale"
            return SearchResponse(
                status=index_status.state,
                query=query,
                message=f"{reason}: {index_status.message} Call sync_index before searching.",
                stale_files=index_status.changed_files,
            )

        store = self._load_store()
        metadata_filter: dict[str, Any] | None = None
        if file_names is not None:
            cleaned = sorted({name.strip() for name in file_names if name.strip()})
            if not cleaned:
                raise ValueError("file_names must contain at least one non-empty name")
            metadata_filter = {"file_name": {"$in": cleaned}}

        matches = store.similarity_search_with_score(
            query,
            k=top_k,
            filter=metadata_filter,
            fetch_k=max(20, top_k * 4),
        )
        results: list[SearchResult] = []
        for rank, (document, score) in enumerate(matches, start=1):
            metadata = document.metadata
            results.append(
                SearchResult(
                    rank=rank,
                    score=float(score),
                    text=document.page_content,
                    chunk_id=str(metadata.get("chunk_id", "")),
                    source=str(metadata.get("source", "")),
                    file_name=str(metadata.get("file_name", "")),
                    file_type=str(metadata.get("file_type", "")),
                    element_type=str(metadata.get("element_type", "document")),
                )
            )
        return SearchResponse(
            status="current",
            query=query,
            results=results,
            message=f"Returned {len(results)} evidence chunk(s).",
        )

    def _status(
        self,
        state: IndexState,
        message: str,
        *,
        manifest: dict[str, Any] | None = None,
        changed_files: list[str] | None = None,
    ) -> IndexStatus:
        manifest = manifest or {}
        return IndexStatus(
            state=state,
            dataset_dir=str(self.dataset_dir),
            index_dir=str(self.index_dir),
            document_count=int(manifest.get("document_count", 0)),
            chunk_count=int(manifest.get("chunk_count", 0)),
            changed_files=changed_files or [],
            message=message,
        )

    def _sync_report(
        self,
        state: IndexState,
        *,
        indexed_files: list[str] | None = None,
        skipped_files: list[str] | None = None,
        failed_files: list[SyncFailure] | None = None,
        chunk_count: int = 0,
        message: str,
    ) -> SyncReport:
        return SyncReport(
            state=state,
            dataset_dir=str(self.dataset_dir),
            indexed_files=indexed_files or [],
            skipped_files=skipped_files or [],
            failed_files=failed_files or [],
            chunk_count=chunk_count,
            message=message,
        )

    def _discover_files(self) -> list[Path]:
        root = self.dataset_dir.resolve(strict=False)
        files: list[Path] = []
        for path in self.dataset_dir.rglob("*"):
            if path.is_symlink() or not path.is_file():
                continue
            if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            resolved = path.resolve(strict=False)
            try:
                resolved.relative_to(root)
            except ValueError:
                continue
            files.append(resolved)
        return sorted(files, key=lambda item: item.relative_to(root).as_posix())

    def _snapshot(self, files: Iterable[Path]) -> list[dict[str, Any]]:
        snapshot: list[dict[str, Any]] = []
        for path in files:
            stat = path.stat()
            snapshot.append(
                {
                    "relative_path": path.relative_to(self.dataset_dir).as_posix(),
                    "size": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                    "sha256": _sha256_file(path),
                }
            )
        return snapshot

    @staticmethod
    def _changed_files(
        stored: list[dict[str, Any]], current: list[dict[str, Any]]
    ) -> list[str]:
        stored_map = {str(item.get("relative_path")): item for item in stored}
        current_map = {str(item.get("relative_path")): item for item in current}
        changed: list[str] = []
        for name in sorted(set(stored_map) | set(current_map)):
            if stored_map.get(name) != current_map.get(name):
                changed.append(name)
        return changed

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        text = str(exc).strip()
        return f"{exc.__class__.__name__}: {text}" if text else exc.__class__.__name__

    def _load_hwp_documents(self, path: Path) -> list[Document]:
        from langchain_hwp_hwpx import HwpHwpxLoader

        loader = HwpHwpxLoader(
            file_path=path,
            mode="elements",
            include_images=False,
            on_encrypted="placeholder",
            on_invalid="placeholder",
            on_error="raise",
            include_extracted_at=False,
        )
        documents = list(loader.lazy_load())
        return [
            doc
            for doc in documents
            if doc.metadata.get("status") not in {"encrypted", "invalid"}
        ]

    def _chunk_documents(
        self,
        path: Path,
        relative_path: str,
        file_hash: str,
        documents: list[Document],
    ) -> list[Document]:
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.config.chunk_size,
            chunk_overlap=self.config.chunk_overlap,
            separators=["\n\n", "\n", ". ", "! ", "? ", " ", ""],
            keep_separator="end",
            length_function=len,
        )
        chunks: list[Document] = []
        for source_index, document in enumerate(documents):
            content = document.page_content.strip()
            if not content:
                continue
            metadata = dict(document.metadata)
            metadata.update(
                {
                    "source": str(path),
                    "relative_path": relative_path,
                    "file_name": path.name,
                    "file_type": path.suffix.lower().lstrip("."),
                    "source_element_index": metadata.get("element_index", source_index),
                }
            )
            prepared = Document(page_content=content, metadata=metadata)
            element_type = str(metadata.get("element_type", "document"))
            if element_type != "body" and len(content) <= self.config.chunk_size:
                split_documents = [prepared]
            else:
                split_documents = splitter.split_documents([prepared])

            for chunk_index, chunk in enumerate(split_documents):
                chunk.metadata["chunk_index"] = chunk_index
                identity = "\0".join(
                    (
                        relative_path,
                        file_hash,
                        element_type,
                        str(metadata["source_element_index"]),
                        str(chunk_index),
                        chunk.page_content,
                    )
                )
                chunk_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()
                chunk.metadata["chunk_id"] = chunk_id
                chunks.append(chunk)
        return chunks

    def _get_embeddings(self) -> Embeddings:
        if self._embeddings is None:
            self._embeddings = self._embeddings_factory()
        return self._embeddings

    def _build_store(self, documents: list[Document]) -> FAISS:
        embeddings = self._get_embeddings()
        # Import FAISS after the Torch-backed embedder. On macOS ARM, loading FAISS's
        # native runtime before Torch can cause an OpenMP shutdown crash.
        import faiss

        vectors = np.asarray(
            embeddings.embed_documents([doc.page_content for doc in documents]),
            dtype="float32",
        )
        if vectors.ndim != 2 or vectors.shape[0] != len(documents) or vectors.shape[1] == 0:
            raise ValueError("Embedding model returned an invalid vector matrix")
        faiss.normalize_L2(vectors)
        index = faiss.IndexFlatIP(int(vectors.shape[1]))
        index.add(vectors)
        docstore_values = {str(doc.metadata["chunk_id"]): doc for doc in documents}
        index_to_docstore_id = {
            position: str(doc.metadata["chunk_id"])
            for position, doc in enumerate(documents)
        }
        return FAISS(
            embedding_function=embeddings,
            index=index,
            docstore=InMemoryDocstore(docstore_values),
            index_to_docstore_id=index_to_docstore_id,
            distance_strategy=DistanceStrategy.MAX_INNER_PRODUCT,
        )

    def _persist_store(
        self,
        store: FAISS,
        snapshot: list[dict[str, Any]],
        *,
        indexed_files: list[str],
        skipped_files: list[str],
        failed_files: list[SyncFailure],
    ) -> None:
        import faiss

        self.config.storage_root.mkdir(parents=True, exist_ok=True)
        temp_dir = self.config.storage_root / f".{self.index_dir.name}.tmp-{uuid.uuid4().hex}"
        backup_dir = self.config.storage_root / f".{self.index_dir.name}.bak-{uuid.uuid4().hex}"
        temp_dir.mkdir(parents=False)

        try:
            index_path = temp_dir / "index.faiss"
            documents_path = temp_dir / "documents.json"
            manifest_path = temp_dir / "manifest.json"
            faiss.write_index(store.index, str(index_path))

            ordered_documents: list[dict[str, Any]] = []
            mapping: dict[str, str] = {}
            for position in range(store.index.ntotal):
                document_id = store.index_to_docstore_id[position]
                document = store.docstore.search(document_id)
                if not isinstance(document, Document):
                    raise IndexDataError(f"Missing document for vector position {position}")
                mapping[str(position)] = document_id
                ordered_documents.append(
                    {
                        "id": document_id,
                        "page_content": document.page_content,
                        "metadata": _json_safe(document.metadata),
                    }
                )
            _write_json(
                documents_path,
                {
                    "schema_version": SCHEMA_VERSION,
                    "documents": ordered_documents,
                    "index_to_docstore_id": mapping,
                },
            )

            document_names = {
                str(item["metadata"].get("relative_path", "")) for item in ordered_documents
            }
            manifest = {
                "schema_version": SCHEMA_VERSION,
                "created_at": _utc_now(),
                "dataset_dir": str(self.dataset_dir),
                "model_name": self.config.model_name,
                "chunk_size": self.config.chunk_size,
                "chunk_overlap": self.config.chunk_overlap,
                "document_count": len(document_names),
                "chunk_count": len(ordered_documents),
                "files": snapshot,
                "indexed_files": indexed_files,
                "skipped_files": skipped_files,
                "failed_files": [item.model_dump() for item in failed_files],
                "index_sha256": _sha256_file(index_path),
                "documents_sha256": _sha256_file(documents_path),
            }
            _write_json(manifest_path, manifest)

            old_exists = self.index_dir.exists()
            if old_exists:
                os.replace(self.index_dir, backup_dir)
            try:
                os.replace(temp_dir, self.index_dir)
            except Exception:
                if old_exists and backup_dir.exists():
                    os.replace(backup_dir, self.index_dir)
                raise
            if backup_dir.exists():
                shutil.rmtree(backup_dir)
        finally:
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
            if backup_dir.exists() and not self.index_dir.exists():
                os.replace(backup_dir, self.index_dir)
            elif backup_dir.exists():
                shutil.rmtree(backup_dir)

    def _read_manifest(self) -> dict[str, Any]:
        path = self.index_dir / "manifest.json"
        if not path.is_file():
            raise IndexDataError("manifest.json is missing")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
            raise IndexDataError("Unsupported or invalid manifest schema")
        if not isinstance(payload.get("files"), list):
            raise IndexDataError("Manifest files list is invalid")
        return payload

    def _validate_persisted_files(self, manifest: dict[str, Any]) -> None:
        index_path = self.index_dir / "index.faiss"
        documents_path = self.index_dir / "documents.json"
        if not index_path.is_file() or not documents_path.is_file():
            raise IndexDataError("Persisted FAISS or document data is missing")
        if manifest.get("index_sha256") != _sha256_file(index_path):
            raise IndexDataError("FAISS index checksum does not match the manifest")
        if manifest.get("documents_sha256") != _sha256_file(documents_path):
            raise IndexDataError("Document data checksum does not match the manifest")

    def _read_documents_payload(self) -> dict[str, Any]:
        path = self.index_dir / "documents.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
            raise IndexDataError("Unsupported or invalid document data schema")
        documents = payload.get("documents")
        mapping = payload.get("index_to_docstore_id")
        if not isinstance(documents, list) or not isinstance(mapping, dict):
            raise IndexDataError("Document data collections are invalid")
        for item in documents:
            if not isinstance(item, dict):
                raise IndexDataError("Document entry must be an object")
            if not isinstance(item.get("id"), str):
                raise IndexDataError("Document id must be a string")
            if not isinstance(item.get("page_content"), str):
                raise IndexDataError("Document content must be a string")
            if not isinstance(item.get("metadata"), dict):
                raise IndexDataError("Document metadata must be an object")
        return payload

    def _load_store(self) -> FAISS:
        manifest = self._read_manifest()
        self._validate_persisted_files(manifest)
        payload = self._read_documents_payload()
        embeddings = self._get_embeddings()
        import faiss

        index = faiss.read_index(str(self.index_dir / "index.faiss"))
        documents = {
            item["id"]: Document(
                page_content=item["page_content"],
                metadata=item["metadata"],
            )
            for item in payload["documents"]
        }
        mapping = {
            int(position): document_id
            for position, document_id in payload["index_to_docstore_id"].items()
        }
        if len(mapping) != index.ntotal or set(mapping) != set(range(index.ntotal)):
            raise IndexDataError("Vector-to-document mapping does not match the FAISS index")
        if any(document_id not in documents for document_id in mapping.values()):
            raise IndexDataError("Vector mapping references an unknown document")
        return FAISS(
            embedding_function=embeddings,
            index=index,
            docstore=InMemoryDocstore(documents),
            index_to_docstore_id=mapping,
            distance_strategy=DistanceStrategy.MAX_INNER_PRODUCT,
        )
