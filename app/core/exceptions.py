class AppError(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class NotFoundError(AppError):
    pass


class ConflictError(AppError):
    pass


class AuthenticationError(AppError):
    pass


class InactiveAccountError(AppError):
    pass


class InsufficientStockError(AppError):
    pass


class ReservationNotFound(AppError):
    pass


class ReservationStateError(AppError):
    pass


class DuplicateOrderError(AppError):
    pass
