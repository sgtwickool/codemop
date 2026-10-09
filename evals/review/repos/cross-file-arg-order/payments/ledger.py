from payments.accounts import Account


class InsufficientFunds(Exception):
    pass


def transfer(source: Account, target: Account, amount: int):
    """Move `amount` (in cents) from one account to another (accounts first, like the rest of
    the ledger)"""
    if source.balance < amount:
        raise InsufficientFunds(source.id)
    source.balance -= amount
    target.balance += amount
