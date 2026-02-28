from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class FraudRequest(_message.Message):
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
    __slots__ = ("is_fraud", "risk_score", "reasons")
    IS_FRAUD_FIELD_NUMBER: _ClassVar[int]
    RISK_SCORE_FIELD_NUMBER: _ClassVar[int]
    REASONS_FIELD_NUMBER: _ClassVar[int]
    is_fraud: bool
    risk_score: float
    reasons: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, is_fraud: bool = ..., risk_score: _Optional[float] = ..., reasons: _Optional[_Iterable[str]] = ...) -> None: ...
