from fastapi import status

from .base import BusinessError, ErrorCode


class RoundDomainError(BusinessError):
    pass


class ActiveRoundAlreadyExistsError(RoundDomainError):
    error_code = ErrorCode.ACTIVE_ROUND_ALREADY_EXISTS
    status_code = status.HTTP_409_CONFLICT


class NoEligibleCatalogError(RoundDomainError):
    error_code = ErrorCode.NO_ELIGIBLE_CATALOG
    status_code = status.HTTP_409_CONFLICT


class RoundNotFoundError(RoundDomainError):
    error_code = ErrorCode.ROUND_NOT_FOUND
    status_code = status.HTTP_404_NOT_FOUND


class RoundAlreadyFinalizedError(RoundDomainError):
    error_code = ErrorCode.ROUND_ALREADY_FINALIZED
    status_code = status.HTTP_409_CONFLICT
