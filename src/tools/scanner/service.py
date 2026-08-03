import logging
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from tools.scanner.interfaces import DocProvider, RepositoryContextParser, RstParser
from tools.scanner.parsers import (
    extract_document_title,
)
from tools.scanner.parsers.docutils.types import DocStyle
from tools.scanner.repositories import check_repository_eligibility
from tools.shared.exceptions import ParseFailure, ProviderError
from tools.shared.ir import Document, Repository, Service
from tools.shared.scan import DocumentScanResult, Issue, IssueCode, RepositoryScanResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _FetchedDocument:
    path: str
    content: str | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        if (self.content is None) == (self.error is None):
            raise ValueError("Exactly one of 'content' or 'error' must be provided")


class ScannerService:
    """Scan one repository's API documentation into a canonical scan result.

    One repository per call, and no derived numbers: scanning a whole
    organization needs durable job state to resume after a rate limit, and an
    aggregate must have a single definition. Both belong to the panel.
    """

    def __init__(
        self,
        doc_provider: DocProvider,
        parser: RstParser,
        style_classifier: Callable[[str], DocStyle],
        max_workers: int,
        api_ref_path: str,
        excluded_segments: Iterable[str] = (),
    ) -> None:
        self.doc_provider = doc_provider
        self.parser = parser
        self.style_classifier = style_classifier
        self.max_workers = max_workers
        self.api_ref_path = api_ref_path.rstrip("/")
        self.excluded_segments = frozenset(excluded_segments)

    def scan_repository(self, repo: str, branch: str = "main") -> RepositoryScanResult:
        """Scan one repository and return per-document parse results.

        Every operation past commit resolution — eligibility, file listing,
        content fetches — reads at the resolved `commit_hash`, never at
        `branch` directly, so the result always represents one immutable
        repository snapshot. If the commit cannot be resolved, the scan
        stops immediately with an error result instead of falling back to
        the (mutable) branch name.
        """
        logger.info("Scanning repo %s@%s", repo, branch)
        try:
            commit_hash = self.doc_provider.get_commit_hash(repo, branch)
        except ProviderError as e:
            # TODO(#70): let rate-limited ProviderError reach background-job
            # orchestration once durable retry state exists.
            return self._unresolved_commit_result(repo, branch, str(e))

        if commit_hash is None:
            return self._unresolved_commit_result(
                repo, branch, "commit SHA could not be resolved"
            )

        eligibility = check_repository_eligibility(
            self.doc_provider,
            repo=repo,
            ref=commit_hash,
            api_ref_path=self.api_ref_path,
        )
        if eligibility.interruption is not None:
            logger.error(
                "Could not check eligibility for %s@%s: %s",
                repo,
                commit_hash,
                eligibility.interruption.message,
            )
            return RepositoryScanResult(
                repository=Repository(repo=repo),
                branch=branch,
                commit_hash=commit_hash,
                interruption=eligibility.interruption,
            )

        if not eligibility.has_api_ref:
            return RepositoryScanResult(
                repository=Repository(repo=repo),
                branch=branch,
                commit_hash=commit_hash,
            )

        try:
            listing = self.doc_provider.list_files(repo, commit_hash)
        except ProviderError as e:
            # TODO(#70): same rate-limit-to-background-job gap as above.
            logger.error("Failed to list files for %s: %s", repo, e)
            return self._failed_service_result(repo, branch, commit_hash, str(e))

        if listing.truncated:
            # A capped tree means we never saw the complete pinned snapshot,
            # so this is a failed scan, not a partial-but-clean one.
            error = listing.truncated_reason or "file tree truncated by provider"
            logger.error("File listing for %s is incomplete: %s", repo, error)
            return self._failed_service_result(repo, branch, commit_hash, error)

        included_paths, excluded_documents = self._list_and_filter_paths(
            repo, listing.paths
        )
        logger.debug("%s: %d candidate RST files", repo, len(included_paths))

        doc_outcomes, error = self._scan_documents(repo, commit_hash, included_paths)
        if error:
            return self._failed_service_result(
                repo,
                branch,
                commit_hash,
                error,
                excluded_documents=excluded_documents,
            )

        return RepositoryScanResult(
            repository=Service(repo=repo, documents=doc_outcomes),
            branch=branch,
            commit_hash=commit_hash,
            excluded_documents=excluded_documents,
        )

    def _unresolved_commit_result(
        self, repo: str, branch: str, reason: str
    ) -> RepositoryScanResult:
        """Build the error result for a repo whose commit could not be resolved.

        Shared by the two ways `get_commit_hash` can fail to produce one: it
        raises (an operational `ProviderError`), or it returns `None` (the ref
        is confirmed not to exist). Both leave the scan with nothing safe to
        read `repo` at, so both are reported the same way.
        """
        error = f"Could not resolve commit for {repo}@{branch}: {reason}"
        logger.error(error)
        return RepositoryScanResult(
            repository=Repository(repo=repo),
            branch=branch,
            error=error,
        )

    def _failed_service_result(
        self,
        repo: str,
        branch: str,
        commit_hash: str,
        error: str,
        *,
        excluded_documents: list[str] | None = None,
    ) -> RepositoryScanResult:
        """Build the error result for a repo confirmed eligible but not fully read.

        Shared by every failure after eligibility is confirmed: listing
        failed, the tree was truncated, or fetching/parsing the documents
        failed. `repository` stays a documentless `Service` - the repo does
        have an `api-ref` path, the scan just could not read it completely.
        """
        return RepositoryScanResult(
            repository=Service(repo=repo),
            branch=branch,
            commit_hash=commit_hash,
            excluded_documents=excluded_documents or [],
            error=error,
        )

    def _list_and_filter_paths(
        self, repo: str, paths: list[str]
    ) -> tuple[list[str], list[str]]:
        """Deduplicate a file listing and split it into included/excluded paths.

        Takes an already-fetched path list rather than calling `list_files`
        itself, so the caller can reject a truncated listing before any path
        here is treated as the complete set.
        """
        unique_paths = list(dict.fromkeys(paths))
        if len(unique_paths) != len(paths):
            logger.warning(
                "Ignored %d duplicate path(s) returned for %s",
                len(paths) - len(unique_paths),
                repo,
            )

        included_paths: list[str] = []
        excluded_documents: list[str] = []
        for path in unique_paths:
            target = excluded_documents if self._is_excluded(path) else included_paths
            target.append(path)
        if excluded_documents:
            logger.info(
                "Skipped %d excluded doc(s) in %s (segments=%s)",
                len(excluded_documents),
                repo,
                sorted(self.excluded_segments),
            )

        return included_paths, excluded_documents

    def _scan_documents(
        self, repo: str, commit_hash: str, included_paths: list[str]
    ) -> tuple[list[Document], str | None]:
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            try:
                fetched_documents = list(
                    pool.map(
                        lambda path: self._fetch_document(repo, path, commit_hash),
                        included_paths,
                    )
                )
            except ProviderError as e:
                # TODO(#70): same rate-limit-to-background-job gap as in
                # scan_repository - this is the call site most likely to
                # actually trip one, since it fetches concurrently per file.
                error = f"Failed to fetch document content for {repo}: {e}"
                logger.error(error)
                return [], error
            try:
                parser_context = self._build_parser_context(fetched_documents)
            except Exception as e:
                error = f"Failed to build parser context: {e}"
                logger.exception("%s for %s", error, repo)
                return [], error
            doc_outcomes = list(
                pool.map(
                    lambda document: self._process_document(
                        repo,
                        document,
                        parser_context,
                    ),
                    fetched_documents,
                )
            )
        return doc_outcomes, None

    def _fetch_document(
        self, repo: str, path: str, commit_hash: str
    ) -> _FetchedDocument:
        try:
            content = self.doc_provider.fetch_content(repo, path, commit_hash)
        except ProviderError:
            # A transport failure means the pinned snapshot could not be read
            # in full, not that this one document is bad - propagate it so
            # _scan_documents fails the whole repository scan.
            raise
        except Exception as e:
            logger.warning("Fetch failed for %s/%s: %s", repo, path, e)
            return _FetchedDocument(path=path, error=str(e))
        return _FetchedDocument(path=path, content=content)

    def _build_parser_context(self, documents: list[_FetchedDocument]) -> object | None:
        if not isinstance(self.parser, RepositoryContextParser):
            return None
        contents = {
            document.path: document.content
            for document in documents
            if document.content is not None
        }
        return self.parser.build_repository_context(contents)

    def _process_document(
        self,
        repo: str,
        document: _FetchedDocument,
        parser_context: object | None,
    ) -> Document:
        """Classify and parse an already fetched document.

        The returned entity owns its scan result. Endpoint sections own their
        section-level results. Gating failures produce a plain document with a
        failure reason; non-endpoint docs produce a successful plain document.
        """
        if document.error is not None:
            return self._build_fallback_document(
                document.path,
                None,
                Issue(code=IssueCode.FETCH_FAILED, details=document.error),
            )

        path = document.path
        content = document.content
        if content is None:  # pragma: no cover - guarded by _fetch_document
            raise ValueError(f"document content is missing for {path}")

        style = self.style_classifier(content)

        if style is DocStyle.NOT_ENDPOINT:
            return self._build_fallback_document(path, content)

        if style is DocStyle.S3_COMPATIBLE:
            return self._build_fallback_document(
                path,
                content,
                Issue(
                    code=IssueCode.UNSUPPORTED_DOC_STYLE,
                    details="S3-style doc (Request Syntax / Sample Request layout)",
                ),
            )

        try:
            if isinstance(self.parser, RepositoryContextParser):
                return self.parser.parse(content, path, context=parser_context)
            else:
                return self.parser.parse(content, path)
        except ParseFailure as e:
            logger.warning("Parse failed for %s/%s: %s", repo, path, e)
            failure_reason = e.issue
        except Exception as e:
            logger.exception("Unexpected parser error for %s/%s", repo, path)
            failure_reason = Issue(
                code=IssueCode.PARSER_ERROR,
                details=f"parser raised: {e}",
            )

        return self._build_fallback_document(path, content, failure_reason)

    def _build_fallback_document(
        self, path: str, content: str | None, failure_reason: Issue | None = None
    ) -> Document:
        title = extract_document_title(content) if content is not None else None
        return Document(
            path=path,
            title=title,
            scan_result=DocumentScanResult(failure_reason=failure_reason),
        )

    def _is_excluded(self, path: str) -> bool:
        return any(seg in self.excluded_segments for seg in path.split("/"))
