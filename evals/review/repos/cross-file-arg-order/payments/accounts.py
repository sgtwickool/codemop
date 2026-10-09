from dataclasses import dataclass


@dataclass
class Account:
    id: str
    balance: int = 0
