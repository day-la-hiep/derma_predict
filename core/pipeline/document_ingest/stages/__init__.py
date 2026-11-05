class StageCancelled(Exception):
    pass


class StageError(RuntimeError):
    """Lỗi người dùng có thể sửa (thiếu file, tuỳ chọn sai...) — hiển thị nguyên văn ở UI."""
