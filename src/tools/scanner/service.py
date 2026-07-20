import logging
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from tools.domain.report import OrgScanResult
from tools.scanner.eligibility import check_repository_eligibility
from tools.scanner.interfaces import DocProvider, RepositoryContextParser, RstParser
from tools.scanner.parsers.docutils.style import DocStyle, extract_document_title
from tools.shared.exceptions import ParseFailure, ProviderError
from tools.shared.ir import Document, Repository, Service
from tools.shared.scan import DocumentScanResult, Issue, IssueCode, RepositoryScanResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _FetchedDocument:
    path: str
    content: str | None = None
    failure: Document | None = None


class ScannerService:
    """Scan API endpoint documentation and produce quality reports."""

    def __init__(
        self,
        doc_provider: DocProvider,
        parser: RstParser,
        style_classifier: Callable[[str], DocStyle],
        max_workers: int,
        api_ref_path: str,
        excluded_segments: Iterable[str] = (),
    ):
        self.doc_provider = doc_provider
        self.parser = parser
        self.style_classifier = style_classifier
        self.max_workers = max_workers
        self.api_ref_path = api_ref_path.rstrip("/")
        self.excluded_segments = frozenset(excluded_segments)

    def scan_organization(
        self,
        org: str,
        branch: str = "main",
    ) -> OrgScanResult:
        """Scan every eligible repo in `org` and aggregate per-document results."""
        logger.info("Scanning organization %s (branch=%s)", org, branch)
        repos = self.doc_provider.list_repos(org)
        result = OrgScanResult(org=org, branch=branch, total_repos=len(repos))

        for repo in repos:
            repo_result = self.scan_repository(repo=repo, branch=branch)
            if (
                not isinstance(repo_result.repository, Service)
                and repo_result.failure_message is None
            ):
                logger.debug("Skipping %s (no %s)", repo, self.api_ref_path)
                result.skipped_repos.append(repo)
                continue
            result.repos.append(repo_result)

        result.eligible_repos = sum(
            isinstance(repo.repository, Service) for repo in result.repos
        )
        logger.info(
            "Org scan complete: %d/%d eligible, %d total documents",
            result.eligible_repos,
            result.total_repos,
            result.total_documents,
        )
        return result

    def scan_repository(self, repo: str, branch: str = "main") -> RepositoryScanResult:
        """Scan one repository and return per-document parse results."""
        logger.info("Scanning repo %s@%s", repo, branch)

        # Pin the snapshot to a commit before checking eligibility so the path
        # check and every content read observe the same repository snapshot.
        try:
            commit_hash = self.doc_provider.get_commit_hash(repo, branch)
        except ProviderError as e:
            # TODO(#70): let rate-limited ProviderError reach background-job
            # orchestration once durable retry state exists.
            error = f"Could not resolve commit for {repo}@{branch}: {e}"
            logger.error(error)
            return RepositoryScanResult(
                repository=Repository(repo=repo),
                branch=branch,
                error=error,
            )

        ref = commit_hash or branch
        eligibility = check_repository_eligibility(
            self.doc_provider,
            repo=repo,
            ref=ref,
            api_ref_path=self.api_ref_path,
        )
        if eligibility.interruption is not None:
            logger.error(
                "Could not check eligibility for %s@%s: %s",
                repo,
                ref,
                eligibility.interruption.message,
            )
            return RepositoryScanResult(
                repository=Repository(repo=repo),
                branch=branch,
                commit_hash=commit_hash,
                interruption=eligibility.interruption,
            )

        if not eligibility.has_api_ref:
            error = None
            if commit_hash is None:
                error = (
                    f"Cannot confirm {repo}@{branch}: commit could not be resolved "
                    f"and {self.api_ref_path} was not found"
                )
                logger.error(error)
            return RepositoryScanResult(
                repository=Repository(repo=repo),
                branch=branch,
                commit_hash=commit_hash,
                error=error,
            )

        try:
            listing = self.doc_provider.list_files(repo, ref)
        except ProviderError as e:
            logger.error("Failed to list files for %s: %s", repo, e)
            # Eligibility succeeded before listing failed, so the repository is
            # still a Service even though this scan produced no documents.
            return RepositoryScanResult(
                repository=Service(repo=repo),
                branch=branch,
                commit_hash=commit_hash,
                error=str(e),
            )

        incomplete_reason = None
        if listing.truncated:
            incomplete_reason = (
                listing.truncated_reason or "file tree truncated by provider"
            )
            logger.warning("File listing for %s is incomplete (truncated)", repo)

        unique_paths = list(dict.fromkeys(listing.paths))
        if len(unique_paths) != len(listing.paths):
            logger.warning(
                "Ignored %d duplicate path(s) returned for %s",
                len(listing.paths) - len(unique_paths),
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

        logger.debug("%s: %d candidate RST files", repo, len(included_paths))

        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            fetched_documents = list(
                pool.map(
                    lambda path: self._fetch_document(repo, path, ref),
                    included_paths,
                )
            )
            try:
                parser_context = self._build_parser_context(fetched_documents)
            except Exception as e:
                error = f"Failed to build parser context: {e}"
                logger.exception("%s for %s", error, repo)
                return RepositoryScanResult(
                    repository=Service(repo=repo),
                    branch=branch,
                    commit_hash=commit_hash,
                    excluded_documents=excluded_documents,
                    incomplete_reason=incomplete_reason,
                    error=error,
                )
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

        return RepositoryScanResult(
            repository=Service(repo=repo, documents=doc_outcomes),
            branch=branch,
            commit_hash=commit_hash,
            excluded_documents=excluded_documents,
            incomplete_reason=incomplete_reason,
        )

    def _fetch_document(self, repo: str, path: str, ref: str) -> _FetchedDocument:
        try:
            content = self.doc_provider.fetch_content(repo, path, ref)
        except Exception as e:
            logger.warning("Fetch failed for %s/%s: %s", repo, path, e)
            return _FetchedDocument(
                path=path,
                failure=Document(
                    path=path,
                    scan_result=DocumentScanResult(
                        failure_reason=Issue(
                            code=IssueCode.FETCH_FAILED,
                            details=str(e),
                        )
                    ),
                ),
            )
        return _FetchedDocument(path=path, content=content)

    def _build_parser_context(
        self, documents: list[_FetchedDocument]
    ) -> object | None:
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
        if document.failure is not None:
            return document.failure

        path = document.path
        content = document.content
        if content is None:  # pragma: no cover - guarded by _fetch_document
            raise ValueError(f"document content is missing for {path}")

        title = extract_document_title(content)
        style = self.style_classifier(content)

        if style is DocStyle.NOT_ENDPOINT:
            return Document(
                path=path,
                title=title,
                scan_result=DocumentScanResult(),
            )

        if style is DocStyle.S3_COMPATIBLE:
            return Document(
                path=path,
                title=title,
                scan_result=DocumentScanResult(
                    failure_reason=Issue(
                        code=IssueCode.UNSUPPORTED_DOC_STYLE,
                        details="S3-style doc (Request Syntax / Sample Request layout)",
                    )
                ),
            )

        try:
            if isinstance(self.parser, RepositoryContextParser):
                parsed = self.parser.parse(content, path, context=parser_context)
            else:
                parsed = self.parser.parse(content, path)
        except ParseFailure as e:
            logger.warning("Parse failed for %s/%s: %s", repo, path, e)
            return Document(
                path=path,
                title=title,
                scan_result=DocumentScanResult(failure_reason=e.issue),
            )
        except Exception as e:
            logger.exception("Unexpected parser error for %s/%s", repo, path)
            return Document(
                path=path,
                title=title,
                scan_result=DocumentScanResult(
                    failure_reason=Issue(
                        code=IssueCode.PARSER_ERROR,
                        details=f"parser raised: {e}",
                    )
                ),
            )

        return parsed

    def _is_excluded(self, path: str) -> bool:
        return any(seg in self.excluded_segments for seg in path.split("/"))
