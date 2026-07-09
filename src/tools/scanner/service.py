import logging
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor

from tools.shared.exceptions import RepositoryError
from tools.domain.interfaces.doc_provider import DocProvider
from tools.domain.interfaces.parser import ParseFailure, RstParser
from tools.domain.report import (
    UNVERSIONED_KEY,
    DocumentScanResult,
    Issue,
    IssueCode,
    OrgScanResult,
    OverallStatus,
    RepoScanResult,
)
from tools.scanner.parsers.docutils.style import DocStyle

logger = logging.getLogger(__name__)


class ScannerService:
    """Discovers API endpoint documents in OTC docs repos.

    Emits a quality report (per :class:`DocumentScanResult`) describing,
    for every endpoint doc encountered, whether it could be fully parsed,
    partially parsed, or not parsed at all — plus the extracted data
    (parameters, examples) and per-section metrics.
    """

    def __init__(
        self,
        doc_provider: DocProvider,
        parser: RstParser,
        style_classifier: Callable[[str], DocStyle],
        max_workers: int,
        excluded_segments: Iterable[str] = (),
    ):
        self.doc_provider = doc_provider
        self.parser = parser
        self.style_classifier = style_classifier
        self.max_workers = max_workers
        # Always wrap in a fresh frozenset so each instance owns its own
        # object. Empty default = no exclusion (OTC-specific values come
        # from [scanner].excluded_segments in scan-config.toml).
        self.excluded_segments = frozenset(excluded_segments)

    # ------------------------------------------------------------------ #
    # Org-level scan
    # ------------------------------------------------------------------ #
    def scan_organization(
        self,
        org: str,
        api_ref_path: str,
        branch: str = "main",
    ) -> OrgScanResult:
        """Scan every eligible repo in `org` and aggregate per-document results.

        `api_ref_path` is the directory whose presence makes a repo
        eligible for scanning. It is required because the right value is
        application-specific; the scanner library does not assume one.
        """
        logger.info("Scanning organization %s (branch=%s)", org, branch)
        repos = self.doc_provider.list_repos(org)
        result = OrgScanResult(org=org, branch=branch, total_repos=len(repos))

        for repo in repos:
            try:
                if not self.doc_provider.path_exists(repo, branch, api_ref_path):
                    logger.debug("Skipping %s (no %s)", repo, api_ref_path)
                    result.skipped_repos.append(repo)
                    continue
            except RepositoryError as e:
                logger.warning("Skipping %s due to repo error: %s", repo, e)
                result.repos.append(
                    RepoScanResult(
                        repo=repo, branch=branch, has_api_ref=False, error=str(e)
                    )
                )
                continue

            repo_result = self.find_endpoints(repo=repo, branch=branch)
            result.repos.append(repo_result)

        result.eligible_repos = sum(1 for r in result.repos if r.has_api_ref)
        logger.info(
            "Org scan complete: %d/%d eligible, %d total documents",
            result.eligible_repos,
            result.total_repos,
            result.total_documents,
        )
        return result

    # ------------------------------------------------------------------ #
    # Repo-level scan
    # ------------------------------------------------------------------ #
    def find_endpoints(self, repo: str, branch: str = "main") -> RepoScanResult:
        """Scan one repository and return per-document parse results."""
        logger.info("Scanning repo %s@%s", repo, branch)
        result = RepoScanResult(repo=repo, branch=branch, has_api_ref=True)

        try:
            listing = self.doc_provider.list_files(repo, branch)
        except RepositoryError as e:
            logger.error("Failed to list files for %s: %s", repo, e)
            result.error = str(e)
            return result

        # A truncated tree means we only saw part of the repo — record it so
        # the result isn't mistaken for an authoritative clean scan (item 16).
        if listing.truncated:
            result.incomplete = True
            result.incomplete_reason = (
                listing.truncated_reason or "file tree truncated by provider"
            )
            logger.warning("File listing for %s is incomplete (truncated)", repo)

        # Drop files under excluded directories before any fetch happens, but
        # record which ones so the skip is visible in the report (item 17).
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

        # Fetch + parse files concurrently to keep org-level scans tractable.
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            doc_outcomes = list(
                pool.map(
                    lambda p: self._process_document(repo, p, branch),
                    included_paths,
                )
            )

        for path, outcome in zip(included_paths, doc_outcomes):
            if outcome is None:
                # Not an endpoint doc — recorded so we don't lose the inventory.
                result.non_endpoint_documents.append(path)
                continue

            result.documents.append(outcome)
            if outcome.overall_status in (OverallStatus.OK, OverallStatus.PARTIAL):
                key = outcome.api_version or UNVERSIONED_KEY
                result.documents_by_version.setdefault(key, []).append(outcome)

        return result

    # ------------------------------------------------------------------ #
    # Per-document
    # ------------------------------------------------------------------ #
    def _process_document(
        self, repo: str, path: str, branch: str
    ) -> DocumentScanResult | None:
        """Fetch, classify and parse a document.

        Returns ``None`` for non-endpoint docs (intro / conceptual pages)
        — these surface in :attr:`RepoScanResult.non_endpoint_documents`
        rather than as failure entries.

        For endpoint docs, returns a :class:`DocumentScanResult` that
        will have either a populated ``sections`` dict (success) or a
        single ``failure_reason`` (gating failure or unsupported style).
        """
        try:
            content = self.doc_provider.fetch_content(repo, path, branch)
        except Exception as e:
            logger.warning("Fetch failed for %s/%s: %s", repo, path, e)
            return DocumentScanResult(
                document=path,
                repo=repo,
                failure_reason=Issue(
                    code=IssueCode.FETCH_FAILED,
                    details=str(e),
                ),
            )

        style = self.style_classifier(content)

        if style is DocStyle.NOT_ENDPOINT:
            return None

        if style is DocStyle.S3_COMPATIBLE:
            return DocumentScanResult(
                document=path,
                repo=repo,
                failure_reason=Issue(
                    code=IssueCode.UNSUPPORTED_DOC_STYLE,
                    details="S3-style doc (Request Syntax / Sample Request layout)",
                ),
            )

        # Style-A → hand off to the parser.
        try:
            parsed = self.parser.parse(content, path)
        except ParseFailure as e:
            logger.warning("Parse failed for %s/%s: %s", repo, path, e)
            return DocumentScanResult(
                document=path,
                repo=repo,
                failure_reason=e.issue,
            )
        except Exception as e:
            logger.exception("Unexpected parser error for %s/%s", repo, path)
            return DocumentScanResult(
                document=path,
                repo=repo,
                failure_reason=Issue(
                    code=IssueCode.PARSER_ERROR,
                    details=f"parser raised: {e}",
                ),
            )

        return DocumentScanResult(
            document=path,
            repo=repo,
            method=parsed.method,
            uri=parsed.uri,
            title=parsed.title,
            api_version=parsed.api_version,
            sections=parsed.sections,
        )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _is_excluded(self, path: str) -> bool:
        return any(seg in self.excluded_segments for seg in path.split("/"))
