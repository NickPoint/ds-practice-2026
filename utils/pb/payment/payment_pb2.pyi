from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class PrepareRequest(_message.Message):
    __slots__ = ("order_id",)
    ORDER_ID_FIELD_NUMBER: _ClassVar[int]
    order_id: str
    def __init__(self, order_id: _Optional[str] = ...) -> None: ...

class CommitRequest(_message.Message):
    __slots__ = ("order_id",)
    ORDER_ID_FIELD_NUMBER: _ClassVar[int]
    order_id: str
    def __init__(self, order_id: _Optional[str] = ...) -> None: ...

class AbortRequest(_message.Message):
    __slots__ = ("order_id",)
    ORDER_ID_FIELD_NUMBER: _ClassVar[int]
    order_id: str
    def __init__(self, order_id: _Optional[str] = ...) -> None: ...

class PrepareResponse(_message.Message):
    __slots__ = ("is_ok", "errors")
    IS_OK_FIELD_NUMBER: _ClassVar[int]
    ERRORS_FIELD_NUMBER: _ClassVar[int]
    is_ok: bool
    errors: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, is_ok: bool = ..., errors: _Optional[_Iterable[str]] = ...) -> None: ...

class CommitResponse(_message.Message):
    __slots__ = ("is_ok", "errors")
    IS_OK_FIELD_NUMBER: _ClassVar[int]
    ERRORS_FIELD_NUMBER: _ClassVar[int]
    is_ok: bool
    errors: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, is_ok: bool = ..., errors: _Optional[_Iterable[str]] = ...) -> None: ...

class AbortResponse(_message.Message):
    __slots__ = ("is_ok", "errors")
    IS_OK_FIELD_NUMBER: _ClassVar[int]
    ERRORS_FIELD_NUMBER: _ClassVar[int]
    is_ok: bool
    errors: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, is_ok: bool = ..., errors: _Optional[_Iterable[str]] = ...) -> None: ...
