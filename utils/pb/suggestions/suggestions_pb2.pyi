from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class InitOrderRequest(_message.Message):
    __slots__ = ("order_id", "order_data")
    ORDER_ID_FIELD_NUMBER: _ClassVar[int]
    ORDER_DATA_FIELD_NUMBER: _ClassVar[int]
    order_id: str
    order_data: SuggestionOrderData
    def __init__(self, order_id: _Optional[str] = ..., order_data: _Optional[_Union[SuggestionOrderData, _Mapping]] = ...) -> None: ...

class InitOrderResponse(_message.Message):
    __slots__ = ("is_ok", "errors")
    IS_OK_FIELD_NUMBER: _ClassVar[int]
    ERRORS_FIELD_NUMBER: _ClassVar[int]
    is_ok: bool
    errors: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, is_ok: bool = ..., errors: _Optional[_Iterable[str]] = ...) -> None: ...

class SuggestionOrderData(_message.Message):
    __slots__ = ("user_id", "ordered_items")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    ORDERED_ITEMS_FIELD_NUMBER: _ClassVar[int]
    user_id: str
    ordered_items: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, user_id: _Optional[str] = ..., ordered_items: _Optional[_Iterable[str]] = ...) -> None: ...

class SuggestionRequest(_message.Message):
    __slots__ = ("order_id", "vector_clock")
    class VectorClockEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: int
        def __init__(self, key: _Optional[str] = ..., value: _Optional[int] = ...) -> None: ...
    ORDER_ID_FIELD_NUMBER: _ClassVar[int]
    VECTOR_CLOCK_FIELD_NUMBER: _ClassVar[int]
    order_id: str
    vector_clock: _containers.ScalarMap[str, int]
    def __init__(self, order_id: _Optional[str] = ..., vector_clock: _Optional[_Mapping[str, int]] = ...) -> None: ...

class SuggestionResponse(_message.Message):
    __slots__ = ("suggestions", "vector_clock")
    class VectorClockEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: int
        def __init__(self, key: _Optional[str] = ..., value: _Optional[int] = ...) -> None: ...
    SUGGESTIONS_FIELD_NUMBER: _ClassVar[int]
    VECTOR_CLOCK_FIELD_NUMBER: _ClassVar[int]
    suggestions: _containers.RepeatedCompositeFieldContainer[Book]
    vector_clock: _containers.ScalarMap[str, int]
    def __init__(self, suggestions: _Optional[_Iterable[_Union[Book, _Mapping]]] = ..., vector_clock: _Optional[_Mapping[str, int]] = ...) -> None: ...

class Book(_message.Message):
    __slots__ = ("book_id", "title", "author")
    BOOK_ID_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    AUTHOR_FIELD_NUMBER: _ClassVar[int]
    book_id: str
    title: str
    author: str
    def __init__(self, book_id: _Optional[str] = ..., title: _Optional[str] = ..., author: _Optional[str] = ...) -> None: ...
