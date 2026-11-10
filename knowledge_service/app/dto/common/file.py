from app.dto.base.shared import File


class FileDto(File):
    """File trên wire"""

    url: str | None = None
