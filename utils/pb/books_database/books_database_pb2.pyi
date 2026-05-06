from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ReadRequest(_message.Message):
    __slots__ = ("title",)
    TITLE_FIELD_NUMBER: _ClassVar[int]
    title: str
    def __init__(self, title: _Optional[str] = ...) -> None: ...

class ReadResponse(_message.Message):
    __slots__ = ("stock",)
    STOCK_FIELD_NUMBER: _ClassVar[int]
    stock: int
    def __init__(self, stock: _Optional[int] = ...) -> None: ...

class WriteRequest(_message.Message):
    __slots__ = ("title", "new_stock")
    TITLE_FIELD_NUMBER: _ClassVar[int]
    NEW_STOCK_FIELD_NUMBER: _ClassVar[int]
    title: str
    new_stock: int
    def __init__(self, title: _Optional[str] = ..., new_stock: _Optional[int] = ...) -> None: ...

class WriteResponse(_message.Message):
    __slots__ = ("success", "error")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    success: bool
    error: str
    def __init__(self, success: bool = ..., error: _Optional[str] = ...) -> None: ...

class ReserveStockRequest(_message.Message):
    __slots__ = ("title", "quantity")
    TITLE_FIELD_NUMBER: _ClassVar[int]
    QUANTITY_FIELD_NUMBER: _ClassVar[int]
    title: str
    quantity: int
    def __init__(self, title: _Optional[str] = ..., quantity: _Optional[int] = ...) -> None: ...

class ReserveStockResponse(_message.Message):
    __slots__ = ("success", "remaining_stock", "error")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    REMAINING_STOCK_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    success: bool
    remaining_stock: int
    error: str
    def __init__(self, success: bool = ..., remaining_stock: _Optional[int] = ..., error: _Optional[str] = ...) -> None: ...

class PropagateWriteRequest(_message.Message):
    __slots__ = ("title", "new_stock")
    TITLE_FIELD_NUMBER: _ClassVar[int]
    NEW_STOCK_FIELD_NUMBER: _ClassVar[int]
    title: str
    new_stock: int
    def __init__(self, title: _Optional[str] = ..., new_stock: _Optional[int] = ...) -> None: ...

class PrepareOrderRequest(_message.Message):
    __slots__ = ("order_id", "items")
    ORDER_ID_FIELD_NUMBER: _ClassVar[int]
    ITEMS_FIELD_NUMBER: _ClassVar[int]
    order_id: str
    items: _containers.RepeatedCompositeFieldContainer[ReserveStockRequest]
    def __init__(self, order_id: _Optional[str] = ..., items: _Optional[_Iterable[_Union[ReserveStockRequest, _Mapping]]] = ...) -> None: ...

class PrepareOrderResponse(_message.Message):
    __slots__ = ("is_ok", "errors")
    IS_OK_FIELD_NUMBER: _ClassVar[int]
    ERRORS_FIELD_NUMBER: _ClassVar[int]
    is_ok: bool
    errors: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, is_ok: bool = ..., errors: _Optional[_Iterable[str]] = ...) -> None: ...

class CommitOrderRequest(_message.Message):
    __slots__ = ("order_id",)
    ORDER_ID_FIELD_NUMBER: _ClassVar[int]
    order_id: str
    def __init__(self, order_id: _Optional[str] = ...) -> None: ...

class CommitOrderResponse(_message.Message):
    __slots__ = ("is_ok", "errors")
    IS_OK_FIELD_NUMBER: _ClassVar[int]
    ERRORS_FIELD_NUMBER: _ClassVar[int]
    is_ok: bool
    errors: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, is_ok: bool = ..., errors: _Optional[_Iterable[str]] = ...) -> None: ...

class AbortOrderRequest(_message.Message):
    __slots__ = ("order_id",)
    ORDER_ID_FIELD_NUMBER: _ClassVar[int]
    order_id: str
    def __init__(self, order_id: _Optional[str] = ...) -> None: ...

class AbortOrderResponse(_message.Message):
    __slots__ = ("is_ok", "errors")
    IS_OK_FIELD_NUMBER: _ClassVar[int]
    ERRORS_FIELD_NUMBER: _ClassVar[int]
    is_ok: bool
    errors: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, is_ok: bool = ..., errors: _Optional[_Iterable[str]] = ...) -> None: ...
