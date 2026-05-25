import logging
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor

from tools.domain.exceptions import RepositoryError
from tools.domain.interfaces.doc_provider import DocProvider
from tools.domain.interfaces.parser import RstParser
from tools.domain.ir import URI_RE
from tools.domain.report import DocumentScanResult, OrgScanResult, RepoScanResult

logger = logging.getLogger(__name__)

# Bucket key used in `documents_by_version` for documents whose api_version
# could not be determined. This is an internal output label, not configuration —
# downstream consumers rely on the exact string to find unversioned docs.
UNVERSIONED_KEY = "unversioned"


class ScannerService:
    """Discovers API endpoint documents in OTC docs repos.

    The scanner emits a structured result useful for evaluating the documentation
    set as a whole:
      * which repos contain an `api-ref/source/` directory and are eligible,
      * which documents within each repo can be parsed into Endpoint metadata,
      * which documents fail and why,
      * how parsed documents distribute across API versions.
    """

    def __init__(
        self,
        doc_provider: DocProvider,
        parser: RstParser,
        max_workers: int = 8,
        excluded_segments: Iterable[str] = (),
    ):
        self.doc_provider = doc_provider
        self.parser = parser
        self.max_workers = max_workers
        # Always wrap in a fresh frozenset so each instance owns its own object.
        # The empty default means "no exclusion" — OTC-specific values are
        # supplied by the application (see [scanner].excluded_segments in
        # scan-config.toml).
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

        `api_ref_path` is the directory whose presence makes a repo eligible
        for scanning (e.g. ``"api-ref/source"`` for OTC docs). It is required
        because the right value is application-specific; the scanner library
        does not assume one.
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
            "Org scan complete: %d/%d eligible, %d documents parsed, %d failed",
            result.eligible_repos,
            result.total_repos,
            result.total_parsed,
            result.total_failed,
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
            paths = self.doc_provider.list_files(repo, branch)
        except RepositoryError as e:
            logger.error("Failed to list files for %s: %s", repo, e)
            result.error = str(e)
            return result

        # Drop files under excluded directories (e.g. out-of-date_apis/).
        included_paths = [p for p in paths if not self._is_excluded(p)]
        excluded_count = len(paths) - len(included_paths)
        if excluded_count:
            logger.info(
                "Skipped %d excluded doc(s) in %s (segments=%s)",
                excluded_count,
                repo,
                sorted(self.excluded_segments),
            )

        logger.debug("%s: %d candidate RST files", repo, len(included_paths))

        # Fetch + parse files concurrently to keep org-level scans tractable.
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            doc_results = list(
                pool.map(
                    lambda p: self._process_document(repo, p, branch),
                    included_paths,
                )
            )

        for doc in doc_results:
            if doc is None:
                continue
            result.documents.append(doc)
            result.total_documents += 1
            if doc.parsed:
                result.parsed_count += 1
                # Group parsed docs by API version for the grouped view.
                key = doc.api_version or UNVERSIONED_KEY
                result.documents_by_version.setdefault(key, []).append(doc)
            else:
                result.failed_count += 1

        return result

    # ------------------------------------------------------------------ #
    # Per-document
    # ------------------------------------------------------------------ #
    def _process_document(
        self, repo: str, path: str, branch: str
    ) -> DocumentScanResult | None:
        """Fetch + classify + parse a document. Returns None for non-API files."""
        try:
            content = self.doc_provider.fetch_content(repo, path, branch)
        except Exception as e:
            logger.warning("Fetch failed for %s/%s: %s", repo, path, e)
            return DocumentScanResult(
                document=path,
                repo=repo,
                parsed=False,
                error=f"fetch error: {e}",
            )

        if not self._is_api_endpoint(content):
            # Not an endpoint doc (intro pages, conceptual material, etc.).
            return None

        try:
            endpoint = self.parser.parse_endpoint(content, path)
        except Exception as e:
            logger.warning("Parse failed for %s/%s: %s", repo, path, e)
            return DocumentScanResult(
                document=path,
                repo=repo,
                parsed=False,
                error=f"parse error: {e}",
            )

        return DocumentScanResult(
            document=path,
            repo=repo,
            parsed=True,
            method=endpoint.method,
            uri=endpoint.path,
            title=endpoint.title or None,
            api_version=endpoint.api_version or None,
        )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _is_excluded(self, path: str) -> bool:
        """True if any path segment matches an excluded segment name."""
        return any(seg in self.excluded_segments for seg in path.split("/"))

    @staticmethod
    def _is_api_endpoint(content: str) -> bool:
        return bool(URI_RE.search(content))
