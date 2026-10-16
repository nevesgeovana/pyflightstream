"""Incremental completion-marker polling for captured solver output."""

from pathlib import Path


class _CompletionScan:
    """Read each appended byte once, retaining a possible partial marker."""

    def __init__(self, path: Path, marker: str) -> None:
        self.path = path
        self.marker = marker.encode("utf-8")
        self.offset = 0
        self.tail = b""
        self.found = False

    def finished(self) -> bool:
        if self.found:
            return True
        try:
            with self.path.open("rb") as stream:
                stream.seek(self.offset)
                while chunk := stream.read(65536):
                    self.offset += len(chunk)
                    combined = self.tail + chunk
                    self.found = self.marker in combined
                    self.tail = combined[-(len(self.marker) - 1) :]
                    if self.found:
                        return True
        except OSError:
            return False
        return False
