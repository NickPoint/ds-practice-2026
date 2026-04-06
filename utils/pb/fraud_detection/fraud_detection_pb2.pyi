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
    order_data: FraudOrderData
    def __init__(self, order_id: _Optional[str] = ..., order_data: _Optional[_Union[FraudOrderData, _Mapping]] = ...) -> None: ...

class InitOrderResponse(_message.Message):
    __slots__ = ("is_ok", "errors")
    IS_OK_FIELD_NUMBER: _ClassVar[int]
    ERRORS_FIELD_NUMBER: _ClassVar[int]
    is_ok: bool
    errors: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, is_ok: bool = ..., errors: _Optional[_Iterable[str]] = ...) -> None: ...

class FraudOrderData(_message.Message):
    __slots__ = ("credit_card", "items", "billing_address", "device", "browser", "terms_accepted")
    CREDIT_CARD_FIELD_NUMBER: _ClassVar[int]
    ITEMS_FIELD_NUMBER: _ClassVar[int]
    BILLING_ADDRESS_FIELD_NUMBER: _ClassVar[int]
    DEVICE_FIELD_NUMBER: _ClassVar[int]
    BROWSER_FIELD_NUMBER: _ClassVar[int]
    TERMS_ACCEPTED_FIELD_NUMBER: _ClassVar[int]
    credit_card: CreditCard
    items: _containers.RepeatedCompositeFieldContainer[Item]
    billing_address: Address
    device: Device
    browser: Browser
    terms_accepted: bool
    def __init__(self, credit_card: _Optional[_Union[CreditCard, _Mapping]] = ..., items: _Optional[_Iterable[_Union[Item, _Mapping]]] = ..., billing_address: _Optional[_Union[Address, _Mapping]] = ..., device: _Optional[_Union[Device, _Mapping]] = ..., browser: _Optional[_Union[Browser, _Mapping]] = ..., terms_accepted: bool = ...) -> None: ...

class FraudRequest(_message.Message):
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

class CreditCard(_message.Message):
    __slots__ = ("number", "expiration_date", "cvv")
    NUMBER_FIELD_NUMBER: _ClassVar[int]
    EXPIRATION_DATE_FIELD_NUMBER: _ClassVar[int]
    CVV_FIELD_NUMBER: _ClassVar[int]
    number: str
    expiration_date: str
    cvv: str
    def __init__(self, number: _Optional[str] = ..., expiration_date: _Optional[str] = ..., cvv: _Optional[str] = ...) -> None: ...

class Item(_message.Message):
    __slots__ = ("name", "quantity")
    NAME_FIELD_NUMBER: _ClassVar[int]
    QUANTITY_FIELD_NUMBER: _ClassVar[int]
    name: str
    quantity: int
    def __init__(self, name: _Optional[str] = ..., quantity: _Optional[int] = ...) -> None: ...

class Address(_message.Message):
    __slots__ = ("country", "city")
    COUNTRY_FIELD_NUMBER: _ClassVar[int]
    CITY_FIELD_NUMBER: _ClassVar[int]
    country: str
    city: str
    def __init__(self, country: _Optional[str] = ..., city: _Optional[str] = ...) -> None: ...

class Device(_message.Message):
    __slots__ = ("type", "os")
    TYPE_FIELD_NUMBER: _ClassVar[int]
    OS_FIELD_NUMBER: _ClassVar[int]
    type: str
    os: str
    def __init__(self, type: _Optional[str] = ..., os: _Optional[str] = ...) -> None: ...

class Browser(_message.Message):
    __slots__ = ("name",)
    NAME_FIELD_NUMBER: _ClassVar[int]
    name: str
    def __init__(self, name: _Optional[str] = ...) -> None: ...

class FraudResponse(_message.Message):
    __slots__ = ("is_fraud", "risk_score", "reasons", "vector_clock")
    class VectorClockEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: int
        def __init__(self, key: _Optional[str] = ..., value: _Optional[int] = ...) -> None: ...
    IS_FRAUD_FIELD_NUMBER: _ClassVar[int]
    RISK_SCORE_FIELD_NUMBER: _ClassVar[int]
    REASONS_FIELD_NUMBER: _ClassVar[int]
    VECTOR_CLOCK_FIELD_NUMBER: _ClassVar[int]
    is_fraud: bool
    risk_score: float
    reasons: _containers.RepeatedScalarFieldContainer[str]
    vector_clock: _containers.ScalarMap[str, int]
    def __init__(self, is_fraud: bool = ..., risk_score: _Optional[float] = ..., reasons: _Optional[_Iterable[str]] = ..., vector_clock: _Optional[_Mapping[str, int]] = ...) -> None: ...
