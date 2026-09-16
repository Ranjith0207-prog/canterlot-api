from beanie import Document

from .book import BookModel, LinkCandidate
from .club import CatalogEntryModel, ClubModel, PendingApprovalSchema
from .error import ErrorCode, ErrorDetail, ErrorResponseModel
from .invite import InviteModel
from .read_book import RatingStats, ReadBookModel
from .round import CandidatePoolEntry, DeadlineDuration, RoundModel
from .round_completion import RoundCompletionModel
from .user import LinkedProviderSchema, UserModel
from .verification import VerificationCodeModel

BEANIE_DOCUMENT_MODELS: list[type[Document]] = [
    BookModel,
    ClubModel,
    InviteModel,
    ReadBookModel,
    RoundModel,
    RoundCompletionModel,
    UserModel,
    VerificationCodeModel,
]

__all__ = [
    "BEANIE_DOCUMENT_MODELS",
    "BookModel",
    "CandidatePoolEntry",
    "CatalogEntryModel",
    "ClubModel",
    "DeadlineDuration",
    "ErrorCode",
    "ErrorDetail",
    "ErrorResponseModel",
    "InviteModel",
    "LinkCandidate",
    "LinkedProviderSchema",
    "PendingApprovalSchema",
    "RatingStats",
    "ReadBookModel",
    "RoundCompletionModel",
    "RoundModel",
    "UserModel",
    "VerificationCodeModel",
]
