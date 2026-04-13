"""Path validation for secure file access."""

import os
import posixpath
import unicodedata
from typing import Optional
from urllib.parse import unquote


class PathValidator:
    """Five-layer progressive path validation against directory traversal attacks."""

    def __init__(self, base_path: Optional[str] = None):
        """Initialize the path validator.

        Args:
            base_path: Base directory path for whitelist validation.
                      If None, uses current working directory.
        """
        self.base_path = base_path or os.getcwd()
        # Ensure base_path is resolved
        self.base_path = os.path.realpath(self.base_path)

    def validate(self, user_path: str) -> str:
        """Validate path with five-layer progressive checks.

        Args:
            user_path: User-provided path to validate

        Returns:
            Resolved canonical path

        Raises:
            ValueError: If path validation fails at any layer
        """
        # Layer 1: Length check (prevent buffer overflow)
        if len(user_path) > 4096:
            raise ValueError("Path too long")

        # Layer 2: Iterative URL decoding (prevent multi-level encoding attacks)
        path = self._decode_all_encodings(user_path)

        # Layer 3: Unicode normalization (prevent Unicode bypass)
        path = self._normalize_unicode(path)

        # Layer 4: Path normalization (remove .. / and redundant /)
        path = self._normalize_path(path)

        # Layer 5: Symbolic link resolution + boundary check
        resolved = self._resolve_and_check_boundaries(path)

        return resolved

    def _decode_all_encodings(self, path: str) -> str:
        """Iteratively decode URL encodings.

        Args:
            path: Path potentially with URL encodings

        Returns:
            Fully decoded path
        """
        prev = None
        current = path
        iterations = 0
        max_iterations = 10  # Prevent infinite loops

        while prev != current and iterations < max_iterations:
            prev = current
            try:
                current = unquote(current)
            except Exception:
                break
            iterations += 1

        return current

    def _normalize_unicode(self, path: str) -> str:
        """Normalize Unicode to NFC form.

        Args:
            path: Path potentially with non-normalized Unicode

        Returns:
            NFC-normalized path
        """
        return unicodedata.normalize('NFC', path)

    def _normalize_path(self, path: str) -> str:
        """Normalize path to remove .. and redundant slashes.

        Args:
            path: Path to normalize

        Returns:
            Normalized path
        """
        # Use posixpath for consistent behavior across platforms
        normalized = posixpath.normpath(path)
        return normalized

    def _resolve_and_check_boundaries(self, path: str) -> str:
        """Resolve symbolic links and check directory traversal boundaries.

        Args:
            path: Path to resolve

        Returns:
            Resolved absolute path

        Raises:
            ValueError: If path attempts to escape base directory
        """
        # Convert to absolute path first
        if not os.path.isabs(path):
            path = os.path.join(self.base_path, path)

        # Resolve symbolic links and get canonical path
        resolved = os.path.realpath(path)

        # Check that resolved path is within base_path
        try:
            # Get relative path from base to resolved
            rel_path = os.path.relpath(resolved, self.base_path)
            # If relative path starts with .., it's outside base_path
            if rel_path.startswith('..'):
                raise ValueError(f"Path traversal detected: {path} -> {resolved}")
        except ValueError as e:
            if "different drives" in str(e):
                # On Windows, different drives also count as traversal
                raise ValueError(f"Path traversal detected: {path}")
            raise

        return resolved

    def set_base_path(self, base_path: str) -> None:
        """Set or update the base path for validation.

        Args:
            base_path: New base directory path
        """
        self.base_path = os.path.realpath(base_path)
