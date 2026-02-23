class MazdaConfigException(Exception):  # noqa: D100
    """Raised when Mazda API client is configured incorrectly."""

    def __init__(self, status):
        """Initialize exception."""
        super().__init__(status)
        self.status = status



class MazdaTokenExpiredException(Exception):
    """Raised when server reports that the access token has expired."""

    def __init__(self, status):
        """Initialize exception."""
        super().__init__(status)
        self.status = status


class MazdaAPIEncryptionException(Exception):
    """Raised when server reports that the request is not encrypted properly."""

    def __init__(self, status):
        """Initialize exception."""
        super().__init__(status)
        self.status = status


class MazdaException(Exception):
    """Raised when an unknown error occurs during API interaction."""

    def __init__(self, status):
        """Initialize exception."""
        super().__init__(status)
        self.status = status



class MazdaRequestInProgressException(Exception):
    """Raised when a request fails because another request is already in progress."""

    def __init__(self, status):
        """Initialize exception."""
        super().__init__(status)
        self.status = status


class MazdaSessionExpiredException(Exception):
    """Raised when server reports a session conflict (600100 — multi-device login).

    The correct response is to clear the stale session ID and re-attach.
    """

    def __init__(self, status):
        """Initialize exception."""
        super().__init__(status)
        self.status = status


class MazdaTermsNotAcceptedException(Exception):
    """Raised when the Mazda terms of service have not been accepted in the app."""

    def __init__(self, status):
        """Initialize exception."""
        super().__init__(status)
        self.status = status
