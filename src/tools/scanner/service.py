import logging
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from tools.domain.report import OrgScanResult, analytics
from tools.scanner.eligibility import check_repository_eligibility
from tools.scanner.interfaces import DocProvider, RstParser
from tools.scanner.parsers.docutils.style import DocStyle
from tools.shared.exceptions import ParseFailure, ProviderError
from tools.shared.ir import Document, Endpoint, Repository, Service
from tools.shared.report import (
    UNVERSIONED_KEY,
    DocumentScanResult,
    Issue,
    IssueCode,
    OverallStatus,
    RepositoryScanResult,
    SectionScanResult,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _DocumentOutcome:
    document_result: DocumentScanResult
    section_results: list[SectionScanResult]


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
                and repo_result.error is None
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

    def scan_repository(
        self, repo: str, branch: str = "main"
    ) -> RepositoryScanResult:
        """Scan one repository and return per-document parse results."""
        logger.info("Scanning repo %s@%s", repo, branch)
        result = RepositoryScanResult(
            repository=Repository(repo=repo),
            branch=branch,
        )

        # Pin the snapshot to a commit before checking eligibility so the path
        # check and every content read observe the same repository snapshot.
        try:
            result.commit_hash = self.doc_provider.get_commit_hash(repo, branch)
        except ProviderError as e:
            # TODO(#70): let rate-limited ProviderError reach background-job
            # orchestration once durable retry state exists.
            result.error = f"Could not resolve commit for {repo}@{branch}: {e}"
            logger.error(result.error)
            return result

        ref = result.commit_hash or branch
        eligibility = check_repository_eligibility(
            self.doc_provider,
            repo=repo,
            ref=ref,
            api_ref_path=self.api_ref_path,
        )
        if eligibility.interruption is not None:
            result.interruption = eligibility.interruption
            result.error = (
                f"Could not check eligibility for {repo}@{ref}: "
                f"{eligibility.interruption.message}"
            )
            logger.error(result.error)
            return result

        if not eligibility.has_api_ref:
            if result.commit_hash is None:
                result.error = (
                    f"Cannot confirm {repo}@{branch}: commit could not be resolved "
                    f"and {self.api_ref_path} was not found"
                )
                logger.error(result.error)
            return result

        result.repository = Service(repo=repo)

        try:
            listing = self.doc_provider.list_files(repo, ref)
        except ProviderError as e:
            logger.error("Failed to list files for %s: %s", repo, e)
            result.error = str(e)
            return result

        if listing.truncated:
            result.incomplete = True
            result.incomplete_reason = (
                listing.truncated_reason or "file tree truncated by provider"
            )
            logger.warning("File listing for %s is incomplete (truncated)", repo)

        included_paths = [p for p in listing.paths if not self._is_excluded(p)]
        result.excluded_documents = [p for p in listing.paths if self._is_excluded(p)]
        if result.excluded_documents:
            logger.info(
                "Skipped %d excluded doc(s) in %s (segments=%s)",
                len(result.excluded_documents),
                repo,
                sorted(self.excluded_segments),
            )

        logger.debug("%s: %d candidate RST files", repo, len(included_paths))

        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            doc_outcomes = list(
                pool.map(
                    lambda p: self._process_document(repo, p, ref),
                    included_paths,
                )
            )

        for path, outcome in zip(included_paths, doc_outcomes):
            if outcome is None:
                result.non_endpoint_documents.append(path)
                continue

            document_result = outcome.document_result
            result.document_results.append(document_result)
            assert isinstance(result.repository, Service)
            result.repository.documents.append(document_result.document)
            result.section_results.extend(outcome.section_results)
            if analytics.doc_overall_status(
                document_result, outcome.section_results
            ) in (
                OverallStatus.OK,
                OverallStatus.PARTIAL,
            ):
                endpoint = document_result.document
                if not isinstance(endpoint, Endpoint):
                    continue
                key = endpoint.api_version or UNVERSIONED_KEY
                result.documents_by_version.setdefault(key, []).append(
                    document_result
                )

        return RepositoryScanResult.model_validate(result.model_dump(mode="json"))

    def _process_document(
        self, repo: str, path: str, branch: str
    ) -> _DocumentOutcome | None:
        """Fetch, classify and parse a document.

        Returns ``None`` for non-endpoint docs (intro / conceptual pages)
        — these surface in
        :attr:`RepositoryScanResult.non_endpoint_documents`
        rather than as failure entries.

        Endpoint data and section results remain separate in the returned
        outcome. Gating failures produce a plain ``Document`` with a failure
        reason and no section results.
        """
        try:
            content = self.doc_provider.fetch_content(repo, path, branch)
        except Exception as e:
            logger.warning("Fetch failed for %s/%s: %s", repo, path, e)
            return _DocumentOutcome(
                document_result=DocumentScanResult(
                    document=Document(path=path),
                    failure_reason=Issue(
                        code=IssueCode.FETCH_FAILED,
                        details=str(e),
                    ),
                ),
                section_results=[],
            )

        style = self.style_classifier(content)

        if style is DocStyle.NOT_ENDPOINT:
            return None

        if style is DocStyle.S3_COMPATIBLE:
            return _DocumentOutcome(
                document_result=DocumentScanResult(
                    document=Document(path=path),
                    failure_reason=Issue(
                        code=IssueCode.UNSUPPORTED_DOC_STYLE,
                        details="S3-style doc (Request Syntax / Sample Request layout)",
                    ),
                ),
                section_results=[],
            )

        try:
            parsed = self.parser.parse(content, path)
        except ParseFailure as e:
            logger.warning("Parse failed for %s/%s: %s", repo, path, e)
            return _DocumentOutcome(
                document_result=DocumentScanResult(
                    document=Document(path=path),
                    failure_reason=e.issue,
                ),
                section_results=[],
            )
        except Exception as e:
            logger.exception("Unexpected parser error for %s/%s", repo, path)
            return _DocumentOutcome(
                document_result=DocumentScanResult(
                    document=Document(path=path),
                    failure_reason=Issue(
                        code=IssueCode.PARSER_ERROR,
                        details=f"parser raised: {e}",
                    ),
                ),
                section_results=[],
            )

        return _DocumentOutcome(
            document_result=DocumentScanResult(document=parsed.endpoint),
            section_results=parsed.section_results,
        )

    def _is_excluded(self, path: str) -> bool:
        return any(seg in self.excluded_segments for seg in path.split("/"))
